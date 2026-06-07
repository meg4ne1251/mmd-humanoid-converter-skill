# Step 0 — Inspect the scene

**Goal:** build an accurate picture of the imported MMD model before touching anything. Everything else in this skill depends on reading the *real* state — names, hierarchy, weights, materials — rather than assuming.

## What to gather

1. **Objects** — what's in the scene, which is the armature, which are meshes, which are junk (physics/collision).
2. **Bone tree** — full parent→child hierarchy with each bone's head/tail, so you can spot the downward waist, twist bones, IK bones, and hidden collections.
3. **Vertex groups per mesh** — these are the weight targets. Twist/IK bones that appear here *may* carry weight and must be handled before deletion. **Important:** a bone having a same-named vertex group does **not** mean it actually carries weight — MMD models routinely have empty vertex groups (e.g. `足ＩＫ`, `腕捩` with 0 weighted verts). Always sum the actual weight, not just check for the group's existence, before deciding whether a bone needs weight transfer vs. plain deletion.
4. **Material slots per mesh** — needed later for part separation.
5. **Bone collections** — MMD hides `_shadow`/`_dummy` and sometimes other groups; note which are hidden.

## Prefer dedicated MCP tools

Use `get_objects_summary` and `get_object_detail_summary` first. Drop to `execute_blender_code` only for things they don't cover (e.g. full bone tree dump, vertex-group listing).

## Inspection snippet (read-only — safe)

```python
import bpy

print("=== OBJECTS ===")
for o in bpy.data.objects:
    extra = ""
    if o.type == 'MESH':
        extra = f" verts={len(o.data.vertices)} vgroups={len(o.vertex_groups)} mats={len(o.material_slots)}"
    print(f"  {o.type:10} {o.name}{extra}")

arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)
if arm:
    print(f"\n=== ARMATURE: {arm.name} ===")
    print("display_type:", arm.data.display_type, " show_in_front:", arm.show_in_front)

    print("\n--- bone collections (eye = visible) ---")
    for coll in arm.data.collections_all:
        print(f"  {'O' if coll.is_visible else 'x'}  {coll.name}  ({len(coll.bones)} bones)")

    print("\n--- bone tree ---")
    roots = [b for b in arm.data.bones if b.parent is None]
    def walk(b, d=0):
        print("  " + "  " * d + f"{b.name}")
        for c in b.children:
            walk(c, d + 1)
    for r in roots:
        walk(r)

print("\n=== VERTEX GROUPS (per mesh) ===")
for o in bpy.data.objects:
    if o.type == 'MESH':
        print(f"  [{o.name}] " + ", ".join(vg.name for vg in o.vertex_groups))

print("\n=== MATERIAL SLOTS (per mesh) ===")
for o in bpy.data.objects:
    if o.type == 'MESH':
        print(f"  [{o.name}] " + ", ".join(s.material.name if s.material else "<none>" for s in o.material_slots))
```

## Measure real weight (not just group existence)

Before treating any bone as "weighted," sum the actual weight on its vertex group. This is what tells twist bones (real weight → transfer first) apart from IK bones (often 0 weight → delete directly):

```python
import bpy
mesh = next(o for o in bpy.data.objects if o.type == 'MESH')  # the body mesh
vg = {g.name: g.index for g in mesh.vertex_groups}

def real_weight(group_name):
    """Return (weighted_vert_count, total_weight) for a vertex group, or None if absent."""
    if group_name not in vg:
        return None
    idx = vg[group_name]
    c = 0; w = 0.0
    for v in mesh.data.vertices:
        for g in v.groups:
            if g.group == idx and g.weight > 0:
                c += 1; w += g.weight
    return (c, round(w, 2))

# e.g. check suspected helper/IK bones before deciding transfer vs. delete
for name in ["腕捩.L", "腕捩1.L", "手捩.L", "足ＩＫ.L", "つま先ＩＫ.L"]:
    print(f"  {name}: {real_weight(name)}")
```

A result of `(0, 0.0)` means the group exists but holds no weight → the bone can be deleted directly (just drop the empty group too). A non-zero result means you must transfer the weight first (`references/05-weight-transfer.md`).

## What to look for in the output

- **Downward waist:** a center/センター bone whose tail is *below* its head, with グループ / センター先 helpers. → Step 3a.
- **Twist / 捩り / upward helper bones:** extra bones along the upper/lower arm, often named with 捩 or 腕 variants, that also appear as vertex groups. → Step 3b + weight transfer.
- **IK/FK bones:** bones around 足ＩＫ / つま先ＩＫ / 手首 controllers, usually parented off to the side rather than in the limb chain. → Step 3c.
- **Hidden collections** (`is_visible == False`) likely holding `_shadow`/`_dummy`. → Step 4.
- **Junk objects:** rigid bodies / joints / colliders, often many small objects. → Step 1.

## Hand it to the user

Summarize what you found — "this model has N twist bones carrying weight, an IK group of M bones, a downward waist, and K hidden-collection bones" — and lay out the plan before any destructive step. This is also where you flag anything unusual that will need manual judgment.

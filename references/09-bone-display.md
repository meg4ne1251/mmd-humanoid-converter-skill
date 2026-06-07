# Step 6 — Connect chain bones, display & tail directions

MMD-imported armatures display as spheres with all tails pointing straight up and **every bone disconnected** (`use_connect = False`), which makes the rig look like a pile of free-floating bones. This step fixes the display, points tails at their children, and **connects the serial chain bones** so the rig reads as a continuous, legible skeleton that behaves better in MotionBuilder/Unity. The connection pass is the substantive part — the display/tail work just sets it up cleanly.

## Display type

```python
import bpy
for o in bpy.data.objects:
    if o.type == 'ARMATURE':
        o.data.display_type = 'OCTAHEDRAL'   # readable bone shape
        o.show_in_front = True
```

## Tail direction rules

| Bone kind | Tail direction |
|---|---|
| Chain middle (exactly one child) | point at the child's head |
| Chain end (no children) | extend along the parent→self direction |
| Multi-child (Hips, Head, ...) | point at the primary child (e.g. Spine) |
| Eye | forward (+Y) |
| Teeth | forward, slightly down |
| HeadTip / leaf | up (+Z) |

```python
import bpy
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones

def point_to_child(b):
    """Point tail at the single child's head, keeping head fixed."""
    kids = [c for c in eb if c.parent == b]
    if len(kids) == 1:
        orig = b.head.copy()
        b.tail = kids[0].head.copy()
        b.head = orig            # re-assert head; setting tail can nudge it

def extend_along_parent(b):
    """End bone: extend tail along parent->self direction."""
    if b.parent:
        d = (b.head - b.parent.head).normalized()
        length = b.length if b.length > 0.001 else 0.05
        b.tail = b.head + d * length

for b in eb:
    kids = [c for c in eb if c.parent == b]
    if len(kids) == 1:
        point_to_child(b)
    elif len(kids) == 0:
        extend_along_parent(b)
    # multi-child bones: handle specifically (e.g. Hips -> Spine1)

# example multi-child override
hips, spine1 = eb.get("Hips"), eb.get("Spine1")
if hips and spine1:
    orig = hips.head.copy(); hips.tail = spine1.head.copy(); hips.head = orig

bpy.ops.object.mode_set(mode='OBJECT')
```

## Connect the chain bones (`use_connect`) — by geometry, not by name

**Why this step exists:** MMD Tools imports every bone with `use_connect = False` — each bone's head floats free of its parent's tail, so even though the parent/child *parenting* is intact, the armature looks like a pile of disconnected, free-floating bones. This is the "bones are all separate / not linked" state you see right after import. Connecting the chain bones makes the rig read as a continuous skeleton and behave better downstream (MotionBuilder/Unity).

**The rule is purely geometric — no name lists, no branch logic:** for each child bone, measure the distance between its **head** and its **parent's tail**. If they already coincide (distance ≈ 0), the modeler intended that bone to continue its parent's chain, so connect it. If they're apart, the bone deliberately starts offset (a limb start off a branch, a free-floating control bone), so leave it disconnected. **Connect every bone whose head meets its parent's tail — jiggle/cloth bones (skirt, sleeve, hair, sash) included.** There is no need to special-case them: if a sleeve segment's head sits on its parent's tail, connecting it just makes the sleeve chain read as a chain, which is correct and harmless.

This is more robust than matching bone names: it adapts to any naming, any model, and never mis-classifies because the geometry *is* the ground truth for "are these two bones in line."

**Why no head ever moves:** the usual `use_connect` trap is that setting it **forces the child's head onto the parent's tail**, distorting the rest pose. Here we only connect bones whose head is *already* on the parent's tail, so the forced move is a **no-op** — nothing shifts, no deformation changes. This also means the old "one connected child per parent" worry disappears: because we never move the parent's tail, a branch parent (e.g. `Spine1` with both `Spine2` and a sash bone sitting on its tail) can have **multiple** children connected at once. Do this **after** Step 5 rename and the tail-direction pass above.

```python
import bpy
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
ctx = view3d_ctx()
with bpy.context.temp_override(**ctx):
    bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones

EPS = 1e-5   # "head coincides with parent tail" tolerance (in Blender units)

# Optional: inspect the distance distribution first to pick EPS. In practice
# there's a clean gap — a cluster at ~0 (the real chain) and everything else
# clearly far — so the exact threshold rarely matters.
connected = []
for b in eb:
    p = b.parent
    if p is None:
        continue
    if (p.tail - b.head).length <= EPS:   # head already on parent's tail
        b.use_connect = True              # connect WITHOUT moving anything (no-op move)
        connected.append(b.name)

with bpy.context.temp_override(**ctx):
    bpy.ops.object.mode_set(mode='OBJECT')

print(f"connected {len(connected)} bones")
```

> **Tip — inspect before committing.** If you want to choose `EPS` deliberately, first run the loop in a dry-run that only records `(b.name, (p.tail - b.head).length)` and look at the spread. On a real run (a 196-bone きりたん) the distances split cleanly into **133 at exactly 0** and the rest at ≥1% of bone length, so any small `EPS` gives the same 133. A clean gap like that means the threshold is not a delicate tuning knob.

After connecting, **pose-test** (`references/06-verify-rig.md`): rotate a few connected chains across categories — a leg (`Leg`/`Foot`), a finger, and a jiggle chain (sleeve/skirt/hair) — and confirm the weighted mesh still follows. Because no head moved, this should always pass; if anything detached, it means a bone was connected whose head was *not* actually on the parent's tail (raise `EPS` scrutiny) — undo and investigate.

Multi-child branch bones whose children **don't** sit on their tail (Hips → legs+spine at different points, Head → eyes/jaw) are simply never matched by the distance test, so they stay disconnected automatically — pointing their tail at the primary child (done in the tail-direction pass above) is enough to make them *look* continuous without moving anything.

## Notes

- `edit_bones` is only writable in Edit Mode; `armature.bones` in Object Mode is read-only for geometry.
- Setting `b.tail` can internally shift `b.head` (especially when connected). Save `orig_head` before and re-assert it after.
- Guard against zero-length bones with a fallback length (e.g. 0.05).
- Always finish in Object Mode.

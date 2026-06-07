# Step 1 — Delete junk objects

**Goal:** keep only the mesh(es) and the armature. MMD imports bring in collision shapes, rigid bodies, and joint objects that are useless for a Humanoid rig and clutter every later step.

These are often hidden — `Alt+H` reveals a swarm of small physics objects.

> **Through the Blender MCP, `bpy.ops.object.hide_view_clear()` and `bpy.ops.object.delete()` fail with "context is incorrect."** Use data-level APIs instead: `obj.hide_set(False)` / `obj.hide_viewport = False` to unhide, and `bpy.data.objects.remove(obj, do_unlink=True)` to delete. See the "Running operators through the Blender MCP" note in SKILL.md. A working subtree-delete is shown at the bottom of this file.

## Identify before deleting (don't guess)

The keep-list is simple: **meshes + the armature.** Everything else is a candidate. But *confirm* by listing candidates and showing the user, because occasionally a mesh you want is hidden too.

```python
import bpy
bpy.ops.object.hide_view_clear()  # reveal hidden objects first

keep_types = {'MESH', 'ARMATURE'}
candidates = [o for o in bpy.data.objects if o.type not in keep_types]
print("KEEP:", [o.name for o in bpy.data.objects if o.type in keep_types])
print("DELETE CANDIDATES:", [(o.name, o.type) for o in candidates])
```

Typical delete types: `EMPTY` (rigid-body/joint placeholders), and any physics helper objects. In MMD imports these are commonly grouped under an empty like `<model>_rigidbodies` / `<model>_joints`.

## Confirm, then delete

Show the candidate list to the user and confirm before deleting — this is a destructive step. The original manual workflow does this by selecting the junk and choosing "Delete Hierarchy" (right-click → 階層を削除), which removes an empty and all its children at once.

```python
import bpy

to_delete = ["<name1>", "<name2>"]  # fill from the confirmed candidate list

bpy.ops.object.select_all(action='DESELECT')
for name in to_delete:
    o = bpy.data.objects.get(name)
    if o:
        o.select_set(True)
# delete selected + their child hierarchy
bpy.context.view_layer.objects.active = None
bpy.ops.object.delete()  # deletes the current selection
```

To delete an empty *and* its whole subtree (the "Delete Hierarchy" equivalent), select the parent empty and use `select_hierarchy`:

```python
bpy.ops.object.select_all(action='DESELECT')
parent = bpy.data.objects.get("<model>_rigidbodies")
if parent:
    parent.select_set(True)
    bpy.context.view_layer.objects.active = parent
    bpy.ops.object.select_grouped(type='CHILDREN_RECURSIVE')
    parent.select_set(True)
    bpy.ops.object.delete()
```

## Context-safe subtree delete (works through the MCP)

MMD imports group the junk under two empties — `rigidbodies` (an empty + ~hundreds of collision MESH children) and `joints` (hundreds of EMPTY children). Delete each whole subtree at the data level:

```python
import bpy

# unhide everything at data level (hide_view_clear() fails via MCP)
for o in bpy.data.objects:
    o.hide_set(False); o.hide_viewport = False

def delete_subtree(parent_name):
    p = bpy.data.objects.get(parent_name)
    if not p:
        return 0
    nodes = []
    def collect(o):
        nodes.append(o)
        for c in o.children:
            collect(c)
    collect(p)
    for o in nodes:
        bpy.data.objects.remove(o, do_unlink=True)   # object.delete() fails via MCP
    return len(nodes)

print("deleted rigidbodies:", delete_subtree("rigidbodies"))
print("deleted joints:",      delete_subtree("joints"))
```

Before deleting, sanity-check that no body mesh hides under `rigidbodies`: list `[o.name for o in bpy.data.objects if o.type=='MESH']` and confirm the real body mesh is **not** in the rigidbodies subtree.

## After

Re-run the object listing from `01-inspect.md` to confirm only meshes + armature remain.

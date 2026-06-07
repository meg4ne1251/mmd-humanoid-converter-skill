# Step 4 — Delete `_shadow` / `_dummy` bones

**Problem:** MMD rigs include bones whose names start with `_shadow` or `_dummy`. They live in a **hidden bone collection** and don't appear even with `Alt+H`, which makes them easy to miss. Their purpose isn't needed for a Humanoid rig, and they ~never carry weight (≈99%), so they're safe to delete once revealed.

## Reveal hidden bone collections, then delete

```python
import bpy

arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
arm.select_set(True)

# make every bone collection visible so the hidden ones show up
for coll in arm.data.collections_all:
    coll.is_visible = True

bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones

targets = [b.name for b in eb if b.name.startswith("_shadow") or b.name.startswith("_dummy")]
print("to delete:", targets)
```

## Confirm no weight, then remove

Before deleting, verify none of these names appear as vertex groups (they shouldn't, but check — this skill never assumes):

```python
weighted = set()
for o in bpy.data.objects:
    if o.type == 'MESH':
        vg = {g.name for g in o.vertex_groups}
        weighted |= (vg & set(targets))
print("unexpectedly weighted:", weighted)   # should be empty
```

If `weighted` is non-empty, transfer those weights first (`references/05-weight-transfer.md`). Otherwise delete:

```python
for name in targets:
    if name not in weighted:
        b = eb.get(name)
        if b:
            eb.remove(b)
bpy.ops.object.mode_set(mode='OBJECT')
```

The original workflow does this manually via Data → Bone Collections, un-hiding the group with the closed-eye icon, then deleting the now-visible bones one by one. The bpy version above does it in bulk but with the same safety check.

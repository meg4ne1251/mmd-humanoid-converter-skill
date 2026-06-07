# Step 6 — Bone display & tail directions (polish)

Cosmetic but worth doing: MMD-imported armatures often display as spheres with all tails pointing straight up and no connection, which makes the rig hard to read. Fixing display + tail direction makes the rig legible and behaves better in MotionBuilder/Unity.

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

## `use_connect` — the subtle trap

Setting `eb.use_connect = True` **forces the child's head onto the parent's tail.** To preserve head positions, move the parent's tail to the child's head **first**, then connect — and **only** when the parent has exactly one child (otherwise moving the tail wrecks the other children).

```python
bpy.ops.object.mode_set(mode='EDIT')
for eb_b in arm.data.edit_bones:
    if eb_b.parent is None:
        continue
    siblings = [b for b in arm.data.edit_bones if b.parent == eb_b.parent]
    if len(siblings) == 1:            # parent has only this child -> safe
        eb_b.parent.tail = eb_b.head.copy()   # move tail first
        eb_b.use_connect = True               # then connect
bpy.ops.object.mode_set(mode='OBJECT')
```

Multi-child bones (Hips, Head) should generally **not** be connected — pointing their tail at the primary child is enough to look connected.

## Notes

- `edit_bones` is only writable in Edit Mode; `armature.bones` in Object Mode is read-only for geometry.
- Setting `b.tail` can internally shift `b.head` (especially when connected). Save `orig_head` before and re-assert it after.
- Guard against zero-length bones with a fallback length (e.g. 0.05).
- Always finish in Object Mode.

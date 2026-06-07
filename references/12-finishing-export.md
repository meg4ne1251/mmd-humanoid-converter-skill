# Step 10 — Optional finishing & export

Optional polish, then export for the downstream pipeline. None of the polish items are required; do them if the user wants them.

## Optional polish

### Delete leaf / tip bones
The little tip bones at the end of chains (finger tips, skirt/hair/accessory jiggle-bone tips, shoe-decoration tips) have no function in Blender and ~99% carry no weight. Removing them tidies the rig.

```python
import bpy
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones

# candidate tips: bones with no children. Confirm no weight before deleting.
weighted = set()
for o in bpy.data.objects:
    if o.type == 'MESH':
        weighted |= {g.name for g in o.vertex_groups}

leaves = [b.name for b in eb if not b.children and b.name not in weighted]
print("leaf-bone deletion candidates:", leaves)   # review before removing
# for n in leaves: eb.remove(eb[n])
bpy.ops.object.mode_set(mode='OBJECT')
```
Review the candidate list with the user — some "leaves" you may want to keep (e.g. a meaningful end-effector).

### Tris → quads
Pure self-satisfaction; nobody downstream will notice. Only if asked.
```python
# per mesh, in Edit Mode with all faces selected:
# bpy.ops.mesh.tris_convert_to_quads()
```

### Build hidden body under clothes
MMD models usually delete body mesh hidden by clothing. If an outfit would expose those gaps, the underlying body needs to be modeled — this is manual modeling work, not automatable; flag it to the user.

## Export → MotionBuilder

When the conversion is done and pose-tested, export FBX and characterize in MotionBuilder.

```python
import bpy
bpy.ops.export_scene.fbx(
    filepath="<output>.fbx",
    use_selection=False,
    add_leaf_bones=False,     # don't re-add the leaf bones you just cleaned
    bake_anim=False,
    mesh_smooth_type='FACE',
)
```

After export: open in MotionBuilder, characterize the Humanoid rig. If clothing work follows, handing the mocap team a characterized model first is appreciated.

## Final reminder

"MMD conversion has no always." If any model needed manual fixes or has remaining quirks, note them for the user rather than implying a clean, guaranteed result.

# Step 10 — Optional finishing & export

Optional polish, then export for the downstream pipeline. None of the polish items are required; do them if the user wants them.

## Optional polish

### Delete tip bones (先端ボーン)

MMD rigs have "先" (tip) bones at the end of every chain — finger tips, eye tips, chest tips, etc. They act as tail-position markers and are never weighted. This step finds them by name (contain `先`), confirms the actual per-vertex weights are zero, then deletes the safe ones.

**Phase 1 — inspect and report** (run first, before any deletion):

```python
import bpy

arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']

tip_names = [b.name for b in arm.data.bones if "先" in b.name]

def has_actual_weight(bone_name):
    for obj in mesh_objs:
        vg = obj.vertex_groups.get(bone_name)
        if not vg:
            continue
        for v in obj.data.vertices:
            for g in v.groups:
                if g.group == vg.index and g.weight > 0:
                    return True
    return False

weighted_tips = [n for n in tip_names if has_actual_weight(n)]
safe_to_delete = [n for n in tip_names if not has_actual_weight(n)]

print(f"先端ボーン候補: {len(tip_names)}本")
print(f"  ウェイトあり（要確認）: {weighted_tips}")
print(f"  ウェイトなし（削除対象）: {safe_to_delete}")
```

Show the user the output. If `weighted_tips` is non-empty, stop and ask whether to transfer or skip those bones before continuing. If all clear, proceed to Phase 2.

**Phase 2 — delete** (run only after user confirms):

```python
import bpy

def view3d_ctx():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return {'window': win, 'area': area, 'region': region,
                                'scene': bpy.context.scene}
    return None

arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
mesh_objs = [o for o in bpy.data.objects if o.type == 'MESH']

tip_names = [b.name for b in arm.data.bones if "先" in b.name]

def has_actual_weight(bone_name):
    for obj in mesh_objs:
        vg = obj.vertex_groups.get(bone_name)
        if not vg:
            continue
        for v in obj.data.vertices:
            for g in v.groups:
                if g.group == vg.index and g.weight > 0:
                    return True
    return False

safe_to_delete = [n for n in tip_names if not has_actual_weight(n)]

bpy.context.view_layer.objects.active = arm
ctx = view3d_ctx()
with bpy.context.temp_override(**ctx):
    bpy.ops.object.mode_set(mode='EDIT')

eb = arm.data.edit_bones
deleted = []
for name in safe_to_delete:
    if name in eb:
        eb.remove(eb[name])
        deleted.append(name)

with bpy.context.temp_override(**ctx):
    bpy.ops.object.mode_set(mode='OBJECT')

print(f"{len(deleted)}本の先端ボーンを削除: {deleted}")
```

Pose-test after deletion to confirm no mesh tearing.

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

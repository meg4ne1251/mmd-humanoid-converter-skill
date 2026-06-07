# Verify the rig deforms correctly

After any restructuring, weight transfer, or rename, confirm the mesh still follows the bones. This is how you catch a torn weight or a dropped vertex group before it compounds.

## Quick programmatic checks

```python
import bpy

arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

# 1. Every vertex group should correspond to an existing bone (no orphans)
bone_names = {b.name for b in arm.data.bones}
for o in bpy.data.objects:
    if o.type == 'MESH':
        orphans = [vg.name for vg in o.vertex_groups if vg.name not in bone_names]
        if orphans:
            print(f"[{o.name}] vertex groups with no matching bone: {orphans}")

# 2. Each mesh should have an Armature modifier pointing at the armature
for o in bpy.data.objects:
    if o.type == 'MESH':
        has = any(m.type == 'ARMATURE' and m.object == arm for m in o.modifiers)
        print(f"[{o.name}] armature-bound: {has}")
```

Orphan vertex groups after a delete/rename are the usual symptom of a problem — investigate before continuing.

## Visual pose test

The definitive check is to actually move a bone and look. Suggest the user do this in Pose Mode, or do it programmatically and render a viewport:

```python
import bpy, math
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')

pb = arm.pose.bones.get("UpArm_L") or arm.pose.bones.get("左腕")
if pb:
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler[2] = math.radians(40)   # swing the arm
bpy.context.view_layer.update()
# render_viewport_to_path (Blender MCP tool) to capture an image for the user
# ... then reset:
if pb:
    pb.rotation_euler[2] = 0
bpy.ops.object.mode_set(mode='OBJECT')
```

Use the Blender MCP `render_viewport_to_path` / `get_screenshot_of_window_as_image` tool to show the user the deformation. If a region of mesh lags behind (doesn't follow the bone), a weight wasn't transferred — undo the deletion and fix the weights first.

## When something's wrong

- Region doesn't follow a bone you kept → a source weight wasn't merged onto it. Re-do the transfer (`references/05-weight-transfer.md`).
- A rename dropped a weight (rare, ~happens) → rename back, or re-assign the vertex group name to match the bone.
- Always prefer undo + fix over pushing forward on a broken rig.

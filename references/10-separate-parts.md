# Step 8 — Separate the mesh into parts

Split the model into logical objects (face, hair, body, clothes, accessories). **Do this last**, after all rig work — separating earlier means redoing weight/bone checks per object.

## Method A — by material (when materials map 1:1 to parts)

If each part has its own material (and parts don't share materials), `separate(type='MATERIAL')` is cleanest. Then join material-fragments that belong to the same logical part and rename.

> **This doesn't always work.** If one part has several materials you'll get extra fragments to re-join; if different parts share a material they'll be wrongly merged. Inspect the material→part relationship first. When it doesn't hold, use Method B.

```python
import bpy

# map each material name to the logical part/object name (build from the real slots)
MAT_TO_OBJ = {
    "前髪": "Hair_Front", "後髪": "Hair_Back",
    "体": "Body_Skin", "腕": "Body_Skin", "顔": "Head_Skin", "頭": "Head_Skin",
    "黒目": "Eye", "瞳1": "Eye", "瞳2": "Eye",
    "スカート": "Skirt", "スカート裏": "Skirt",
    "ブレザー": "Blazer", "ブレザー裏": "Blazer",
    "靴": "Shoes",
    # ...
}

src = bpy.data.objects["<merged-body-mesh>"]

bpy.ops.object.select_all(action='DESELECT')
src.select_set(True)
bpy.context.view_layer.objects.active = src
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.separate(type='MATERIAL')
bpy.ops.object.mode_set(mode='OBJECT')

# bucket the resulting fragments by target group (the original src is in selection too)
groups = {}
for o in bpy.context.selected_objects:
    for slot in o.material_slots:
        if slot.material and slot.material.name in MAT_TO_OBJ:
            groups.setdefault(MAT_TO_OBJ[slot.material.name], []).append(o)
            break

# join fragments per group and rename
for name, objs in groups.items():
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    act = bpy.context.active_object
    act.name = name
    act.data.name = name
```

## Method B — fallback when materials don't map cleanly

```python
# loose parts: split disconnected mesh islands into separate objects
bpy.ops.mesh.separate(type='LOOSE')

# manual: select the vertices/faces of a part first (L = linked select in the UI),
# then separate the current selection
bpy.ops.mesh.separate(type='SELECTED')
```

For manual selection, the artist's `L` (linked-select under cursor) is the interactive equivalent; programmatically you'd select by vertex group or island and then `separate(type='SELECTED')`.

## Notes

- `separate()` runs in **Edit Mode** on the selected object — deselect-all first, then select only the source.
- The original object stays in `selected_objects` after separation; bucket by material to route it correctly.
- Armature modifier and vertex groups carry over to every separated object automatically.
- After `join()`, the active object is the merged result.

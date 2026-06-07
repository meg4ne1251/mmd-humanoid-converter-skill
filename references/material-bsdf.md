# Step 7 — Convert materials to Principled BSDF

MMD models import with one of **two different node setups** depending on the MMD Tools version — check which one you have before doing anything:

- **Old layout (toon mix):** `Emission` + `BSDF_Transparent` + `MIX_SHADER` + `LIGHT_PATH`, plus `MATH`/`FRAME` helpers. Replace with a single Principled BSDF (the `MIX_SHADER`-based procedure below).
- **New layout (mmd_shader node group), verified on a live import:** the material already contains a `BSDF_PRINCIPLED` node **but it is a dummy** — `Output.Surface` is fed by an `mmd_shader` node *group*, and the Principled's `Base Color` is left at its default value (texture not connected). `mmd_base_tex` (a `TEX_IMAGE`, Color+Alpha, fed by an `mmd_tex_uv` group) is the real texture. **If you export this as-is, downstream tools (Unity/MotionBuilder) ignore `mmd_shader` and the textures are lost.** You must rewire: `mmd_base_tex.Color → Principled.Base Color`, `.Alpha → Principled.Alpha` (if 4-channel), and `Principled.BSDF → Output.Surface` (replacing the group). The `MIX_SHADER` guard below would *skip* these materials and silently leave them broken — detect the new layout by `Output.Surface` not being driven by the Principled node.

For a standard pipeline, the goal in both cases is a single **Principled BSDF** driving the output, while **reusing** the existing image/mapping/UV nodes.

## New-layout rewire (mmd_shader group → Principled)

```python
import bpy
for m in {s.material for o in bpy.data.objects if o.type=='MESH' for s in o.material_slots if s.material}:
    if not m.use_nodes: continue
    nt = m.node_tree; nodes = nt.nodes; links = nt.links
    out = next((n for n in nodes if n.type=='OUTPUT_MATERIAL'), None)
    p   = next((n for n in nodes if n.type=='BSDF_PRINCIPLED'), None)
    base = next((n for n in nodes if n.type=='TEX_IMAGE' and 'base' in n.name.lower()), None) \
           or next((n for n in nodes if n.type=='TEX_IMAGE'), None)
    if not out or not p: continue
    # already correct?
    if out.inputs['Surface'].is_linked and out.inputs['Surface'].links[0].from_node==p \
       and p.inputs['Base Color'].is_linked:
        continue
    if base:
        links.new(base.outputs['Color'], p.inputs['Base Color'])
        if base.image and base.image.channels == 4:
            links.new(base.outputs['Alpha'], p.inputs['Alpha'])
    links.new(p.outputs['BSDF'], out.inputs['Surface'])   # replaces mmd_shader group
    spec = p.inputs.get('Specular IOR Level') or p.inputs.get('Specular')
    if spec: spec.default_value = 0.0
    p.inputs['Roughness'].default_value = 0.8
```

After rewiring, switch a viewport to Material Preview and render — textures (skin, hair, clothes) should display correctly. The original MMD layout (`MIX_SHADER`) is handled by the procedure further down.

---

## Old layout: toon mix-shader replacement

## The cardinal rule

> **Never call `nodes.clear()`.** Wiping the whole node tree can break mesh structure in some setups (e.g. when displacement is involved). Instead, *keep* the `TEX_IMAGE`, `MAPPING`, `UVMAP`, and `OUTPUT_MATERIAL` nodes and remove only the toon-specific nodes.

## Procedure

1. Grab the nodes to keep: `OUTPUT_MATERIAL`, `TEX_IMAGE`, `MAPPING`, `UVMAP`.
2. Remove only the toon nodes: `MIX_SHADER`, `EMISSION`, `BSDF_TRANSPARENT`, `LIGHT_PATH`, `MATH`, `FRAME`.
3. Clear existing links.
4. Add a `Principled BSDF`, reconnect texture → Base Color (+ Alpha if RGBA), mapping/UV → texture, BSDF → output.

```python
import bpy

remove_types = {'MIX_SHADER', 'EMISSION', 'BSDF_TRANSPARENT', 'LIGHT_PATH', 'MATH', 'FRAME'}

for mat in bpy.data.materials:
    if not mat.use_nodes:
        continue
    tree, nodes, links = mat.node_tree, mat.node_tree.nodes, mat.node_tree.links
    # skip materials already converted (no toon mix shader present)
    if not any(n.type == 'MIX_SHADER' for n in nodes):
        continue

    output  = next((n for n in nodes if n.type == 'OUTPUT_MATERIAL'), None)
    tex     = next((n for n in nodes if n.type == 'TEX_IMAGE'), None)
    mapping = next((n for n in nodes if n.type == 'MAPPING'), None)
    uvmap   = next((n for n in nodes if n.type == 'UVMAP'), None)

    for n in list(nodes):
        if n.type in remove_types:
            nodes.remove(n)
    for l in list(links):
        links.remove(l)

    p = nodes.new('ShaderNodeBsdfPrincipled')
    p.location = (0, 0)
    p.inputs['Roughness'].default_value = 0.8
    # Blender 5.x socket name; on 4.x use 'Specular'
    spec = p.inputs.get('Specular IOR Level') or p.inputs.get('Specular')
    if spec: spec.default_value = 0.0

    if output:
        links.new(p.outputs['BSDF'], output.inputs['Surface'])
    if tex:
        links.new(tex.outputs['Color'], p.inputs['Base Color'])
        if tex.image and tex.image.channels == 4:
            links.new(tex.outputs['Alpha'], p.inputs['Alpha'])
        if mapping:
            links.new(mapping.outputs['Vector'], tex.inputs['Vector'])
            if uvmap:
                links.new(uvmap.outputs['UV'], mapping.inputs['Vector'])
```

## Blender version differences

| Item | 4.x and earlier | 5.x |
|---|---|---|
| Specular socket name | `Specular` | `Specular IOR Level` |
| `material.shadow_method` | exists | **removed** |
| `blend_method` | `CLIP`/etc. | behavior may differ |

The `spec = ... or ...` fallback above handles both naming conventions. If you set transparency-related material properties, guard them with `hasattr` checks since some were removed in 5.x.

## Idempotency

The `if not any(... MIX_SHADER ...)` guard means re-running skips already-converted materials, so the step is safe to run more than once.

# Step 7 — Convert materials to Principled BSDF

MMD models import with a toon-shader node setup (`Emission` + `BSDF_Transparent` + `MIX_SHADER` + `LIGHT_PATH`, plus `MATH`/`FRAME` helpers). For a standard pipeline, replace it with a single **Principled BSDF**, while **reusing** the existing image/mapping/UV nodes.

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

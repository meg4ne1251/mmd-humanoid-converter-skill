# Weight transfer (bone → bone)

The single most important safety mechanism in this skill. Before deleting any weighted bone (twist, IK, helper), **merge its vertex-group weight onto the bone that should keep it.** Skipping this tears the mesh — the deleted bone's vertices stop following anything.

This is the bpy equivalent of the original hand-built addon: a temporary `VERTEX_WEIGHT_MIX` modifier copies weights from a source vertex group into a destination vertex group, then is applied and removed.

## Modes

- **SET (overwrite):** destination weight is replaced by source. Use when the destination has no meaningful existing weight there.
- **ADD (accumulate):** source weight is added to destination. Use when merging split limb weights (twist bones) into the real bone, where the real bone already holds part of the weight.

> **ADD must be applied once only.** Running ADD twice on the same pair double-counts and corrupts the weight gradient. If you accidentally run it twice, undo immediately.

For MMD twist/helper merges, **ADD + delete-source** is the usual choice.

## The function

```python
import bpy

def transfer_weight(mesh_obj, src, dst, mode='ADD', delete_source=True):
    """Merge vertex-group `src` into `dst` on mesh_obj using a temp VERTEX_WEIGHT_MIX.
       mode: 'ADD' (accumulate) or 'SET' (overwrite). ADD must run only once per pair."""
    if src not in mesh_obj.vertex_groups:
        print(f"  skip: source group '{src}' not on {mesh_obj.name}")
        return False
    if dst not in mesh_obj.vertex_groups:
        mesh_obj.vertex_groups.new(name=dst)

    bpy.context.view_layer.objects.active = mesh_obj
    mod = mesh_obj.modifiers.new(name="WT_TMP", type='VERTEX_WEIGHT_MIX')
    mod.mix_mode = mode            # 'ADD' or 'SET'
    mod.mix_set = 'B'              # affect vertices in either group
    mod.mask_constant = 1.0        # full strength on all vertices
    mod.vertex_group_a = dst       # destination (kept)
    mod.vertex_group_b = src       # source (merged in)
    try:
        bpy.ops.object.modifier_apply(modifier=mod.name)
    except RuntimeError as e:
        mesh_obj.modifiers.remove(mod)
        print(f"  FAILED {src}->{dst}: {e}")
        return False

    if delete_source:
        vg = mesh_obj.vertex_groups.get(src)
        if vg:
            mesh_obj.vertex_groups.remove(vg)
    print(f"  {src} -> {dst} ({mode}){' [src deleted]' if delete_source else ''}")
    return True


def flip_lr(name):
    """Return the L/R-mirrored name, or '' if no L/R pattern found."""
    pairs = [('.L', '.R'), ('_L', '_R'), ('_left', '_right'), ('.left', '.right'),
             ('左', '右')]
    for a, b in pairs:
        if name.endswith(a): return name[:-len(a)] + b
        if name.endswith(b): return name[:-len(b)] + a
        if name.startswith(a): return b + name[len(a):]   # e.g. 左腕 -> 右腕
        if name.startswith(b): return a + name[len(b):]
    return ""
```

## Typical usage — merge arm twist bones, both sides

```python
mesh = bpy.data.objects["<body-mesh-name>"]   # the mesh whose weights you're fixing

# left-side pairs: source twist/helper -> real arm bone
pairs = [
    ("左腕捩",  "左腕"),
    ("左手捩",  "左ひじ"),
    ("<left-helper>", "左腕"),
]

for src, dst in pairs:
    transfer_weight(mesh, src, dst, mode='ADD', delete_source=True)
    # mirror to the right side automatically
    rs, rd = flip_lr(src), flip_lr(dst)
    if rs and rd:
        transfer_weight(mesh, rs, rd, mode='ADD', delete_source=True)
```

Run this for **each mesh** that has the relevant vertex groups (after part-separation there may be several; before separation usually one body mesh).

## Verify before deleting the bones

After transfer, confirm the source groups are gone and the destination holds weight:

```python
for o in bpy.data.objects:
    if o.type == 'MESH':
        names = [vg.name for vg in o.vertex_groups]
        print(o.name, "腕捩 present?", any("捩" in n for n in names))
```

Only once the weights are safely merged should you delete the helper/twist/IK bones in Edit Mode (back in `references/04-bone-structure.md`).

## When transfer isn't enough

Some IK/control bones hold weight in awkward places where a clean merge isn't obvious. In that case fall back to manual weight painting onto Foot/Toe/Hand, or ask the user to repaint. "MMD conversion has no always" — surface the case rather than forcing a bad automatic merge.

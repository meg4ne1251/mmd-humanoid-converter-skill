# Step 11 — Tidy material & texture names

The last editing step before export. MMD/VRoid imports leave materials and image
textures with long, opaque names like `N00_007_01_Tops_01_CLOTH_01 (Instance)` and
base textures called `_12.png`. This step renames each material to a **short, clear,
half-width ASCII** name and makes its **base-color texture carry the exact same name**,
so the downstream FBX ships clean, predictable material/texture pairs.

> **Run this before the FBX export (Step 12).** FBX bakes the current datablock names
> into the file (and, depending on path mode, copies textures using the image name), so
> the names must be final before export. Renaming after export has no effect on the file
> already written.

## The rules (from the user)

1. **Every material gets a short, clear ASCII name.** No Japanese, no `(Instance)`, no
   `N00_000_00_…` prefixes — just a readable token (`Body`, `Face`, `Hair_01`, `Tops_01`,
   `Bottoms`, `Shoes`, `Onepiece`, …).
2. **Material name == base texture name, always.** The material and its base-color image
   must end up with the identical string. (Material and Image are different datablock
   types, so Blender allows the same name on both — no `.001` suffix.)
3. **If one texture is shared by several materials, duplicate it.** A base image used by
   more than one material is copied (`image.copy()`) so that *each* material owns its own
   image named after that material. After this step there is never a base texture shared
   across two materials.

Auxiliary textures (TOON, sphere/matcap) are handled separately — see below.

## Don't hard-code: inspect, propose, confirm

Per the skill's core rule, **do not assume a naming scheme**. Read the real material list
first, then **propose a clean name for each material** (your judgment — strip the cruft,
keep the meaningful token, disambiguate duplicates with `_01/_02…`), present the full
mapping table to the user, and only apply after they approve. Different model authors use
different conventions; the *mechanics* below are reusable, the *name mapping* is per-model.

## Step 11.0 — Inspect

List materials, their image-texture nodes, and how many users each image has. This shows
which textures are shared (candidates for duplication) and which names are long/opaque.

```python
import bpy
print("=== MATERIALS ===")
for m in bpy.data.materials:
    imgs = [n.image.name for n in (m.node_tree.nodes if m.use_nodes and m.node_tree else [])
            if n.type == 'TEX_IMAGE' and n.image]
    print(f"[{m.users}u] {m.name!r}  imgs={imgs}")
print("=== IMAGES ===")
for im in bpy.data.images:
    if im.name in ('Render Result', 'Viewer Node'):
        continue
    print(f"[{im.users}u] {im.name!r}")
```

Note **0-user (orphan) materials** (e.g. `Material`, `mmd_tools_rigid_*`) — they are not
on any mesh and won't export. Leave them out of the rename; optionally purge them with
`bpy.ops.outliner.orphans_purge` or by reporting them to the user. Don't rename them.

## Identifying the "base" texture reliably

A material usually has three image nodes: **base color**, **toon**, **sphere/matcap**.
The base-color one is what the material/texture name must match. Detect it robustly:

1. **Primary:** the image node whose Color output feeds the Principled BSDF `Base Color`
   input (works after Step 7's BSDF conversion).
2. **Fallback:** the image node named `mmd_base_tex` or labelled `Mmd Base Tex` (MMD Tools'
   own naming, present even before BSDF conversion). Toon is `mmd_toon_tex` / `Mmd Toon Tex`.

```python
def tex_node(mat, kind):
    """kind: 'base' or 'toon'. Returns the TEX_IMAGE node or None."""
    nt = mat.node_tree
    if not nt:
        return None
    if kind == 'base':
        for n in nt.nodes:                      # primary: trace Base Color
            if n.type == 'BSDF_PRINCIPLED':
                for l in n.inputs['Base Color'].links:
                    if l.from_node.type == 'TEX_IMAGE' and l.from_node.image:
                        return l.from_node
        names, labels = ('mmd_base_tex',), ('Mmd Base Tex',)
    else:
        names, labels = ('mmd_toon_tex',), ('Mmd Toon Tex',)
    for n in nt.nodes:                          # fallback: by node name/label
        if n.type == 'TEX_IMAGE' and n.image and (n.name in names or n.label in labels):
            return n
    return None
```

## Step 11.1 — Dry run (print the plan, change nothing)

Always dry-run first and show the user. This catches missing base textures and surfaces
any shared base image that will be duplicated.

```python
import bpy
from collections import Counter

# rename_map = {<current material name>: <clean ASCII name>, ...}  # your proposed mapping

basecnt = Counter()
for old in rename_map:
    m = bpy.data.materials.get(old)
    bn = tex_node(m, 'base') if m else None
    if bn:
        basecnt[bn.image.name] += 1

for old, new in rename_map.items():
    m = bpy.data.materials.get(old)
    if not m:
        print("!! missing material:", old); continue
    bn, tn = tex_node(m, 'base'), tex_node(m, 'toon')
    bi = bn.image.name if bn else None
    ti = tn.image.name if tn else None
    shared = bi and basecnt[bi] > 1
    print(f"{old!r} -> {new!r}")
    print(f"    base {bi!r} -> {new!r}  {'(SHARED: will DUPLICATE)' if shared else ''}")
    print(f"    toon {ti!r} -> {new+'_toon'!r}  "
          f"{'(shared: leave as-is)' if ti and bpy.data.images[ti].users > 1 else ''}")
```

## Step 11.2 — Apply

After user confirmation. Renames the material, renames or **duplicates** the base image to
match, and tidies the (1:1) toon image to `<name>_toon`. Shared auxiliary textures
(matcap/sphere, or a toon shared by many materials) are intentionally left untouched —
they're shared utilities, and duplicating them per material would bloat the export.

```python
import bpy

def set_img_name(img, name):
    img.name = name
    return img.name  # Blender may append .001 on a cross-image collision; check the result

claimed = {}   # base image already renamed -> True (the first material to use it keeps it)
log = []
for old, new in rename_map.items():
    m = bpy.data.materials.get(old)
    if not m:
        log.append(f"MISSING {old}"); continue

    m.name = new                                   # rule 1: material -> clean name

    bn = tex_node(m, 'base')                        # rule 2 + 3: base texture
    if bn and bn.image:
        img = bn.image
        if img in claimed:
            # rule 3: this base image is already owned by another material -> duplicate
            nimg = img.copy()
            bn.image = nimg
            log.append(f"{new}: base DUPLICATED -> {set_img_name(nimg, new)}")
        else:
            claimed[img] = True
            log.append(f"{new}: base RENAMED -> {set_img_name(img, new)}")
    else:
        log.append(f"{new}: NO base texture found (check node tree)")

    tn = tex_node(m, 'toon')                        # auxiliary: toon
    if tn and tn.image:
        timg = tn.image
        if timg.users > 1:
            log.append(f"{new}: toon shared (users={timg.users}) -> left {timg.name!r}")
        else:
            log.append(f"{new}: toon RENAMED -> {set_img_name(timg, new + '_toon')}")

print("\n".join(log))
```

Notes on the duplicate logic: the **first** material to reference a shared base image keeps
(renames) the original; every later material sharing it gets a fresh `image.copy()` named
after itself. Result: every material ends with a base image whose name equals the material
name, and no base image is shared. A copied image still points at the same file on disk
(`filepath` is copied), so no pixels are lost; if you want each duplicate to be a truly
independent file, pack (`img.pack()`) or save-as before export.

## Step 11.3 — Verify

Confirm the invariant holds: for every renamed material, its base texture name equals the
material name, and nothing long/non-ASCII remains except the intentional shared helpers.

```python
import bpy, re
ok = True
for new in rename_map.values():
    m = bpy.data.materials.get(new)
    bn = tex_node(m, 'base') if m else None
    bi = bn.image.name if bn and bn.image else None
    if bi != new:
        ok = False; print(f"  MISMATCH {new!r}: base={bi!r}")
print("ALL MATCH" if ok else "PROBLEMS FOUND")
for im in bpy.data.images:                          # leftover messy names (excl. shared helpers)
    if im.users and (not re.fullmatch(r'[A-Za-z0-9_.\- ]+', im.name) or len(im.name) > 24):
        print(f"  still messy: [{im.users}u] {im.name!r}")
```

## Pitfalls

- **A material with no base texture** (pure color material) — `tex_node` returns `None`.
  Rename the material only; there's no texture to match. Report it.
- **Two materials legitimately want the same clean name** — disambiguate in the mapping
  (`Tops_01`, `Tops_02`). Don't let two materials collapse to one name.
- **Cross-image name collision** — if an image named `Body` already exists from an
  unrelated source, `img.name = 'Body'` yields `Body.001`. `set_img_name` returns the
  actual name; check it. Usually safe because you renamed the only `Body` already.
- **Shared helper textures** (matcap/sphere, e.g. `MatcapWarp.png` used by 18 materials)
  are *not* base textures and must stay shared — leaving them is correct, not a bug.
- **Validated** on the 月見ヤチヨ VRoid-derived model (22 used materials): all bases were
  1:1, all 22 ended with material==base-texture names, toons → `<name>_toon`, the two
  shared helpers (`MatcapWarp.png` 18u, `Shader_NoneBlack.png` 4u) left intact.

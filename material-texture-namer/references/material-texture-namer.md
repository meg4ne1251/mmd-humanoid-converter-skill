# Material & Texture Namer — implementation

Copy-pasteable bpy for both modes. Run each block through the Blender MCP
(`execute_blender_code`). Always **inspect → dry-run → confirm → apply → verify**.

The two modes:

| Mode | Material name | Base texture name | Toon texture | Shared base texture |
|------|---------------|-------------------|--------------|---------------------|
| **1 — match only** | unchanged | set to the material's current name | left as-is | duplicated |
| **2 — match + clarify** | renamed to short ASCII | set to the new material name | → `<name>_toon` (if 1:1) | duplicated |

In both modes, **shared helper textures** (matcap/sphere, or a toon used by many materials)
are left shared on purpose — duplicating a 18-user matcap per material just bloats the file.

## Shared helper: detect the base / toon texture node

A material usually has up to three image nodes: base color, toon, sphere/matcap. The
detector below finds the base (the one whose name must match the material) and the toon,
robustly across MMD-imported, BSDF-converted, and generic materials.

```python
import bpy

TOON_NAMES, TOON_LABELS = ('mmd_toon_tex',), ('Mmd Toon Tex',)
SPHERE_NAMES, SPHERE_LABELS = ('mmd_sphere_tex',), ('Mmd Sphere Tex',)

def _img_behind(node, _seen=None):
    """Walk back from a node to the first TEX_IMAGE feeding it (handles Mix/Group)."""
    if node is None:
        return None
    if node.type == 'TEX_IMAGE' and node.image:
        return node
    _seen = _seen or set()
    if node in _seen:
        return None
    _seen.add(node)
    for inp in node.inputs:
        for l in inp.links:
            hit = _img_behind(l.from_node, _seen)
            if hit:
                return hit
    return None

def base_node(mat):
    nt = mat.node_tree
    if not nt:
        return None
    # 1) image feeding Principled Base Color (covers BSDF-converted & generic materials)
    for n in nt.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            for l in n.inputs['Base Color'].links:
                hit = _img_behind(l.from_node)
                if hit:
                    return hit
    # 2) MMD Tools' own base node (covers MMD materials before BSDF conversion)
    for n in nt.nodes:
        if n.type == 'TEX_IMAGE' and n.image and (n.name == 'mmd_base_tex' or n.label == 'Mmd Base Tex'):
            return n
    # 3) if there's exactly one image that isn't a known toon/sphere, use it
    imgs = [n for n in nt.nodes if n.type == 'TEX_IMAGE' and n.image
            and n.name not in TOON_NAMES + SPHERE_NAMES
            and n.label not in TOON_LABELS + SPHERE_LABELS]
    if len(imgs) == 1:
        return imgs[0]
    return None  # ambiguous -> caller must ask the user

def toon_node(mat):
    nt = mat.node_tree
    if not nt:
        return None
    for n in nt.nodes:
        if n.type == 'TEX_IMAGE' and n.image and (n.name in TOON_NAMES or n.label in TOON_LABELS):
            return n
    return None
```

## Inspect

```python
import bpy
print("=== MATERIALS ===")
for m in bpy.data.materials:
    imgs = [n.image.name for n in (m.node_tree.nodes if m.use_nodes and m.node_tree else [])
            if n.type == 'TEX_IMAGE' and n.image]
    print(f"[{m.users}u] {m.name!r}  imgs={imgs}")
print("=== IMAGES (excl. internal) ===")
for im in bpy.data.images:
    if im.name in ('Render Result', 'Viewer Node'):
        continue
    print(f"[{im.users}u] {im.name!r}")
```

Collect the **target materials**: those with `users > 0` (actually on a mesh). Report
0-user orphans (e.g. `Material`, `mmd_tools_rigid_*`) but leave them out of the rename.

## Dry run (change nothing, print the plan)

```python
import bpy
from collections import Counter

# MODE 1: target name = current material name
# MODE 2: target name = your proposed clean ASCII name; build rename_map yourself:
#   rename_map = {'<current material name>': '<clean ASCII name>', ...}

MODE = 1                      # set to 1 or 2
rename_map = {}               # MODE 2 only

targets = [m for m in bpy.data.materials if m.users > 0]

def target_name(m):
    return rename_map.get(m.name, m.name) if MODE == 2 else m.name

# count how many target materials share each base image
basecnt = Counter()
for m in targets:
    bn = base_node(m)
    if bn:
        basecnt[bn.image.name] += 1

for m in targets:
    new = target_name(m)
    bn, tn = base_node(m), toon_node(m)
    bi = bn.image.name if bn else None
    ti = tn.image.name if tn else None
    shared = bi and basecnt[bi] > 1
    print(f"{m.name!r} -> material {'(unchanged)' if MODE==1 else repr(new)}")
    if bi is None:
        print("    base: NONE FOUND  (ambiguous or flat-color — ask the user)")
    else:
        print(f"    base {bi!r} -> {new!r}  {'(SHARED: will DUPLICATE)' if shared else ''}")
    if MODE == 2 and ti:
        tshared = bpy.data.images[ti].users > 1
        print(f"    toon {ti!r} -> {new+'_toon'!r}  {'(shared: leave)' if tshared else ''}")
```

**Mode 1:** show this and confirm. **Mode 2:** show the material→name mapping table *and*
this dry-run, and get explicit approval before applying.

## Apply

```python
import bpy

MODE = 1                      # set to 1 or 2  (match the dry run)
rename_map = {}               # MODE 2 only

targets = [m for m in bpy.data.materials if m.users > 0]

def target_name(m):
    return rename_map.get(m.name, m.name) if MODE == 2 else m.name

def set_img_name(img, name):
    img.name = name
    return img.name           # Blender may append .001 on a cross-image collision — check

claimed = {}                  # base image already renamed -> first owner keeps it
log = []
for m in targets:
    new = target_name(m)

    if MODE == 2:
        m.name = new          # rule: material -> clean ASCII name (mode 2 only)

    bn = base_node(m)
    if bn and bn.image:
        img = bn.image
        if img in claimed:
            # shared base image already owned by another material -> duplicate it
            nimg = img.copy()
            bn.image = nimg
            log.append(f"{new}: base DUPLICATED -> {set_img_name(nimg, new)}")
        else:
            claimed[img] = True
            log.append(f"{new}: base RENAMED -> {set_img_name(img, new)}")
    else:
        log.append(f"{new}: NO base texture (flat color or ambiguous) — material name only")

    if MODE == 2:
        tn = toon_node(m)
        if tn and tn.image:
            timg = tn.image
            if timg.users > 1:
                log.append(f"{new}: toon shared (users={timg.users}) -> left {timg.name!r}")
            else:
                log.append(f"{new}: toon RENAMED -> {set_img_name(timg, new + '_toon')}")

print("\n".join(log))
```

How the duplicate logic works: the **first** target material to reference a shared base
image keeps (renames) the original; every later material sharing it gets a fresh
`image.copy()` named after itself. End state: each material's base image is named exactly
the material name, and no base image is shared.

## Verify

```python
import bpy, re

MODE = 1                      # set to 1 or 2
rename_map = {}               # MODE 2 only

targets = [m for m in bpy.data.materials if m.users > 0]
def target_name(m):
    return rename_map.get(m.name, m.name) if MODE == 2 else m.name

ok = True
for m in targets:
    new = target_name(m)
    mm = bpy.data.materials.get(new) if MODE == 2 else m
    bn = base_node(mm) if mm else None
    bi = bn.image.name if bn and bn.image else None
    if bn is not None and bi != new:
        ok = False
        print(f"  MISMATCH material {new!r}: base={bi!r}")
print("ALL MATCH" if ok else "PROBLEMS FOUND")

if MODE == 2:
    for im in bpy.data.images:    # leftover messy names, excl. shared helpers
        if im.users and (not re.fullmatch(r'[A-Za-z0-9_.\- ]+', im.name) or len(im.name) > 24):
            print(f"  still messy: [{im.users}u] {im.name!r}")

print("shared helpers left in place:")
for im in bpy.data.images:
    if im.users > 1:
        print(f"  [{im.users}u] {im.name!r}")
```

## Pitfalls

- **Ambiguous base** — if `base_node` returns `None` because several non-toon/sphere image
  nodes exist, don't guess; ask the user which is the base color texture.
- **Two materials want the same name (mode 2)** — disambiguate in `rename_map`
  (`Tops_01`, `Tops_02`). Never collapse two materials to one name.
- **Cross-image name collision** — if an image named `Body` already exists from an
  unrelated source, `img.name = 'Body'` becomes `Body.001`. `set_img_name` returns the
  real result; check it.
- **Shared helper textures** (e.g. `MatcapWarp.png` used by many materials) are *not* base
  textures and must stay shared — leaving them is correct, not a bug.
- **Mode 1 with Japanese/long material names** — the texture inherits that exact name. If
  export-safe ASCII is needed, run mode 2.

---
name: material-texture-namer
description: Match Blender material names and base-color image names, duplicating shared base images, optionally tidying names to readable ASCII. Use for material/texture naming after MMD, VRoid or FBX import. Prefer background Blender CLI for saved models; GUI/MCP is optional.
---

# Material & Texture Namer

This skill drives Blender (preferably through background CLI) to clean up **material and texture
names** so that every material's **base-color texture carries the same name as the
material**. Imported models — especially MMD/VRoid — arrive with long, opaque names like
`N00_007_01_Tops_01_CLOTH_01 (Instance)` and base textures called `_12.png`; this skill
fixes that, and guarantees no base texture is shared across two materials (it duplicates
shared ones so each material owns its own same-named texture).

It is a focused, standalone extraction of the "tidy material & texture names" step from the
MMD→Humanoid conversion workflow, usable on any Blender model.

## The one hard invariant

> **After this skill runs, for every processed material, its base-color texture has the
> exact same name as the material, and no base texture is shared between materials.**

(Material and Image are different datablock types, so Blender allows the identical name on
both — there is no `.001` suffix collision between a material and its image.)

## Prerequisites — confirm, don't assume

1. **Blender is installed and the input blend is saved.** No GUI/MCP connection is required.
   For an unsaved interactive scene, save a copy first or use GUI/MCP explicitly.
2. **The model's materials use nodes** (`use_nodes = True`). For MMD models,
   this works whether or not the materials have been converted to Principled BSDF yet (the
   base-texture detector handles both — see the reference).
3. **Preserve the source and save to a new output.** The bundled CLI uses new output
   directories and checkpoints. Back up separately when editing a live GUI scene.

When bundled with the converter, prefer its `scripts/mmd_cli.py`: inspect, then apply a
material-only plan (`armature: null`, explicit `meshes`, `rename_materials` operation).
Mode 1 sets each destination to the existing material name, with `ascii_only: false`
and `tidy_toon: false`; mode 2 uses approved ASCII names and the defaults. Specify exact
base/toon node names when detection is ambiguous. It supports unrigged meshes without
bone edits. If installed alone without the parent scripts, run this skill's reference
bpy in a disposable background Blender process, as described in its execution section.

## Step 0 — Ask the mode first (required)

If the user's requested mode is not already clear, present the two modes and **wait for
their choice**:

```
マテリアル/テクスチャの名前整理を始めます。モードを選んでください：

1）名前一致のみ
   マテリアル名はそのままに、各マテリアルの「基準テクスチャ（ベースカラー）」の
   名前をマテリアル名に一致させます。複数マテリアルで共有されているテクスチャは
   複製して、必ずマテリアルごとに同名のテクスチャがあるようにします。
   ※ 名前の付け直し（わかりやすくする作業）はしません。

2）名前一致＋わかりやすくリネーム
   1) に加えて、長くて分かりにくいマテリアル名を短い半角英数字の名前に付け直し、
   テクスチャも同じ名前に揃えます。補助のTOONテクスチャは <名前>_toon に整え、
   共有されている matcap / sphere などのユーティリティテクスチャはそのまま残します。
```

Both modes share the same inspection → dry-run → apply → verify pipeline. The full,
copy-pasteable bpy implementation for both modes lives in
`references/material-texture-namer.md` — **read it before acting.**

## Step 1 — Inspect

List materials, their image-texture nodes, and per-image user counts. This reveals which
textures are shared (will be duplicated) and which names are long/opaque. Skip 0-user
orphan materials (e.g. `Material`, `mmd_tools_rigid_*`) — report them but don't rename
them. → `references/material-texture-namer.md` (§Inspect)

## Step 2 — Build the plan

**Mode 1 (match only):** the target name for each material is the material's *current*
name. No mapping decision needed — just confirm which node is the base texture per material
and which base images are shared (those get duplicated). Show the user the dry-run and
confirm.

**Mode 2 (match + clarify):** **propose a clean short ASCII name for each material** (your
judgment — strip cruft like `(Instance)` and `N00_000_00_…`, keep the meaningful token,
disambiguate duplicates with `_01/_02…`). **Present the full mapping table and get the
user's approval** before applying — different authors use different conventions, so never
hard-code a scheme; read the real names and decide. → `references/material-texture-namer.md`
(§Dry run)

## Step 3 — Apply

Run the apply function for the chosen mode: rename the material (mode 2 only), set the base
texture's name to match (duplicating it first if it's shared by other materials), and — in
mode 2 — tidy the 1:1 toon texture to `<name>_toon`. Shared helper textures
(matcap/sphere, or a toon shared by many materials) are left untouched on purpose. →
`references/material-texture-namer.md` (§Apply)

## Step 4 — Verify

Confirm the invariant: for every processed material, base-texture name == material name,
and nothing long/non-ASCII remains except the intentional shared helpers (mode 2). Report
the result, any materials with no base texture, and any shared helpers left in place. →
`references/material-texture-namer.md` (§Verify)

## Notes & limits

- A material with **no base texture** (a flat-color material) is renamed (mode 2) but has
  no texture to match — report it.
- If the base texture is **ambiguous** (several image nodes, none clearly the base, no MMD
  marker), stop and ask the user which one is the base.
- Duplicated images still point at the same file on disk; pack (`img.pack()`) or save-as
  before export if you need each to be an independent file.
- Mode 1 keeps existing material names verbatim — including Japanese or long ones. If those
  names need to be export-safe ASCII, use mode 2 instead.

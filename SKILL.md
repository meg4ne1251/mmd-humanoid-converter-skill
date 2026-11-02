---
name: mmd-humanoid-converter
description: Convert MMD PMX/PMD models or saved Blender scenes to Humanoid rigs, transferring helper-bone weights, restructuring and renaming bones, tidying materials and exporting FBX/textures. Prefer background Blender CLI; use GUI/MCP for interactive corrections. Use for MMD cleanup and preparation for Unity or MotionBuilder.
---

# MMD → Humanoid Converter

This skill runs Blender **in background mode through `scripts/mmd_cli.py`** to convert an MMD model into a clean Humanoid rig. Accept saved `.blend` scenes or import `.pmx`/`.pmd` with MMD Tools. Use GUI/MCP only when interaction is needed.

Read [CLI workflow and plan schema](references/cli-workflow.md) before execution. It defines the `inspect → plan → dry-run → apply → verify/render → export` path, checkpoint handling and supported operations. The CLI mechanics were integration-tested on synthetic data in Blender 5.1.1; real models still require model-specific mappings and inspection. The historical live-model validation below describes the earlier MCP workflow, not a completed CLI validation of every model.

> **Validated end-to-end** on a real MMD model (a 196-bone きりたん variant, 43 materials) on Blender 5.x: full run from inspection through twist-bone weight transfer, IK/shoulder-helper removal, waist re-rooting, Humanoid rename, material rewire, part separation, material/texture name tidy, and FBX export — pose-tested at each destructive step. The reference files carry the concrete pitfalls found during that run (multi-user mesh data, MCP operator-context failures, the `mmd_shader` node-group material layout, etc.). MMD conversion still "has no always" — treat the skill as semi-automatic, not guaranteed.

## Read this first: the mindset

**MMD conversion has no "always."** Every model is structured and named differently. There is no fixed bone list you can hard-code. The single most important rule of this skill is: **inspect the real scene before you act.** Read the actual armature, the actual bones, the actual vertex groups, the actual material slots — then decide. Never assume a bone exists, never assume a name, never assume a hierarchy.

This skill is **semi-automatic by design.** The assistant handles deterministic work (renaming, weight math, deleting clearly-unneeded bones); model-specific judgment remains necessary. Inspect before destructive operations, and follow the user's selected execution mode for confirmations. Some models need manual corrections; report them clearly.

## Goal: the target hierarchy

The end state is the Humanoid hierarchy. The waist (Hips) is the root of the body and everything grows **upward** from it:

```
Reference → Parent → Hips
  Hips ├─ UpLeg_L → Leg_L → Foot_L → Toe_L
       ├─ UpLeg_R → Leg_R → Foot_R → Toe_R
       └─ Spine1 → Spine2 → Spine3
              ├─ Shoulder_L → UpArm_L → ForeArm_L → Hand_L (→ fingers)
              ├─ Shoulder_R → UpArm_R → ForeArm_R → Hand_R (→ fingers)
              └─ Neck → Head
```

By contrast, raw MMD rigs have a **downward** waist (センター/グループ/センター先 etc.), upward "twist"/捩り helper bones splitting the arm weights across several bones, and separate IK/FK control bones around the wrists/ankles. Converting means reshaping the MMD rig into the structure above.

The full naming map (body, legs, arms, fingers, costume/hair) is in `references/bone-naming.md`. Read it before any renaming. Note that source bone names come in two styles depending on the MMD Tools import settings — 左/右 prefix (`左腕捩`) or `.L`/`.R` suffix (`腕捩.L`) — so always read the real names from the scene rather than copying example names verbatim.

## Execution path and prerequisites

1. Locate the input file and Blender executable. The launcher checks `--blender`, `BLENDER_BIN`, PATH and the standard macOS app location; it does not depend on interactive shell aliases. System Python 3.10+ is sufficient to launch it.
2. Use a saved `.blend`, `.pmx` or `.pmd`. MMD Tools is needed for PMX/PMD import, not for ordinary edits to an already imported blend. `.fbx` may also be inspected. Read actual importer settings instead of assuming they match a previous model.
3. Preserve the source. CLI commands write only to a **new** output directory and save an initial checkpoint plus per-operation checkpoints; verify `input_unchanged` in the report. This satisfies the backup requirement without asking the user to make a manual copy. For an unsaved GUI scene, save a separate input copy first; the CLI cannot read another process's unsaved memory.
4. Choose/retain the user's step or batch mode below. Inspect first, summarize the scene, then create an explicit model-specific JSON plan. Do not open Blender's GUI or request MCP setup merely to inspect, edit, render or export a saved input.

```sh
python3 scripts/mmd_cli.py inspect "input.blend" --output-dir "work/inspect-01"
```

Check the exit status and `report.json`, not just the existence of an output file. `apply --dry-run` simulates the plan in memory; `apply` writes checkpoints and `converted.blend`. `export --textures` writes a new blend, FBX and `tex/`, then checks saved/reloaded data. Read warnings and generate rest/pose images before reporting success. Follow applicable local post-export instructions once FBX and textures are verified.

### GUI/MCP fallback only

For manual modeling, weight painting or an explicitly interactive task, use the connected Blender instance. Save a backup before destructive edits there. Dedicated MCP inspection tools are useful if available. The following context workaround and per-step GUI snippets apply **only** to this fallback; the CLI worker sets active object/selection/mode and does not search for VIEW_3D areas.

Code run via `execute_blender_code` does **not** have a normal UI context, so many `bpy.ops` operators fail with *"context is incorrect"* or *"poll() failed"* — confirmed on Blender 5.x with `hide_view_clear`, `object.delete`, `object.mode_set`, `object.select_all`, `view3d.*`, `render.opengl`, etc. Two reliable workarounds:

1. **Prefer data-level APIs over operators** wherever one exists — they need no context:
   - hide/unhide: `obj.hide_set(False)` / `obj.hide_viewport = False` (not `hide_view_clear`)
   - delete object + subtree: `bpy.data.objects.remove(obj, do_unlink=True)` (not `object.delete`)
   - clear pose: set `pb.location/rotation_euler/rotation_quaternion/scale` directly (not `pose.transforms_clear`)
   - pose-bone constraints are editable straight from Object Mode via `arm.pose.bones[*].constraints` — no need to enter Pose Mode at all.
2. **When you truly need an operator** (e.g. `mode_set` to EDIT for `edit_bones`, or `render.opengl`), wrap it in a VIEW_3D context override:

```python
def view3d_ctx():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        return {'window': win, 'area': area, 'region': region, 'scene': bpy.context.scene}
    return None

ctx = view3d_ctx()
with bpy.context.temp_override(**ctx):
    bpy.ops.object.mode_set(mode='EDIT')
```

Also: `mode_set(mode='POSE')` only works when the **active object is the armature**. If a mesh is active you'll get *enum "POSE" not found*. Set `bpy.context.view_layer.objects.active = arm` first. And there is usually **no camera** in an MMD scene, so `render_viewport_to_path` fails — use `bpy.ops.render.opengl(write_still=True)` (inside the context override) to capture a viewport image instead.

## The workflow

Work through these in order. **Read the linked reference before each step**, then encode supported edits in the CLI plan using `references/cli-workflow.md`. The reference snippets preserve historical bpy patterns; GUI-context wrappers are not the execution path for CLI. Mark progress and follow the selected mode at destructive steps.

### Mode selection — ask before Step 0

Before doing anything, present the user with two modes and wait for their choice:

```
変換を開始します。モードを選んでください：

A）ステップ実行モード（推奨）
   各フェーズで削除・変更内容を確認してから進みます。初めてのモデルや
   構造が複雑なモデルにはこちらを推奨します。

B）一括実行モード
   問題がなければ確認なしで全フェーズを連続実行します。
   以下の場合のみ中断して報告します：
   ・ウェイトが乗っている予想外のボーンが見つかったとき
   ・ボーン名が想定と大きく異なり自動マッピングできないとき
   ・アーマチュアが複数あるなど構造が想定外のとき
```

**In step-by-step mode (A):** present the plan for each destructive operation (what will be deleted/moved/renamed, and why) and wait for confirmation before executing.

**In batch mode (B):** execute each step without confirmation, but **always stop and report** when any of the following is true — then ask how to proceed before continuing:
- A bone marked for deletion still carries vertex weights and no obvious transfer target exists.
- Bone names don't match any expected MMD pattern, making automatic mapping ambiguous.
- Multiple armatures are found in the scene.
- Any step raises an unexpected error.

In both modes, **always run Step 0 (scene inspection) first** and show the user a summary of what was found before touching anything.

### Step 0 — Inspect the scene
Before anything, build a picture of what you're working with: list objects, find the armature(s), dump the bone tree, list vertex groups per mesh, list material slots, check which bone collections are hidden. → `references/01-inspect.md`

### Step 1 — Delete junk objects
MMD imports bring in collision/physics/rigid-body objects (visible after Alt+H). Keep only the mesh(es) and the armature; delete the rest. Inspect and confirm the deletion list first. → `references/02-cleanup-objects.md`

### Step 2 — Clear bone constraints
In Pose Mode, MMD models have many constraint-driven (colored) bones. Remove all pose-bone constraints so later restructuring isn't fighting them. → `references/03-constraints.md`

### Step 3 — Restructure the bones (the hard part)
This is the core. It breaks into sub-steps, each with weight-safety implications:

- **3a. Fix the waist & spine.** Rotate the downward MMD waist to point upward, rebuild the Hips→Spine parenting, and delete center/group/center-tip bones. → `references/04-bone-structure.md`
- **3b. Remove arm twist / upward helper bones.** These almost always carry part of the arm's weight. **Transfer their weights onto the real arm bone first, then delete.** → weight rules in `references/05-weight-transfer.md`, deletion in `references/04-bone-structure.md`.
- **3c. Remove IK/FK control bones** (wrists/ankles). Check for weights; transfer to Foot/Toe/Hand or repaint, then delete. Do **not** delete the actual Foot bone.
- **3d. Other stray bones.** Anything not in the target hierarchy and not a physics/jiggle bone (skirt, ribbon, shoelace, hair) is a deletion candidate — but only after confirming it carries no weight.

After each deletion batch, have the user (or you, via pose test) verify the mesh still follows the rig. → `references/06-verify-rig.md`

### Step 4 — Delete `_shadow` / `_dummy` bones
These live in hidden bone collections and don't even show with Alt+H. Make the collection visible, then delete (they almost never carry weight). → `references/07-shadow-dummy.md`

### Step 5 — Rename bones to the Humanoid convention
Rename to Hips/Spine#/Neck/Head, UpLeg/Leg/Foot/Toe, Shoulder/UpArm/ForeArm/Hand, fingers, with `_L`/`_R` suffixes. Renaming in Object Mode on `armature.bones` auto-updates vertex group names. Rarely a rename drops a weight — pose-test after. → `references/bone-naming.md` + `references/08-rename.md`

### Step 6 — Connect chain bones, fix display & tail directions
MMD Tools imports every bone with `use_connect = False`, so the armature looks like a pile of free-floating bones even though parenting is intact. Set armature to OCTAHEDRAL + show-in-front, point each bone's tail at its child (or extend end bones along the parent direction), then **connect bones by geometry**: for each child, if its **head already coincides with its parent's tail** (distance ≈ 0), connect it; otherwise leave it free. This is a purely geometric test — no bone-name lists, no branch logic — and it **connects every in-line bone including jiggle/cloth chains (sleeve, skirt, hair, sash)**, since the modeler placed those heads on their parent's tail too. Because we only connect heads that are *already* on the parent's tail, the `use_connect` move is a no-op: no rest-pose head shifts, deformation is untouched, and a branch parent can have multiple children connected at once. Bones whose head sits offset from the parent's tail (limb starts, free controls, mismatched branches) never match and stay disconnected. Pose-test after connecting. → `references/09-bone-display.md`

### Step 7 — Convert materials to Principled BSDF (optional but common)
MMD toon shaders (Emission + Transparent + Mix + LightPath) → Principled BSDF, **reusing** the existing texture/mapping/UV nodes. Never `nodes.clear()`. → `references/material-bsdf.md`

### Step 8 — Separate the mesh into parts
Split face/hair/body/clothes/accessories into separate objects. Material-based separation works when materials map 1:1 to parts; otherwise fall back to loose/selected separation. Do this **last**, after rig work. → `references/10-separate-parts.md`

### Step 9 — Rename face shape keys
Rename the Japanese vowel shape keys `あ い う え お` → `a i u e o`. → `references/11-shapekeys.md`

### Step 10 — Optional finishing
Polish the rig. None of these sub-steps are required — do them if the user wants them.

- **10a. Delete tip bones (先端ボーン).** Find all bones whose name contains `先`, verify actual per-vertex weights are zero, then delete in Edit Mode. If any carry weight, stop and ask before proceeding. → `references/12-finishing-export.md`
- **10b. Tris → quads.** Only if the user explicitly asks.
- **10c. Hidden body under clothes.** MMD models typically delete body mesh covered by clothing. This is manual modeling work — flag it to the user rather than attempting automation.

### Step 11 — Tidy material & texture names
The last **editing** step before export. Rename opaque material names to clear ASCII and make **material name == base-color image name**. Duplicate shared base images; tidy unique toon images to `<name>_toon`, retaining shared helpers. Read the actual names, show the proposed mapping, dry-run and follow the selected mode for approval. Use the CLI `rename_materials` operation **before** export. → `references/13-material-texture-rename.md`

### Step 12 — Export
After numerical pose tests and image review, use CLI `export` (with `--textures` if requested) for FBX plus a saved blend and roundtrip checks. It uses `add_leaf_bones=False`, `bake_anim=False` and `use_mesh_modifiers=False` to preserve shape keys. Follow applicable local characterization instructions after texture validation; SDK checks do not prove MotionBuilder HIK or appearance. → `references/cli-workflow.md` + `references/12-finishing-export.md`

### Step 13 — Export textures to `tex/` folder (Optional)
Export all textures used in the model into a `tex/` folder located in the same directory as the `.blend` file. Textures are exported in PNG format and named `[Blender内でのテクスチャの名前].png` (e.g. `Face.png`, `Clothes_01.png`), stripping existing extensions to prevent duplicates like `.png.png` or `.bmp.png`. Blender's internal image filepaths are updated to relative `//tex/<name>.png`. → `references/14-texture-export.md`

### Conversation closing rule (会話終了時の必須確認)
**モデル変換・出力を実施した会話で、テクスチャ出力の希望がまだ分からない場合に以下を尋ねること：**
> 「追加でテクスチャの出力を行いますか？」

これに対してクライアント（ユーザー）が出力を希望した場合は、Step 13（`references/14-texture-export.md`）と同じ手順・条件（blendファイルと同じディレクトリに `tex/` フォルダを作成、Blender内テクスチャ名.png として保存、二重拡張子防止、Blender内パスを `//tex/...` に更新）でテクスチャを出力する。

既に希望が示されている／出力済みの場合は再確認しない。手順・スクリプト編集や調査だけの会話にはこの質問を適用しない。

## Weight transfer — the heart of the cleanup

Many MMD arm/leg weights are split across twist/helper bones, so deleting those bones naively tears the mesh. The fix is to **merge the split weights onto the single real bone before deleting.** This skill does it directly in bpy with a temporary `VERTEX_WEIGHT_MIX` modifier (the same mechanism the original hand-tool used), supporting **SET (overwrite)** and **ADD (accumulate)** modes, optional source-group deletion, and L/R mirroring. ADD must be applied **once only** — running it twice corrupts the weight gradient. The complete, copy-pasteable implementation and the rules live in `references/05-weight-transfer.md` — read it before transferring any weights.

## Safety checklist (apply at every destructive step)

- Inspect first: read the real bones / vertex groups / materials, never guess.
- Before deleting a bone: confirm it carries no weight, or transfer its weight first.
- Surface the deletion/restructure plan and obtain confirmation when the selected execution mode requires it.
- Operate in the correct mode (Object / Edit / Pose); set active object & selection explicitly.
- In Edit Mode use `edit_bones`; in Object Mode use `armature.bones` (read-only for geometry, but renaming works here).
- After changes, update the depsgraph before reading computed values; pose-test after restructuring/renaming.
- CLI failures retain checkpoints and diagnostics; resume from the last good checkpoint with a new matching plan. Do not rerun ADD against a partially changed model.
- When unsure, stop and ask — a wrong delete can ruin the model, and "MMD conversion has no always."

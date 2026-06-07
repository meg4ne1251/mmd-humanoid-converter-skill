---
name: mmd-humanoid-converter
description: Convert an MMD (MikuMikuDance) PMX/PMD model into a clean Humanoid-rig model inside Blender via the Blender MCP. Use this skill whenever the user wants to convert, retarget, clean up, or "humanoid-ify" an MMD model in Blender — including removing MMD-specific bones (twist/IK/center/group bones), transferring vertex weights onto the real arm/leg bones, fixing the downward-pointing waist bone, renaming bones to the Humanoid convention (Hips/Spine/UpArm/ForeArm/Hand/UpLeg/Leg/Foot/Toe), splitting the mesh into parts, and renaming Japanese shape keys. Trigger this even if the user only says "I imported an MMD model and want to use it in Unity/MotionBuilder" or "make this MMD model usable for our rig," since that is exactly this workflow.
---

# MMD → Humanoid Converter

This skill drives Blender (through the Blender MCP) to convert an MMD model — imported via the **MMD Tools** addon — into a clean Humanoid rig that matches the VLL standard bone hierarchy. It is the automation of a workflow that used to be done by hand.

## Read this first: the mindset

**MMD conversion has no "always."** Every model is structured and named differently. There is no fixed bone list you can hard-code. The single most important rule of this skill is: **inspect the real scene before you act.** Read the actual armature, the actual bones, the actual vertex groups, the actual material slots — then decide. Never assume a bone exists, never assume a name, never assume a hierarchy.

This skill is **semi-automatic by design.** Claude does the tedious, deterministic work (renaming, weight math, deleting clearly-unneeded bones), but **destructive operations** — deleting bones, clearing weights, restructuring parenting — must be preceded by an inspection and a short confirmation with the user. The goal is "do the rote work, surface the judgment calls," not "fully automatic perfect conversion." Some models will need manual fixes; that's expected, and the skill should say so rather than pretend otherwise.

## Goal: the target hierarchy

The end state is the VLL-standard Humanoid hierarchy. The waist (Hips) is the root of the body and everything grows **upward** from it:

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

The full naming map (body, legs, arms, fingers, costume/hair) is in `references/bone-naming.md`. Read it before any renaming.

## Prerequisites — confirm, don't assume

Before starting, confirm with the user (and verify in-scene where possible):

1. **Blender is open with the Blender MCP addon connected.** This skill cannot work otherwise.
2. **The MMD model is already imported** via the MMD Tools addon (File → Import → MikuMikuDance Model `.pmd/.pmx`). Importing the file itself is outside this skill — if nothing is in the scene, ask the user to import first. Note the Blender version (behavior differs between 4.x and 5.x; see `references/material-bsdf.md`).

If you need API details mid-task, prefer the dedicated Blender MCP tools (`get_objects_summary`, `get_object_detail_summary`, `search_api_docs`, etc.) and fall back to `execute_blender_code` only when no dedicated tool fits. Always set mode / active object / selection explicitly before operators, and update the depsgraph before reading computed values.

### Running operators through the Blender MCP (read this — it bites every step)

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

Work through these in order. Each step has a dedicated reference file with the exact bpy patterns and the specific pitfalls discovered in real conversions — **read the linked reference before doing the step.** Mark progress and check in with the user at the destructive steps.

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

### Step 6 — Fix bone display & tail directions (polish)
Set armature to OCTAHEDRAL + show-in-front, point each bone's tail at its child (or extend end bones along the parent direction) so the rig reads cleanly. → `references/09-bone-display.md`

### Step 7 — Convert materials to Principled BSDF (optional but common)
MMD toon shaders (Emission + Transparent + Mix + LightPath) → Principled BSDF, **reusing** the existing texture/mapping/UV nodes. Never `nodes.clear()`. → `references/material-bsdf.md`

### Step 8 — Separate the mesh into parts
Split face/hair/body/clothes/accessories into separate objects. Material-based separation works when materials map 1:1 to parts; otherwise fall back to loose/selected separation. Do this **last**, after rig work. → `references/10-separate-parts.md`

### Step 9 — Rename face shape keys
Rename the Japanese vowel shape keys `あ い う え お` → `a i u e p`. → `references/11-shapekeys.md`

### Step 10 — Optional finishing & export
Delete leaf/tip bones, tris→quads, build hidden body mesh under clothes if needed. Then export FBX → characterize in MotionBuilder. → `references/12-finishing-export.md`

## Weight transfer — the heart of the cleanup

Many MMD arm/leg weights are split across twist/helper bones, so deleting those bones naively tears the mesh. The fix is to **merge the split weights onto the single real bone before deleting.** This skill does it directly in bpy with a temporary `VERTEX_WEIGHT_MIX` modifier (the same mechanism the original hand-tool used), supporting **SET (overwrite)** and **ADD (accumulate)** modes, optional source-group deletion, and L/R mirroring. ADD must be applied **once only** — running it twice corrupts the weight gradient. The complete, copy-pasteable implementation and the rules live in `references/05-weight-transfer.md` — read it before transferring any weights.

## Safety checklist (apply at every destructive step)

- Inspect first: read the real bones / vertex groups / materials, never guess.
- Before deleting a bone: confirm it carries no weight, or transfer its weight first.
- Surface the deletion/restructure plan to the user and get a confirmation.
- Operate in the correct mode (Object / Edit / Pose); set active object & selection explicitly.
- In Edit Mode use `edit_bones`; in Object Mode use `armature.bones` (read-only for geometry, but renaming works here).
- After changes, update the depsgraph before reading computed values; pose-test after restructuring/renaming.
- When unsure, stop and ask — a wrong delete can ruin the model, and "MMD conversion has no always."

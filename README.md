# mmd-humanoid-converter

A **Claude skill** that converts an MMD (MikuMikuDance) `.pmx` / `.pmd` model into a clean **Humanoid-rig** model inside Blender, driving Blender through the **Blender MCP**.

It automates a workflow that was previously done entirely by hand: stripping MMD-specific bones (twist / IK / center / group bones), transferring split vertex weights onto the real limb bones, flipping the downward MMD waist into an upward Humanoid `Hips`, renaming bones to the Humanoid convention, separating the mesh into parts, and renaming the Japanese vowel shape keys.

> ⚠️ **MMD conversion has no "always."** Every model is structured and named differently, so this skill is **semi-automatic**: it does the rote work and asks you to confirm the judgment calls (especially destructive bone/weight operations). It does not guarantee a perfect, hands-off conversion of every model.

## What it does

Target rig (VLL Humanoid standard):

```
Reference → Parent → Hips
  Hips ├─ UpLeg_L → Leg_L → Foot_L → Toe_L
       ├─ UpLeg_R → Leg_R → Foot_R → Toe_R
       └─ Spine1 → Spine2 → Spine3
              ├─ Shoulder_L → UpArm_L → ForeArm_L → Hand_L (→ fingers)
              ├─ Shoulder_R → UpArm_R → ForeArm_R → Hand_R (→ fingers)
              └─ Neck → Head
```

Workflow steps: inspect → delete junk objects → clear bone constraints → restructure bones (waist/spine, twist & IK removal with weight transfer) → delete `_shadow`/`_dummy` → rename to Humanoid → fix bone display → convert materials to Principled BSDF → separate parts → rename shape keys → optional finishing → FBX export.

## Requirements

- **Blender** (4.x or 5.x; some node socket names differ — the skill handles both) with the **[MMD Tools](https://extensions.blender.org/add-ons/mmd-tools/)** addon installed.
- The target MMD model already **imported** into Blender (File → Import → MikuMikuDance Model).
- A **Blender MCP** server running and connected to your Claude client.
- A Claude client that supports skills (e.g. Claude Code / Cowork).

## Install

This repository **is** the skill (single-skill repo). Clone it into your skills directory:

```bash
git clone <this-repo-url> mmd-humanoid-converter
```

Then make the folder available to Claude as a skill (place it where your client loads skills from). Once loaded, the skill triggers when you ask Claude to convert / clean up / humanoid-ify an MMD model in Blender.

## Usage

1. In Blender: import your `.pmx`/`.pmd` with MMD Tools and start the Blender MCP server.
2. In Claude: e.g. *"I imported an MMD model in Blender — convert it to our Humanoid rig."*
3. Claude inspects the scene, proposes a plan, and works through the steps, pausing for confirmation before destructive operations.

## Layout

```
.
├── SKILL.md          # the skill: workflow orchestrator
├── references/       # per-step detail (bpy code + pitfalls)
│   ├── 01-inspect.md
│   ├── 02-cleanup-objects.md
│   ├── 03-constraints.md
│   ├── 04-bone-structure.md
│   ├── 05-weight-transfer.md
│   ├── 06-verify-rig.md
│   ├── 07-shadow-dummy.md
│   ├── 08-rename.md
│   ├── 09-bone-display.md
│   ├── 10-separate-parts.md
│   ├── 11-shapekeys.md
│   ├── 12-finishing-export.md
│   ├── bone-naming.md
│   └── material-bsdf.md
├── CLAUDE.md         # project/dev notes
└── README.md
```

## License & disclaimer

Provided as-is. MMD model conversion results vary by model; verify rig deformation after conversion and expect some models to need manual touch-up. Respect the original MMD model's distribution terms and license when using converted assets.

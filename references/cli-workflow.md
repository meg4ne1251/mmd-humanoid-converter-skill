# CLI workflow and conversion plans

Use `scripts/mmd_cli.py` from the installed skill root. It finds Blender via `--blender`,
`BLENDER_BIN`, PATH, then the standard macOS application location. A shell alias is not
required. Python 3.10+ launches Blender's own Python in background mode; installing `bpy`
into system Python is unnecessary. The launcher does not start an MCP server.

## Commands

Every `--output-dir` must be **new**. Each run writes `request.json`, `blender.log`, and
`report.json`; success requires exit code 0 **and** `report.json.ok == true`. Failed runs
retain diagnostics and any completed checkpoints. Never use the presence of an FBX alone
as evidence of success. The input file is hashed before/after execution and never saved over.
The examples use the Git-ignored `work/` directory; keep private model outputs out of commits.

```sh
python3 scripts/mmd_cli.py inspect "input.blend" --output-dir "work/01-inspect"
# Read report.json and construct a model-specific plan.json, then:
python3 scripts/mmd_cli.py apply "input.blend" --plan "plan.json" --dry-run --output-dir "work/02-preview"
python3 scripts/mmd_cli.py apply "input.blend" --plan "plan.json" --output-dir "work/03-converted"
python3 scripts/mmd_cli.py verify "work/03-converted/converted.blend" --pose "UpArm_L:Z:30" --output-dir "work/04-verify"
python3 scripts/mmd_cli.py render "work/03-converted/converted.blend" --views front side --pose "UpArm_L:Z:30" --output-dir "work/05-images"
python3 scripts/mmd_cli.py export "work/03-converted/converted.blend" --textures --require-humanoid --output-dir "work/06-export"
```

These names are examples: inspect the model and choose actual weighted bones for pose
tests. Run commands **sequentially**, checking each result before the next command.
`verify`/`render`/`export` infer the rig only when there is exactly one armature; optional
`--armature` and `--meshes` assert its name and complete bound-mesh list, not permission
to guess between several rigs. `--require-humanoid` requires `Parent`, `Hips`, `Spine1`,
`Head`, and bilateral UpArm/ForeArm/Hand/UpLeg/Leg/Foot. It is a name-presence check;
the downstream characterizer still checks Character slots, hierarchy and T-pose.

`inspect` also accepts `.pmx`, `.pmd`, or `.fbx`. PMX/PMD require installed MMD Tools;
FBX requires Blender's FBX addon. The import runs with `EXEC_DEFAULT`, with no file dialog
or log written next to the source model. To specify import settings:

```json
{"scale": 0.08, "rename_bones": false}
```

Save this as `import-options.json` and add `--import-options import-options.json` to
**both** inspect and apply when importing the original PMX/PMD. The values must be valid
properties of the installed MMD Tools importer. Use `--mmd-addon MODULE` only if module
discovery is ambiguous. Saving an initial imported `.blend` checkpoint freezes the import
settings; subsequent plans should target that file and its new hash. `.fbx` input is
imported without animation and is useful for inspection, not for preserving animation.

## Plan format

`inspect` reports exact names, bone geometry/hierarchy/constraints, real weighted vertex
counts and sums, mesh bindings, material slots, texture node names and image paths.
Build a JSON plan from this data; the CLI deliberately does not infer deletions from
Japanese names, guess a base image, or classify materials by substring.

The following small example describes a **synthetic rig**; replace every model-dependent
name, coordinate and hash with inspected values. It is not a universal MMD mapping.

```json
{
  "version": 1,
  "input_sha256": "copy the input_sha256 from the inspect report",
  "armature": "Rig",
  "meshes": ["Body"],
  "operations": [
    {"type": "clear_constraints"},
    {"type": "transfer_weights", "pairs": [{"source": "Helper", "target": "Root", "mode": "ADD"}]},
    {"type": "edit_bones", "delete": ["Helper"]},
    {"type": "rename_bones", "mapping": {"Root": "Hips"}}
  ],
  "required_bones": ["Hips"],
  "pose_tests": ["Hips:Y:30"]
}
```

The hash must equal the actual input file. Applying a plan to a checkpoint produced by
that plan is rejected. `meshes` must include **all** meshes bound to the armature so weight
checks cannot silently omit clothing or another body fragment. Multiple armatures stop
the conversion. `dry-run` executes the same operations in a disposable Blender process
and writes only the report/log/request, without saving blend checkpoints, FBX or textures.

For a material-only plan, set `armature` to `null`, list the model's meshes explicitly,
and use only `principled_materials` / `rename_materials`. This also supports models without
an armature and does not trigger conversion or characterization.

## Supported operations

Operations execute in listed order. Names in an operation refer to the state **at that
point**, including earlier renames and separated objects. Each successful operation is
verified and saved as `checkpoints/NNN-operation.blend`; `000-input.blend` preserves the
loaded input. The final result is `converted.blend`. Restore a checkpoint and build a new
plan with its hash when resuming; do not replay ADD operations against changed data.

| `type` | Fields and behavior |
|---|---|
| `delete_objects` | `names: [object names]`, exact list, **not recursive**. Include inspected physics children. Cannot remove the selected rig/model meshes. Surviving children keep world transforms when their parent is deleted. |
| `clear_constraints` | Removes pose-bone constraints from the chosen rig. |
| `reset_pose` | Resets bone transforms to neutral after inspection; refuses an active animation action. Does not change shape-key values. |
| `transfer_weights` | `pairs: [{source, target, mode}]`; `mode` defaults to ADD, SET also supported. Single-user mesh data first, apply weight modifier, check actual per-vertex result and unchanged geometry/shape keys, then remove source group. Missing sources, repeated sources, self-transfer and weight overflow stop execution. |
| `edit_bones` | Optional `add: [{name, head, tail, parent, use_deform}]`, `update: {bone: {head, tail, roll, parent, use_deform}}`, `delete: [names]`. Coordinates are armature-local, roll is radians; `parent: null` makes a root. New bones default to non-deforming. Reparent surviving children explicitly before deleting their parent. Nonzero weights, cycles and zero lengths are rejected. Moving a weighted head requires `allow_weighted_head_move: true` on that update; never use this merely to put Hips at the origin—add a weight-free Parent instead. |
| `rename_bones` | `mapping: {old: new}`. Checks destinations and uses temporary names so swaps work; vertex groups must follow. |
| `connect_bones` | Optional `tolerance` (default `1e-7`, max `1e-5` Blender units). Connects only already coincident heads/tails, reports maximum head shift; sets OCTAHEDRAL/in-front display. Tail edits belong in `edit_bones.update`, based on actual geometry. |
| `principled_materials` | `materials: {material: {base_color_node: "exact node name", alpha: true}}`. Reuses image/UV nodes, connects Base Color/Alpha to Principled and Principled to the active output, never clears the node tree. `base_color_node: null` retains the shader's constant color. Ambiguous shader/output nodes stop. |
| `separate_materials` | `object: "mesh"`, `parts: {new_object: [material names]}`. Must classify every used material exactly once. Separates and rejoins each part, checks shape-key names, updates the model-mesh scope for later operations. Cannot split a single shared material into two semantic parts; use inspected vertex/island selection in a custom background bpy script for that case. |
| `rename_shape_keys` | Optional `objects` and `mapping`; default mapping is `あ/い/う/え/お → a/i/u/e/o`. Other keys remain. Name collisions stop. |
| `clear_shape_keys` | Explicit `objects: [model mesh names]`. Removes shape keys only from these objects; use only after checking they are unwanted copies. |
| `rename_materials` | `mapping: {old: {name: "ASCII_name", base_color_node: "optional exact node", toon_node: "optional exact node"}}`. Duplicates base images and enforces material==base-image names. Without an explicit base node, traces the active Principled Base Color; complex graphs require a node name. Flat-color materials have no image to rename and are reported. `ascii_only` defaults true; set false for standalone match-only mode, which preserves existing names. `tidy_toon` defaults true; set false for match-only mode. Unique MMD toon images become `<name>_toon`; shared helpers stay shared. |

Material names and PNG filenames must not collide even on case-insensitive filesystems.
Unknown plan/operation fields are errors. No operation chooses a different model or an
unrelated image when a reference is missing.

## Verification, images and export

`verify` checks bone geometry, weighted orphan groups (excluding MMD bookkeeping groups),
invalid vertices/weights, missing external images and optional required bones. Unweighted
vertices and missing UV layers are warnings to examine. It does not prove anatomical
correctness or good deformation. Pose tests need a rig with constraints cleared and no
active animation action. They rotate one named bone, require actual evaluated-mesh motion,
and verify restoration. Look at the generated images for deformation quality; a moving
vertex alone is not proof that every vertex has the right weight.

`render` uses temporary orthographic cameras, a world background and Cycles CPU, in an
unsaved process. Views are front (-Y), side (+X), back (+Y), top (+Z), in Blender world
coordinates. It writes rest and optional posed images and never uses `view3d.*`,
`render.opengl`, or screenshot APIs. If the source has an unusual orientation or complex
world shader, adjust a custom background inspection script rather than rotating the
source rig blindly. Reports never mark visual quality as verified automatically.

`export` saves a new `converted.blend`, optionally exports `tex/*.png`, then outputs
`converted.fbx` with only the selected rig/model, no added leaf bones, no animation bake,
and `use_mesh_modifiers=False` to retain shape keys. **Other modifiers are not baked**:
if the model needs evaluated modifiers, inspect and apply only appropriate ones to a
copy first; do not silently lose shape keys by enabling generic modifier baking.

The `--textures` path saves PNG via `image.save()` (no render view transform), strips
recognized existing extensions, rejects filename collisions/UDIM/sequences/linked-library
images, sets `//tex/...`, saves and reopens the blend to check references. It exports image
nodes used by the model's materials, excluding unrelated scenes/orphan images/render buffers.
The output blend and tex directory live together. The source blend and source images stay
unchanged. Without `--textures`, existing image references are remapped to the new blend;
they are not copied and the result may depend on original texture locations.

Export reloads the blend to check mesh/shape geometry, then reloads FBX in an empty scene
to check bone names/count, model meshes, polygon counts, UV layer counts, shape names and
used material names. It matches world-space vertex positions and bone weights within
reported tolerances while allowing FBX splits at UV/normal boundaries. This is not full
per-corner UV/normal or numeric shape-delta equivalence, nor
MotionBuilder HIK/appearance verification; `motionbuilder_verified` stays false. Follow
any applicable local post-export instructions after FBX **and** tex validation.

## When GUI/MCP is useful

Use it for an unsaved active scene that the user wants to inspect/edit interactively,
manual mesh modeling/weight painting, or visual adjustments that need interaction. A
saved model, pose renders or ordinary bone/weight/material operations do not require a
GUI. Existing per-step snippets illustrate the algorithms; their VIEW_3D overrides apply
only to the GUI/MCP path and should not be copied into background execution.

If the launcher exits before writing a Blender report, read `blender.log` and distinguish
process-start restrictions from model errors. Do not interpret a Metal/GPU startup failure
as a need to open a GUI, and do not repeatedly retry a failed mutation on the same state.

## Validation

Run `python3 -m unittest discover -s tests -p 'test_*.py' -v` with Blender available.
The tests generate their own rig, meshes, images and shape keys in a temporary directory;
no private models or licenses are needed. The synthetic pipeline is tested on Blender
5.1.1; other installed versions and real-model conversions need their own verification.

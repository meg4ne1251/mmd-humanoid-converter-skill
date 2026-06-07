# Step 5 — Rename bones to the Humanoid convention

Apply the names from `references/bone-naming.md`. The key convenience: **renaming a bone automatically renames the matching vertex group**, so weights follow the rename — no manual vertex-group editing needed.

## Do it in Object Mode on `armature.bones`

Renaming works on the data bones (`armature.bones`); you do **not** need Edit Mode for this, and Object Mode is where the vertex-group auto-follow happens cleanly.

```python
import bpy

arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

# Build this map explicitly from the REAL bone names you read in inspection.
# Do not hard-code blindly — confirm each source name exists.
rename_map = {
    "下半身":   "Hips",
    "上半身":   "Spine1",
    "上半身2":  "Spine2",
    "首":       "Neck",
    "頭":       "Head",
    "左肩":     "Shoulder_L",  "右肩":   "Shoulder_R",
    "左腕":     "UpArm_L",     "右腕":   "UpArm_R",
    "左ひじ":   "ForeArm_L",   "右ひじ": "ForeArm_R",
    "左手首":   "Hand_L",      "右手首": "Hand_R",
    "左足":     "UpLeg_L",     "右足":   "UpLeg_R",
    "左ひざ":   "Leg_L",       "右ひざ": "Leg_R",
    "左足首":   "Foot_L",      "右足首": "Foot_R",
    "左つま先": "Toe_L",       "右つま先": "Toe_R",
    # fingers, costume, hair ... fill from bone-naming.md
}

renamed, missing = 0, []
for old, new in rename_map.items():
    b = arm.data.bones.get(old)
    if b is None:
        missing.append(old); continue
    if old != new:
        b.name = new
        renamed += 1

print("renamed:", renamed, " missing (check names!):", missing)
```

## Pitfalls

- **Rename ordering / collisions.** If a target name already exists, Blender appends `.001`. Watch for clashes (e.g. renaming two bones into the same name). Rename leaf-to-root or use unique intermediate names if needed.
- **Rare weight drop.** In a small number of cases a rename can detach a weight (observed ~twice in years of manual work). It's rare but real — **pose-test after renaming** (`references/06-verify-rig.md`) and, if a region stops following, re-assign the vertex group name to match the bone.
- **Confirm sources exist.** The `missing` list above is your safety net: if expected MMD names aren't found, your mapping is wrong for this model — re-inspect rather than push on.

## Spine numbering

Keep spine numbers contiguous. If the model has 上半身 + 上半身2 only, that's `Spine1`, `Spine2` — don't jump to `Spine3`. If it has three, use `Spine1/2/3`.

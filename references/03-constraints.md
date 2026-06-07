# Step 2 — Clear bone constraints

**Goal:** remove all pose-bone constraints so the later restructuring (rotating the waist, re-parenting, deleting bones) isn't fought by IK/copy-rotation/limit constraints.

In MMD rigs the constraint-driven bones show up **colored** in Pose Mode (and may be hidden — `Alt+H` reveals them). Each carries one or more constraints visible in the Bone Constraint Properties tab. The original workflow deletes them one bone at a time via the ❌ button; in bpy we can clear them all at once.

## Clear every pose-bone constraint

Pose-bone constraints are editable directly from Object Mode — **no need to enter Pose Mode** (which avoids the MCP `mode_set` context issue entirely):

```python
import bpy

arm = next((o for o in bpy.data.objects if o.type == 'ARMATURE'), None)

cleared = 0
for pb in arm.pose.bones:
    n = len(pb.constraints)
    if n:
        for c in list(pb.constraints):
            pb.constraints.remove(c)
        cleared += n

remaining = sum(len(pb.constraints) for pb in arm.pose.bones)
print("constraints removed:", cleared, " remaining:", remaining)
```

(Real example: a typical MMD model had 47 constraints on 43 bones — TRANSFORM on twist bones, COPY_TRANSFORMS on `_shadow_*`, IK on feet. All clear cleanly this way.)

## Notes

- Constraints live on **pose bones** (`armature.pose.bones[*].constraints`), not edit bones or data bones. You must be on the armature object; Pose Mode is the natural place but `pose.bones` is accessible from Object Mode too.
- This is comparatively safe (it changes behavior, not geometry/weights), but still report how many were removed so the user can sanity-check.
- After clearing, the colored bones should appear normal. If the model visibly deforms when you clear constraints, that's expected — those constraints were posing the rig; the rest bind pose is what matters for conversion.

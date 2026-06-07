# Step 3 — Restructure the bones

This is the core of the conversion and the part most likely to need human judgment. The target is the hierarchy in SKILL.md. Work in **Edit Mode** for geometry/parenting (`edit_bones`); switch to **Pose Mode** to test deformation afterward.

> **MCP context:** entering Edit Mode needs a VIEW_3D context override, and `mode_set(mode='POSE')` needs the armature to be the active object. See the "Running operators through the Blender MCP" note in SKILL.md. All Edit-Mode snippets below assume you wrapped `mode_set` with `temp_override(**view3d_ctx())`.

> **Weight safety dominates this whole step.** Most bones you delete here (twist, IK, helpers) carry part of the limb's weight. **Always check weight and transfer it first** (see `references/05-weight-transfer.md`) before deleting. Deleting a weighted bone tears the mesh.

## Order of operations

1. 3a — Fix waist & spine
2. 3b — Remove arm twist / upward helper bones (transfer weights first)
3. 3c — Remove IK/FK control bones (check weights first)
4. 3d — Remove other stray bones (check weights first)
5. Pose-test (`references/06-verify-rig.md`)

---

## 3a — Fix the waist & spine

**Problem:** the MMD waist (センター / グループ / センター先 and a 下半身/上半身 split) points **downward**, the opposite of the VLL Hips which roots the body and grows upward.

**Plan (confirm with user before editing):**
- Identify which bone should become **Hips** (usually the 下半身 root / 腰, the pelvis the legs hang from).
- Re-point its tail upward toward the first spine bone, and rebuild parenting so legs and spine are children of Hips.
- Delete the MMD-only helpers: センター (center), グループ (group), センター先 (center-tip), and any other non-deforming control bones in the torso root.

Because every model names these differently, **read the bone tree from `01-inspect.md` and map them explicitly** — don't pattern-match blindly. Present the mapping (`腰→Hips`, `上半身→Spine1`, `上半身2→Spine2`, …, delete `センター/グループ/センター先`) to the user.

```python
import bpy
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones

# --- example: re-root the pelvis as Hips and re-parent spine/legs ---
hips   = eb["腰"]            # the bone you mapped to Hips
spine1 = eb["上半身"]        # first spine bone
upleg_l = eb["左足"]; upleg_r = eb["右足"]

# parent spine + legs under hips, growing upward
spine1.parent  = hips
upleg_l.parent = hips
upleg_r.parent = hips

# point hips tail at spine1 so it reads upward (keep head fixed)
orig = hips.head.copy()
hips.tail = spine1.head.copy()
hips.head = orig

# --- delete MMD-only torso control bones AFTER confirming they hold no weight ---
for name in ["センター", "グループ", "センター先"]:
    b = eb.get(name)
    if b:
        eb.remove(b)

bpy.ops.object.mode_set(mode='OBJECT')
```

### Root bone at the model origin

After re-rooting, the topmost bone is usually the pelvis/Hips (e.g. `下半身`), whose head sits at hip height (`head.z ≈ 0.9`), not at the model origin. The VLL hierarchy expects a `Reference`/`Parent` above Hips, and it is desirable for **the root bone's head to sit at (or near) the model origin**.

**Do not move a weighted bone's head to the origin** — the pelvis carries thousands of weighted verts, and shifting its rest-pose head distorts that deformation. Instead, **add a new, weight-free root bone whose head is at the origin** and parent the existing root (Hips) under it. This satisfies the requirement with **zero weight movement**:

```python
import bpy
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
ctx = view3d_ctx()
with bpy.context.temp_override(**ctx):
    bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones

old_root = next(b for b in eb if b.parent is None)   # e.g. 下半身 / Hips
root = eb.new("Parent")            # weight-free; rename to your convention later
root.head = (0.0, 0.0, 0.0)        # model origin
root.tail = old_root.head.copy()   # point up at Hips so it reads cleanly
old_root.parent = root

with bpy.context.temp_override(**ctx):
    bpy.ops.object.mode_set(mode='OBJECT')
```

If creating the origin root would instead require complex weight surgery (it shouldn't, since the new bone holds no weight), skip it — the user has said not to force it.

> Note on `use_connect`: connecting a child to its parent forces the child's head onto the parent's tail. To keep heads in place, move the parent's tail to the child's head **first**, then set `use_connect = True` — and only do this when the parent has exactly one child. See `references/09-bone-display.md` for the safe pattern; for pure restructuring you usually don't need `use_connect` at all.

---

## 3b — Remove arm twist / upward helper bones

**Problem:** MMD arms have extra bones — twist/捩り bones and "upward-growing" helper bones that split the arm into ~4 segments. Crucially, **the arm's weight is divided across these bones**, so the real 腕/ひじ bone does *not* hold all the weight.

**Procedure:**
1. From the vertex-group list, identify which helper/twist bones carry weight.
2. **Transfer their weights onto the real arm bone** (e.g. `腕捩` → `腕`, `手捩` → `ひじ`) using ADD mode, deleting the source group as you go. Mirror for L/R. → `references/05-weight-transfer.md`.
3. Verify the real arm bone now holds the merged weight.
4. Delete the now-empty helper/twist bones in Edit Mode.

```python
import bpy
arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
eb = arm.data.edit_bones

# delete only AFTER weights are transferred and verified empty
for name in ["左腕捩", "右腕捩", "左手捩", "右手捩", "<upward-helper-names>"]:
    b = eb.get(name)
    if b:
        eb.remove(b)

bpy.ops.object.mode_set(mode='OBJECT')
```

---

## 3c — Remove IK/FK control bones

**Problem:** ankles/toes (and often wrists) have IK/FK control bones — usually parented as a **separate group** off the upper/lower body chain rather than inside the limb. VLL doesn't use them.

**Procedure:**
- Identify the IK group (足ＩＫ, つま先ＩＫ, and any 手ＩＫ if present), confirm via the bone tree that they sit apart from the limb chain.
- **Check for weights.** Often they have none → delete directly. If they *do* carry weight, transfer onto Foot/Toe/Hand (or repaint manually), then delete.
- **Do not delete the actual Foot bone** — only the IK controllers around it. (The original author's screenshot accidentally selected `foot`; that one stays.)
- Delete both L and R.

Pose-test the legs/feet afterward — IK removal is a common place for surprises.

---

## 3d — Other stray bones

Anything left that is **not** in the target hierarchy is a deletion candidate — *unless* it's a physics/jiggle bone you want to keep (skirt スカート, ribbon リボン, shoelace 靴紐, hair 髪). Rule of thumb from the original workflow: *not in the VLL hierarchy AND not a jiggle/cloth bone → delete, after confirming no weight.* When unsure, ask.

---

## After every deletion batch

Update the depsgraph and pose-test (`references/06-verify-rig.md`). If something detaches, undo and investigate the weights before retrying.

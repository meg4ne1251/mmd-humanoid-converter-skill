# VLL Humanoid bone naming

The target naming convention. Read this before any renaming (Step 5). `_L` / `_R` suffixes pair left and right. Keep spine numbering **contiguous** (Spine1, Spine2, Spine3 — never skip a number).

## Target hierarchy (recap)

```
Reference → Parent → Hips
  Hips ├─ UpLeg_L → Leg_L → Foot_L → Toe_L
       ├─ UpLeg_R → Leg_R → Foot_R → Toe_R
       └─ Spine1 → Spine2 → Spine3
              ├─ Shoulder_L → UpArm_L → ForeArm_L → Hand_L (→ fingers)
              ├─ Shoulder_R → UpArm_R → ForeArm_R → Hand_R (→ fingers)
              └─ Neck → Head
```

## Torso / neck / head

| Part | Name |
|---|---|
| Pelvis / waist | `Hips` |
| Spine (bottom→top) | `Spine1`, `Spine2`, `Spine3`, … (contiguous) |
| Neck | `Neck` |
| Head | `Head` |

## Legs

| Part | Left | Right |
|---|---|---|
| Thigh | `UpLeg_L` | `UpLeg_R` |
| Lower leg / knee | `Leg_L` | `Leg_R` |
| Ankle / foot | `Foot_L` | `Foot_R` |
| Toe | `Toe_L` | `Toe_R` |

## Arms

| Part | Left | Right |
|---|---|---|
| Shoulder / clavicle | `Shoulder_L` | `Shoulder_R` |
| Upper arm | `UpArm_L` | `UpArm_R` |
| Forearm | `ForeArm_L` | `ForeArm_R` |
| Wrist / hand | `Hand_L` | `Hand_R` |

## Fingers (children of Hand_L / Hand_R)

Pattern: `Hand{Finger}_{LR}.{n}` where `n` counts from the knuckle outward (1, 2, 3).

| Finger | Example (left) |
|---|---|
| Thumb | `HandThumb_L.1`, `.2`, `.3` |
| Index | `HandIndex_L.1`, `.2`, `.3` |
| Middle | `HandMiddle_L.1`, `.2`, `.3` |
| Ring | `HandRing_L.1`, `.2`, `.3` |
| Pinky | `HandPinky_L.1`, `.2`, `.3` |

## Costume / hair (free naming, kept off the Humanoid chain)

These aren't part of the Humanoid standard — keep them, preserve L/R, and use a readable pattern:

```
{Part}_{index}_{LR}.{chain}
e.g. Skirt_1_L.1, Blazer_2_R.2, Hair_Back_1_L
```

## Common MMD → VLL name mapping (verify per model — names vary!)

This is a *starting* guide, not a hard-coded truth. Always read the real bone names from the scene first.

| MMD (typical) | VLL |
|---|---|
| 全ての親 | `Parent` (or root → `Reference`/`Parent`) |
| 下半身 / 腰 | `Hips` |
| 上半身 | `Spine1` |
| 上半身2 | `Spine2` |
| 上半身3 (if present) | `Spine3` |
| 首 | `Neck` |
| 頭 | `Head` |
| 左肩 / 右肩 | `Shoulder_L` / `Shoulder_R` |
| 左腕 / 右腕 | `UpArm_L` / `UpArm_R` |
| 左ひじ / 右ひじ | `ForeArm_L` / `ForeArm_R` |
| 左手首 / 右手首 | `Hand_L` / `Hand_R` |
| 左足 / 右足 | `UpLeg_L` / `UpLeg_R` |
| 左ひざ / 右ひざ | `Leg_L` / `Leg_R` |
| 左足首 / 右足首 | `Foot_L` / `Foot_R` |
| 左つま先 / 右つま先 | `Toe_L` / `Toe_R` |
| 左親指０..２ etc. | `HandThumb_L.1..3` etc. |

Fingers in MMD are often numbered `０/１/２` (knuckle→tip); map them to `.1/.2/.3`.

# Step 9 — Rename face shape keys

MMD face shape keys for the vowels use Japanese kana: `あ い う え お`. Rename them to the Latin convention used downstream: **`a i u e p`**.

Note the last one is **`p`**, not `o` — that's the intended mapping (matches the downstream lip-sync naming). Don't "correct" it to `o`.

```python
import bpy

KANA_MAP = {"あ": "a", "い": "i", "う": "u", "え": "e", "お": "p"}

for o in bpy.data.objects:
    if o.type != 'MESH' or not o.data.shape_keys:
        continue
    for kb in o.data.shape_keys.key_blocks:
        if kb.name in KANA_MAP:
            new = KANA_MAP[kb.name]
            print(f"  [{o.name}] {kb.name} -> {new}")
            kb.name = new
```

## Notes

- Shape keys live on `mesh.data.shape_keys.key_blocks`. The `Basis` key is the rest shape — leave it alone.
- Run this on whichever object holds the face shape keys (often the face/head mesh after separation, or the body mesh before).
- If a target name already exists, Blender will append a suffix — check the output for unexpected collisions.
- Skipping this step causes headaches later in the pipeline, so don't omit it even though it's quick.

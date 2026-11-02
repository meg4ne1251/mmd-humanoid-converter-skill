# Step 13 — Export textures to `tex/`

Use the CLI `export --textures` path from [CLI workflow](cli-workflow.md). It outputs
a new `converted.blend`, `converted.fbx`, and `tex/` in the same directory. The original
blend, FBX and source images are preserved. Texture export is optional unless requested
or required by applicable local postprocessing instructions.

```sh
python3 scripts/mmd_cli.py export "converted-input.blend" --textures --output-dir "new-export-directory"
```

For model-conversion conversations, ask 「追加でテクスチャの出力を行いますか？」 only
when the user's preference is still unknown. Do not repeat it after consent/export, or
when only editing documentation/scripts. When export is already authorized, perform it
and proceed to applicable local postprocessing without another confirmation.

## Output rules

- Export images referenced by the chosen model's material image nodes, including auxiliary
  images; exclude unrelated models, orphan images and render buffers.
- Write PNG using `image.file_format = 'PNG'` and `image.save()`. Avoid `save_render()`
  for texture assets because scene render color management can alter texture colors.
- Use `<Blender image name>.png`, removing recognized pre-existing image extensions to
  prevent `.png.png` / `.bmp.png`. Step 11 base names yield `Face.png`, `Clothes.png`, etc.
- Reject filename collisions (including case-insensitive collisions), missing pixels,
  unsupported image sequences/UDIM and linked-library images rather than silently skipping.
- Establish the new blend directory **before** assigning `//tex/...`, then save again.
  Assigning those paths while the source blend is still current and saving elsewhere can
  remap them back toward the wrong directory.
- Check PNG files and reopen the saved blend to verify relative paths. Check exit code,
  `report.json.ok`, warnings and `input_unchanged`; partial files are not a successful export.

When using a custom background bpy script or GUI/MCP, follow the same order and checks.
If no blend exists yet, save an output copy in the chosen new directory first. Never
overwrite source images simply because their current filepath happens to point there.

Once FBX and textures are verified, follow the applicable local characterizer procedure
with these exact outputs. SDK roundtrip checks and MotionBuilder's actual rendering/HIK
are separate verification stages.

# Step 13 — Export textures to `tex/` folder (Optional)

**Goal:** Export all textures used in the Blender model into a `tex` directory located in the same directory as the `.blend` file, saved in **PNG** format with filenames matching the Blender texture names (`<texture_name>.png`), and update Blender's internal image filepaths to relative `//tex/<texture_name>.png`.

> **Conversation Rule (Important):**
> 全ての作業が終わった後に、会話が終わる時のコメントで必ずユーザーに **「追加でテクスチャの出力を行いますか？」** と確認すること。
> クライアントが出力を希望した場合は、本リファレンスに記載されている手順・条件でテクスチャを出力する。

---

## The rules

1. **Output location:** A `tex/` folder created directly inside the directory where the current `.blend` file is saved (`os.path.dirname(bpy.data.filepath)`).
   - If the `.blend` file has never been saved (`bpy.data.filepath` is empty), ask the user to save the `.blend` file first.
2. **File format:** PNG format for all exported textures (`img.save_render` with `.png`).
3. **Naming convention:** `[Blender内でのテクスチャの名前].png`
   - To prevent double extensions (e.g. `t4.png.png` or `toon.bmp.png`), strip any existing extension before appending `.png`:
     `fname = f"{os.path.splitext(img.name)[0]}.png"`
   - Base color textures tidied in Step 11 (e.g. `Face`, `Eyes`, `Clothes_01`) naturally export as `Face.png`, `Eyes.png`, `Clothes_01.png`.
4. **Update Blender filepaths:** Update each image datablock's `filepath` to relative `//tex/<filename>` and set `file_format = 'PNG'`. This makes the `.blend` file cleanly self-contained alongside its `tex/` folder and ensures FBX export references the clean textures.
5. **Target images:** All images with `users > 0`, excluding internal render buffers (`Render Result`, `Viewer Node`).

---

## Python implementation (MCP safe)

```python
import bpy
import os

filepath = bpy.data.filepath
if not filepath:
    raise RuntimeError("Blend file must be saved before exporting textures.")

blend_dir = os.path.dirname(filepath)
tex_dir = os.path.join(blend_dir, "tex")
os.makedirs(tex_dir, exist_ok=True)

# Select all images used in the file
images_to_save = [
    img for img in bpy.data.images
    if img.users > 0 and img.name not in ('Render Result', 'Viewer Node')
]

results = []
for img in sorted(images_to_save, key=lambda x: x.name):
    # Rule: blender内でのテクスチャの名前.png (prevent double extensions)
    base_name = os.path.splitext(img.name)[0]
    fname = f"{base_name}.png"
    out_path = os.path.join(tex_dir, fname)

    try:
        # Save as PNG
        img.save_render(filepath=out_path)
        size = os.path.getsize(out_path)

        # Update image filepath in Blender to relative path //tex/...
        img.filepath = f"//tex/{fname}"
        img.file_format = 'PNG'

        results.append({
            "name": img.name,
            "filename": fname,
            "size": size,
            "status": "OK"
        })
    except Exception as e:
        results.append({
            "name": img.name,
            "filename": fname,
            "error": str(e),
            "status": "ERROR"
        })

print(f"Exported {len([r for r in results if r['status'] == 'OK'])}/{len(images_to_save)} textures to {tex_dir}")
for r in results:
    if r['status'] == 'OK':
        print(f"  [OK] {r['name']:15} -> {r['filename']:20} ({r['size']:,} bytes)")
    else:
        print(f"  [ERROR] {r['name']}: {r.get('error')}")
```

---

## Verification

After export:
1. Verify all files exist in `tex/` and have size > 0.
2. Confirm all image datablocks in Blender resolve their relative paths without missing files:
   ```python
   for img in bpy.data.images:
       if img.users > 0 and img.name not in ('Render Result', 'Viewer Node'):
           assert os.path.exists(bpy.path.abspath(img.filepath)), f"Missing: {img.name}"
   print("All texture paths verified successfully.")
   ```

"""Integration tests using Blender and generated data, never private MMD assets.

Run: python3 -m unittest discover -s tests -p 'test_*.py' -v
BLENDER_BIN can select an installed Blender. Artifacts live in a temporary folder.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from mmd_cli import find_blender


class BlenderCliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.blender = find_blender()
        except ValueError as error:
            raise unittest.SkipTest(str(error))
        cls.tmp = tempfile.TemporaryDirectory(prefix="mmd-cli-tests-")
        cls.directory = Path(cls.tmp.name)
        process = subprocess.run([cls.blender, "--background", "--disable-autoexec", "--python-exit-code", "1",
                                  "--python", str(ROOT / "tests/blender_fixture.py"), "--", str(cls.directory)],
                                 capture_output=True, text=True)
        if process.returncode:
            raise RuntimeError(process.stdout + process.stderr)
        cls.source = cls.directory / "source.blend"
        cls.original_hash = hashlib.sha256(cls.source.read_bytes()).hexdigest()
        cls.image_hash = hashlib.sha256((cls.directory / "source.png").read_bytes()).hexdigest()
        cls.plan = {
            "version": 1, "input_sha256": cls.original_hash, "armature": "Rig", "meshes": ["Body"],
            "operations": [
                {"type": "delete_objects", "names": ["ImportRoot"]},
                {"type": "clear_constraints"},
                {"type": "transfer_weights", "pairs": [{"source": "Helper", "target": "Root"}]},
                {"type": "edit_bones", "add": [{"name": "Parent", "head": [0, 0, 0], "tail": [0, 0, 1]}],
                 "update": {"Root": {"parent": "Parent"}}, "delete": ["Helper", "Tip", "_shadow"]},
                {"type": "rename_bones", "mapping": {"Root": "Hips"}},
                {"type": "connect_bones"},
                {"type": "principled_materials", "materials": {
                    "OldFace": {"base_color_node": "base"}, "OldClothes": {"base_color_node": "base"}}},
                {"type": "separate_materials", "object": "Body", "parts": {
                    "Face": ["OldFace"], "Clothes": ["OldClothes"]}},
                {"type": "rename_shape_keys"},
                {"type": "clear_shape_keys", "objects": ["Clothes"]},
                {"type": "rename_materials", "mapping": {
                    "OldFace": {"name": "Face"}, "OldClothes": {"name": "Clothes"}}},
            ],
            "required_bones": ["Parent", "Hips"], "pose_tests": ["Hips:Y:30"],
        }

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def launch(self, command, name, source=None, extra=(), success=True):
        output = self.directory / name
        args = [sys.executable, str(ROOT / "scripts/mmd_cli.py"), "--blender", self.blender,
                command, str(source or self.source), "--output-dir", str(output), *extra]
        process = subprocess.run(args, capture_output=True, text=True)
        if success and process.returncode:
            log = (output / "blender.log").read_text() if (output / "blender.log").exists() else ""
            self.fail(process.stdout + process.stderr + log)
        if not success:
            self.assertNotEqual(process.returncode, 0)
        report = json.loads((output / "report.json").read_text()) if (output / "report.json").exists() else None
        return output, report

    def write_plan(self, name, plan):
        path = self.directory / (name + ".json")
        path.write_text(json.dumps(plan, ensure_ascii=False))
        return str(path)

    def test_pipeline_and_retention(self):
        inspected, info = self.launch("inspect", "inspect")
        self.assertTrue(info["background"])
        self.assertEqual(info["input_sha256"], self.original_hash)
        self.assertEqual(len(info["scene"]["armatures"]), 1)
        plan = self.write_plan("full-plan", self.plan)
        dry, preview = self.launch("apply", "dry-run", extra=["--plan", plan, "--dry-run"])
        self.assertTrue(preview["ok"])
        self.assertFalse((dry / "converted.blend").exists())
        self.assertFalse((dry / "checkpoints").exists())
        applied, result = self.launch("apply", "applied", extra=["--plan", plan])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["operations"]), 11)
        self.assertEqual(len(list((applied / "checkpoints").glob("*.blend"))), 12)
        self.assertLess(result["poses"][0]["restore_error"], 1e-6)
        objects = {o["name"]: o for o in result["scene"]["objects"]}
        self.assertAlmostEqual(objects["Rig"]["matrix_world"][0][3], 0.25)
        self.assertEqual(set(objects["Face"]["shape_keys"]), {"Basis", "a", "i", "u", "e", "o"})
        self.assertFalse(objects["Clothes"]["shape_keys"])
        exported, output = self.launch("export", "exported", applied / "converted.blend", ["--textures", "--pose", "Hips:Y:20"])
        self.assertTrue(output["fbx_roundtrip"]["ok"])
        self.assertTrue(output["blend_roundtrip"]["ok"])
        self.assertEqual(len(output["skin_roundtrip"]), 2)
        self.assertEqual({p.name for p in (exported / "tex").glob("*.png")}, {"Face.png", "Clothes.png"})
        self.assertFalse(output["motionbuilder_verified"])
        self.launch("verify", "verified", exported / "converted.blend", ["--pose", "Hips:X:20"])
        rendered, images = self.launch("render", "rendered", exported / "converted.blend",
                                       ["--resolution", "64", "--views", "front", "side", "--pose", "Hips:Y:20"])
        self.assertEqual(len(images["images"]), 4)
        self.assertTrue(all(Path(p).stat().st_size for p in images["images"]))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)
        self.assertEqual(hashlib.sha256((self.directory / "source.png").read_bytes()).hexdigest(), self.image_hash)
        self.launch("apply", "wrong-input", applied / "converted.blend", ["--plan", plan], success=False)
        self.launch("inspect", "inspect", success=False)  # output protection

    def test_reject_weighted_deletion_and_keep_source(self):
        plan = {**self.plan, "operations": [{"type": "edit_bones", "delete": ["Helper"]}]}
        path = self.write_plan("unsafe-delete", plan)
        output, report = self.launch("apply", "unsafe-delete", extra=["--plan", path], success=False)
        self.assertIn("still carries weight", report["error"])
        self.assertFalse((output / "converted.blend").exists())
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), self.original_hash)

    def test_reject_duplicate_add(self):
        pair = {"source": "Helper", "target": "Root"}
        plan = {**self.plan, "operations": [{"type": "transfer_weights", "pairs": [pair, pair]}]}
        path = self.write_plan("duplicate-add", plan)
        output, report = self.launch("apply", "duplicate-add", extra=["--plan", path], success=False)
        self.assertIn("Duplicate", report["error"])
        self.assertFalse((output / "converted.blend").exists())

    def test_reject_ambiguous_material_and_parent_cycle(self):
        cases = [
            ("bad-material", {"type": "principled_materials", "materials": {"OldFace": {"base_color_node": "missing"}}}, "Invalid base"),
            ("bad-parent", {"type": "edit_bones", "update": {"Root": {"parent": "Helper"}}}, "Parent cycle"),
        ]
        for name, op, message in cases:
            with self.subTest(name=name):
                path = self.write_plan(name, {**self.plan, "operations": [op]})
                output, report = self.launch("apply", name, extra=["--plan", path], success=False)
                self.assertIn(message, report["error"])
                self.assertFalse((output / "converted.blend").exists())

    def test_material_only_unrigged_match_names(self):
        source = self.directory / "unrigged.blend"
        plan = {"version": 1, "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "armature": None, "meshes": ["Body"], "operations": [
                    {"type": "rename_materials", "ascii_only": False, "tidy_toon": False,
                     "mapping": {"OldFace": {"name": "顔", "base_color_node": "base"},
                                 "OldClothes": {"name": "服", "base_color_node": "base"}}}]}
        path = self.write_plan("material-only", plan)
        output, report = self.launch("apply", "material-only", source, ["--plan", path])
        self.assertFalse(report["scene"]["armatures"])
        materials = {m["name"]: m for m in report["scene"]["materials"]}
        for name in ["顔", "服"]:
            self.assertEqual(next(n["image"] for n in materials[name]["nodes"] if n["name"] == "base"), name)
        self.assertTrue((output / "converted.blend").exists())

    def test_pmx_import_without_dialog(self):
        source = self.directory / "synthetic.pmx"
        if not source.exists():
            self.skipTest("MMD Tools not installed")
        options = self.directory / "import-options.json"
        options.write_text(json.dumps({"scale": 0.08, "types": ["MESH", "ARMATURE"]}))
        # Enum-flag properties need a Python set, converted by the worker.
        output, report = self.launch("inspect", "pmx-inspect", source, ["--import-options", str(options)])
        self.assertTrue(report["ok"])
        self.assertEqual(len(report["scene"]["armatures"]), 1)
        meshes = [o for o in report["scene"]["objects"] if o["type"] == "MESH"]
        self.assertEqual(len(meshes), 1)
        self.assertEqual(meshes[0]["vertices"], 3)


if __name__ == "__main__":
    unittest.main()

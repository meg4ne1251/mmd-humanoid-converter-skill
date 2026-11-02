#!/usr/bin/env python3
"""Launch the MMD workflow in a separate, background Blender process."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_blender(explicit=None):
    requested = explicit or os.environ.get("BLENDER_BIN")
    if requested:
        found = shutil.which(requested) or Path(requested).expanduser()
        if Path(found).is_file() and os.access(found, os.X_OK):
            return str(Path(found).resolve())
        raise ValueError(f"Blender executable not found: {requested}")
    found = shutil.which("blender")
    if found:
        return found
    mac = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if sys.platform == "darwin" and mac.is_file():
        return str(mac)
    raise ValueError("Blender not found. Set BLENDER_BIN or pass --blender /path/to/blender.")


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--blender", help="Executable path (also accepts BLENDER_BIN)")
    sub = root.add_subparsers(dest="command", required=True)
    for command, description in [
        ("inspect", "Inspect a saved .blend, .pmx, .pmd or .fbx; write JSON"),
        ("apply", "Apply an explicit JSON plan to a copy, with checkpoints"),
        ("verify", "Check rig, weights, images and optional pose tests"),
        ("export", "Save a copy, export FBX, optionally PNGs; reload and verify"),
        ("render", "Generate inspection images with temporary cameras"),
    ]:
        item = sub.add_parser(command, help=description)
        item.add_argument("input", type=Path)
        item.add_argument("--output-dir", type=Path, required=True,
                          help="New directory; existing paths are never overwritten")
        item.add_argument("--mmd-addon", help="Explicit MMD Tools module if automatic discovery is ambiguous")
        item.add_argument("--import-options", type=Path, help="JSON MMD Tools EXEC options (e.g. scale, rename_bones)")
        if command == "apply":
            item.add_argument("--plan", type=Path, required=True)
            item.add_argument("--dry-run", action="store_true",
                              help="Simulate in memory; only write the report and log")
        elif command != "inspect":
            item.add_argument("--armature")
            item.add_argument("--meshes", nargs="+", help="All meshes bound to the chosen armature")
            item.add_argument("--require-humanoid", action="store_true")
            item.add_argument("--pose", action="append", default=[], metavar="BONE:AXIS:DEGREES",
                              help="Repeatable numerical pose check; render also writes posed images")
        if command == "export":
            item.add_argument("--textures", action="store_true", help="Export used images as tex/*.png")
        if command == "render":
            item.add_argument("--views", nargs="+", choices=["front", "side", "back", "top"],
                              default=["front", "side"])
            item.add_argument("--resolution", type=int, default=512)
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    output = args.output_dir.expanduser().resolve()
    source = args.input.expanduser().resolve()
    try:
        if not source.is_file() or source.suffix.lower() not in {".blend", ".pmx", ".pmd", ".fbx"}:
            raise ValueError("Input must be an existing .blend, .pmx, .pmd or .fbx file")
        if output.exists():
            raise ValueError(f"Output directory already exists: {output}")
        binary = find_blender(args.blender)
        source_hash = sha256(source)
        job = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
        job.update(input=str(source), output_dir=str(output), input_sha256=source_hash)
        if args.import_options:
            job["import_options"] = json.loads(args.import_options.expanduser().read_text(encoding="utf-8"))
            if not isinstance(job["import_options"], dict):
                raise ValueError("Import options must be a JSON object")
        if args.command == "apply":
            plan_path = args.plan.expanduser().resolve()
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            if plan.get("input_sha256") != source_hash:
                raise ValueError("Plan input_sha256 does not match this input. Inspect it and rebuild the plan.")
            job["plan"] = plan
            job["plan_path"] = str(plan_path)
        if args.command == "render" and not 64 <= args.resolution <= 4096:
            raise ValueError("Resolution must be between 64 and 4096")
        output.mkdir(parents=True, exist_ok=False)
        request = output / "request.json"
        request.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        worker = Path(__file__).with_name("blender_worker.py").resolve()
        command = [binary, "--background", "--disable-autoexec", "--python-exit-code", "1",
                   "--python", str(worker), "--", str(request)]
        print(f"Blender {args.command}: {source}\nLog: {output / 'blender.log'}", flush=True)
        with (output / "blender.log").open("w", encoding="utf-8") as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=False)
        report_path = output / "report.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {
            "ok": False, "error": "Blender exited without a report; inspect blender.log"
        }
        report["process_returncode"] = process.returncode
        report["input_unchanged"] = source.is_file() and sha256(source) == source_hash
        report["ok"] = bool(report.get("ok") and process.returncode == 0 and report["input_unchanged"])
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"ok": report["ok"], "report": str(report_path),
                          "error": report.get("error")}, ensure_ascii=False))
        return 0 if report["ok"] else 1
    except (OSError, ValueError, KeyError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

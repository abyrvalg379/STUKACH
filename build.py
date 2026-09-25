# -*- coding:utf-8 -*-
"""Build the STUKACH distribution zip.

Release checklist built in:
  1. prints every commit since the last release tag - confirm everything you
     meant to ship is actually here (today's lesson: a fix landed minutes
     after the release and missed the zip);
  2. warns when the working tree is dirty;
  3. packs the tracked addon files into ../out/blender/v<version>/STUKACH.zip.

Usage:  python build.py
"""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).parent

# Explicit whitelist - the release artifact must be deterministic, never a
# directory glob (doc tooling lives next to the addon sources).
FILES = [
    "__init__.py",
    "blender_manifest.toml",
    "core.py",
    "LICENSE",
    "manager.py",
    "naming.py",
    "preferences.py",
    "properties.py",
    "README.md",
    "README.ru.md",
    "ui.py",
    "update_checker.py",
]


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=HERE).stdout.strip()


def main():
    version = ""
    for line in (HERE / "blender_manifest.toml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("version"):
            version = line.split("=")[1].strip().strip('"')
            break
    if not version:
        sys.exit("cannot read version from blender_manifest.toml")

    tag = git("describe", "--tags", "--abbrev=0")
    print(f"=== commits since {tag} (release checklist) ===")
    log = git("log", f"{tag}..HEAD", "--oneline") if tag else "(no tags)"
    print(log or "(none)")
    print("=== anything above that should NOT ship? abort now ===\n")

    status = git("status", "--porcelain")
    if status:
        print("WARNING - dirty working tree:")
        print(status)
        print()

    files = FILES
    missing = [f for f in files if not (HERE / f).exists()]
    if missing:
        sys.exit(f"missing files: {missing}")

    out_dir = HERE.parent / "out" / "blender" / f"v{version}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / "STUKACH.zip"
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            z.write(HERE / f, f)
    z = zipfile.ZipFile(dst)
    man = z.read("blender_manifest.toml").decode("utf-8", "replace")
    print(f"built {dst} ({os.path.getsize(dst)} bytes, {len(z.namelist())} files)")
    print(f"manifest version present: {version in man}")
    print("reminder: sync the same files to the installed extension dir + reload,")
    print("then: gh release create v" + version + " <zip> --latest")


if __name__ == "__main__":
    main()

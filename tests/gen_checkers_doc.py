# -*- coding: utf-8 -*-
"""Generate docs/CHECKS.md (the checker reference) from the code registries.

Sources (no Blender required):
  * the addon dump written by the smoke test's registry_dump step
    (tests/smoke_blender.py): $STUKACH_REGISTRY_OUT or
    <temp>/stukach_registry_dump.json — 42 checks with severity, category
    and the first docstring line;
  * the vendored stukach_core rule registry (_core/registry.py, RULES) —
    DCC-free rules (RULES + SCENE_RULES) with severity, default params
    and evaluator docstrings.  Needs numpy importable by the host python.

The generated file is committed.  CI regenerates it after the smoke run and
fails on drift, so the reference can never go stale:

    python tests/gen_checkers_doc.py --check

Local flow: run the smoke test, then this script, commit docs/CHECKS.md
together with the registry change.
"""
import argparse
import importlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "CHECKS.md"
DUMP = os.environ.get("STUKACH_REGISTRY_OUT") or os.path.join(
    tempfile.gettempdir(), "stukach_registry_dump.json")

# first sentence: a dot followed by whitespace ('0.01 mm' stays intact)
_FIRST_SENTENCE = re.compile(r"(?<=\.)\s")


def _summary(text: str) -> str:
    """One-line first sentence of a docstring."""
    if not text or not text.strip():
        return ""
    collapsed = " ".join(text.strip().split())
    return _FIRST_SENTENCE.split(collapsed, maxsplit=1)[0]


def _cell(text: str) -> str:
    """One-line, pipe-safe markdown cell."""
    return " ".join(text.split()).replace("|", "\\|") if text else "—"


def load_dump() -> dict:
    with open(DUMP, encoding="utf-8") as fh:
        return json.load(fh)


def load_core_rules() -> dict:
    """RULES + SCENE_RULES (scene-scope batch rules like uv_padding)."""
    sys.path.insert(0, str(REPO))
    try:
        core = importlib.import_module("_core")
        return {**core.RULES, **getattr(core, "SCENE_RULES", {})}
    finally:
        sys.path.pop(0)


def render(dump: dict, rules: dict) -> str:
    lines = [
        "# Checker reference",
        "",
        "Generated from the code registries — do not edit by hand.",
        "Regenerate: run the smoke test, then `python tests/gen_checkers_doc.py`.",
        "",
        f"## Core rules (stukach_core) — {len(rules)}",
        "",
        "DCC-free rules shared by every STUKACH build. Severity is decided by",
        "the registry; each DCC layer maps the verdicts onto its own UI.",
        "",
        "| Rule | Severity | Defaults | Description |",
        "|---|---|---|---|",
    ]
    for rule_id, (severity, evaluator, defaults) in rules.items():
        params = ", ".join(f"{k}={v}" for k, v in defaults.items()) or "—"
        desc = _cell(_summary(evaluator.__doc__))
        lines.append(f"| `{rule_id}` | {severity} | {params} | {desc} |")

    lines += [
        "",
        f"## Addon checks (Blender) — {len(dump)}",
        "",
        "The full checker set of the Blender addon. Checks marked *core* run",
        "their detection in stukach_core (shared verbatim with the Maya build",
        "via the parity gate in the smoke test).",
        "",
        "| Check | Severity | Category | Core | Description |",
        "|---|---|---|---|---|",
    ]
    for key in sorted(dump):
        info = dump[key]
        # honest delegation: the dump carries the addon's CORE_DELEGATED set —
        # a name match with a core rule is NOT evidence of delegation
        in_core = "core" if info.get("core_delegated") else ""
        lines.append(f"| `{key}` | {info['severity']} | {info['category']} | "
                     f"{in_core} | {_cell(_summary(info['doc']))} |")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true",
                    help="verify the committed file is fresh; exit 1 on drift")
    args = ap.parse_args()

    text = render(load_dump(), load_core_rules())

    if args.check:
        if not OUT.exists():
            print(f"[gen] FAIL: {OUT} does not exist")
            return 1
        committed = OUT.read_text(encoding="utf-8")
        if committed != text:
            print(f"[gen] FAIL: {OUT} is stale - regenerate and commit it")
            return 1
        print(f"[gen] OK: {OUT} is fresh")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"[gen] wrote {OUT} ({len(text)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

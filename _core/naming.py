# -*- coding: utf-8 -*-
"""DCC-free naming contract and hygiene validators.

Moved from the STUKACH Blender addon (strangler stage 3, 2026-10-03).
Everything here operates on plain strings and the policy dict — no bpy,
no maya.  The policy dict shape (see the Blender addon's
get_active_policy):  {"object": {"required_prefixes": [...],
"required_suffixes": [...], "positions": [...]}, "collection": {...}}.
"""
from __future__ import annotations

import re
from typing import List, Optional

# ── code-level defaults ───────────────────────────────────────────────────────

NAMING_RULES = {
    "object": {
        "lowercase": True,
        # Plan-class markers (hero / mid / bg) are PREFIXES in the pipeline
        # (hero_tower_geo), so they are deliberately NOT suffixes here —
        # a name ending in "_hero" gets the no-suffix hint on purpose.
        "allowed_suffixes": [
            "_grp", "_geo", "_proxy",
            "_l", "_r",
            "_left", "_right", "_front", "_back", "_top", "_bottom",
            "_mask_dust", "_mask_dirt", "_mask_leaks",
            "_clean", "_damaged", "_interior", "_notail",
        ],
        # All entries MUST be lowercase — comparison is done on name.lower()
        "forbidden_base_names": [
            # Blender
            "cube", "sphere", "plane", "cylinder", "cone", "torus",
            "suzanne", "beziercircle", "beziercurve", "curve", "nurbs",
            "text", "camera", "light", "sun", "area", "spot",
            "empty", "armature", "lattice", "metaball",
            # Maya
            "pcube", "psphere", "pcylinder", "pcone", "pplane", "ptorus",
            "polysurface", "group", "locator",
            "nurbscircle", "nurbssphere", "nurbscylinder",
            "nurbscone", "nurbsplane",
            # 3ds Max
            "box", "teapot", "geosphere",
            "editable_poly", "editable_mesh", "editablepoly", "editablemesh",
            "dummy", "point", "line",
            # Generic traps
            "object", "mesh", "model", "asset",
        ],
    },
    "collection": {
        "lowercase": True,
        "skip_names": {"scene collection", "master collection"},
    },
    "material": {
        "lowercase": True,
        "required_suffix": "_mat",
    },
}

DEFAULT_POSITIONS: tuple = (
    "_l", "_r", "_left", "_right", "_front", "_back", "_top", "_bottom",
)
DEFAULT_PREFIXES: tuple = ("hero_", "mid_", "bg_")

_pat_blender_num = re.compile(r"\.\d+$")
_pat_mat_numbering = re.compile(r"\.\d{3,}$")
_pat_trailing_digits = re.compile(r"\d+$")
_pat_forbidden_chars = re.compile(r'[\s/\\:*?"<>|]')

_forbidden_set: Optional[frozenset] = None


def _ensure_forbidden_cache():
    global _forbidden_set
    if _forbidden_set is None:
        _forbidden_set = frozenset(
            NAMING_RULES["object"].get("forbidden_base_names", []))


def _strip_numbering(name_lower: str) -> str:
    """'cube.001' / 'pCube1' → base without numbering, for the default-name
    check ('cube_hero' stays 'cube_hero' — not a default name)."""
    s = _pat_blender_num.sub("", name_lower)
    return _pat_trailing_digits.sub("", s)


# ── the contract ──────────────────────────────────────────────────────────────

class NamingContract:
    """One name shape for every object:  [prefix] core [position] [_a] [_01] suffix

    Slots come from the naming policy; the variant (a single a-z letter) and
    the two-digit number are conventions, not configuration.  The contract is
    matched case-insensitively — letter case is the hygiene rules' job."""

    @staticmethod
    def _alt(tokens) -> str:
        esc = sorted((re.escape(t) for t in tokens), key=len, reverse=True)
        return "(?:" + "|".join(esc) + ")?" if esc else ""

    @staticmethod
    def _template(prefixes, positions, suffixes) -> str:
        parts = []
        if prefixes:
            parts.append("[" + "|".join(prefixes) + "]")
        parts.append("name")
        if positions:
            parts.append("[" + "|".join(positions) + "]")
        parts += ["[_a]", "[_01]"]
        parts.append("|".join(suffixes))
        return " ".join(parts)

    @classmethod
    def build(cls, policy: dict, role: str):
        """(compiled_regex, template) for *role* — or None when the policy
        defines no suffixes for it (nothing to enforce)."""
        domain = policy.get(role, {})
        suffixes = [s for s in domain.get("required_suffixes", []) if s]
        if not suffixes:
            return None
        prefixes = domain.get("required_prefixes", [])
        if role == "object":
            positions = set(DEFAULT_POSITIONS)
            positions.update(domain.get("positions", []))
            positions = sorted(positions)
        else:
            positions = []
        pre = cls._alt(prefixes)
        pos = cls._alt(positions)
        suf = "(?:" + "|".join(re.escape(s) for s in suffixes) + ")"
        pattern = re.compile(
            f"^{pre}[a-z0-9_]+?{pos}(?:_[a-z])?(?:_\\d{{2}})?{suf}$")
        return pattern, cls._template(prefixes, positions, suffixes)


# ── hygiene + contract validators ─────────────────────────────────────────────

def _find(name: str, check: str, rule: str, severity: str, message: str) -> dict:
    return {"check": check, "rule": rule, "severity": severity, "message": message}


def validate_object_name(name: str, obj_type: str, policy: dict) -> List[dict]:
    """Hygiene rules + the naming contract for one object name.

    obj_type: 'MESH' / 'EMPTY' / other — EMPTY objects are exempt from the
    contract (their _grp suffix is the hierarchy validator's job: one
    problem, one verdict).  Returns a list of finding dicts sorted ERROR
    first; empty list = clean."""
    _ensure_forbidden_cache()
    results: List[dict] = []
    if not name.strip():
        results.append(_find(name, "obj_naming", "empty_name", "ERROR",
                             "Empty object name"))
        return results

    name_lower = name.lower()

    if _pat_forbidden_chars.search(name):
        results.append(_find(name, "obj_naming", "forbidden_chars", "ERROR",
                             f"Forbidden characters or spaces in '{name}'"))

    # Pipeline names are a-z, 0-9, _ only; the lowercase rule cannot catch
    # Cyrillic ('дом' == 'дом'.lower()), so this is its own guard.
    if not name.isascii():
        results.append(_find(name, "obj_naming", "non_ascii", "ERROR",
                             f"Non-ASCII characters in '{name}' (a-z, 0-9, _ only)"))

    if _pat_blender_num.search(name):
        results.append(_find(name, "obj_naming", "blender_numbering", "ERROR",
                             f"Blender auto-numbering (name conflict): '{name}'"))

    base = _strip_numbering(name_lower)
    if base in _forbidden_set or name_lower in _forbidden_set:
        results.append(_find(name, "obj_naming", "forbidden_base_name", "ERROR",
                             f"Default DCC name: '{name}'"))

    if name != name_lower:
        results.append(_find(name, "obj_naming", "lowercase", "WARNING",
                             f"Name must be lowercase: '{name}'"))

    # the contract — matched on the lowercased name
    contract = NamingContract.build(policy or {}, "object")
    if contract is not None and obj_type != "EMPTY":
        regex, template = contract
        if not regex.match(name_lower):
            results.append(_find(name, "obj_naming", "contract_mismatch", "WARNING",
                                 f"Does not match the contract: {template}"))

    results.sort(key=lambda r: 0 if r["severity"] == "ERROR" else 1)
    return results


def validate_collection_name(name: str, policy: dict,
                             skip_names: Optional[set] = None) -> Optional[dict]:
    """Hygiene rules + the contract for one collection name.  None = clean."""
    _ensure_forbidden_cache()
    if skip_names and name.lower() in {s.lower() for s in skip_names}:
        return None
    if not name.strip():
        return _find(name, "col_naming", "empty_name", "ERROR", "Empty collection name")

    name_lower = name.lower()

    if _pat_forbidden_chars.search(name):
        return _find(name, "col_naming", "forbidden_chars", "ERROR",
                     f"Forbidden characters in '{name}'")

    if not name.isascii():
        return _find(name, "col_naming", "non_ascii", "ERROR",
                     f"Non-ASCII characters in '{name}' (a-z, 0-9, _ only)")

    if _pat_blender_num.search(name):
        return _find(name, "col_naming", "blender_numbering", "ERROR",
                     f"Blender auto-numbering: '{name}'")

    if name != name_lower:
        return _find(name, "col_naming", "lowercase", "WARNING",
                     f"Name must be lowercase: '{name}'")

    contract = NamingContract.build(policy or {}, "collection")
    if contract is not None:
        regex, template = contract
        if not regex.match(name_lower):
            return _find(name, "col_naming", "contract_mismatch", "WARNING",
                         f"Does not match the contract: {template}")
    return None


def validate_material_name(name: str, required_suffix: str = "_mat",
                           check_numbering: bool = True) -> List[dict]:
    """Material name hygiene + suffix convention (strangler 5b: the suffix
    and numbering checks moved here from the DCC layers).  Returns finding
    dicts, ERROR first; empty list = clean."""
    results: List[dict] = []
    if not name.isascii():
        results.append(_find(name, "mat_naming", "non_ascii", "ERROR",
                             f"Non-ASCII characters in '{name}' (a-z, 0-9, _ only)"))
    if check_numbering and _pat_mat_numbering.search(name):
        results.append(_find(name, "mat_naming", "mat_numbering", "WARNING",
                             f"Blender auto-numbering: '{name}'"))
    if required_suffix and not name.lower().endswith(required_suffix.lower()):
        results.append(_find(name, "mat_naming", "mat_suffix", "WARNING",
                             f"Material name must end with '{required_suffix}': '{name}'"))
    results.sort(key=lambda r: 0 if r["severity"] == "ERROR" else 1)
    return results


def mesh_data_target(obj_name: str, mesh_suffixes: List[str],
                     obj_suffixes: Optional[List[str]] = None) -> str:
    """<object name minus its suffix> + first mesh suffix ('body_geo' →
    'body_mesh').  obj_suffixes default to the object allowed_suffixes."""
    if obj_suffixes is None:
        obj_suffixes = NAMING_RULES.get("object", {}).get("allowed_suffixes", [])
    name = obj_name
    low = name.lower()
    first = mesh_suffixes[0] if mesh_suffixes else "_mesh"
    for s in obj_suffixes:
        s = s.lower()
        if s and low.endswith(s) and len(name) > len(s):
            return name[:-len(s)] + first
    return name + first


def validate_mesh_data_name(obj_name: str, datablock_name: str,
                            mesh_suffixes: List[str]) -> Optional[dict]:
    """Mesh datablock must carry the object's name or a pipeline mesh suffix.

    Clean when the datablock is named like its object (case-insensitive) or
    ends with one of *mesh_suffixes*.  None = clean."""
    if not datablock_name:
        return None
    low = datablock_name.lower()
    if low == obj_name.lower():
        return None
    if any(low.endswith(s.lower()) for s in mesh_suffixes if s):
        return None
    return _find(datablock_name, "mesh_data_naming", "mesh_data_name", "WARNING",
                 f"Mesh datablock '{datablock_name}' is not named like its "
                 f"object and has no mesh suffix")


def validate_name(name: str, kind: str, obj_type: str = "MESH",
                  policy: Optional[dict] = None,
                  skip_names: Optional[set] = None) -> List[dict]:
    """Dispatch by *kind*: 'object' | 'collection' | 'material'.

    Unified entry point for the DCC adapters; returns finding dicts, ERROR
    first, empty list = clean."""
    if kind == "object":
        return validate_object_name(name, obj_type, policy)
    if kind == "collection":
        f = validate_collection_name(name, policy, skip_names)
        return [f] if f else []
    if kind == "material":
        return validate_material_name(name)
    return []

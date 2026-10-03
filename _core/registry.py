# -*- coding: utf-8 -*-
"""Rule registry: id → (severity, evaluator, default params).

Severity vocabulary matches the DCC layers (BLOCKER / WARNING / INFO).
The registry is data — the manuals/checker reference is generated from it.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from .model import MeshSnapshot, Finding
from .checks import topology, surface, symmetry, scene

# rule id → (severity, evaluator callable, param name → default)
RULES: Dict[str, tuple] = {
    # topology
    "triangles":          ("WARNING", topology.check_triangles, {}),
    "ngons":              ("BLOCKER", topology.check_ngons, {}),
    "non_manifold":       ("BLOCKER", topology.check_non_manifold, {}),
    "zero_area":          ("BLOCKER", topology.check_zero_area, {"threshold": 1e-10}),
    "poles":              ("INFO",    topology.check_poles, {}),
    "isolated_verts":     ("WARNING", topology.check_isolated_verts, {}),
    "boundary_edges":     ("WARNING", topology.check_boundary_edges, {}),
    "duplicate_verts":    ("BLOCKER", topology.check_duplicate_verts, {"merge_dist": 1e-5}),
    "lamina":             ("BLOCKER", topology.check_lamina, {}),
    "zero_length_edges":  ("BLOCKER", topology.check_zero_length_edges, {"tol": 1e-8}),
    "starlike":           ("WARNING", topology.check_starlike,
                          {"zero_area_threshold": 1e-10}),
    "missing_uvs":        ("WARNING", topology.check_missing_uvs, {"zero_sq": 1e-12}),
    # surface
    "face_aspect_ratio":  ("INFO",    surface.check_face_aspect_ratio, {"threshold": 6.0}),
    # symmetry
    "symmetry_x":         ("INFO",    symmetry.check_symmetry, {"axis": 0, "threshold": 0.001}),
    "symmetry_y":         ("INFO",    symmetry.check_symmetry, {"axis": 1, "threshold": 0.001}),
    "symmetry_z":         ("INFO",    symmetry.check_symmetry, {"axis": 2, "threshold": 0.001}),
    # scene
    "duplicated_names":   ("BLOCKER", scene.check_duplicated_names, {}),
    "shape_names":        ("WARNING", scene.check_shape_names, {}),
    "trailing_numbers":   ("WARNING", scene.check_trailing_numbers, {}),
    "uncentered_pivots":  ("INFO",    scene.check_uncentered_pivots, {"threshold": 0.05}),
    "parent_geometry":    ("WARNING", scene.check_parent_geometry, {}),
}


def run_checks(snap: MeshSnapshot, enabled=None, params: Optional[dict] = None) -> list:
    """Run enabled rules against one snapshot.

    *enabled* — iterable of rule ids (None = all).  *params* — {rule_id:
    {param: value}} overrides of the registry defaults.  Returns the list of
    non-clean findings; clean rules produce nothing."""
    params = params or {}
    findings = []
    for rule_id, (severity, evaluator, defaults) in RULES.items():
        if enabled is not None and rule_id not in enabled:
            continue
        merged = dict(defaults)
        merged.update(params.get(rule_id, {}))
        finding: Optional[Finding] = evaluator(snap, **merged)
        if finding is not None and finding.count > 0:
            # severity always comes from the registry — single source of truth
            finding.severity = severity
            findings.append(finding)
    findings.sort(key=lambda f: ({"BLOCKER": 0, "WARNING": 1, "INFO": 2}[f.severity],
                                 -f.count))
    return findings

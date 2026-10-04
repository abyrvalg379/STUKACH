# -*- coding: utf-8 -*-
"""Rule registry: id → (severity, evaluator, default params).

Severity vocabulary matches the DCC layers (BLOCKER / WARNING / INFO).
The registry is data — the manuals/checker reference is generated from it.
"""
from __future__ import annotations

from typing import Callable, Dict, Optional

from .model import MeshSnapshot, Finding
from .checks import topology, surface, symmetry, scene, uv, transform

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
    # uv
    "uv_single_set":      ("WARNING", uv.check_uv_single_set, {"expected": 1}),
    "uv_udim_bounds":     ("BLOCKER", uv.check_uv_udim_bounds, {"eps": 1e-5}),
    "uv_micro_shell":     ("WARNING", uv.check_uv_micro_shell, {"island_area": 1e-5}),
    "uv_overlap":         ("BLOCKER", uv.check_uv_overlap, {"max_tris": 80000}),
    "uv_stretch":         ("WARNING", uv.check_uv_stretch, {"threshold": 0.5}),
    "uv_texel_density":   ("INFO",    uv.check_uv_texel_density,
                          {"tex_size": 2048, "target_td": 0.0, "tolerance": 0.20,
                           "unit_scale": 1.0}),
    "uv_material_udim":   ("BLOCKER", uv.check_uv_material_udim, {}),
    # transforms
    "origin_at_zero":      ("INFO",    transform.check_origin_at_zero, {"threshold": 0.001}),
    "scale":               ("BLOCKER", transform.check_scale, {"tol": 0.001}),
    "non_applied_transform": ("BLOCKER", transform.check_non_applied_transform,
                            {"tol": 0.001}),
    # surface
    "face_aspect_ratio":  ("INFO",    surface.check_face_aspect_ratio, {"threshold": 6.0}),
    "sharp_edges":        ("WARNING", surface.check_sharp_edges,
                           {"threshold_deg": 60.0, "bevel_ratio": 0.005,
                            "skip_custom_normals": True}),
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
    # name conventions (strangler 5b): names come from node/shape/material_names
    "mesh_data_naming":   ("WARNING", scene.check_mesh_data_naming,
                           {"mesh_suffixes": ["_mesh", "_geo", "_grp"]}),
    "mat_suffix":         ("WARNING", scene.check_mat_suffix, {"required_suffix": "_mat"}),
    "mat_numbering":      ("WARNING", scene.check_mat_numbering, {}),
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


# ── scene scope: cross-object rules over a batch of snapshots ────────────────
# rule id → (severity, evaluator(snaps, **params) → list[Finding], defaults).
# Findings carry owner = the key the snapshot was passed under; elements
# index that owner's snapshot.

SCENE_RULES: Dict[str, tuple] = {
    "uv_padding": ("INFO", uv.check_uv_padding_batch,
                   {"tex_size": 4096, "shell_px": 16, "tile_px": 8,
                    "max_polys": 50_000, "max_uv_verts": 200_000}),
}


def run_scene_checks(snaps: Dict[str, MeshSnapshot], enabled=None,
                     params: Optional[dict] = None) -> list:
    """Run enabled scene-scope rules over a batch of snapshots.

    *snaps* — {owner: MeshSnapshot}.  Same severity/params conventions as
    run_checks; zero-count findings are filtered."""
    params = params or {}
    findings = []
    for rule_id, (severity, evaluator, defaults) in SCENE_RULES.items():
        if enabled is not None and rule_id not in enabled:
            continue
        merged = dict(defaults)
        merged.update(params.get(rule_id, {}))
        for finding in evaluator(snaps, **merged):
            if finding.count > 0:
                finding.severity = severity
                findings.append(finding)
    findings.sort(key=lambda f: ({"BLOCKER": 0, "WARNING": 1, "INFO": 2}[f.severity],
                                 -f.count, f.owner))
    return findings

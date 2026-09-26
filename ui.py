# -*- coding:utf-8 -*-
import bpy
from . import manager as _manager_mod
from .properties import CHECK_CATEGORIES, pretty_name, category_enabled, _FIX_OPERATORS


# ── Health-strip: category → hidden COLOR property name ──────────────────────
_CAT_HS_KEYS = {
    "TOPOLOGY":   "hs_topology",
    "TRANSFORMS": "hs_transforms",
    "SYMMETRY":   "hs_symmetry",
    "UV":         "hs_uv",
    "NAMING":     "hs_naming",
    "MATERIALS":  "hs_materials",
    "CLEANUP":    "hs_cleanup",
}


def _addon_version() -> str:
    """Extension version from blender_manifest.toml (no bl_info in 4.2+)."""
    try:
        import tomllib
        from pathlib import Path
        manifest = Path(__file__).parent / "blender_manifest.toml"
        with open(manifest, "rb") as fh:
            return tomllib.load(fh).get("version", "?")
    except Exception:
        return "?"


_ADDON_VERSION = _addon_version()


def _MC():
    """Always returns the current MeshCheck class — safe across hot-reloads."""
    return _manager_mod.MeshCheck

# ── Per-check severity ────────────────────────────────────────────────────────
# BLOCKER  → any count > 0 contributes to CRITICAL status
# WARNING  → any count > 0 contributes to WARNING status only
# INFO     → informational only; never affects object/asset status
# Threshold (CHECK_THRESHOLDS) is still used for per-check UI colour (yellow/red dot).

CHECK_SEVERITY: dict = {
    # ── BLOCKERS — real pipeline stoppers ────────────────────────────────────
    "non_manifold":          "BLOCKER",   # breaks subdivision, export, Boolean ops
    "z_fighting":            "BLOCKER",   # coplanar faces destroy render
    "duplicate_verts":       "BLOCKER",   # coincident verts break normals / simulations
    "zero_area":             "BLOCKER",   # degenerate faces → NaN normals, broken UV
    "non_applied_transform": "BLOCKER",   # rotation breaks export normals / physics
    "scale":                 "BLOCKER",   # non-unit scale breaks simulations / TD
    "uv_overlap":            "BLOCKER",   # breaks baking / lightmap
    "uv_udim_bounds":        "BLOCKER",   # island spans two UDIM tiles — breaks UDIM texturing
    "uv_material_udim":      "BLOCKER",   # mixed materials on one UDIM — breaks baking/automation
    "mat_assignment":        "BLOCKER",   # missing material slot = black render
    "missing_textures":      "BLOCKER",   # broken file reference
    "lamina":                "BLOCKER",   # zero-thickness faces break booleans / export
    "zero_length_edges":     "BLOCKER",   # degenerate edges break subdivision / export
    "duplicated_names":      "BLOCKER",   # linked-library name collisions break export
    "ngons":                 "BLOCKER",   # not allowed in the pipeline - auto-fixable (triangulate)

    # ── WARNINGS — artist must review before delivery ────────────────────────
    "isolated_verts":        "WARNING",   # cleanup noise
    "modifier_stack":        "WARNING",   # unapplied modifiers change exported geo
    "uv_single_set":         "WARNING",   # extra UV layers
    "uv_micro_shell":        "WARNING",   # tiny UV islands
    "uv_stretch":            "WARNING",   # angle distortion visible on textures
    "obj_naming":            "WARNING",   # naming convention
    "col_naming":            "WARNING",
    "mat_numbering":         "WARNING",
    "mesh_data_naming":      "WARNING",   # Mesh.101 data blocks pollute pipelines   # Material.001 leftover names
    "mat_suffix":            "WARNING",   # material name convention
    "unused_data":           "WARNING",   # empty vgroups / leftover attributes
    "sharp_edges_not_hard":  "WARNING",   # smooth-shaded sharp corners — shading artifacts
    "starlike":              "WARNING",   # self-intersecting polygon outlines
    "missing_uvs":           "WARNING",   # unmapped faces break baking
    "trailing_numbers":      "WARNING",   # Cube.001-style name leftovers
    "uncentered_pivots":     "INFO",      # convention check (like origin_at_zero) — bbox-center pivots are not universal, e.g. buildings pivot at world zero
    "parent_geometry":       "WARNING",   # mesh parented under mesh breaks hierarchies

    # ── INFO — artist awareness, no pipeline impact ───────────────────────────
    "boundary_edges":        "INFO",      # open edges — may be intentional
    "face_aspect_ratio":     "INFO",      # elongated quads — artist judgement
    "triangles":             "INFO",      # midpoly workflow — artist review only
    "poles":                 "INFO",      # topology consideration
    "origin_at_zero":        "INFO",      # pivot off-origin — may be intentional
    "symmetry_x":            "INFO",      # symmetry check — informational
    "symmetry_y":            "INFO",
    "symmetry_z":            "INFO",
    "uv_texel_density":      "INFO",      # TD reference — informational unless target set
    "uv_padding":            "INFO",      # padding may vary intentionally per UDIM
}

# ── Per-check count thresholds for UI colour (yellow dot vs red dot) ──────────
# count == 0              → green
# 0 < count <= threshold  → yellow
# count >  threshold      → red
# (threshold 0 means any count > 0 = red immediately)
#
# triangles / ngons / poles are user-configurable in Preferences → Check Thresholds.
# All other checks default to 0 (any issue → red immediately).
CHECK_THRESHOLDS: dict = {
    "non_manifold":          0,
    "boundary_edges":        0,
    "isolated_verts":        0,
    "duplicate_verts":       0,
    "face_aspect_ratio":     0,
    "zero_area":             0,
    "z_fighting":            0,
    "triangles":             50,
    "ngons":                 0,
    "poles":                 20,
    "non_applied_transform": 0,
    "scale":                 0,
    "origin_at_zero":        0,
    "modifier_stack":        0,
    "symmetry_x":            0,
    "symmetry_y":            0,
    "symmetry_z":            0,
    "uv_single_set":         0,
    "uv_overlap":            0,
    "uv_micro_shell":        0,
    "uv_texel_density":      0,
    "uv_stretch":            0,
    "uv_padding":            0,
    "uv_udim_bounds":        0,
    "uv_material_udim":      0,
    "obj_naming":            0,
    "mesh_data_naming":      0,
    "col_naming":            0,
    "mat_numbering":         0,
    "mat_suffix":            0,
    "mat_assignment":        0,
    "missing_textures":      0,
    "unused_data":           0,
    "lamina":                0,
    "zero_length_edges":     0,
    "sharp_edges_not_hard":  0,
    "starlike":              0,
    "missing_uvs":           0,
    "duplicated_names":      0,
    "trailing_numbers":      0,
    "uncentered_pivots":     0,
    "parent_geometry":       0,
}

# Checks whose thresholds are user-configurable in Preferences
_PREFS_THRESHOLDS: frozenset = frozenset({'triangles', 'ngons', 'poles'})


def _get_prefs():
    """Return MeshCheckPreferences or None."""
    import bpy
    addon_name = __name__.rsplit(".", 1)[0]
    try:
        return bpy.context.preferences.addons[addon_name].preferences
    except Exception:
        return None


def _get_threshold(check: str, prefs=None) -> int:
    """Return the yellow/red dot threshold for *check*.

    For triangles / ngons / poles the value is read from MeshCheckPreferences
    (passed in as *prefs* when available, otherwise fetched from bpy.context).
    All other checks use the hardcoded CHECK_THRESHOLDS table.
    """
    if check in _PREFS_THRESHOLDS:
        p = prefs
        if p is None:
            try:
                addon = __name__.rsplit(".", 1)[0]
                p = bpy.context.preferences.addons[addon].preferences
            except Exception:
                p = None
        if p is not None:
            return int(getattr(p, f"threshold_{check}",
                               CHECK_THRESHOLDS.get(check, 0)))
    return CHECK_THRESHOLDS.get(check, 0)


_STATUS_ICON = {
    "grey":   "RADIOBUT_OFF",
    "green":  "CHECKMARK",
    "yellow": "INFO",
    "red":    "ERROR",
}

_STATUS_TEXT = {
    "grey":   "",
    "green":  "",
    "yellow": "!",
    "red":    "!!",
}


def _get_check_count(mc_obj, check: str) -> int:
    checker = mc_obj._checks.get(check)
    if checker is None:
        return 0
    val = checker.count
    return int(val) if not callable(val) else 0


def get_category_status(mesh_check, category: str) -> str:
    active_checks = [
        c for c in CHECK_CATEGORIES.get(category, [])
        if getattr(mesh_check, c, False)
    ]
    if not active_checks:
        return "grey"

    total = sum(
        _get_check_count(mc_obj, check)
        for mc_obj in _manager_mod.MeshCheck.objects.values()
        for check in active_checks
    )

    if total == 0:
        return "green"

    threshold = max(_get_threshold(c) for c in active_checks)
    return "red" if total > threshold else "yellow"


def _compute_asset_summary(mc) -> dict:
    """Aggregate issue counts per category.

    Returns per-category (blocker_count, warning_count) tuples and overall totals.
    Severity is taken from CHECK_SEVERITY; CHECK_THRESHOLDS is NOT used here —
    it only governs the per-check UI dot colour.
    """
    cat_counts: dict = {}
    total_blockers = total_warnings = 0

    for cat, checks in CHECK_CATEGORIES.items():
        cat_b = cat_w = 0
        for check in checks:
            if not getattr(mc, check, False) or not category_enabled(check):
                continue
            total = sum(_get_check_count(mc_obj, check) for mc_obj in _manager_mod.MeshCheck.objects.values())
            if total == 0:
                continue
            sev = CHECK_SEVERITY.get(check, "WARNING")
            if sev == "BLOCKER":
                cat_b += total
            elif sev != "INFO":
                cat_w += total
        cat_counts[cat] = (cat_b, cat_w)
        total_blockers += cat_b
        total_warnings += cat_w

    return {
        "obj_count":       len(_manager_mod.MeshCheck.objects),
        "total_blockers":  total_blockers,
        "total_warnings":  total_warnings,
        "total_issues":    total_blockers + total_warnings,
        "cat_counts":      cat_counts,
    }


def _get_object_status(mc_obj, mc) -> str:
    """Returns 'critical', 'warning', or 'clean' for a single tracked object."""
    has_blocker = has_warning = False
    for cat_checks in CHECK_CATEGORIES.values():
        for check in cat_checks:
            if not getattr(mc, check, False) or not category_enabled(check):
                continue
            count = _get_check_count(mc_obj, check)
            if count == 0:
                continue
            sev = CHECK_SEVERITY.get(check, "WARNING")
            if sev == "BLOCKER":
                has_blocker = True
            elif sev != "INFO":
                has_warning = True
    if has_blocker:
        return "critical"
    if has_warning:
        return "warning"
    return "clean"


def _get_asset_status(mc) -> str:
    """Returns 'none', 'ready', 'warning', or 'critical'.

    CRITICAL requires at least one BLOCKER check to have count > 0.
    WARNING checks (triangles, ngons, etc.) never escalate to CRITICAL.
    """
    has_any_active = False
    has_blocker    = False
    has_warning    = False

    if not _manager_mod.MeshCheck.objects and not mc.coordinator_mode:
        return "none"

    if _manager_mod.MeshCheck.objects:
        for cat_checks in CHECK_CATEGORIES.values():
            for check in cat_checks:
                if not getattr(mc, check, False) or not category_enabled(check):
                    continue
                has_any_active = True
                total = sum(
                    _get_check_count(mc_obj, check)
                    for mc_obj in _manager_mod.MeshCheck.objects.values()
                )
                if total == 0:
                    continue
                sev = CHECK_SEVERITY.get(check, "WARNING")
                if sev == "BLOCKER":
                    has_blocker = True
                elif sev != "INFO":
                    has_warning = True

    # Hierarchy validator — acceptance gate.  Findings count ONLY in
    # Coordinator Mode: the hierarchy is assembled AFTER the asset is
    # finished, so an artist mid-production must not see a failed status
    # because of it.  In Coordinator Mode errors escalate to CRITICAL,
    # warnings to REVIEW.  A scan alone can produce a verdict even when
    # no mesh checks have been run.
    if mc.coordinator_mode:
        hier = _manager_mod.MeshCheck.hierarchy_result
        if hier is not None:
            from .naming import hierarchy_effective_issues
            eff = hierarchy_effective_issues(hier)
            e = sum(1 for i in eff if i.severity == "ERROR")
            w = sum(1 for i in eff if i.severity == "WARNING")
            if e or w:
                has_any_active = True
                if e:
                    has_blocker = True
                else:
                    has_warning = True

    if not has_any_active:
        return "none"

    if has_blocker:
        return "critical"
    if has_warning:
        return "warning"
    return "ready"


def _draw_delta_row(layout, label: str, was: int, now: int, *,
                    icon: str = "NONE",
                    is_new: bool = False,
                    is_gone: bool = False,
                    big: bool = False,
                    blocker: bool = False) -> None:
    """One comparison row: label  |  was → now  delta-badge."""
    row = layout.row(align=True)
    if big:
        row.scale_y = 1.1

    # Label column (left, stretches)
    lbl = row.row()
    lbl.alignment = "LEFT"

    if is_gone:
        lbl.enabled = False
        lbl.label(text=label, icon=icon if icon != "NONE" else "OBJECT_DATA")
    elif is_new:
        lbl.alert = (now > 0)
        lbl.label(text=f"[NEW]  {label}", icon=icon if icon != "NONE" else "OBJECT_DATA")
    else:
        lbl.label(text=label, icon=icon)

    # Delta column (right, fixed)
    right = row.row()
    right.alignment = "RIGHT"

    if is_gone:
        right.enabled = False
        right.label(text=f"{was} → —")
        return

    if is_new:
        right.alert = (now > 0)
        right.label(text=f"→ {now}",
                    icon="TRIA_UP" if now > 0 else "CHECKMARK")
        return

    delta = now - was
    if delta < 0:
        # Improved — no alert (shows as normal/positive)
        right.label(text=f"{was} → {now}  ↓{abs(delta)}", icon="TRIA_DOWN_BAR")
    elif delta > 0:
        right.alert = True
        right.label(text=f"{was} → {now}  ↑{delta}", icon="TRIA_UP_BAR")
    else:
        # Unchanged
        if now == 0:
            right.enabled = False
            right.label(text="clean", icon="CHECKMARK")
        else:
            right.label(text=f"{was} → {now}  =", icon="REMOVE")


def draw_coordinator_panel(layout, mc, context) -> None:
    """Coordinator Mode — same checks as artist view, BLOCKER + WARNING only (no INFO)."""
    from .properties import _AC_CHECKPOINT_KEY

    # ── Header ────────────────────────────────────────────────────────────────
    # Switching back is done by the "Artist Mode" toolbar button under Run —
    # no duplicate toggle here, title only.
    layout.label(text="Coordinator Mode", icon="COMMUNITY")

    # ── Asset status badge ────────────────────────────────────────────────────
    status = _get_asset_status(mc)
    status_box = layout.box()
    if status == "critical":
        r = status_box.row()
        r.alert = True
        r.label(text="ASSET STATUS: CRITICAL", icon="CANCEL")
        sub = status_box.row()
        sub.scale_y = 0.75
        sub.alert = True
        sub.label(text="Blockers must be resolved before publish")
    elif status == "warning":
        r = status_box.row()
        r.label(text="ASSET STATUS: REVIEW", icon="INFO")
        sub = status_box.row()
        sub.scale_y = 0.75
        sub.enabled = False
        sub.label(text="Warnings require artist decision")
    elif status == "ready":
        r = status_box.row()
        r.label(text="ASSET STATUS: READY", icon="CHECKMARK")
    else:
        r = status_box.row()
        r.enabled = False
        r.label(text="Run validation first", icon="PLAY")

    # ── Scene Units (always shown) ────────────────────────────────────────────
    _draw_scene_units_row(layout, mc)

    # ── Scope ─────────────────────────────────────────────────────────────────
    scope_row = layout.row(align=True)
    scope_row.operator("asset_checker.validate_scene",      text="Scene",      icon="WORLD")
    scope_row.operator("asset_checker.validate_collection", text="Collection", icon="OUTLINER_COLLECTION")
    scope_row.operator("asset_checker.clear_validation",    text="",           icon="X")

    # Coordinator-facing report — verdict format when coordinator_mode is on
    act_row = layout.row(align=True)
    act_row.scale_y = 0.9
    act_row.operator("asset_checker.copy_summary", text="Copy Report", icon="COPYDOWN")

    layout.separator(factor=0.3)

    # ── Filtered checkers (BLOCKER + WARNING only) ────────────────────────────
    checks_box = layout.box()
    checks_box.label(text="Critical & Warning Checks:", icon="ERROR")
    mc.draw_options(checks_box, severity_filter={'BLOCKER', 'WARNING'})

    if prefs := _get_prefs():
        xr_row = checks_box.row(align=True)
        xr_row.scale_y = 0.8
        xr_row.prop(prefs, "overlay_xray", text="X-Ray", toggle=True, icon='XRAY')
        off_row = checks_box.row(align=True)
        off_row.scale_y = 0.8
        off_row.prop(prefs, "faces_offset", text="Face Offset")
        off_row.prop(prefs, "points_offset", text="Point Offset")

    # ── Export / Pre-flight / Checkpoint ─────────────────────────────────────
    has_results = bool(_manager_mod.MeshCheck.objects)
    cp_exists   = bool(context.scene.get(_AC_CHECKPOINT_KEY))

    exp_box = layout.box()
    exp_row = exp_box.row(align=True)
    exp_row.label(text="Export:", icon="EXPORT")
    exp_row.enabled = has_results
    for fmt, lbl in (('JSON', 'JSON'), ('CSV', 'CSV'), ('HTML', 'HTML')):
        op = exp_row.operator("asset_checker.export_report", text=lbl)
        op.fmt = fmt

    pf_row = exp_box.row(align=True)
    pf_row.label(text="Pre-flight:", icon="CHECKMARK")
    pf_row.enabled = has_results
    op_fbx = pf_row.operator("asset_checker.preflight_export", text="FBX", icon="EXPORT")
    op_fbx.fmt = 'FBX'
    op_usd = pf_row.operator("asset_checker.preflight_export", text="USD", icon="EXPORT")
    op_usd.fmt = 'USD'

    cp_row = exp_box.row(align=True)
    cp_row.label(text="Checkpoint:", icon="BOOKMARKS")
    cp_row.operator("asset_checker.save_checkpoint",
                    text="Update" if cp_exists else "Save", icon="FILE_TICK")
    cp_row.operator("asset_checker.load_checkpoint", text="", icon="IMPORT")
    if cp_exists:
        cp_row.operator("asset_checker.clear_checkpoint", text="", icon="X", emboss=False)


def draw_hierarchy_block(layout, mc):
    """Pipeline hierarchy validator — collapsible sub-section.

    Renders as a standalone top-level panel block (sibling of the category boxes).
    *mc* is MeshCheckProperties (WindowManager.mesh_check_props).

    Sections:
      • Header row: collapse toggle · "Hierarchy" label · Scan/Re-scan · X
      • (when expanded) Summary · Issue list · Hierarchy Tree
    """
    from .naming import (
        HierarchyResult,
        HierarchyValidator,
        hierarchy_effective_issues,
        hierarchy_ignored_count,
        hierarchy_rule_summary,
        HIER_RULE_LABELS,
        _ROLE_ASSET_ROOT,
        _ROLE_ICONS,
        INFO, WARNING, ERROR, SEVERITY_ICON,
    )
    from .manager import MeshCheck

    result: HierarchyResult = MeshCheck.hierarchy_result

    # ── Collapsible header ────────────────────────────────────────────────────
    hdr = layout.row(align=True)
    tria = "TRIA_DOWN" if mc.hierarchy_block_open else "TRIA_RIGHT"
    hdr.prop(mc, "hierarchy_block_open", text="", icon=tria, emboss=False)
    hdr.label(text="Hierarchy", icon="EMPTY_AXIS")

    # Scan / Re-scan + Clear on the right side of the header
    right = hdr.row(align=True)
    right.alignment = "RIGHT"
    if result is None:
        right.operator("asset_checker.scan_hierarchy", text="Scan", icon="PLAY")
    else:
        right.operator("asset_checker.scan_hierarchy", text="", icon="FILE_REFRESH")
        right.operator("asset_checker.clear_hierarchy", text="", icon="X", emboss=False)

    if not mc.hierarchy_block_open:
        # Collapsed — show one-line status badge
        if result is not None:
            badge = layout.row(align=True)
            badge.scale_y = 0.75
            eff = hierarchy_effective_issues(result)
            e = sum(1 for i in eff if i.severity == ERROR)
            w = sum(1 for i in eff if i.severity == WARNING)
            if HierarchyValidator.is_stale(result):
                badge.label(text="  Stale — hierarchy changed, re-scan",
                            icon="FILE_REFRESH")
            elif not eff:
                badge.label(text=f"  Clean  ·  {len(result.asset_roots)} root(s)", icon="CHECKMARK")
            else:
                if e:
                    badge.label(text=f"  {e} error(s)", icon=SEVERITY_ICON[ERROR])
                if w:
                    badge.label(text=f"  {w} warning(s)", icon=SEVERITY_ICON[WARNING])
        return

    # ── Expanded content ──────────────────────────────────────────────────────

    if result is None:
        layout.label(text="Press Scan to validate hierarchy", icon="INFO")
        return

    eff = hierarchy_effective_issues(result)
    e = sum(1 for i in eff if i.severity == ERROR)
    w = sum(1 for i in eff if i.severity == WARNING)
    n_roots = len(result.asset_roots)
    n_ignored = hierarchy_ignored_count(result)

    if HierarchyValidator.is_stale(result):
        stale = layout.row(align=True)
        stale.label(text="Stale — hierarchy changed since this scan",
                    icon="FILE_REFRESH")

    summ = layout.row(align=True)
    if not eff:
        summ.label(
            text=f"Clean  ·  {n_roots} root(s)  ·  {result.objects_scanned} obj",
            icon="CHECKMARK",
        )
    else:
        if e:
            summ.label(text=f"{e} error(s)", icon=SEVERITY_ICON[ERROR])
        if w:
            summ.label(text=f"{w} warning(s)", icon=SEVERITY_ICON[WARNING])
        right2 = summ.row()
        right2.alignment = "RIGHT"
        right2.label(text=f"{n_roots} root(s)  ·  {result.objects_scanned} obj")

    # Controls: issues-only filter + suppressed findings restore + skeleton
    ctrl = layout.row(align=True)
    ctrl.prop(mc, "hierarchy_issues_only", text="Issues only", icon="FILTER",
              toggle=True, emboss=False)
    if n_ignored:
        right3 = ctrl.row(align=True)
        right3.alignment = "RIGHT"
        right3.operator("asset_checker.hierarchy_clear_ignores",
                        text=f"{n_ignored} ignored — clear", icon="LOOP_BACK", emboss=False)

    # ── One-click fixes for aggregated findings ──────────────────────────────
    fix_counts: dict = {}
    for i in eff:
        fix_counts[i.rule] = fix_counts.get(i.rule, 0) + 1
    # Coordinator Lock: fixes and skeleton are artist tools — the curator
    # still gets the summary and the issue tree below.
    _hier_lock = bool(mc.coordinator_mode
                      and getattr(_get_prefs(), "coordinator_lock", False))
    fx = layout.row(align=True)
    if not _hier_lock and fix_counts.get("missing_grp_suffix"):
        fx.operator("asset_checker.hierarchy_fix_grp_suffix",
                    text=f"Add _grp ({fix_counts['missing_grp_suffix']})")
    if not _hier_lock and fix_counts.get("parent_mismatch"):
        fx.operator("asset_checker.hierarchy_fix_renumber",
                    text=f"Renumber ({fix_counts['parent_mismatch']})")
    if not _hier_lock and (fix_counts.get("orphan_empty") or fix_counts.get("orphan_mesh")):
        n_orph = fix_counts.get("orphan_empty", 0) + fix_counts.get("orphan_mesh", 0)
        fx.operator("asset_checker.hierarchy_fix_adopt",
                    text=f"Connect orphans ({n_orph})")
    if not _hier_lock and fix_counts.get("no_asset_root"):
        fx.operator("asset_checker.hierarchy_fix_create_root", text="Create root")
    if not _hier_lock:
        fx.operator("asset_checker.hierarchy_create_skeleton", text="Skeleton",
                    icon="ADD")

    # ── Helpers ───────────────────────────────────────────────────────────────
    issues_by_obj: dict = {}
    for issue in eff:
        issues_by_obj.setdefault(issue.obj_name, []).append(issue)

    def _subtree_names(root_name):
        out = set()
        stack = [root_name]
        while stack:
            n = stack.pop()
            out.add(n)
            stack.extend(result.children_of.get(n, []))
        return out

    def _issue_row(col, issue):
        row = col.row(align=True)
        role_icon = _ROLE_ICONS.get(issue.role, "DOT")
        nm = issue.obj_name
        row.label(text=f"  {nm}  —  {issue.message}", icon=role_icon)
        if nm != "[scene]" and bpy.data.objects.get(nm):
            op = row.operator("asset_checker.select_object", text="",
                              icon="RESTRICT_SELECT_OFF", emboss=False)
            op.object_name = nm
            op2 = row.operator("asset_checker.hierarchy_ignore_toggle", text="",
                               icon="HIDE_ON", emboss=False)
            op2.object_name = nm
            op2.rule = issue.rule

    def _tree_row(col, name, depth, role):
        obj_issues = issues_by_obj.get(name, [])
        n_iss = len(obj_issues)
        node_icon = _ROLE_ICONS.get(role, "DOT")
        issue_icon = ("ERROR" if any(i.severity == ERROR for i in obj_issues)
                      else ("INFO" if n_iss else "BLANK1"))
        r = col.row(align=True)
        r.label(text=f"{'   ' * depth}{name}", icon=node_icon)
        if n_iss:
            r.label(text="", icon=issue_icon)
        if bpy.data.objects.get(name):
            op = r.operator("asset_checker.select_object", text="",
                            icon="RESTRICT_SELECT_OFF", emboss=False)
            op.object_name = name
            if any(i.severity in (WARNING, ERROR) for i in obj_issues):
                op2 = r.operator("asset_checker.hierarchy_ignore_toggle", text="",
                                 icon="HIDE_ON", emboss=False)
                op2.object_name = name
                op2.rule = obj_issues[0].rule

    # ── Scene-level findings (no/multiple roots) ─────────────────────────────
    scene_issues = issues_by_obj.get("[scene]", [])
    if scene_issues:
        col = layout.column(align=True)
        for issue in scene_issues:
            _issue_row(col, issue)

    # ── Issues only — aggregated one row per rule (anti-wall-of-text) ────────
    if mc.hierarchy_issues_only:
        expanded = MeshCheck._hier_expanded_rules
        for rule, sev, count, samples in hierarchy_rule_summary(eff):
            is_open_rule = rule in expanded
            grp = layout.row(align=True)
            grp.operator("asset_checker.hierarchy_toggle_rule",
                         text="",
                         icon="TRIA_DOWN" if is_open_rule else "TRIA_RIGHT",
                         emboss=False).rule = rule
            grp.label(text=HIER_RULE_LABELS.get(rule, rule),
                      icon=SEVERITY_ICON[ERROR if sev == ERROR else WARNING])
            cnt = grp.row()
            cnt.alignment = "RIGHT"
            cnt.label(text=f"× {count}")
            if not is_open_rule:
                if samples:
                    grp.label(text="·  " + ", ".join(samples), icon="BLANK1")
                continue
            detail = layout.column(align=True)
            shown = 0
            for issue in eff:
                if issue.rule != rule:
                    continue
                if shown >= 10:
                    detail.label(text=f"  …and {count - shown} more",
                                 icon="BLANK1")
                    break
                _issue_row(detail, issue)
                shown += 1
        return

    # ── Per-asset root sections (lazy: subtree drawn only when expanded) ─────
    collapsed = MeshCheck._hier_collapsed_roots
    names_in_roots: set = set()
    _SUBTREE_CAP = 40
    for root_name in result.asset_roots:
        names = _subtree_names(root_name)
        names_in_roots |= names
        r_err = sum(1 for i in eff if i.obj_name in names and i.severity == ERROR)
        r_warn = sum(1 for i in eff if i.obj_name in names and i.severity == WARNING)
        is_collapsed = root_name in collapsed

        hdr = layout.row(align=True)
        hdr.operator("asset_checker.hierarchy_toggle_root",
                     text="", icon="TRIA_RIGHT" if is_collapsed else "TRIA_DOWN",
                     emboss=False).root_name = root_name
        hdr.label(text=root_name, icon=_ROLE_ICONS.get(_ROLE_ASSET_ROOT, "DOT"))
        if r_err:
            hdr.label(text=f"{r_err}E", icon=SEVERITY_ICON[ERROR])
        if r_warn:
            hdr.label(text=f"{r_warn}W", icon=SEVERITY_ICON[WARNING])
        if not r_err and not r_warn:
            hdr.label(text="", icon="CHECKMARK")

        if is_collapsed:
            continue

        sec = layout.column(align=True)
        drawn = [0]

        def _draw_subtree(col, name, depth, role):
            if drawn[0] >= _SUBTREE_CAP:
                return
            _tree_row(col, name, depth, role)
            drawn[0] += 1
            for child in sorted(result.children_of.get(name, [])):
                _draw_subtree(col, child, depth + 1,
                              result.node_roles.get(child, ""))

        _draw_subtree(sec, root_name, 0, _ROLE_ASSET_ROOT)
        extra = len(names) - drawn[0]
        if extra > 0:
            sec.label(text=f"  …and {extra} more nodes — use Issues only",
                      icon="BLANK1")

    # ── Orphans (outside every root) — dedup by object, capped ───────────────
    orphan_issues = [i for i in eff
                     if i.obj_name != "[scene]"
                     and i.obj_name not in names_in_roots]
    if orphan_issues:
        orphan_objs: dict = {}
        for issue in orphan_issues:
            orphan_objs.setdefault(issue.obj_name, issue)
        hdr2 = layout.row(align=True)
        hdr2.label(text=f"Not connected to any root  ·  {len(orphan_objs)} object(s)",
                   icon="QUESTION")
        col = layout.column(align=True)
        for n, (obj_name, issue) in enumerate(orphan_objs.items()):
            if n >= 5:
                col.label(text=f"  …and {len(orphan_objs) - 5} more",
                          icon="BLANK1")
                break
            _issue_row(col, issue)


def _draw_ignore_list_block(layout, mc) -> None:
    """Collapsible 'Ignored Issues' block — shows all per-object ignores.

    Only rendered when at least one tracked object has ignored checks.
    Each row: object name · ignored check names · [X] clear.
    Header: total count · [Clear All].
    """
    from .properties import get_obj_ignore_list, _CHECK_LABELS, _AC_IGNORE_KEY

    # Collect (name, obj, ignored_set) for all tracked objects that have ignores
    objects_with_ignores = []
    for obj in list(_manager_mod.MeshCheck.objects.keys()):
        try:
            name = obj.name
        except ReferenceError:
            continue
        ignored = get_obj_ignore_list(obj)
        if ignored:
            objects_with_ignores.append((name, obj, ignored))

    if not objects_with_ignores:
        return   # nothing to show — block disappears automatically

    total_count = sum(len(ig) for _, _, ig in objects_with_ignores)

    box = layout.box()

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = box.row(align=True)
    tria = "TRIA_DOWN" if mc.ignore_list_open else "TRIA_RIGHT"
    hdr.prop(mc, "ignore_list_open", text="", icon=tria, emboss=False)
    hdr.label(
        text=f"Ignored Issues  ({total_count})",
        icon="HIDE_ON",
    )
    # Clear-all button sits on the right of the header
    hdr.operator(
        "asset_checker.clear_all_ignores",
        text="", icon="X", emboss=False,
    )

    if not mc.ignore_list_open:
        return

    # ── Per-object rows ───────────────────────────────────────────────────────
    col = box.column(align=True)
    for obj_name, obj, ignored in sorted(objects_with_ignores, key=lambda x: x[0]):
        row = col.row(align=True)

        # Object name
        name_part = row.row(align=True)
        name_part.alignment = "LEFT"
        name_part.label(
            text=f"{obj_name}:",
            icon="OBJECT_DATA",
        )

        # Ignored check labels (human-readable)
        check_labels = [
            _CHECK_LABELS.get(c, pretty_name(c))
            for c in sorted(ignored)
        ]
        chips = row.row(align=True)
        chips.enabled = False
        chips.label(text=", ".join(check_labels))

        # Per-object clear button
        op = row.operator(
            "asset_checker.clear_ignore_object",
            text="", icon="X", emboss=False,
        )
        op.obj_name = obj_name

    # Hint at the bottom
    hint = box.row()
    hint.scale_y = 0.7
    hint.enabled = False
    hint.label(
        text="Ignored issues are excluded from the pipeline report",
        icon="INFO",
    )


def draw_naming_audit_block(layout, mc) -> None:
    """Naming Audit block — scene-wide check, collapsible.

    Renders as a standalone top-level panel block (sibling of the category boxes).
    *mc* is MeshCheckProperties (WindowManager.mesh_check_props).

    Sections:
      • Header row: collapse toggle · "Naming Audit" label · Run/Re-run · X
      • (collapsed) one-line status badge
      • (expanded) error/warning list with click-to-select
    """
    from .naming import NamingAudit, INFO, WARNING, ERROR, SEVERITY_ICON

    if mc is None:
        try:
            mc = bpy.context.window_manager.mesh_check_props
        except Exception:
            return

    # ── Collapsible header ────────────────────────────────────────────────────
    hdr = layout.row(align=True)
    tria = "TRIA_DOWN" if mc.naming_audit_open else "TRIA_RIGHT"
    hdr.prop(mc, "naming_audit_open", text="", icon=tria, emboss=False)
    hdr.label(text="Naming Audit", icon="VIEWZOOM")

    right = hdr.row(align=True)
    right.alignment = "RIGHT"
    if not NamingAudit._ran:
        right.operator("asset_checker.run_naming_audit", text="Run", icon="PLAY")
    else:
        right.operator("asset_checker.run_naming_audit", text="", icon="FILE_REFRESH")
        right.operator("asset_checker.clear_naming_audit", text="", icon="X", emboss=False)

    if not mc.naming_audit_open:
        # Collapsed — one-line status badge
        if NamingAudit._ran:
            badge = layout.row(align=True)
            badge.scale_y = 0.75
            if NamingAudit.is_clean():
                badge.label(text="  Scene naming is clean", icon="CHECKMARK")
            else:
                e, w = NamingAudit.error_count(), NamingAudit.warning_count()
                if e:
                    badge.label(text=f"  {e} error(s)", icon=SEVERITY_ICON[ERROR])
                if w:
                    badge.label(text=f"  {w} warning(s)", icon=SEVERITY_ICON[WARNING])
        return

    # ── Expanded content ──────────────────────────────────────────────────────
    if not NamingAudit._ran:
        layout.label(text="Press Run to scan scene naming", icon="INFO")
        return

    if NamingAudit.is_clean():
        layout.label(text="Scene naming is clean", icon="CHECKMARK")
        return

    e, w = NamingAudit.error_count(), NamingAudit.warning_count()
    summary = layout.row(align=True)
    if e:
        summary.label(text=f"{e} error(s)", icon=SEVERITY_ICON[ERROR])
    if w:
        summary.label(text=f"{w} warning(s)", icon=SEVERITY_ICON[WARNING])

    for sev in (ERROR, WARNING, INFO):
        group = [r for r in NamingAudit._results if r.severity == sev]
        if not group:
            continue
        sev_col = layout.column(align=True)
        sev_col.alert = (sev == ERROR)
        sev_col.label(text=sev, icon=SEVERITY_ICON[sev])
        for result in group:
            row = sev_col.row(align=True)
            # Full name and reason — no hard truncation
            row.label(text=f"{result.object_name}  —  {result.message}")
            if result.check == "obj_naming":
                op = row.operator(
                    "asset_checker.select_object",
                    text="", icon="RESTRICT_SELECT_OFF", emboss=False,
                )
                op.object_name = result.object_name


def _draw_scene_units_row(layout, mc) -> None:
    """Scene Units inline check — drawn above the categories box.

    Toggle sits on the left; when enabled, shows OK (green) or issues (red).
    ERROR severity: any deviation from METRIC/METERS/scale_length=1.0.
    """
    from .core import check_scene_units

    row = layout.row(align=True)
    icon = "CHECKBOX_HLT" if mc.scene_units else "CHECKBOX_DEHLT"
    row.prop(mc, "scene_units", icon=icon, emboss=False, text="Scene Units")

    if not mc.scene_units:
        return

    result = check_scene_units()
    status = row.row(align=True)
    status.alignment = "RIGHT"
    if result['ok']:
        status.label(text="METRIC · m · 1.0", icon="CHECKMARK")
    else:
        status.alert = True
        status.label(text="  ·  ".join(result['issues']), icon="ERROR")


class ASSET_CHECKER_PT_Panel(bpy.types.Panel):
    # bl_label фиксируется при регистрации — ui.py переимпортируется при каждом
    # reload, так что версия всегда актуальна на момент старта/перезагрузки.
    bl_label = f"STUKACH v{_ADDON_VERSION}"
    bl_idname = "ASSET_CHECKER_PT_Panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "STUKACH"

    @classmethod
    def poll(cls, context):
        return True

    @staticmethod
    def _draw_score_block(layout, mc):
        """Compact asset summary: scope badge · obj count · issue count · per-category."""
        if not _manager_mod.MeshCheck.objects:
            layout.box().label(text="Awaiting suspects.", icon="GHOST_ENABLED")
            return

        summary = _compute_asset_summary(mc)
        status  = _get_asset_status(mc)

        _st_icon = {
            "ready":    "CHECKMARK",
            "warning":  "INFO",
            "critical": "ERROR",
            "none":     "RADIOBUT_OFF",
        }

        scope = _manager_mod.MeshCheck._scope
        if scope == "COLLECTION":
            scope_label = _manager_mod.MeshCheck._scope_collection or "COLLECTION"
        elif scope == "SCENE":
            scope_label = "SCENE"
        else:
            scope_label = "SELECTION"

        box = layout.box()
        box.alert = (status == "critical")

        # ── Row 1: icon · obj count · blocker + warning counts · scope ──────
        row = box.row(align=True)
        n_b = summary["total_blockers"]
        n_w = summary["total_warnings"]
        if n_b and n_w:
            count_text = f"{summary['obj_count']} obj  ·  {n_b} block  {n_w} warn"
        elif n_b:
            count_text = f"{summary['obj_count']} obj  ·  {n_b} blockers"
        elif n_w:
            count_text = f"{summary['obj_count']} obj  ·  {n_w} warnings"
        else:
            count_text = f"{summary['obj_count']} obj  ·  clean"
        row.label(text=count_text, icon=_st_icon.get(status, "RADIOBUT_OFF"))
        badge = row.row()
        badge.alignment = "RIGHT"
        badge.label(text=f"[ {scope_label} ]")

        # ── Row 2: category health strip — real colored swatches, no text ───
        # Hover a cell → category name + color legend (property tooltip).
        _strip_green = (0.25, 0.80, 0.35, 1.0)
        _strip_yellow = (0.92, 0.76, 0.20, 1.0)
        _strip_red = (0.90, 0.26, 0.24, 1.0)
        cats_row = box.row(align=True)
        cats_row.scale_y = 0.75
        for cat, (cat_b, cat_w) in summary["cat_counts"].items():
            hs_key = _CAT_HS_KEYS.get(cat)
            if hs_key:
                color = (_strip_red if cat_b else
                         _strip_yellow if cat_w else _strip_green)
                try:
                    setattr(mc, hs_key, color)
                except Exception:
                    pass
                cats_row.prop(mc, hs_key, text="")
            else:
                icon = "ERROR" if cat_b else ("INFO" if cat_w else "CHECKMARK")
                cats_row.label(text=f"{cat[:2]}:{cat_b + cat_w}", icon=icon)

        # ── Row 3: Next Issue navigation + summary copy ─────────────────────
        action_row = box.row(align=True)
        action_row.operator("asset_checker.next_issue",
                            text="Next Issue", icon="ZOOM_SELECTED")
        action_row.operator("asset_checker.copy_summary", text="",
                            icon="COPYDOWN")

    @staticmethod
    def _draw_object_details(ob_box, obj, mc_obj, mc):
        """Expanded object: findings only.

        Severity icon + check name + count, compact Sel / Ign / Fix on the
        right.  The V/E/F/T stats and the 'N checks clean' line are gone —
        noise for this menu (author-approved redesign, 2026-09-26)."""
        from .properties import get_obj_ignore_list, _FIX_OPERATORS

        addon_name = __name__.rsplit(".", 1)[0]
        try:
            prefs = bpy.context.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None

        ignored_checks = get_obj_ignore_list(obj)

        active_checks = [
            (check, mc_obj._checks.get(check))
            for checks in CHECK_CATEGORIES.values()
            for check in checks
            if getattr(mc, check, False) and category_enabled(check)
            and mc_obj._checks.get(check) is not None
        ]

        def _draw_check_row(parent, check, checker, ignored):
            count     = _get_check_count(mc_obj, check)
            threshold = _get_threshold(check, prefs)

            row = parent.row(align=True)

            if ignored:
                row.alert = False
                lbl = row.row(align=True)
                lbl.enabled = False
                lbl.label(text=f"{pretty_name(check)}  (ign)", icon="HIDE_ON")
                op = row.operator(
                    "asset_checker.toggle_ignore",
                    text="", icon="HIDE_OFF", emboss=False,
                )
                op.obj_name   = obj.name
                op.check_name = check
                return

            mt    = getattr(checker, 'metric_text', '')
            name  = mt if mt else pretty_name(check)
            hot   = count > threshold            # real shading artifact risk
            icon  = "ERROR" if hot else "INFO"

            row.alert = hot
            row.label(text=f"{name}  ({count})", icon=icon)

            rr = row.row(align=True)
            rr.alignment = 'RIGHT'
            if hasattr(checker, 'get_select_data'):
                element_type, _ = checker.get_select_data()
                if element_type is not None:
                    op = rr.operator(
                        "asset_checker.select_check_elements",
                        text="", icon="VIEWZOOM",
                    )
                    op.obj_name   = obj.name
                    op.check_name = check
            fix_id = _FIX_OPERATORS.get(check)
            if fix_id and count > 0:
                op = rr.operator(fix_id, text="", icon="CHECKMARK")
            op = rr.operator(
                "asset_checker.toggle_ignore",
                text="", icon="HIDE_ON",
            )
            op.obj_name   = obj.name
            op.check_name = check

        # every finding is its own slim strip — visible separation between
        # different error types
        for check, checker in active_checks:
            ignored = check in ignored_checks
            count   = _get_check_count(mc_obj, check)
            if not ignored and count == 0:
                continue
            strip = ob_box.box()
            _draw_check_row(strip, check, checker, ignored)

    @staticmethod
    def _draw_asset_status(layout, mc):
        """Asset Status block — pipeline gate summary at bottom of panel."""
        status = _get_asset_status(mc)

        box = layout.box()
        box.alert = (status == "critical")

        if status == "none":
            box.label(text="No active checks.", icon="RADIOBUT_OFF")
            return

        if status == "ready":
            box.label(text="ASSET STATUS: PIPELINE READY", icon="CHECKMARK")
            box.label(text="Asset is production-ready")
        elif status == "warning":
            box.label(text="ASSET STATUS: WARNING", icon="INFO")
            box.label(text="Needs more work before delivery")
        elif status == "critical":
            box.label(text="ASSET STATUS: CRITICAL", icon="ERROR")
            box.label(text="Publish blocked — fix blockers first")

    @staticmethod
    def _draw_hierarchy_block(layout, mc):
        """Deprecated shim — delegates to module-level draw_hierarchy_block()."""
        draw_hierarchy_block(layout, mc)

    @staticmethod
    def _draw_naming_audit(layout, mc=None):
        """Deprecated shim — delegates to module-level draw_naming_audit_block()."""
        draw_naming_audit_block(layout, mc)

    @staticmethod
    def _draw_naming_issues(layout, mc):
        """Severity-grouped 'Invalid Naming' block with click-to-select."""
        from .naming import INFO, WARNING, ERROR, SEVERITY_ICON

        all_results = []
        seen_cols: set = set()   # deduplicate collection issues across tracked objects

        for mc_obj in _manager_mod.MeshCheck.objects.values():
            if mc.obj_naming:
                checker = mc_obj._checks.get("obj_naming")
                if checker and hasattr(checker, "results"):
                    all_results.extend(checker.results)
            if mc.col_naming:
                checker = mc_obj._checks.get("col_naming")
                if checker and hasattr(checker, "results"):
                    for r in checker.results:
                        if r.object_name not in seen_cols:
                            seen_cols.add(r.object_name)
                            all_results.append(r)

        if not all_results:
            return

        box = layout.box()
        box.label(
            text=f"Invalid Naming  ({len(all_results)} issue{'s' if len(all_results) != 1 else ''})",
            icon="ERROR",
        )

        for sev in (ERROR, WARNING, INFO):
            group = [r for r in all_results if r.severity == sev]
            if not group:
                continue
            sev_col = box.column(align=True)
            sev_col.alert = (sev == ERROR)
            sev_col.label(text=sev, icon=SEVERITY_ICON[sev])
            for result in group:
                row = sev_col.row(align=True)
                # Full text — hard-truncating made long names/messages unreadable
                row.label(text=f"{result.object_name}  —  {result.message}")
                # select button only makes sense for object-level issues
                if result.check == "obj_naming":
                    op = row.operator(
                        "asset_checker.select_object",
                        text="", icon="RESTRICT_SELECT_OFF", emboss=False,
                    )
                    op.object_name = result.object_name

    def draw(self, context):
        layout = self.layout
        mc = context.window_manager.mesh_check_props

        # Lazy import — avoids stale module-level reference after hot-reload


        addon_name = __name__.rsplit(".", 1)[0]
        try:
            prefs = context.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None

        # Update badge — only a result still newer than the installed version
        if prefs is not None and getattr(prefs, "update_result", "").startswith("Update available"):
            from . import update_checker
            if update_checker.result_is_valid():
                row = layout.row(align=True)
                row.operator("asset_checker.open_releases",
                             text=prefs.update_result, icon="WORLD")

        # ── Main action button ───────────────────────────────────────────────
        sub = layout.row()
        sub.scale_y = 0.55
        sub.label(text="Pipeline Snitch System")

        btn_text = "STUKACH ACTIVE" if mc.show_overlay else "RUN STUKACH"
        btn_icon = "RADIOBUT_ON"    if mc.show_overlay else "PLAY"
        run_row = layout.row(align=True)
        run_row.scale_y = 1.3
        run_row.prop(mc, "show_overlay", text=btn_text, toggle=True, icon=btn_icon)

        # ── Mode toolbar: Coordinator ⇄ Artist + Live ────────────────────────
        aux_row = layout.row(align=True)
        if mc.coordinator_mode:
            aux_row.prop(mc, "coordinator_mode", text="Artist Mode",
                         toggle=True, icon="USER")
        else:
            aux_row.prop(mc, "coordinator_mode", text="Coordinator Mode",
                         toggle=True, icon="COMMUNITY")
        aux_row.prop(mc, "live_update", text="Live",
                     toggle=True, icon="FILE_REFRESH")

        # ── Branch: Coordinator Mode ─────────────────────────────────────────
        if mc.coordinator_mode:
            try:
                draw_coordinator_panel(layout, mc, context)
            except Exception as _exc:
                import traceback
                layout.label(text=f"Coordinator error: {_exc}", icon="ERROR")
                print("[STUKACH] draw_coordinator_panel error:")
                traceback.print_exc()
            return

        # ── Hints — compact, single row when both apply ──────────────────────
        _hint_restored = _manager_mod.MeshCheck._state_restored and not mc.show_overlay
        _hint_stale    = _manager_mod.MeshCheck._scene_stale and mc.show_overlay
        _hint_validating = bool(_manager_mod.MeshCheck._validation_queue)
        if _hint_validating:
            done = len(_manager_mod.MeshCheck.objects)
            left = len(_manager_mod.MeshCheck._validation_queue)
            total = done + left
            factor = done / total if total else 1.0
            try:
                mc.validation_progress = factor
            except Exception:
                pass
            layout.prop(mc, "validation_progress", slider=True,
                        text=f"Validating {done}/{total}")
        elif _hint_restored or _hint_stale:
            hint = layout.row()
            hint.scale_y = 0.75
            if _hint_restored and _hint_stale:
                hint.label(text="  Restored — Run to revalidate · scene changed",
                           icon="RECOVER_LAST")
            elif _hint_restored:
                hint.label(text="  Settings restored — press Run to revalidate",
                           icon="RECOVER_LAST")
            else:
                hint.label(text="  Scene changed — re-run to include new objects",
                           icon="FILE_REFRESH")

        # ── Score block (replaces status bar) ───────────────────────────────
        self._draw_score_block(layout, mc)

        # ── Scope buttons ────────────────────────────────────────────────────
        scope_row = layout.row(align=True)
        scope_row.operator("asset_checker.validate_scene",      text="Scene",      icon="WORLD")
        scope_row.operator("asset_checker.validate_collection", text="Collection", icon="OUTLINER_COLLECTION")
        scope_row.operator("asset_checker.clear_validation",    text="Clear",      icon="X")

        box = layout.box()
        box.label(text="Pipeline Checks:", icon="FILE_TEXT")
        # View helper — mirrors Blender's built-in Face Orientation overlay.
        # Replaces the old flipped/invalid normals counters (too many false
        # positives on interior geometry) — one place for all check views.
        fo_split = box.split(factor=0.5, align=True)
        fo_left = fo_split.row(align=True)
        fo_left.prop(mc, "face_orientation", text="Face Orientation",
                     toggle=True, icon='FACESEL')
        fo_right = fo_split.row(align=True)
        fo_right.prop(mc, "scene_units", text="Scene Units", toggle=True)

        # X-Ray — pinned right under the view helpers (author request)
        if prefs:
            xr_row = box.row(align=True)
            xr_row.scale_y = 0.8
            xr_row.prop(prefs, "overlay_xray", text="X-Ray", toggle=True, icon='XRAY')
            off_row = box.row(align=True)
            off_row.scale_y = 0.8
            off_row.prop(prefs, "faces_offset", text="Face Offset")
            off_row.prop(prefs, "points_offset", text="Point Offset")

        mc.draw_options(box)

        if not _manager_mod.MeshCheck.objects:
            return

        # ── Collapsible object-list section header ────────────────────────────
        n_obj    = len(_manager_mod.MeshCheck.objects)
        n_issues = 0
        for _obj, _mc_obj in _manager_mod.MeshCheck.objects.items():
            try:
                _obj.name  # probe — raises ReferenceError if removed
            except ReferenceError:
                continue
            if _get_object_status(_mc_obj, mc) != "clean":
                n_issues += 1

        # ── Pre-compute visible objects (filter) — the section header shows
        # the visible/total split when any filter is active, so it must be
        # known before the header is drawn.
        filter_text = mc.obj_filter_text.lower().strip()
        errors_only = mc.obj_filter_errors_only
        check_filter = mc.obj_filter_check
        filter_active = bool(filter_text) or errors_only or (check_filter and check_filter != "__all__")

        visible = []
        for obj, mc_obj in _manager_mod.MeshCheck.objects.items():
            try:
                obj_name = obj.name
            except ReferenceError:
                continue
            if filter_text and filter_text not in obj_name.lower():
                continue
            obj_status = _get_object_status(mc_obj, mc)
            if errors_only and obj_status == "clean":
                continue
            if check_filter and check_filter != "__all__":
                chk = mc_obj._checks.get(check_filter)
                if not chk or chk.count <= 0:
                    continue
            visible.append((obj, mc_obj, obj_name, obj_status))

        sec_box  = layout.box()
        sec_head = sec_box.row(align=True)

        tria_sec = "TRIA_DOWN" if mc.obj_list_open else "TRIA_RIGHT"
        sec_head.prop(mc, "obj_list_open", text="", icon=tria_sec, emboss=False)

        # Label: "Objects  18   ⚠ 3"  /  "Objects  5 / 18   ⚠ 3" when filtered
        sec_head.label(text="Objects", icon="OBJECT_DATA")
        cnt = sec_head.row()
        cnt.alignment = "RIGHT"
        cnt.label(text=f"{len(visible)} / {n_obj}" if filter_active else str(n_obj))
        if n_issues:
            cnt.label(text=str(n_issues), icon="ERROR")

        if mc.obj_list_open:
            if mc.obj_sort_worst:
                def _issue_score(mc_obj):
                    t = 0
                    for chk_name, checker in mc_obj._checks.items():
                        if getattr(mc, chk_name, False):
                            t += checker.count
                    return t
                visible.sort(key=lambda t: -_issue_score(t[1]))

            # ── Filters slim row + collapse icon right ──────────────────────
            srow = sec_box.split(factor=0.62)
            frow = srow.row(align=True)
            frow.prop(mc, "obj_filter_errors_only", text="Issues", icon="FILTER", toggle=True)
            frow.prop(mc, "obj_sort_worst", text="", icon="SORT_DESC")
            frow.prop(mc, "obj_filter_check", text="")
            rrow = srow.row(align=True)
            rrow.alignment = "RIGHT"

            def _stat(o):
                try:
                    return bool(o.mesh_check_statistics)
                except ReferenceError:
                    return False

            any_open = any(_stat(o) for o in _manager_mod.MeshCheck.objects)
            col_icon = "TRIA_DOWN"   if any_open else "TRIA_RIGHT"
            rrow.operator("asset_checker.collapse_objects", text="",
                          icon=col_icon, emboss=False)

            # ── Object list: By-Type style rows ──────────────────────────────
            _BADGE = {"critical": "ERROR", "warning": "INFO", "clean": "CHECKMARK"}

            if not visible and not filter_text:
                sec_box.label(text="All objects clean", icon="CHECKMARK")

            from .properties import get_obj_ignore_list

            for obj, mc_obj, obj_name, obj_status in visible:
                try:
                    stat = obj.mesh_check_statistics
                except ReferenceError:
                    continue

                n_ignored = len(get_obj_ignore_list(obj))

                n_bad = 0
                for _cn, _chk in mc_obj._checks.items():
                    if getattr(mc, _cn, False) and category_enabled(_cn):
                        n_bad += _chk.count

                # each object in its own frame — meshes must not merge into
                # a wall of rows
                ob_box = sec_box.box()
                row = ob_box.row(align=True)
                row.alert = (obj_status == "critical")
                tria = "TRIA_DOWN" if stat else "TRIA_RIGHT"
                row.prop(obj, "mesh_check_statistics",
                         text=f"{obj_name}  ({n_bad})", icon=tria, emboss=False)
                rr = row.row(align=True)
                rr.alignment = "RIGHT"
                if n_ignored and not stat:
                    ig = rr.row(align=True)
                    ig.enabled = False
                    ig.label(text=str(n_ignored), icon="HIDE_ON")
                rr.label(text="", icon=_BADGE[obj_status])

                if stat:
                    try:
                        ob_box.indent(level=1)
                    except Exception:
                        pass
                    self._draw_object_details(ob_box, obj, mc_obj, mc)
                    try:
                        ob_box.indent(level=0)
                    except Exception:
                        pass

        # ── Check presets — native dropdown + save/remove + share ───────────
        preset_row = layout.row(align=True)
        preset_row.menu("ASSET_CHECKER_MT_presets", text="Presets", icon="PRESET")
        preset_row.separator(factor=0.4)
        preset_row.operator("asset_checker.preset_add",    text="", icon="ADD",    emboss=False)
        preset_row.operator("asset_checker.preset_remove", text="", icon="REMOVE", emboss=False)
        # EXPORT opens a submenu listing each saved preset (per-preset export)
        preset_row.menu("ASSET_CHECKER_MT_preset_export", text="", icon="EXPORT")
        preset_row.operator("asset_checker.preset_import", text="", icon="IMPORT", emboss=False)

        # Ignored Issues block — shown only when there are active ignores
        _draw_ignore_list_block(layout, mc)

        # Invalid Naming block — shown when any naming check is active
        if mc.obj_naming or mc.col_naming:
            self._draw_naming_issues(layout, mc)

        # Asset Status — bottom-of-panel pipeline verdict
        self._draw_asset_status(layout, mc)

        # ── Export / Pre-flight / Checkpoint ─────────────────────────────────
        from .properties import _AC_CHECKPOINT_KEY
        has_results = bool(_manager_mod.MeshCheck.objects)
        cp_exists   = bool(context.scene.get(_AC_CHECKPOINT_KEY))

        exp_box = layout.box()

        # Labels in a fixed-width column so buttons start at the same X
        d_row = exp_box.split(factor=0.32, align=True)
        d_left = d_row.column()
        d_left.label(text="Export", icon="EXPORT")
        d_right = d_row.row(align=True)
        d_right.enabled = has_results
        for fmt, lbl in (('JSON', 'JSON'), ('CSV', 'CSV'), ('HTML', 'HTML')):
            op = d_right.operator("asset_checker.export_report", text=lbl)
            op.fmt = fmt

        d_row = exp_box.split(factor=0.32, align=True)
        d_left = d_row.column()
        d_left.label(text="Pre-flight", icon="CHECKMARK")
        d_right = d_row.row(align=True)
        d_right.enabled = has_results
        op_fbx = d_right.operator("asset_checker.preflight_export", text="FBX", icon="EXPORT")
        op_fbx.fmt = 'FBX'
        op_usd = d_right.operator("asset_checker.preflight_export", text="USD", icon="EXPORT")
        op_usd.fmt = 'USD'

        d_row = exp_box.split(factor=0.32, align=True)
        d_left = d_row.column()
        d_left.label(text="Checkpoint", icon="BOOKMARKS")
        d_right = d_row.row(align=True)
        d_right.operator("asset_checker.save_checkpoint",
                         text="Update" if cp_exists else "Save", icon="FILE_TICK")
        d_right.operator("asset_checker.load_checkpoint", text="", icon="IMPORT")
        if cp_exists:
            d_right.operator("asset_checker.clear_checkpoint", text="", icon="X", emboss=False)

        dbg_row = exp_box.row(align=True)
        dbg_row.scale_y = 0.8
        dbg_row.alignment = "RIGHT"
        dbg_row.operator("asset_checker.copy_debug_info",
                         text="Debug Info", icon="CONSOLE", emboss=False)


class ASSET_CHECKER_PT_UV_Panel(bpy.types.Panel):
    """STUKACH UV-панель в редакторе UV."""

    bl_label = f"STUKACH v{_ADDON_VERSION}"
    bl_idname = "ASSET_CHECKER_PT_UV_Panel"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "STUKACH"

    _UV_CHECKS = (
        "uv_single_set", "uv_overlap", "uv_micro_shell",
        "uv_texel_density", "uv_stretch", "uv_padding", "uv_udim_bounds",
        "uv_material_udim",
    )

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        mc = context.window_manager.mesh_check_props



        btn_text = "STUKACH ACTIVE" if mc.show_overlay else "RUN STUKACH"
        btn_icon = "RADIOBUT_ON"    if mc.show_overlay else "PLAY"
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.prop(mc, "show_overlay", text=btn_text, toggle=True, icon=btn_icon)

        addon_name = __name__.rsplit(".", 1)[0]
        try:
            prefs = context.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None

        # ── UV map naming / rename (PROKLADKA-style DCC conventions) ─────────
        # Placed at the very top so it never gets lost under long check/object
        # lists below.
        if _manager_mod.MeshCheck.objects:
            from collections import Counter
            _names = Counter()
            for _obj in _manager_mod.MeshCheck.objects:
                try:
                    for _l in _obj.data.uv_layers:
                        _names[_l.name] += 1
                except (ReferenceError, AttributeError):
                    continue
            name_box = layout.box()
            name_box.label(text="UV Map Names:", icon="UV_DATA")
            if _names:
                name_box.label(text="  ·  ".join(f"{n} ×{c}" for n, c in _names.most_common()),
                               icon="FONT_DATA")
                rn_row = name_box.row(align=True)
                rn_row.prop(mc, "uv_rename_target", text="")
                rn_row.operator("asset_checker.uv_rename", text="Rename")

        # UV-чеки
        box = layout.box()
        box.label(text="UV Checks", icon="UV")
        col_a = box.column(align=True)
        for check in self._UV_CHECKS:
            r = col_a.row(align=True)
            icon = "CHECKBOX_HLT" if getattr(mc, check, False) else "CHECKBOX_DEHLT"
            r.prop(mc, check, icon=icon, emboss=False,
                   text=pretty_name(check))
            # Expanding spacer: keeps the name left-aligned, swatch right
            r.label(text="")
            if prefs and hasattr(prefs, f"{check}_color"):
                c = r.row()
                c.scale_x = 0.15
                c.scale_y = 0.8
                c.alignment = "RIGHT"
                c.prop(prefs, f"{check}_color", text="")

        # Texel Density quick settings (shown when TD check is active)
        if prefs and getattr(mc, "uv_texel_density", False):
            import math as _math
            td_box = layout.box()
            td_box.label(text="Texel Density Settings", icon="UV_DATA")
            for lbl_text, prop_id, suffix in (
                    ("Tex Size:",  "uv_td_texture_size", ""),
                    ("Target:",    "uv_td_target",       "px/cm"),
                    ("Tolerance:", "uv_td_tolerance",    "%")):
                d_row = td_box.split(factor=0.35, align=True)
                d_left = d_row.column()
                d_left.label(text=lbl_text)
                d_right = d_row.row(align=True)
                d_right.prop(prefs, prop_id, text="")
                if suffix:
                    d_right.label(text=suffix)

            # ── UV Space + Density summary ──────────────────────────────
            td_box.separator(factor=0.5)

            # Scope toggle: All Objects ↔ Active Object
            scope_row = td_box.row(align=True)
            scope_row.prop(
                mc, "uv_td_scope_active",
                text="Active Object" if mc.uv_td_scope_active else "All Objects",
                icon="OBJECT_DATA" if mc.uv_td_scope_active else "MESH_DATA",
                toggle=True,
            )

            # Gather UV area + world area for chosen scope
            _total_uv    = 0.0
            _total_world = 0.0
            if mc.uv_td_scope_active:
                _active = context.object
                _mc_o   = _manager_mod.MeshCheck.objects.get(_active) if _active else None
                if _mc_o:
                    _ch = _mc_o._checks.get("uv_texel_density")
                    if _ch:
                        _total_uv    = getattr(_ch, '_uv_area',    0.0)
                        _total_world = getattr(_ch, '_world_area', 0.0)
            else:
                for _mc_o in _manager_mod.MeshCheck.objects.values():
                    _ch = _mc_o._checks.get("uv_texel_density")
                    if _ch:
                        _total_uv    += getattr(_ch, '_uv_area',    0.0)
                        _total_world += getattr(_ch, '_world_area', 0.0)

            stats_col = td_box.column(align=True)
            stats_col.label(
                text=f"UV Space:  {_total_uv * 100.0:.2f} %",
                icon="UV_DATA",
            )
            if _total_world > 1e-10 and _total_uv > 1e-10:
                _TD_SIZES = {'0': 512, '1': 1024, '2': 2048, '3': 4096}
                _tex_sz = _TD_SIZES.get(prefs.uv_td_texture_size, 2048)
                try:
                    _sl = bpy.context.scene.unit_settings.scale_length or 1.0
                except Exception:
                    _sl = 1.0
                _agg_td = _tex_sz * _math.sqrt(_total_uv) / (_math.sqrt(_total_world) * 100.0 * _sl)
                stats_col.label(text=f"Density:   {_agg_td:.2f} px/cm", icon="GRAPH")
            else:
                stats_col.label(text="Density:   N/A", icon="GRAPH")

        # UV Padding quick settings + UDIM stats (shown when padding check is active)
        if getattr(mc, "uv_padding", False):
            pad_box = layout.box()
            pad_box.label(text="UV Padding Settings", icon="UV_FACESEL")
            if prefs:
                row = pad_box.row(align=True)
                row.label(text="Tex Size:")
                row.prop(prefs, "uv_padding_texture_size", text="")
                row = pad_box.row(align=True)
                row.label(text="Shell (px):")
                row.prop(prefs, "uv_padding_shell_px", text="")
                row = pad_box.row(align=True)
                row.label(text="Tile border (px):")
                row.prop(prefs, "uv_padding_tile_px", text="")

            # ── UDIM Padding Map ─────────────────────────────────────────────
            try:
                from .core import _uv_padding_tile_stats
                _pad_stats = _uv_padding_tile_stats
            except Exception:
                _pad_stats = {}

            if _pad_stats:
                pad_box.separator(factor=0.4)
                # Collapsible header
                hdr = pad_box.row(align=True)
                _tria_p = "TRIA_DOWN" if mc.uv_padding_stats_open else "TRIA_RIGHT"
                hdr.prop(mc, "uv_padding_stats_open",
                         text="", icon=_tria_p, emboss=False)

                # Count total bad tiles for the badge
                _n_bad_tiles = sum(
                    1 for s in _pad_stats.values()
                    if s['bad_shell'] > 0 or s['bad_tile'] > 0
                )
                _hdr_text = f"UDIM Padding Map  ({len(_pad_stats)} tile{'s' if len(_pad_stats) != 1 else ''})"
                hdr.label(text=_hdr_text, icon="TEXTURE")
                if _n_bad_tiles:
                    _hr = hdr.row()
                    _hr.alignment = "RIGHT"
                    _hr.label(text=str(_n_bad_tiles), icon="ERROR")

                if mc.uv_padding_stats_open:
                    _sorted_tiles = sorted(
                        _pad_stats.items(),
                        key=lambda kv: 1001 + kv[0][0] + kv[0][1] * 10,
                    )
                    for (tu, tv), st in _sorted_tiles:
                        _udim_num = 1001 + tu + tv * 10
                        _mb       = st['min_border_px']
                        _ms       = st.get('min_shell_px')    # float or None
                        _n_isl    = st['n_islands']
                        _n_obj    = st['n_objects']
                        _bs       = st['bad_shell']
                        _bt       = st['bad_tile']
                        _any_bad  = _bs > 0 or _bt > 0

                        # ── Per-tile sub-box ─────────────────────────────────
                        tile_box = pad_box.box()

                        # Row 1: UDIM  |  N isl, N obj  |  status icon
                        r1 = tile_box.row(align=True)
                        _udim_icon = "ERROR" if _any_bad else "CHECKMARK"
                        r1.label(text=f"UDIM {_udim_num}", icon=_udim_icon)
                        _info = f"{_n_isl} isl  {_n_obj} obj"
                        r1.label(text=_info)
                        if _any_bad:
                            _viol = []
                            if _bs:
                                _viol.append(f"{_bs} shell")
                            if _bt:
                                _viol.append(f"{_bt} border")
                            _rr = r1.row()
                            _rr.alignment = "RIGHT"
                            _rr.label(text=", ".join(_viol))

                        # Row 2: Shell spacing  |  Border spacing
                        r2 = tile_box.row(align=True)
                        r2.scale_y = 0.85

                        # Shell
                        if _ms is not None:
                            _sh_icon = "ERROR" if _bs > 0 else "CHECKMARK"
                            r2.label(
                                text=f"Shell: {_ms:.2f}px",
                                icon=_sh_icon,
                            )
                        else:
                            # Too dense for exact measurement — show threshold direction
                            _sh_icon = "ERROR" if _bs > 0 else "CHECKMARK"
                            _sh_text = "Shell: <..." if _bs > 0 else "Shell: OK"
                            r2.label(text=_sh_text, icon=_sh_icon)

                        # Border
                        _bd_icon = "ERROR" if _bt > 0 else "CHECKMARK"
                        r2.label(text=f"Border: {_mb:.2f}px", icon=_bd_icon)

        if not _manager_mod.MeshCheck.objects:
            layout.box().label(text="Awaiting suspects.", icon="GHOST_ENABLED")
            return

        # ── Collapsible object-list section ──────────────────────────────────
        n_obj    = len(_manager_mod.MeshCheck.objects)
        n_issues = sum(
            1 for mc_obj in _manager_mod.MeshCheck.objects.values()
            if any(
                getattr(mc, ch, False) and _get_check_count(mc_obj, ch) > 0
                for ch in self._UV_CHECKS
            )
        )

        sec_box  = layout.box()
        sec_head = sec_box.row(align=True)

        tria_sec = "TRIA_DOWN" if mc.uv_obj_list_open else "TRIA_RIGHT"
        sec_head.prop(mc, "uv_obj_list_open", text="", icon=tria_sec, emboss=False)
        sec_head.label(text="Objects", icon="OBJECT_DATA")

        cnt = sec_head.row()
        cnt.alignment = "RIGHT"
        cnt.label(text=str(n_obj))
        if n_issues:
            cnt.label(text=str(n_issues), icon="ERROR")

        if mc.uv_obj_list_open:
            for obj, mc_obj in _manager_mod.MeshCheck.objects.items():
                try:
                    obj_name = obj.name
                except ReferenceError:
                    continue

                obj_status = _get_object_status(mc_obj, mc)
                _BADGE = {"critical": "ERROR", "warning": "INFO", "clean": "CHECKMARK"}

                ob_box  = sec_box.box()
                ob_head = ob_box.row()
                split   = ob_head.split(factor=0.88)
                split.label(text=obj_name, icon="MESH_DATA")
                right = split.row()
                right.alignment = "RIGHT"
                right.label(text="", icon=_BADGE[obj_status])

                any_active = False
                for check in self._UV_CHECKS:
                    if not getattr(mc, check, False):
                        continue
                    any_active = True
                    checker = mc_obj._checks.get(check)
                    if checker is None:
                        continue
                    count = checker.count
                    threshold = _get_threshold(check, prefs)

                    if count == 0:
                        icon = "CHECKMARK"
                    elif count > threshold:
                        icon = "ERROR"
                    else:
                        icon = "INFO"

                    mt = getattr(checker, 'metric_text', '')
                    label = mt if mt else f"{pretty_name(check)}: {count}"
                    ob_box.label(text=label, icon=icon)

                if not any_active:
                    ob_box.label(text="Enable UV checks above", icon="INFO")

        # ── Material → UDIM map ──────────────────────────────────────────────
        # Aggregate across all tracked objects
        _agg_mat_tiles: dict = {}
        for _mc_o in _manager_mod.MeshCheck.objects.values():
            for _mat, _tiles in getattr(_mc_o, '_mat_udim_map', {}).items():
                if _mat not in _agg_mat_tiles:
                    _agg_mat_tiles[_mat] = set()
                _agg_mat_tiles[_mat].update(_tiles)

        if _agg_mat_tiles:
            mu_box = layout.box()
            mu_box.label(text="Material  →  UDIM", icon="MATERIAL")
            for _mat_name, _tiles in sorted(_agg_mat_tiles.items()):
                _udims = sorted(1001 + tu + tv * 10 for tu, tv in _tiles)
                _udim_str = "  ".join(str(u) for u in _udims)
                _is_sel = mc.mat_udim_selected == _mat_name
                row = mu_box.row(align=True)
                op = row.operator(
                    "asset_checker.highlight_mat_udim",
                    text=_mat_name,
                    icon="RADIOBUT_ON" if _is_sel else "RADIOBUT_OFF",
                    depress=_is_sel,
                )
                op.mat_name = _mat_name
                row.label(text=_udim_str)


def register():
    bpy.utils.register_class(ASSET_CHECKER_PT_Panel)
    bpy.utils.register_class(ASSET_CHECKER_PT_UV_Panel)


def unregister():
    bpy.utils.unregister_class(ASSET_CHECKER_PT_UV_Panel)
    bpy.utils.unregister_class(ASSET_CHECKER_PT_Panel)

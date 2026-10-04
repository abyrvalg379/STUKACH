# -*- coding: utf-8 -*-
"""Scene-context evaluators: names, pivots, parenting."""
from __future__ import annotations

from typing import Optional

from typing import Optional

from ..model import MeshSnapshot, Finding


def check_duplicated_names(snap: MeshSnapshot) -> Optional[Finding]:
    """Short name used by more than one node in the scene (FBX/AYON killers)."""
    n = snap.scene.get("short_names", {}).get(snap.short_name, 0)
    if n <= 1:
        return None
    return Finding("duplicated_names", "BLOCKER", 1, [],
                   metric="'%s' used by %d nodes" % (snap.short_name, n))


def check_shape_names(snap: MeshSnapshot) -> Optional[Finding]:
    """Shape node must be named '<transform>Shape' (Maya convention)."""
    if snap.shape_short == snap.short_name + "Shape":
        return None
    return Finding("shape_names", "WARNING", 1, [],
                   metric="shape '%s' != '%sShape'" % (snap.shape_short, snap.short_name))


def check_trailing_numbers(snap: MeshSnapshot) -> Optional[Finding]:
    """Name ends with digits (pCube1-style leftovers)."""
    name = snap.short_name.split(":")[-1]
    if not (name and name[-1].isdigit()):
        return None
    return Finding("trailing_numbers", "WARNING", 1, [],
                   metric="trailing digits in '%s'" % snap.short_name)


def check_uncentered_pivots(snap: MeshSnapshot, threshold: float = 0.05) -> Optional[Finding]:
    """Rotate pivot far from the WORLD bbox center (fraction of the bbox
    diagonal).

    World semantics (strangler 6a, user-approved): the pivot is compared
    against the bbox of the WORLD-space points — consistent for placed,
    rotated and parented objects.  Requires the adapter to report
    world_matrix; rotate_pivot must be the pivot in world space (Maya
    reports xform rotatePivot ws=True, Blender its matrix translation).
    Without a world matrix the snapshot's own space is used as-is.
    Convention check, INFO: buildings often keep every pivot at world
    origin."""
    rp = snap.rotate_pivot
    if not snap.points:
        return None
    wm = snap.world_matrix
    if len(wm) >= 12:
        def world(p):
            x, y, z = p
            return (wm[0] * x + wm[1] * y + wm[2] * z + wm[3],
                    wm[4] * x + wm[5] * y + wm[6] * z + wm[7],
                    wm[8] * x + wm[9] * y + wm[10] * z + wm[11])
    else:
        # no world matrix reported — the snapshot's own space is used as-is
        def world(p):
            return p
    xs, ys, zs = [], [], []
    for pt in snap.points:
        wx, wy, wz = world(pt)
        xs.append(wx)
        ys.append(wy)
        zs.append(wz)
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    cz = (min(zs) + max(zs)) / 2.0
    diag = ((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2 +
            (max(zs) - min(zs)) ** 2) ** 0.5
    if diag < 1e-9:
        return None
    dist = ((rp[0] - cx) ** 2 + (rp[1] - cy) ** 2 + (rp[2] - cz) ** 2) ** 0.5
    if dist <= diag * threshold:
        return None
    return Finding("uncentered_pivots", "INFO", 1, [],
                   metric="pivot off-center by %.1f%% of bbox" % (dist / diag * 100.0))


def check_parent_geometry(snap: MeshSnapshot) -> Optional[Finding]:
    """Mesh parented under another mesh — breaks export hierarchies."""
    if "mesh" not in snap.parent_types:
        return None
    return Finding("parent_geometry", "WARNING", 1, [],
                   metric="parented under a mesh")


# ── name-convention rules (strangler 5b) ─────────────────────────────────────
# These read names, not geometry: node/shape carry the object/datablock names,
# material_names the material slots (empty = adapter didn't report → N/A,
# the Maya build keeps its own checks until its adapter reports slots).


def check_mesh_data_naming(snap: MeshSnapshot,
                           mesh_suffixes: Optional[List[str]] = None) -> Optional[Finding]:
    """Mesh datablock must be named like its object or carry a mesh suffix
    ('body_geo' object → 'body_mesh' datablock).  N/A without both names."""
    from ..naming import mesh_data_target, validate_mesh_data_name
    suffixes = list(mesh_suffixes) if mesh_suffixes else ["_mesh", "_geo", "_grp"]
    node, datablock = snap.node, snap.shape
    if not node or not datablock:
        return None
    f = validate_mesh_data_name(node, datablock, suffixes)
    if f is None:
        return None
    target = mesh_data_target(node, suffixes)
    return Finding("mesh_data_naming", "WARNING", 1, [],
                   metric="%s  →  %s" % (datablock, target))


def check_mat_suffix(snap: MeshSnapshot,
                     required_suffix: str = "_mat") -> Optional[Finding]:
    """Every material name must carry the pipeline suffix (default '_mat')
    and stay ASCII.  N/A when the adapter reports no material slots."""
    from ..naming import validate_material_name
    if not snap.material_names:
        return None
    bad = [m for m in snap.material_names
           if validate_material_name(m, required_suffix, check_numbering=False)]
    if not bad:
        return None
    extra = " +%d" % (len(bad) - 1) if len(bad) > 1 else ""
    return Finding("mat_suffix", "WARNING", len(bad), [],
                   metric="Mat suffix: '%s'%s" % (bad[0], extra))


def check_mat_numbering(snap: MeshSnapshot) -> Optional[Finding]:
    """Material names must not keep Blender auto-numbering (.001) — stale
    default copies break shader assignment downstream.  N/A without slots."""
    from ..naming import validate_material_name
    if not snap.material_names:
        return None
    bad = [m for m in snap.material_names
           if validate_material_name(m, required_suffix="", check_numbering=True)]
    if not bad:
        return None
    extra = " +%d" % (len(bad) - 1) if len(bad) > 1 else ""
    return Finding("mat_numbering", "WARNING", len(bad), [],
                   metric="Mat numbering: '%s'%s" % (bad[0], extra))

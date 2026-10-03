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
    """Rotate pivot far from the bbox center (fraction of bbox diagonal).

    Convention check, INFO: buildings often keep every pivot at world origin."""
    rp = snap.rotate_pivot
    if not snap.points:
        return None
    xs = [pt[0] for pt in snap.points]
    ys = [pt[1] for pt in snap.points]
    zs = [pt[2] for pt in snap.points]
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

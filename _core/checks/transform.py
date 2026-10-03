# -*- coding: utf-8 -*-
"""Object-transform evaluators, read from the snapshot matrices.

world_matrix covers the full parent chain; local_matrix is the object's own
(basis) transform — scale/rotation rules read the LOCAL one, exactly like
the addon reads obj.scale / obj.rotation_euler.  Rules are N/A when the
adapter didn't report the corresponding matrix."""
from __future__ import annotations

from math import sqrt

from typing import Optional

from ..model import MeshSnapshot, Finding


def _mat3(m):
    return (m[0], m[1], m[2]), (m[4], m[5], m[6]), (m[8], m[9], m[10])


def check_origin_at_zero(snap: MeshSnapshot,
                         threshold: float = 0.001) -> Optional[Finding]:
    """Object origin (pivot point) is not at world zero — world-space
    translation, so parented objects are judged by their real position."""
    wm = snap.world_matrix
    if len(wm) < 16:
        return None
    loc = (wm[12], wm[13], wm[14])
    if all(abs(c) <= threshold for c in loc):
        return None
    return Finding("origin_at_zero", "INFO", 1, [],
                   metric="Origin: (%.3f, %.3f, %.3f)" % loc)


def check_scale(snap: MeshSnapshot, tol: float = 0.001) -> Optional[Finding]:
    """Object scale deviates from 1.0 by more than *tol* on any axis."""
    lm = snap.local_matrix
    if len(lm) < 16:
        return None
    for col in _mat3(lm):
        length = sqrt(col[0] * col[0] + col[1] * col[1] + col[2] * col[2])
        if abs(length - 1.0) > tol:
            return Finding("scale", "BLOCKER", 1, [])
    return None


def check_non_applied_transform(snap: MeshSnapshot,
                                tol: float = 0.001) -> Optional[Finding]:
    """Object carries a rotation that should be applied to the mesh — the
    rotation block of the local matrix differs from identity."""
    lm = snap.local_matrix
    if len(lm) < 16:
        return None
    r = _mat3(lm)
    # column lengths (scale); normalised columns form the pure rotation
    scales = [sqrt(c[0] * c[0] + c[1] * c[1] + c[2] * c[2])
              for c in r]
    for ci in range(3):
        s = scales[ci] or 1.0
        for ri in range(3):
            v = r[ri][ci] / s
            expected = 1.0 if ri == ci else 0.0
            if abs(v - expected) > tol:
                return Finding("non_applied_transform", "BLOCKER", 1, [])
    return None

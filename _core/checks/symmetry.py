# -*- coding: utf-8 -*-
"""Symmetry evaluators — the numpy mirror-key grid (Blender-parity algorithm)."""
from __future__ import annotations

from typing import Optional

from typing import Optional

from ..model import MeshSnapshot, Finding


def check_symmetry(snap: MeshSnapshot, axis: int = 0,
                   threshold: float = 0.001) -> Optional[Finding]:
    """A vertex is asymmetric when its mirror key is absent.

    Coords are rounded to an int grid (threshold = cell size), packed into
    one int64 per vertex and binary-searched in the sorted set."""
    import numpy as np
    n = len(snap.points)
    if n == 0:
        return None
    co_np = np.array(snap.points, dtype=np.float64).reshape(n, 3)

    inv = 1.0 / max(threshold, 1e-9)
    SHIFT = 1_000_000
    SPAN = 2 * SHIFT + 1

    gi = np.round(co_np * inv).astype(np.int64)
    gi = np.clip(gi, -SHIFT, SHIFT)
    gc = gi + SHIFT

    packed = (gc[:, 0] * SPAN + gc[:, 1]) * SPAN + gc[:, 2]
    packed_sorted = np.sort(packed)

    mi = gc.copy()
    mi[:, axis] = (-gi[:, axis]).clip(-SHIFT, SHIFT) + SHIFT
    m_packed = (mi[:, 0] * SPAN + mi[:, 1]) * SPAN + mi[:, 2]

    idx = np.searchsorted(packed_sorted, m_packed)
    idx = np.clip(idx, 0, len(packed_sorted) - 1)
    asym_mask = packed_sorted[idx] != m_packed

    bad = [("vert", int(i)) for i in np.where(asym_mask)[0].tolist()]
    if not bad:
        return None
    rule = {0: "symmetry_x", 1: "symmetry_y", 2: "symmetry_z"}.get(axis, "symmetry")
    return Finding(rule, "INFO", len(bad), bad)

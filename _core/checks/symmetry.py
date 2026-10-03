# -*- coding: utf-8 -*-
"""Symmetry evaluators — the numpy mirror-key grid (Blender-parity algorithm)."""
from __future__ import annotations

from typing import Dict, Iterable, Optional

from ..model import MeshSnapshot, Finding

_RULE_BY_AXIS = {0: "symmetry_x", 1: "symmetry_y", 2: "symmetry_z"}


def _mirror_search(snap: MeshSnapshot, axes: Iterable[int],
                   threshold: float) -> Dict[int, Dict]:
    """Shared pass for every symmetry evaluator: coords → grid → packed int64
    keys → one sort.  Returns {axis: {n, asym_mask}} for the per-axis
    evaluators to turn into Findings."""
    import numpy as np
    n = len(snap.points)
    if n == 0:
        return {axis: {"n": 0, "asym_mask": None} for axis in axes}
    co_np = np.array(snap.points, dtype=np.float64).reshape(n, 3)

    inv = 1.0 / max(threshold, 1e-9)
    SHIFT = 1_000_000
    SPAN = 2 * SHIFT + 1

    gi = np.round(co_np * inv).astype(np.int64)
    gi = np.clip(gi, -SHIFT, SHIFT)
    gc = gi + SHIFT

    packed = (gc[:, 0] * SPAN + gc[:, 1]) * SPAN + gc[:, 2]
    packed_sorted = np.sort(packed)

    out = {}
    for axis in axes:
        mi = gc.copy()
        mi[:, axis] = (-gi[:, axis]).clip(-SHIFT, SHIFT) + SHIFT
        m_packed = (mi[:, 0] * SPAN + mi[:, 1]) * SPAN + mi[:, 2]
        idx = np.searchsorted(packed_sorted, m_packed)
        idx = np.clip(idx, 0, len(packed_sorted) - 1)
        out[axis] = {"n": n, "asym_mask": packed_sorted[idx] != m_packed}
    return out


def _to_finding(rule: str, probe: Dict) -> Optional[Finding]:
    import numpy as np
    mask = probe["asym_mask"]
    if mask is None or not mask.any():
        return None
    bad = [("vert", int(i)) for i in np.where(mask)[0].tolist()]
    return Finding(rule, "INFO", len(bad), bad)


def check_symmetry_batch(snap: MeshSnapshot, axes: Iterable[int] = (0, 1, 2),
                         threshold: float = 0.001) -> Dict[int, Optional[Finding]]:
    """Every requested symmetry axis in ONE shared pass.

    Coords convert to numpy once and the packed key set sorts once; each
    axis only mirrors its component and binary-searches.  Batched consumers
    (the Blender addon runs X/Y/Z per object) get the single conversion +
    single sort instead of three."""
    probes = _mirror_search(snap, axes, threshold)
    return {axis: _to_finding(_RULE_BY_AXIS.get(axis, "symmetry"), probe)
            for axis, probe in probes.items()}


def check_symmetry(snap: MeshSnapshot, axis: int = 0,
                   threshold: float = 0.001) -> Optional[Finding]:
    """A vertex is asymmetric when its mirror key is absent.

    Coords are rounded to an int grid (threshold = cell size), packed into
    one int64 per vertex and binary-searched in the sorted set."""
    return check_symmetry_batch(snap, axes=(axis,), threshold=threshold)[axis]

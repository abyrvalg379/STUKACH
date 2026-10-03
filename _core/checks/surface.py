# -*- coding: utf-8 -*-
"""Surface evaluators: aspect ratio, hard edges (tranche 2)."""
from __future__ import annotations

import math
from typing import Optional

from typing import Optional

from ..model import MeshSnapshot, Finding


def check_face_aspect_ratio(snap: MeshSnapshot, threshold: float = 6.0) -> Optional[Finding]:
    """Quad faces whose aspect ratio exceeds *threshold* (tris/ngons skip).

    ratio = max(avg_longer_pair, avg_shorter_pair) / min(...) over the two
    pairs of opposite quad edges."""
    pts = snap.points
    bad = []
    for fi, verts in enumerate(snap.face_verts):
        if len(verts) != 4:
            continue
        a, b, c, d = (pts[v] for v in verts)
        e0 = math.sqrt((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2)
        e1 = math.sqrt((b[0]-c[0])**2 + (b[1]-c[1])**2 + (b[2]-c[2])**2)
        e2 = math.sqrt((c[0]-d[0])**2 + (c[1]-d[1])**2 + (c[2]-d[2])**2)
        e3 = math.sqrt((d[0]-a[0])**2 + (d[1]-a[1])**2 + (d[2]-a[2])**2)
        avg_a = (e0 + e2) * 0.5
        avg_b = (e1 + e3) * 0.5
        if avg_a < 1e-10 or avg_b < 1e-10:
            continue
        ratio = avg_a / avg_b if avg_a > avg_b else avg_b / avg_a
        if ratio > threshold:
            bad.append(("face", fi))
    if not bad:
        return None
    return Finding("face_aspect_ratio", "INFO", len(bad), bad)

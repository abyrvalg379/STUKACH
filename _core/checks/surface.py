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

# ── sharp edges (strangler 6b) ───────────────────────────────────────────────

def check_sharp_edges(snap: MeshSnapshot, threshold_deg: float = 60.0,
                      bevel_ratio: float = 0.005,
                      skip_custom_normals: bool = True) -> Optional[Finding]:
    """Sharp corners (dihedral >= *threshold_deg*) whose edge is still marked
    smooth — smooth shading across a sharp corner shades wrong.  Only MISSED
    sharp edges are flagged; already-marked ones are meaningless on hardsurf.

    Skips (user-approved 6a/6b semantics, from the Blender addon):
      * custom-normal-driven shading (``custom_normal_driven``) — the sharp
        flag does not affect the render there; a count=0 Finding with the
        skip metric is returned so direct callers can show it;
      * edges whose BOTH faces are flat-shaded — they render hard anyway;
      * bevel-aware (``bevel_ratio``): a smooth sharp edge hugging a NARROW
        strip face (face area / longest edge below *bevel_ratio* of the bbox
        diagonal, both LOCAL) is a deliberate chamfer.

    Manifold edges only (edge_conn == 2).  Maya parity: same angle math on
    edge_smooth; set bevel_ratio=0 to disable the bevel skip (the Maya build
    never had one)."""
    from math import acos, sqrt
    if skip_custom_normals and snap.custom_normal_driven:
        return Finding("sharp_edges", "WARNING", 0, [],
                       metric="skipped: shading is custom-normal driven")

    pts = snap.points
    if not pts or not snap.edges:
        return None
    n_faces = len(snap.face_verts)
    if not n_faces:
        return None
    have_face_smooth = len(snap.face_smooth) == n_faces

    if bevel_ratio > 0.0:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        zs = [p[2] for p in pts]
        diag = sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2 +
                    (max(zs) - min(zs)) ** 2)
        if diag <= 1e-9:
            diag = 1.0
        strip_max = bevel_ratio * diag
    else:
        strip_max = None

    edge_faces = snap.edge_faces()   # lazy shared map (corner-walk derived)

    normals: list = [None] * n_faces

    def face_normal(fi):
        n = normals[fi]
        if n is not None:
            return n or None
        nx = ny = nz = 0.0
        vs = snap.face_verts[fi]
        for i in range(len(vs)):
            a = pts[vs[i - 1]]
            b = pts[vs[i]]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        length = sqrt(nx * nx + ny * ny + nz * nz)
        if length < 1e-12:
            normals[fi] = ()   # degenerate — memoized as "no normal"
            return None
        normals[fi] = (nx / length, ny / length, nz / length)
        return normals[fi]

    def is_strip(fi):
        """Narrow strip face (area / longest edge below strip_max)."""
        if strip_max is None:
            return False
        area = snap.face_area[fi] if (fi < len(snap.face_area)
                                      and snap.face_area[fi] > 0.0) else None
        if area is None:
            # recompute unsigned area from the fan triangles
            vs = snap.face_verts[fi]
            ax, ay, az = pts[vs[0]]
            area = 0.0
            for i in range(1, len(vs) - 1):
                b = pts[vs[i]]
                c = pts[vs[(i + 1) % len(vs)]]
                ux, uy, uz = b[0] - ax, b[1] - ay, b[2] - az
                vx, vy, vz = c[0] - ax, c[1] - ay, c[2] - az
                cx = uy * vz - uz * vy
                cy = uz * vx - ux * vz
                cz = ux * vy - uy * vx
                area += sqrt(cx * cx + cy * cy + cz * cz) * 0.5
        longest = 0.0
        vs = snap.face_verts[fi]
        for i in range(len(vs)):
            a = pts[vs[i - 1]]
            b = pts[vs[i]]
            d = sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 +
                     (a[2] - b[2]) ** 2)
            if d > longest:
                longest = d
        if longest <= 0.0:
            return False
        return area / longest < strip_max

    cos_threshold = None
    bad = []
    for eid, faces in edge_faces.items():
        if eid >= len(snap.edge_smooth) or eid >= len(snap.edge_conn):
            continue
        if not snap.edge_smooth[eid] or snap.edge_conn[eid] != 2:
            continue
        if len(faces) != 2:
            continue
        if have_face_smooth:
            if not snap.face_smooth[faces[0]] and not snap.face_smooth[faces[1]]:
                continue   # flat on both sides — renders hard regardless
        if is_strip(faces[0]) or is_strip(faces[1]):
            continue   # deliberate chamfer
        n0 = face_normal(faces[0])
        n1 = face_normal(faces[1])
        if n0 is None or n1 is None:
            continue
        if cos_threshold is None:
            from math import cos, radians
            cos_threshold = cos(radians(threshold_deg))
        dot = n0[0] * n1[0] + n0[1] * n1[1] + n0[2] * n1[2]
        if dot < cos_threshold:
            bad.append(("edge", eid))
    if not bad:
        return None
    return Finding("sharp_edges", "WARNING", len(bad), bad)

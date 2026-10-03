# -*- coding: utf-8 -*-
"""UV evaluators: uv-set count, UV islands, UDIM bounds, micro shells.

Island welding is Blender-parity: two faces share an island when they have
the same 3-D edge AND identical UV positions (rounded to 6 decimals) on that
edge's corners.  Faces the adapter reports without UVs (None) are excluded
from islands entirely — missing_uvs owns that verdict."""
from __future__ import annotations

from typing import List, Optional

from ..model import MeshSnapshot, Finding


def uv_islands(snap: MeshSnapshot, precision: int = 6) -> Optional[List[int]]:
    """UV-island id per face (union-find), or None without an active UV set.

    Loop order follows the face contour: corner i's UV neighbours are
    corners (i-1, i+1) of the same face, so loop indices are derived from
    the per-face flat uv tuples."""
    face_uvs = snap.face_uvs
    if not face_uvs or all(uvs is None for uvs in face_uvs):
        return None

    lu: List[Optional[tuple]] = []
    for pi, uvs in enumerate(face_uvs):
        nv = len(snap.face_verts[pi]) if pi < len(snap.face_verts) else 0
        if uvs is None:
            # keep the loop-index alignment: one entry per corner
            lu.extend([None] * nv)
            continue
        for i in range(0, len(uvs), 2):
            lu.append((round(uvs[i], precision), round(uvs[i + 1], precision)))

    n = len(face_uvs)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edge_map = {}
    loop_base = 0
    for pi, verts in enumerate(snap.face_verts):
        uvs = face_uvs[pi]
        if uvs is None:
            continue
        nv = len(verts)
        for i in range(nv):
            li0 = loop_base + i
            li1 = loop_base + (i + 1) % nv
            v0, v1 = verts[i], verts[(i + 1) % nv]
            u0, u1 = lu[li0], lu[li1]
            if v0 < v1:
                edge_map.setdefault((v0, v1), []).append((pi, u0, u1))
            else:
                edge_map.setdefault((v1, v0), []).append((pi, u1, u0))
        loop_base += nv

    for entries in edge_map.values():
        if len(entries) < 2:
            continue
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                pa, ua0, ua1 = entries[i]
                pb, ub0, ub1 = entries[j]
                if ua0 == ub0 and ua1 == ub1:
                    ra, rb = find(pa), find(pb)
                    if ra != rb:
                        parent[ra] = rb

    roots = {}
    out = [-1] * n
    for pi in range(n):
        if face_uvs[pi] is None:
            continue
        r = find(pi)
        if r not in roots:
            roots[r] = len(roots)
        out[pi] = roots[r]
    return out


def check_uv_single_set(snap: MeshSnapshot, expected: int = 1) -> Optional[Finding]:
    """Exactly one UV set on the mesh (extra sets double the texture work;
    none at all is missing_uvs' territory — this rule just counts sets)."""
    n = snap.uv_set_count
    if n is None or n == expected:
        return None
    return Finding("uv_single_set", "WARNING", 1,
                   metric="%d UV set(s)" % n if n else "no UV set")


def _island_uv_bbox(snap: MeshSnapshot, p2i: List[int],
                    n_islands: int):
    """Per-island UV bbox: (u_min, v_min, u_max, v_max) lists.

    Non-finite UV values (NaN leftovers) are skipped — they cannot legally
    participate in tile math, and missing_uvs owns garbage-UV verdicts."""
    from math import isfinite
    INF = float("inf")
    u_min = [INF] * n_islands
    v_min = [INF] * n_islands
    u_max = [-INF] * n_islands
    v_max = [-INF] * n_islands
    for fi, uvs in enumerate(snap.face_uvs):
        isl = p2i[fi]
        if isl < 0 or uvs is None:
            continue
        for i in range(0, len(uvs), 2):
            u, v = uvs[i], uvs[i + 1]
            if not (isfinite(u) and isfinite(v)):
                continue
            if u < u_min[isl]: u_min[isl] = u
            if u > u_max[isl]: u_max[isl] = u
            if v < v_min[isl]: v_min[isl] = v
            if v > v_max[isl]: v_max[isl] = v
    return u_min, v_min, u_max, v_max


def check_uv_udim_bounds(snap: MeshSnapshot, eps: float = 1e-5) -> Optional[Finding]:
    """UV islands whose bbox spans more than one 1x1 UDIM tile — such shells
    land on several tiles and break single-tile texture assignments."""
    import math
    from math import isfinite
    p2i = uv_islands(snap)
    if p2i is None:
        return None
    n_islands = max(p2i) + 1
    u_min, v_min, u_max, v_max = _island_uv_bbox(snap, p2i, n_islands)
    bad_faces: List[tuple] = []
    bad_count = 0
    for isl in range(n_islands):
        if not (isfinite(u_min[isl]) and isfinite(v_min[isl])
                and isfinite(u_max[isl]) and isfinite(v_max[isl])):
            continue   # island with no finite UVs — nothing to measure
        if (math.floor(u_max[isl] - eps) > math.floor(u_min[isl] + eps)
                or math.floor(v_max[isl] - eps) > math.floor(v_min[isl] + eps)):
            bad_count += 1
            bad_faces.extend(("face", fi) for fi, i in enumerate(p2i) if i == isl)
    if not bad_count:
        return None
    return Finding("uv_udim_bounds", "BLOCKER", bad_count, bad_faces)


def check_uv_micro_shell(snap: MeshSnapshot,
                         island_area: float = 1e-5) -> Optional[Finding]:
    """UV islands whose total UV area is below *island_area* — collapsed or
    forgotten shells too small to receive meaningful texture detail
    (≈ 6px x 6px at 2048 for the default threshold).  Area sums the fan
    triangles of each face's UV contour."""
    p2i = uv_islands(snap)
    if p2i is None:
        return None
    n_islands = max(p2i) + 1
    areas = [0.0] * n_islands
    for fi, uvs in enumerate(snap.face_uvs):
        isl = p2i[fi]
        if isl < 0 or uvs is None:
            continue
        nv = len(uvs) // 2
        if nv < 3:
            continue
        ax, ay = uvs[0], uvs[1]
        for i in range(1, nv - 1):
            bx, by = uvs[i * 2], uvs[i * 2 + 1]
            cx, cy = uvs[(i + 1) * 2], uvs[(i + 1) * 2 + 1]
            areas[isl] += abs((bx - ax) * (cy - ay) - (cx - ax) * (by - ay)) * 0.5
    bad = [isl for isl in range(n_islands) if areas[isl] < island_area]
    if not bad:
        return None
    bad_set = set(bad)
    bad_faces = [("face", fi) for fi, i in enumerate(p2i) if i in bad_set]
    return Finding("uv_micro_shell", "WARNING", len(bad), bad_faces)

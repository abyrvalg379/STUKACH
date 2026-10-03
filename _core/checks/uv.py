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


# ── UV overlap (inter-island) ────────────────────────────────────────────────
# Exact 2-D tests ported 1:1 from the addon implementation (strangler 4b) —
# strict epsilons are semantic: on-edge touches are NOT overlaps.


def _uv_point_in_tri_strict(p, a, b, c) -> bool:
    """Point P strictly inside triangle ABC (2D); on-edge returns False."""
    def cross(o, u, v):
        return (u[0] - o[0]) * (v[1] - o[1]) - (u[1] - o[1]) * (v[0] - o[0])
    d1, d2, d3 = cross(a, b, p), cross(b, c, p), cross(c, a, p)
    eps = 1e-9
    return (d1 > eps and d2 > eps and d3 > eps) or (d1 < -eps and d2 < -eps and d3 < -eps)


def _seg_intersect_2d(p1, p2, p3, p4) -> bool:
    """True if segment p1-p2 strictly intersects segment p3-p4 (not at shared endpoints)."""
    def cross2d(a, b):
        return a[0] * b[1] - a[1] * b[0]
    rx = p2[0] - p1[0]
    ry = p2[1] - p1[1]
    sx = p4[0] - p3[0]
    sy = p4[1] - p3[1]
    rxs = cross2d((rx, ry), (sx, sy))
    if abs(rxs) < 1e-10:
        return False  # parallel or collinear
    qpx = p3[0] - p1[0]
    qpy = p3[1] - p1[1]
    t = cross2d((qpx, qpy), (sx, sy)) / rxs
    u = cross2d((qpx, qpy), (rx, ry)) / rxs
    eps = 1e-9
    return eps < t < 1.0 - eps and eps < u < 1.0 - eps


def _uv_tris_truly_overlap(t1, t2) -> bool:
    """True if two UV triangles genuinely overlap (not just share an edge).

    1. Any vertex of t1 strictly inside t2 (and vice versa).
    2. Exact-duplicate / stacked triangles — centroid test.
    3. X-crossing: edges cross without any vertex containment."""
    a1, b1, c1 = t1
    a2, b2, c2 = t2
    for p in (a1, b1, c1):
        if _uv_point_in_tri_strict(p, a2, b2, c2):
            return True
    for p in (a2, b2, c2):
        if _uv_point_in_tri_strict(p, a1, b1, c1):
            return True
    mid1 = ((a1[0] + b1[0] + c1[0]) / 3, (a1[1] + b1[1] + c1[1]) / 3)
    if _uv_point_in_tri_strict(mid1, a2, b2, c2):
        return True
    mid2 = ((a2[0] + b2[0] + c2[0]) / 3, (a2[1] + b2[1] + c2[1]) / 3)
    if _uv_point_in_tri_strict(mid2, a1, b1, c1):
        return True
    edges1 = ((a1, b1), (b1, c1), (c1, a1))
    edges2 = ((a2, b2), (b2, c2), (c2, a2))
    for e1 in edges1:
        for e2 in edges2:
            if _seg_intersect_2d(e1[0], e1[1], e2[0], e2[1]):
                return True
    return False


def _uv_grid_candidates(aabbs, tri_poly, tri_island, grid_size: int = 128):
    """2D spatial-hash broad-phase over pre-computed AABB lists.

    Returns (i, j) pairs with i < j, different polygons, and — when island
    ids are given — different UV islands (intra-island self-overlaps of
    manually folded shells are the addon's documented blind spot)."""
    n = len(aabbs)
    if n == 0:
        return []
    u_lo = min(a[0] for a in aabbs)
    v_lo = min(a[1] for a in aabbs)
    u_hi = max(a[2] for a in aabbs)
    v_hi = max(a[3] for a in aabbs)
    span_u = u_hi - u_lo
    span_v = v_hi - v_lo
    if span_u < 1e-12 or span_v < 1e-12:
        return [(i, j) for i in range(n) for j in range(i + 1, n)
                if tri_poly[i] != tri_poly[j]
                and (not tri_island or tri_island[i] != tri_island[j])]
    inv_u = (grid_size - 1) / span_u
    inv_v = (grid_size - 1) / span_v
    grid = {}
    for i in range(n):
        umin, vmin, umax, vmax = aabbs[i]
        for gx in range(int((umin - u_lo) * inv_u), int((umax - u_lo) * inv_u) + 1):
            for gy in range(int((vmin - v_lo) * inv_v), int((vmax - v_lo) * inv_v) + 1):
                grid.setdefault(gx * grid_size + gy, []).append(i)
    seen = set()
    out = []
    for cell in grid.values():
        m = len(cell)
        for a in range(m):
            i = cell[a]
            for b in range(a + 1, m):
                j = cell[b]
                key = (i, j) if i < j else (j, i)
                if key in seen:
                    continue
                seen.add(key)
                if tri_poly[key[0]] == tri_poly[key[1]]:
                    continue
                if tri_island and tri_island[key[0]] == tri_island[key[1]]:
                    continue
                out.append(key)
    return out


def check_uv_overlap(snap: MeshSnapshot, max_tris: int = 80_000,
                     grid_size: int = 128) -> Optional[Finding]:
    """Overlapping UV triangles from DIFFERENT islands (inter-island overlaps
    — the common pipeline problem; manually folded intra-island shells are
    the documented blind spot).

    Fan-triangulates each face's UV contour, drops non-finite triangles
    before any grid math, broad-phases on a 2D grid, then exact-tests the
    survivors.  count = flagged polygons."""
    from math import isfinite
    p2i = uv_islands(snap)
    if p2i is None:
        return None

    tris = []          # (face_idx, (u,v), (u,v), (u,v))
    for fi, uvs in enumerate(snap.face_uvs):
        if uvs is None:
            continue
        nv = len(uvs) // 2
        for i in range(1, nv - 1):
            tris.append((fi,
                         (uvs[0], uvs[1]),
                         (uvs[i * 2], uvs[i * 2 + 1]),
                         (uvs[(i + 1) * 2], uvs[(i + 1) * 2 + 1])))
    n_tris = len(tris)
    if n_tris == 0 or n_tris > max_tris:
        return None

    tris = [t for t in tris
            if all(isfinite(c) for c in t[1] + t[2] + t[3])]
    if not tris:
        return None

    aabbs = []
    tri_poly = []
    tri_isl = []
    for fi, a, b, c in tris:
        us = (a[0], b[0], c[0])
        vs = (a[1], b[1], c[1])
        aabbs.append((min(us), min(vs), max(us), max(vs)))
        tri_poly.append(fi)
        tri_isl.append(p2i[fi])

    flagged_polys = set()
    for i, j in _uv_grid_candidates(aabbs, tri_poly, tri_isl, grid_size):
        umin_i, vmin_i, umax_i, vmax_i = aabbs[i]
        umin_j, vmin_j, umax_j, vmax_j = aabbs[j]
        if (umax_i < umin_j or umax_j < umin_i
                or vmax_i < vmin_j or vmax_j < vmin_i):
            continue
        if _uv_tris_truly_overlap(tris[i][1:], tris[j][1:]):
            flagged_polys.add(tris[i][0])
            flagged_polys.add(tris[j][0])
    if not flagged_polys:
        return None
    return Finding("uv_overlap", "BLOCKER", len(flagged_polys),
                   [("face", fi) for fi in sorted(flagged_polys)])


# ── UV stretch + texel density ───────────────────────────────────────────────

def check_uv_stretch(snap: MeshSnapshot, threshold: float = 0.5) -> Optional[Finding]:
    """Faces whose UV corner angles deviate from the 3-D corner angles by
    more than *threshold* radians — any stretched corner flags the face.

    3-D angles are measured in LOCAL space (the addon compares me.vertices
    coords, not world positions); degenerate corners (zero-length edges in
    3-D or UV) are skipped, not flagged."""
    from math import acos, sqrt
    pts = snap.points
    bad: List[tuple] = []
    for fi, verts in enumerate(snap.face_verts):
        uvs = snap.face_uvs[fi] if fi < len(snap.face_uvs) else None
        if uvs is None:
            continue
        nv = len(verts)
        stretched = False
        for i in range(nv):
            j = (i + 1) % nv
            k = (i - 1) % nv
            p0 = pts[verts[i]]
            e0 = (pts[verts[j]][0] - p0[0], pts[verts[j]][1] - p0[1],
                  pts[verts[j]][2] - p0[2])
            e1 = (pts[verts[k]][0] - p0[0], pts[verts[k]][1] - p0[1],
                  pts[verts[k]][2] - p0[2])
            m0 = sqrt(e0[0] * e0[0] + e0[1] * e0[1] + e0[2] * e0[2])
            m1 = sqrt(e1[0] * e1[0] + e1[1] * e1[1] + e1[2] * e1[2])
            if m0 <= 1e-10 or m1 <= 1e-10:
                continue
            cos3 = (e0[0] * e1[0] + e0[1] * e1[1] + e0[2] * e1[2]) / (m0 * m1)
            cos3 = 1.0 if cos3 > 1.0 else (-1.0 if cos3 < -1.0 else cos3)
            u0 = (uvs[i * 2], uvs[i * 2 + 1])
            au = (uvs[j * 2] - u0[0], uvs[j * 2 + 1] - u0[1])
            av = (uvs[k * 2] - u0[0], uvs[k * 2 + 1] - u0[1])
            ma = sqrt(au[0] * au[0] + au[1] * au[1])
            mb = sqrt(av[0] * av[0] + av[1] * av[1])
            if ma <= 1e-10 or mb <= 1e-10:
                continue
            cosu = (au[0] * av[0] + au[1] * av[1]) / (ma * mb)
            cosu = 1.0 if cosu > 1.0 else (-1.0 if cosu < -1.0 else cosu)
            if abs(acos(cos3) - acos(cosu)) > threshold:
                stretched = True
                break
        if stretched:
            bad.append(("face", fi))
    if not bad:
        return None
    return Finding("uv_stretch", "WARNING", len(bad), bad)


def check_uv_texel_density(snap: MeshSnapshot, tex_size: int = 2048,
                           target_td: float = 0.0, tolerance: float = 0.20,
                           unit_scale: float = 1.0) -> Optional[Finding]:
    """Texel density px/cm: TD = tex_size x sqrt(uv_area) / (sqrt(world_area)
    x 100 x unit_scale).  Aggregates over fan-triangulated UV contours and
    world-space triangles (world_matrix 3x3, translation irrelevant).

    count is 0 unless a *target_td* is set — then 1 when the deviation
    exceeds *tolerance* (fraction).  The Finding is returned even when clean
    so direct callers can read the density from ``metric``."""
    from math import sqrt
    wm = snap.world_matrix
    if len(wm) >= 11:
        m00, m01, m02 = wm[0], wm[1], wm[2]
        m10, m11, m12 = wm[4], wm[5], wm[6]
        m20, m21, m22 = wm[8], wm[9], wm[10]
    else:
        m00 = m11 = m22 = 1.0
        m01 = m02 = m10 = m12 = m20 = m21 = 0.0

    uv_area = 0.0
    world_area = 0.0
    pts = snap.points
    for fi, verts in enumerate(snap.face_verts):
        uvs = snap.face_uvs[fi] if fi < len(snap.face_uvs) else None
        if uvs is None:
            continue
        nv = len(verts)
        p0 = pts[verts[0]]
        for i in range(1, nv - 1):
            uv_ax = uvs[i * 2] - uvs[0]
            uv_ay = uvs[i * 2 + 1] - uvs[1]
            uv_bx = uvs[(i + 1) * 2] - uvs[0]
            uv_by = uvs[(i + 1) * 2 + 1] - uvs[1]
            uv_area += abs(uv_ax * uv_by - uv_ay * uv_bx) * 0.5

            p1 = pts[verts[i]]
            p2 = pts[verts[(i + 1) % nv]]
            ax, ay, az = p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]
            bx, by, bz = p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]
            # edges through the world 3x3 (translation is irrelevant for area)
            e1 = (ax * m00 + ay * m01 + az * m02,
                  ax * m10 + ay * m11 + az * m12,
                  ax * m20 + ay * m21 + az * m22)
            e2 = (bx * m00 + by * m01 + bz * m02,
                  bx * m10 + by * m11 + bz * m12,
                  bx * m20 + by * m21 + bz * m22)
            cx = e1[1] * e2[2] - e1[2] * e2[1]
            cy = e1[2] * e2[0] - e1[0] * e2[2]
            cz = e1[0] * e2[1] - e1[1] * e2[0]
            world_area += sqrt(cx * cx + cy * cy + cz * cz) * 0.5

    if world_area < 1e-10 or uv_area < 1e-10:
        return None

    scale = unit_scale if unit_scale > 1e-10 else 1.0
    density = (tex_size * sqrt(uv_area)) / (sqrt(world_area) * 100.0 * scale)

    count = 0
    if target_td > 0.0:
        deviation = abs(density - target_td) / target_td
        count = 1 if deviation > tolerance else 0

    if target_td > 0.0:
        metric = "TD: %.2f / %.2f px/cm" % (density, target_td)
    else:
        metric = "TD: %.2f px/cm" % density
    return Finding("uv_texel_density", "WARNING", count, [], metric=metric)


def check_uv_material_udim(snap: MeshSnapshot) -> Optional[Finding]:
    """One UDIM tile must not contain UV shells from different material groups.

    Each island votes for its dominant tile by UV centroid; tiles holding
    islands of more than one material are flagged.  count = bad tiles.
    Elements: ("face", fi) for every face on a bad tile, plus
    ("minority", fi) for the faces of non-dominant materials on those tiles
    (the natural selection/fix target).  Requires the adapter to report
    face_mat; without it the rule is not applicable."""
    from math import floor, isfinite
    if not snap.face_mat or len(snap.face_mat) != len(snap.face_verts):
        return None
    p2i = uv_islands(snap)
    if p2i is None:
        return None
    n_islands = max(p2i) + 1
    island_votes = [dict() for _ in range(n_islands)]
    island_mats = [set() for _ in range(n_islands)]
    for fi, uvs in enumerate(snap.face_uvs):
        isl = p2i[fi]
        if isl < 0 or uvs is None or not uvs:
            continue
        island_mats[isl].add(snap.face_mat[fi])
        lt = len(uvs) // 2
        u_sum = sum(uvs[0::2])
        v_sum = sum(uvs[1::2])
        cu, cv = u_sum / lt, v_sum / lt
        if not (isfinite(cu) and isfinite(cv)):
            continue
        tile = (int(floor(cu)), int(floor(cv)))
        island_votes[isl][tile] = island_votes[isl].get(tile, 0) + 1

    island_tile = [max(d, key=d.get) if d else None for d in island_votes]
    tile_mats = {}
    tile_islands = {}
    for isl in range(n_islands):
        tile = island_tile[isl]
        if tile is None:
            continue
        tile_mats.setdefault(tile, set()).update(island_mats[isl])
        tile_islands.setdefault(tile, []).append(isl)

    bad_tiles = {t for t, mats in tile_mats.items() if len(mats) > 1}
    if not bad_tiles:
        return None

    island_polys = {}
    for fi, isl in enumerate(p2i):
        if isl >= 0:
            island_polys.setdefault(isl, []).append(fi)

    elements: List[tuple] = []
    for tile in bad_tiles:
        mat_counts = {}
        for isl in tile_islands[tile]:
            for fi in island_polys.get(isl, ()):
                mi = snap.face_mat[fi]
                mat_counts[mi] = mat_counts.get(mi, 0) + 1
        dominant = max(mat_counts, key=mat_counts.get)
        for isl in tile_islands[tile]:
            for fi in island_polys.get(isl, ()):
                elements.append(("face", fi))
                if snap.face_mat[fi] != dominant:
                    elements.append(("minority", fi))

    names = ", ".join("UDIM %d" % (1001 + t[0] + t[1] * 10)
                      for t in sorted(bad_tiles)[:3])
    metric = ("Mat/UDIM: %d tile%s (%s)"
              % (len(bad_tiles), "s" if len(bad_tiles) > 1 else "", names))
    return Finding("uv_material_udim", "BLOCKER", len(bad_tiles), elements,
                   metric=metric)

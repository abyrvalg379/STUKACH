# -*- coding: utf-8 -*-
"""Cross-object Z-fighting (scene scope, strangler 6c).

Port of the Blender addon's inter-object pass: face pairs of DIFFERENT
objects that are coplanar, similarly wound and practically coincident:

  pass 1 — geometrically intersecting faces (the addon used BVHTree.overlap,
           replaced here by an AABB grid broad-phase + the Moeller tri-tri
           test over fan triangles; coplanar triangles are reported as NOT
           intersecting — pass 2 owns them and the centroid+winding filters
           make the two implementations agree);
  pass 2 — parallel duplicates (a Shift-D copy left in place): face
           centroids within *threshold*, found through a centroid grid.

Both passes share the same acceptance filter: face normals (world space)
dot above *normal_dot* and centroids within *threshold*.  Findings and the
per-pair face sets are returned separately so a DCC layer can render "who
fights whom" without parsing strings.
"""
from __future__ import annotations

from math import sqrt
from typing import Dict, List, Optional, Tuple

from ..model import MeshSnapshot, Finding


def _world_points(snap: MeshSnapshot):
    wm = snap.world_matrix
    if len(wm) >= 12:
        return [(wm[0] * x + wm[1] * y + wm[2] * z + wm[3],
                 wm[4] * x + wm[5] * y + wm[6] * z + wm[7],
                 wm[8] * x + wm[9] * y + wm[10] * z + wm[11])
                for (x, y, z) in snap.points]
    return list(snap.points)


def _newell(pts, verts):
    nx = ny = nz = 0.0
    n = len(verts)
    for i in range(n):
        a = pts[verts[i - 1]]
        b = pts[verts[i]]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    length = sqrt(nx * nx + ny * ny + nz * nz)
    if length < 1e-12:
        return None
    return (nx / length, ny / length, nz / length)


def _face_world_data(snap: MeshSnapshot):
    """(tris, normals, centroids, aabbs) — fan triangles and per-face data in
    world space; faces without usable geometry are skipped."""
    pts = _world_points(snap)
    tris = []            # (face_idx, p0, p1, p2)
    normals = []         # (face_idx, unit normal or (0,0,0))
    centroids = []       # (face_idx, centroid)
    aabbs = []           # (face_idx, (xmin, ymin, zmin, xmax, ymax, zmax))
    for fi, verts in enumerate(snap.face_verts):
        nv = len(verts)
        if nv < 3:
            continue
        poly = [pts[v] for v in verts]
        n = _newell(pts, verts) or (0.0, 0.0, 0.0)
        cx = sum(p[0] for p in poly) / nv
        cy = sum(p[1] for p in poly) / nv
        cz = sum(p[2] for p in poly) / nv
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        zs = [p[2] for p in poly]
        normals.append((fi, n))
        centroids.append((fi, (cx, cy, cz)))
        aabbs.append((fi, (min(xs), min(ys), min(zs),
                           max(xs), max(ys), max(zs))))
        for i in range(1, nv - 1):
            tris.append((fi, poly[0], poly[i], poly[i + 1]))
    return tris, normals, centroids, aabbs


def _tri_tri_intersect(t1, t2) -> bool:
    """Moeller-style non-coplanar triangle intersection.  Coplanar pairs are
    reported as NOT intersecting (pass 2 territory — module docstring)."""

    def sub(a, b):
        return (a[0] - b[0], a[1] - b[1], a[2] - b[2])

    def cross(u, v):
        return (u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0])

    def dot(u, v):
        return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]

    (p1, q1, r1), (p2, q2, r2) = t1, t2
    EPS = 1e-12

    def straddle(d1, d2, d3):
        """Strict 2+1 sign split (zero = touching the plane is degenerate —
        pass 2 owns such pairs)."""
        s1 = 1 if d1 > EPS else (-1 if d1 < -EPS else 0)
        s2 = 1 if d2 > EPS else (-1 if d2 < -EPS else 0)
        s3 = 1 if d3 > EPS else (-1 if d3 < -EPS else 0)
        if 0 in (s1, s2, s3):
            return None
        if s1 == s2 == s3:
            return None
        return (s1, s2, s3)

    n2 = cross(sub(q2, p2), sub(r2, p2))
    dp1 = dot(sub(p1, p2), n2)
    dq1 = dot(sub(q1, p2), n2)
    dr1 = dot(sub(r1, p2), n2)
    if straddle(dp1, dq1, dr1) is None:
        return False

    n1 = cross(sub(q1, p1), sub(r1, p1))
    dp2 = dot(sub(p2, p1), n1)
    dq2 = dot(sub(q2, p1), n1)
    dr2 = dot(sub(r2, p1), n1)
    if straddle(dp2, dq2, dr2) is None:
        return False

    def interval(t, ip, iq, ir, fp, fq, fr):
        """Intersection segment of *t* with the cutting plane.  *ip* is the
        single-side vertex (distance *fp*), (ip, iq) and (ip, ir) cross."""
        vp, vq, vr = t[ip], t[iq], t[ir]
        t01 = fp / (fp - fq)
        t02 = fp / (fp - fr)
        p01 = (vp[0] + t01 * (vq[0] - vp[0]),
               vp[1] + t01 * (vq[1] - vp[1]),
               vp[2] + t01 * (vq[2] - vp[2]))
        p02 = (vp[0] + t02 * (vr[0] - vp[0]),
               vp[1] + t02 * (vr[1] - vp[1]),
               vp[2] + t02 * (vr[2] - vp[2]))
        return p01, p02

    if (dp1 > 0) == (dq1 > 0):          # vertex 2 alone
        seg1 = interval(t1, 2, 0, 1, dr1, dp1, dq1)
    elif (dp1 > 0) == (dr1 > 0):        # vertex 1 alone
        seg1 = interval(t1, 1, 0, 2, dq1, dp1, dr1)
    else:                               # vertex 0 alone
        seg1 = interval(t1, 0, 1, 2, dp1, dq1, dr1)

    if (dp2 > 0) == (dq2 > 0):
        seg2 = interval(t2, 2, 0, 1, dr2, dp2, dq2)
    elif (dp2 > 0) == (dr2 > 0):
        seg2 = interval(t2, 1, 0, 2, dq2, dp2, dr2)
    else:
        seg2 = interval(t2, 0, 1, 2, dp2, dq2, dr2)

    def less(a, b):
        if a[0] != b[0]:
            return a[0] < b[0]
        if a[1] != b[1]:
            return a[1] < b[1]
        return a[2] < b[2]

    lo1, hi1 = (seg1 if less(*seg1) else (seg1[1], seg1[0]))
    lo2, hi2 = (seg2 if less(*seg2) else (seg2[1], seg2[0]))
    return not less(hi1, lo2) and not less(hi2, lo1)


def check_z_fighting_inter_scene(snaps, threshold: float = 0.0001,
                                 normal_dot: float = 0.99,
                                 max_total_faces: int = 500_000):
    """Inter-object Z-fighting over a batch of snapshots (scene scope).

    Returns (findings, pairs):
      findings — {owner: Finding} with ("face", fi) elements; empty dict when
        nothing fights (or the total-face guard tripped — the addon keeps its
        legacy silence);
      pairs — {(owner, other): set(face_idx)} for rendering "who fights whom",
        only the faces of *owner*, mirrored for every fighting pair.
    """
    if len(snaps) < 2:
        return {}, {}
    total_faces = sum(len(s.face_verts) for s in snaps.values())
    if total_faces > max_total_faces:
        return {}, {}

    data = {}
    obj_aabb = {}
    for owner, snap in snaps.items():
        if not snap.points or not snap.face_verts:
            continue   # name-only / synthetic snapshots carry no geometry
        tris, normals, centroids, aabbs = _face_world_data(snap)
        if not tris:
            continue
        data[owner] = (tris, dict(normals), dict(centroids))
        lo = [min(a[1][k] for a in aabbs) for k in range(3)]
        hi = [max(a[1][k + 3] for a in aabbs) for k in range(3)]
        obj_aabb[owner] = (lo, hi)

    thr_sq = threshold * threshold
    cell = max(threshold, 1e-12)
    hits: Dict[Tuple[str, str], set] = {}

    def mark(a, fa, b, fb):
        hits.setdefault((a, b), set()).add(fa)
        hits.setdefault((b, a), set()).add(fb)

    ordered = list(data.keys())
    for i in range(len(ordered)):
        a = ordered[i]
        tris_a, norm_a, cent_a = data[a]
        lo_a, hi_a = obj_aabb[a]
        for j in range(i + 1, len(ordered)):
            b = ordered[j]
            tris_b, norm_b, cent_b = data[b]
            lo_b, hi_b = obj_aabb[b]
            if any(lo_a[k] > hi_b[k] + threshold or lo_b[k] > hi_a[k] + threshold
                   for k in range(3)):
                continue

            # ── pass 1: intersecting faces ────────────────────────────────
            grid = {}
            for fi, p0, p1, p2 in tris_a:
                kx = int(min(p0[0], p1[0], p2[0]) // cell)
                ky = int(min(p0[1], p1[1], p2[1]) // cell)
                kz = int(min(p0[2], p1[2], p2[2]) // cell)
                grid.setdefault((kx, ky, kz), []).append((fi, p0, p1, p2))
            checked = set()
            for fi_b, p0, p1, p2 in tris_b:
                x0, x1 = min(p0[0], p1[0], p2[0]), max(p0[0], p1[0], p2[0])
                y0, y1 = min(p0[1], p1[1], p2[1]), max(p0[1], p1[1], p2[1])
                z0, z1 = min(p0[2], p1[2], p2[2]), max(p0[2], p1[2], p2[2])
                cx0, cy0, cz0 = int(x0 // cell), int(y0 // cell), int(z0 // cell)
                cx1 = int(x1 // cell)
                cy1 = int(y1 // cell)
                cz1 = int(z1 // cell)
                if (cx1 - cx0 + 1) * (cy1 - cy0 + 1) * (cz1 - cz0 + 1) > 4096:
                    continue   # oversized triangle against a threshold-sized grid
                for kx in range(cx0, cx1 + 1):
                    for ky in range(cy0, cy1 + 1):
                        for kz in range(cz0, cz1 + 1):
                            for fi_a, q0, q1, q2 in grid.get((kx, ky, kz), ()):
                                key = (fi_a, fi_b)
                                if key in checked:
                                    continue
                                if _tri_tri_intersect((p0, p1, p2),
                                                      (q0, q1, q2)):
                                    checked.add(key)
            for (fi_a, fi_b) in sorted(checked):
                na, nb = norm_a[fi_a], norm_b[fi_b]
                if na[0] * nb[0] + na[1] * nb[1] + na[2] * nb[2] <= normal_dot:
                    continue
                ca, cb = cent_a[fi_a], cent_b[fi_b]
                d2 = ((ca[0] - cb[0]) ** 2 + (ca[1] - cb[1]) ** 2 +
                      (ca[2] - cb[2]) ** 2)
                if d2 <= thr_sq:
                    mark(a, fi_a, b, fi_b)

            # ── pass 2: parallel coincident duplicates (centroid grid) ────
            inv = 1.0 / cell
            cgrid = {}
            for fi_b, c in cent_b.items():
                cgrid.setdefault((int(c[0] * inv), int(c[1] * inv),
                                  int(c[2] * inv)), []).append((fi_b, c))
            seen = set()
            for fi_a, ca in cent_a.items():
                gx, gy, gz = int(ca[0] * inv), int(ca[1] * inv), int(ca[2] * inv)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for dz in (-1, 0, 1):
                            for fi_b, cb in cgrid.get((gx + dx, gy + dy,
                                                       gz + dz), ()):
                                key = (fi_a, fi_b)
                                if key in seen:
                                    continue
                                seen.add(key)
                                d2 = ((ca[0] - cb[0]) ** 2 +
                                      (ca[1] - cb[1]) ** 2 +
                                      (ca[2] - cb[2]) ** 2)
                                if d2 > thr_sq:
                                    continue
                                na, nb = norm_a[fi_a], norm_b[fi_b]
                                if (na[0] * nb[0] + na[1] * nb[1] +
                                        na[2] * nb[2] <= normal_dot):
                                    continue
                                mark(a, fi_a, b, fi_b)

    if not hits:
        return {}, {}

    per_owner: Dict[str, set] = {}
    others: Dict[str, set] = {}
    for (owner, other), faces in hits.items():
        per_owner.setdefault(owner, set()).update(faces)
        others.setdefault(owner, set()).add(other)

    findings = {}
    for owner, faces in per_owner.items():
        names_sorted = ", ".join(sorted(others[owner]))
        findings[owner] = Finding(
            "z_fighting_inter", "BLOCKER", len(faces),
            [("face", fi) for fi in sorted(faces)],
            metric="Z-Fight inter: %d face(s) vs %s" % (len(faces), names_sorted),
            owner=owner)
    return findings, hits


def check_z_fighting_inter_batch(snaps, threshold: float = 0.0001,
                                 normal_dot: float = 0.99,
                                 max_total_faces: int = 500_000):
    """Registry wrapper: findings only (run_scene_checks path)."""
    findings, _ = check_z_fighting_inter_scene(snaps, threshold, normal_dot,
                                               max_total_faces)
    return list(findings.values())

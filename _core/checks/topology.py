# -*- coding: utf-8 -*-
"""Pure topology evaluators: (MeshSnapshot, params) -> Finding | None.

Ported from the STUKACH addon implementations (strangler stage 2, 2026-10-03).
Findings carry index-based elements; adapters render native component strings.
lamina / starlike / missing_uvs / duplicate_verts are SELF-COMPUTED from the
snapshot geometry — no DCC-provided flags required.
"""
from __future__ import annotations

from typing import Optional

from ..model import MeshSnapshot, Finding, edge_length


def check_triangles(snap: MeshSnapshot) -> Optional[Finding]:
    bad = [("face", fi) for fi, verts in enumerate(snap.face_verts) if len(verts) == 3]
    if not bad:
        return None
    return Finding("triangles", "WARNING", len(bad), bad)


def check_ngons(snap: MeshSnapshot) -> Optional[Finding]:
    bad = [("face", fi) for fi, verts in enumerate(snap.face_verts) if len(verts) > 4]
    if not bad:
        return None
    return Finding("ngons", "BLOCKER", len(bad), bad)


def check_non_manifold(snap: MeshSnapshot) -> Optional[Finding]:
    ve = snap.vert_edges()
    vf = snap.vert_faces()
    ef = snap.edge_faces()

    # 1) non-manifold edges: shared by more than 2 faces
    bad_edges = [("edge", eid) for eid, conn in enumerate(snap.edge_conn) if conn > 2]

    # 2) non-contiguous vertex fans: faces around a vertex must form one fan
    #    (shared-edge walk) — catches two islands sharing a single vertex
    bad_verts = []
    for v, f_ids in vf.items():
        e_ids = ve.get(v, ())
        if len(f_ids) > 1 and len(e_ids) > 1:
            fset = set(f_ids)
            adj = {f: set() for f in f_ids}
            for e in e_ids:
                shared = [f for f in ef.get(e, ()) if f in fset]
                for i in range(len(shared)):
                    for j in range(i + 1, len(shared)):
                        adj[shared[i]].add(shared[j])
                        adj[shared[j]].add(shared[i])
            visited = {f_ids[0]}
            queue = [f_ids[0]]
            while queue:
                cur = queue.pop()
                for nb in adj[cur]:
                    if nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            if len(visited) < len(f_ids):
                bad_verts.append(("vert", v))

    # 3) lamina faces (same contour-repeat test the lamina rule uses)
    bad_faces = []
    for fi, verts in enumerate(snap.face_verts):
        n = len(verts)
        ekeys = set()
        for i in range(n):
            a, b = verts[i], verts[(i + 1) % n]
            ekeys.add((a, b) if a < b else (b, a))
        if len(set(verts)) < n or len(ekeys) < n:
            bad_faces.append(("face", fi))

    # 4) isolated vertices (referenced by nothing)
    referenced = set(ve.keys()) | set(vf.keys())
    iso = [("vert", v) for v in range(len(snap.points)) if v not in referenced]

    bad_verts = list(dict.fromkeys(bad_verts + iso))
    elements = bad_edges + bad_faces + bad_verts
    if not elements:
        return None
    parts = []
    if bad_edges:
        parts.append("%d edges" % len(bad_edges))
    if bad_faces:
        parts.append("%d lamina" % len(bad_faces))
    if bad_verts:
        parts.append("%d verts" % len(bad_verts))
    return Finding("non_manifold", "BLOCKER", len(elements), elements,
                   metric=" + ".join(parts))


def check_zero_area(snap: MeshSnapshot, threshold: float = 1e-10) -> Optional[Finding]:
    bad = [("face", fi) for fi, area in enumerate(snap.face_area) if area < threshold]
    if not bad:
        return None
    return Finding("zero_area", "BLOCKER", len(bad), bad)


def check_poles(snap: MeshSnapshot) -> Optional[Finding]:
    """N-poles (3 edges) and E-poles (5+) on INTERIOR vertices only.

    Boundary vertices are excluded: their reduced valence is topologically
    expected, not a pole (Blender-parity semantics)."""
    boundary_verts = set()
    for eid, conn in enumerate(snap.edge_conn):
        if conn <= 1:
            boundary_verts.update(snap.edges[eid])
    n_poles = e_poles = more_poles = 0
    bad = []
    for v, e_ids in snap.vert_edges().items():
        if v in boundary_verts:
            continue
        ne = len(e_ids)
        if ne == 3:
            n_poles += 1
            bad.append(("vert", v))
        elif ne == 5:
            e_poles += 1
            bad.append(("vert", v))
        elif ne > 5:
            more_poles += 1
            bad.append(("vert", v))
    if not bad:
        return None
    parts = []
    if n_poles:
        parts.append("%dN" % n_poles)
    if e_poles:
        parts.append("%dE" % e_poles)
    if more_poles:
        parts.append("%d+" % more_poles)
    return Finding("poles", "INFO", len(bad), bad, metric=" ".join(parts))


def check_isolated_verts(snap: MeshSnapshot) -> Optional[Finding]:
    referenced = set(snap.vert_edges().keys()) | set(snap.vert_faces().keys())
    bad = [("vert", v) for v in range(len(snap.points)) if v not in referenced]
    if not bad:
        return None
    return Finding("isolated_verts", "WARNING", len(bad), bad)


def check_boundary_edges(snap: MeshSnapshot) -> Optional[Finding]:
    bad = [("edge", eid) for eid, conn in enumerate(snap.edge_conn) if conn == 1]
    if not bad:
        return None
    return Finding("boundary_edges", "WARNING", len(bad), bad)


def _islands(snap: MeshSnapshot) -> list:
    """Union-find over the edge graph → island id per vertex index."""
    parent = list(range(len(snap.points)))

    def find(x):
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for a, b in snap.edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    return [find(i) for i in range(len(parent))]


def check_duplicate_verts(snap: MeshSnapshot, merge_dist: float = 1e-5) -> Optional[Finding]:
    """Overlapping vertices within *merge_dist* that belong to ONE shell.

    Coincident verts of different shells (bolted plates, stacked parts) are
    intentional hard-surface practice and are NOT flagged (Blender-parity).
    numpy grid hash — no scipy required."""
    import numpy as np
    n = len(snap.points)
    if n < 2:
        return None
    co = np.array(snap.points, dtype=np.float64)
    finite = np.isfinite(co).all(axis=1)
    reasonable = (np.abs(co) < 1e8).all(axis=1)
    valid = np.where(finite & reasonable)[0]
    if len(valid) < 2:
        return None

    inv = 1.0 / max(merge_dist, 1e-12)
    g = np.floor(co[valid] * inv).astype(np.int64)
    cells: dict = {}
    for row, vi in zip(g, valid):
        cells.setdefault(tuple(row), []).append(int(vi))

    def _pairs_close(a_list, b_list):
        out = []
        for ia in a_list:
            for ib in b_list:
                if ia == ib:
                    continue
                d2 = float(((co[ia] - co[ib]) ** 2).sum())
                if d2 <= merge_dist * merge_dist:
                    out.append((ia, ib))
        return out

    pairs = []
    for (cx, cy, cz), bucket in cells.items():
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    neighbor = cells.get((cx + dx, cy + dy, cz + dz))
                    if neighbor is None:
                        continue
                    pairs.extend(_pairs_close(bucket, neighbor))
    if not pairs:
        return None

    islands = _islands(snap)
    dup = set()
    for ia, ib in pairs:
        if islands[ia] == islands[ib]:   # same shell only
            # find_doubles semantics: the higher index is the copy that
            # merges into the surviving lower-index vertex — only it flags
            dup.add(max(ia, ib))
    if not dup:
        return None
    bad = [("vert", int(i)) for i in sorted(dup)]
    return Finding("duplicate_verts", "BLOCKER", len(bad), bad)


def check_lamina(snap: MeshSnapshot) -> Optional[Finding]:
    """Lamina faces — the contour repeats a vertex or traverses the same
    edge twice, so the face has zero thickness (isLamina analog, computed)."""
    bad = []
    for fi, verts in enumerate(snap.face_verts):
        n = len(verts)
        if n < 2:
            continue
        ekeys = set()
        for i in range(n):
            a, b = verts[i], verts[(i + 1) % n]
            ekeys.add((a, b) if a < b else (b, a))
        if len(set(verts)) < n or len(ekeys) < n:
            bad.append(("face", fi))
    if not bad:
        return None
    return Finding("lamina", "BLOCKER", len(bad), bad)


def check_zero_length_edges(snap: MeshSnapshot, tol: float = 1e-8) -> Optional[Finding]:
    bad = []
    pts = snap.points
    for i, (v0, v1) in enumerate(snap.edges):
        if edge_length(pts, (v0, v1)) <= tol:
            bad.append(("edge", i))
    if not bad:
        return None
    return Finding("zero_length_edges", "BLOCKER", len(bad), bad)


def _outline_crosses(pts) -> bool:
    """True if any two non-adjacent segments of the 2-D polygon intersect."""
    n = len(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def on_seg(a, b, p):
        return (min(a[0], b[0]) - 1e-12 <= p[0] <= max(a[0], b[0]) + 1e-12 and
                min(a[1], b[1]) - 1e-12 <= p[1] <= max(a[1], b[1]) + 1e-12)

    for i in range(n):
        a1, a2 = pts[i], pts[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue   # ring-adjacent segments share a vertex legitimately
            b1, b2 = pts[j], pts[(j + 1) % n]
            d1 = cross(b1, b2, a1)
            d2 = cross(b1, b2, a2)
            d3 = cross(a1, a2, b1)
            d4 = cross(a1, a2, b2)
            if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
               ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
                return True
            if d1 == 0 and on_seg(b1, b2, a1):
                return True
            if d2 == 0 and on_seg(b1, b2, a2):
                return True
            if d3 == 0 and on_seg(a1, a2, b1):
                return True
            if d4 == 0 and on_seg(a1, a2, b2):
                return True
    return False


def _has_zero_edge(pts) -> bool:
    """Zero-length contour edge (consecutive coincident verts — a 'stitched'
    face).  Maya treats such faces as non-starlike."""
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        if (x2 - x1) ** 2 + (y2 - y1) ** 2 <= 1e-12:
            return True
    return False


def _centroid_sees_all(pts) -> bool:
    """Vertex-averaged centroid must lie inside the polygon AND on the inner
    side of every edge (concave faces whose centroid cannot see the whole
    outline are non-starlike — isStarlike parity)."""
    n = len(pts)
    area2 = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        area2 += x1 * y2 - x2 * y1
    if abs(area2) < 1e-12:
        return True   # degenerate projection — the crossing test decides
    orient = 1.0 if area2 > 0 else -1.0
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n

    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > cy) != (yj > cy) and \
                cx < (xj - xi) * (cy - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    if not inside:
        return False

    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        cr = (x2 - x1) * (cy - y1) - (y2 - y1) * (cx - x1)
        if cr * orient < -1e-12:
            return False
    return True


def check_starlike(snap: MeshSnapshot,
                   zero_area_threshold: float = 1e-10) -> Optional[Finding]:
    """Non-starlike faces (quads and n-gons; tris cannot self-intersect).

    The contour is projected onto the face plane (dominant Newell axis
    dropped; degenerate normal → flattest vertex axis) and tested with
    outline-crossing, zero-edge and centroid-visibility probes.  Faces
    claimed by zero_area / lamina are excluded — one defect, one finding."""
    zero_area = {fi for fi, area in enumerate(snap.face_area)
                 if area < zero_area_threshold}
    lamina = set()
    for fi, verts in enumerate(snap.face_verts):
        n = len(verts)
        ekeys = set()
        for i in range(n):
            a, b = verts[i], verts[(i + 1) % n]
            ekeys.add((a, b) if a < b else (b, a))
        if len(set(verts)) < n or len(ekeys) < n:
            lamina.add(fi)
    claimed = zero_area | lamina

    pts3 = snap.points
    bad = []
    for fi, verts in enumerate(snap.face_verts):
        if fi in claimed or len(verts) < 4:
            continue
        poly = [pts3[v] for v in verts]
        # dominant Newell axis
        nx = ny = nz = 0.0
        n = len(poly)
        for i in range(n):
            a, b = poly[i], poly[(i + 1) % n]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        if nx * nx + ny * ny + nz * nz < 1e-20:
            spreads = [max(p[k] for p in poly) - min(p[k] for p in poly)
                       for k in range(3)]
            if sum(1 for s in spreads if s <= 1e-12) >= 2:
                continue   # contour is a line — zero_area's domain
            ax = min(range(3), key=lambda k: spreads[k])
        else:
            ax = max(range(3), key=lambda k: abs((nx, ny, nz)[k]))
        keep = [k for k in range(3) if k != ax]
        pts = [(p[keep[0]], p[keep[1]]) for p in poly]
        if (_outline_crosses(pts) or _has_zero_edge(pts)
                or not _centroid_sees_all(pts)):
            bad.append(("face", fi))
    if not bad:
        return None
    return Finding("starlike", "WARNING", len(bad), bad)


def check_missing_uvs(snap: MeshSnapshot, zero_sq: float = 1e-12) -> Optional[Finding]:
    """Faces without usable UV mapping: no layer at all (adapter passes
    None), or every loop of the face sits at (0, 0) — unmapped leftovers."""
    bad = []
    for fi, uvs in enumerate(snap.face_uvs):
        if uvs is None:
            bad.append(("face", fi))
            continue
        # addon parity: a face counts as mapped unless EVERY loop sits at
        # (0, 0); NaN coordinates fail the <= test and read as mapped
        if all(u * u + v * v <= zero_sq
               for u, v in zip(uvs[0::2], uvs[1::2])):
            bad.append(("face", fi))
    if not bad:
        return None
    return Finding("missing_uvs", "WARNING", len(bad), bad)

# -*- coding: utf-8 -*-
"""Pure topology evaluators: (MeshSnapshot, params) -> Finding | None.

Ported 1:1 from MAYA_STUKACH core.py SnapshotCheck implementations
(2026-10-03 strangler, stage 1).  Findings carry index-based elements;
adapters render native component strings.
"""
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

    # 3) lamina faces (same data the Lamina rule uses)
    bad_faces = [("face", fi) for fi, is_lam in enumerate(snap.face_lamina) if is_lam]

    # 4) isolated vertices (referenced by nothing)
    referenced = set(ve.keys()) | set(vf.keys())
    iso = [("vert", v) for v in range(len(snap.points)) if ("vert", v) not in
           set() and v not in referenced]
    iso = [t for t in iso if t[1] not in referenced]

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


def check_duplicate_verts(snap: MeshSnapshot, merge_dist: float = 1e-5) -> Optional[Finding]:
    """Overlapping vertices within *merge_dist* (0.01 mm default).

    scipy.spatial.cKDTree; degrades silently to clean when scipy/numpy is
    unavailable (adapters warn about the environment themselves)."""
    n = len(snap.points)
    if n < 2:
        return None
    try:
        from scipy.spatial import cKDTree
    except ImportError:
        return None
    import numpy as np
    co_all = np.array(snap.points, dtype=np.float64)
    finite = np.isfinite(co_all).all(axis=1)
    reasonable = (np.abs(co_all) < 1e8).all(axis=1)
    mask = finite & reasonable
    valid_idx = np.where(mask)[0]
    co = co_all[mask]
    if len(co) < 2:
        return None
    tree = cKDTree(co)
    pairs = tree.query_pairs(r=merge_dist, output_type='ndarray')
    if len(pairs) == 0:
        return None
    dup_local = np.unique(pairs.ravel())
    dup_mesh = np.sort(valid_idx[dup_local])
    bad = [("vert", int(i)) for i in dup_mesh]
    return Finding("duplicate_verts", "BLOCKER", len(bad), bad)


def check_lamina(snap: MeshSnapshot) -> Optional[Finding]:
    bad = [("face", i) for i, is_lamina in enumerate(snap.face_lamina) if is_lamina]
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


def check_starlike(snap: MeshSnapshot) -> Optional[Finding]:
    """Non-starlike faces — polygon outline self-intersects (flag == False)."""
    bad = [("face", i) for i, st in enumerate(snap.face_starlike) if st is False]
    if not bad:
        return None
    return Finding("starlike", "WARNING", len(bad), bad)


def check_missing_uvs(snap: MeshSnapshot) -> Optional[Finding]:
    bad = [("face", i) for i, uvs in enumerate(snap.face_uvs) if uvs is None]
    if not bad:
        return None
    return Finding("missing_uvs", "WARNING", len(bad), bad)

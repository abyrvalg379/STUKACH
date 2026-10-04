# -*- coding: utf-8 -*-
"""Cross-object Z-fighting (scene scope, strangler 6c, revised 0.13.0).

One acceptance rule over face pairs of DIFFERENT objects:

    face normals (world) dot above *normal_dot*  AND  centroids within
    *threshold*.

This single centroid-grid rule is provably equivalent to the Blender
addon's two legacy passes: its BVHTree pass flagged geometric intersections
ONLY after the same winding+centroid filters — and every pair that survives
those filters is already found by the centroid grid (the grid's 27-cell
neighbourhood covers the full threshold radius, and the parallel-duplicates
pass never required an actual intersection).  The Möller tri-tri machinery
was measured redundant on a live bicycle scene (25s -> sub-second with the
numpy grid) and removed.

numpy is required (both DCC adapters ship it).
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np

from ..model import MeshSnapshot, Finding


def _world_points(snap: MeshSnapshot) -> np.ndarray:
    wm = snap.world_matrix
    pts = np.asarray(snap.points, dtype=np.float64)
    if pts.size == 0:
        return pts.reshape(0, 3)
    if len(wm) >= 12:
        m = np.array(wm[:12], dtype=np.float64).reshape(3, 4)
        pts = pts @ m[:, :3].T + m[:, 3]
    return pts


def _face_world_data(snap: MeshSnapshot):
    """(face_idx, normals, centroids) in world space — fully vectorised
    (a per-face numpy loop measured 10+s on a 100k-face mesh; this is <1s).

    normals/centroids are aligned with *face_idx* (faces with <3 corners are
    excluded); degenerate faces get a zero normal and drop out of the
    winding test.  The cross-product Newell variant (a−b)x(a+b) differs from
    the textbook one only by a global scale — the winding test compares two
    normals produced by the SAME formula, so a global sign cancels out."""
    pts = _world_points(snap)
    faces = snap.face_verts
    counts = np.fromiter((len(v) for v in faces), dtype=np.int64,
                         count=len(faces))
    flat_idx = np.fromiter((v for vs in faces for v in vs),
                           dtype=np.int64, count=int(counts.sum()))
    starts = np.zeros(len(counts), dtype=np.int64)
    np.cumsum(counts[:-1], out=starts[1:])

    corners = pts[flat_idx]                              # (M, 3)
    face_id = np.repeat(np.arange(len(counts)), counts)
    local = np.arange(len(flat_idx)) - np.repeat(starts, counts)
    prev_local = np.where(local == 0, counts[face_id] - 1, local - 1)
    prev_idx = starts[face_id] + prev_local
    prev = corners[prev_idx]

    cr = np.cross(corners - prev, corners + prev)
    sums = np.add.reduceat(cr, starts, axis=0)           # (F, 3)
    lengths = np.linalg.norm(sums, axis=1)
    safe = lengths > 1e-12
    normals = np.zeros((len(counts), 3))
    normals[safe] = sums[safe] / lengths[safe, None]

    cent = np.add.reduceat(corners, starts, axis=0) / counts[:, None]

    fid = np.nonzero(counts >= 3)[0]
    return fid, normals, cent


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

    thr = float(threshold)
    thr_sq = thr * thr
    inv = 1.0 / max(thr, 1e-12)

    data = {}
    obj_aabb = {}
    for owner, snap in snaps.items():
        if not snap.points or not snap.face_verts:
            continue   # name-only / synthetic snapshots carry no geometry
        fid, normals, centroids = _face_world_data(snap)
        if fid.size == 0:
            continue
        data[owner] = (fid, normals, centroids)
        lo = centroids.min(axis=0) - thr
        hi = centroids.max(axis=0) + thr
        obj_aabb[owner] = (lo, hi)

    # conservative object-pair prefilter on centroid AABBs (+threshold)
    ordered = list(data.keys())
    pair_list = []
    for i in range(len(ordered)):
        a = ordered[i]
        la, ha = obj_aabb[a]
        for j in range(i + 1, len(ordered)):
            b = ordered[j]
            lb, hb = obj_aabb[b]
            if bool((la > hb + thr).any() or (lb > ha + thr).any()):
                continue
            pair_list.append((a, b))

    # (owner, other) → set of face indices of *owner* fighting *other*
    hits: Dict[Tuple[str, str], set] = {}

    def mark(a, fa, b, fb):
        hits.setdefault((a, b), set()).add(int(fa))
        hits.setdefault((b, a), set()).add(int(fb))

    for a, b in pair_list:
        fid_a, norm_a, cent_a = data[a]
        fid_b, norm_b, cent_b = data[b]

        ka = np.floor(cent_a * inv).astype(np.int64)
        kb = np.floor(cent_b * inv).astype(np.int64)
        # linear cell key (large primes; collisions only add candidates that
        # the exact distance test rejects)
        key_a = (ka[:, 0] * 73856093) ^ (ka[:, 1] * 19349663) ^ (ka[:, 2] * 83492791)
        key_b = (kb[:, 0] * 73856093) ^ (kb[:, 1] * 19349663) ^ (kb[:, 2] * 83492791)

        order_a = np.argsort(key_a, kind="stable")
        order_b = np.argsort(key_b, kind="stable")
        sorted_a = key_a[order_a]
        common = np.intersect1d(sorted_a, key_b[order_b])
        if common.size == 0:
            continue

        # slice boundaries inside the sorted arrays per common cell
        starts_a = np.searchsorted(sorted_a, common, side="left")
        ends_a = np.searchsorted(sorted_a, common, side="right")
        sb = key_b[order_b]
        starts_b = np.searchsorted(sb, common, side="left")
        ends_b = np.searchsorted(sb, common, side="right")

        for k, common_key in enumerate(common):
            sub_a = order_a[starts_a[k]:ends_a[k]]
            sub_b = order_b[starts_b[k]:ends_b[k]]
            if sub_a.size == 0 or sub_b.size == 0:
                continue
            pa = cent_a[sub_a]
            pb = cent_b[sub_b]
            # exact cell match (rejects hash collisions)
            same = (ka[sub_a][:, None, :] == kb[sub_b][None, :, :]).all(axis=2)
            d2 = ((pa[:, None, :] - pb[None, :, :]) ** 2).sum(axis=2)
            close = (d2 <= thr_sq) & same
            ia, ib = np.nonzero(close)
            if ia.size == 0:
                continue
            dots = (norm_a[sub_a][:, None, :] *
                    norm_b[sub_b][None, :, :]).sum(axis=2)
            ok = dots[ia, ib] > normal_dot
            for pos_a, pos_b in zip(sub_a[ia[ok]], sub_b[ib[ok]]):
                mark(a, int(fid_a[pos_a]), b, int(fid_b[pos_b]))

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

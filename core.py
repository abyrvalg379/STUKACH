# -*- coding:utf-8 -*-
import bpy
import bmesh
import math
import mathutils
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import List, Tuple, Set

_RE_LOWERCASE = re.compile(r"^[a-z0-9_]+$")
_RE_GRP_SUFFIX = re.compile(r"^[a-z0-9_]+_grp$")

_MICRO_SHELL_UV_AREA        = 1e-12  # per-triangle fallback — truly degenerate UV only
_MICRO_SHELL_ISLAND_AREA    = 1e-5   # per-island threshold ≈ 6 px×6 px at 2048
_UV_OVERLAP_MAX_TRIS        = 80_000  # BVH guard — skip on very dense meshes
_UV_ISLAND_MAX_POLYS        = 15_000  # shared-cache island detection guard
_UV_MICRO_SHELL_MAX_POLYS   = 100_000 # micro-shell island detection guard (higher limit)
_UV_STRETCH_MAX_POLYS       = 300_000 # UV stretch guard — numpy-vectorized, handles large meshes
_UV_PADDING_MAX_POLYS       = 50_000  # padding-only guard — higher limit, no shared cache
_UV_STRETCH_DEFAULT_THRESHOLD = 0.5  # radians ≈ 28°

# Module-level island cache: keyed by (me.as_pointer(), n_loops).
# Cleared in MeshCheckObject.update_datas() before each validation cycle so
# UVPaddingCheck and UVUDIMBounds share one computation per update.
_uv_island_cache: dict = {}

# Module-level cache for _uv_island_membership results.
# Multiple checks (UVOverlapCheck, UVMicroShellCheck, UVPaddingCheck) may call
# _uv_island_membership for the same mesh in a single update cycle. Caching
# avoids O(n_loops) Union-Find work 3× per update.
# Key: (me.as_pointer(), n_loops, uv_layer_name). Cleared in update_datas().
_uv_membership_cache: dict = {}

# Global registry for cross-object UV padding computation.
# Key: me.as_pointer()  →  dict with island UV data for this mesh.
# Populated by UVPaddingCheck.set_datas(); consumed by run_global_uv_padding().
# Cleared in MeshCheck.reset_mesh_check() and at scene validation start.
_uv_padding_registry: dict = {}

# Per-UDIM-tile statistics produced by run_global_uv_padding().
# Key: (tu, tv) tuple  →  {n_islands, n_objects, min_border_px, bad_shell, bad_tile}
# Read by ASSET_CHECKER_PT_UV_Panel to show the UDIM Padding Map block.
_uv_padding_tile_stats: dict = {}


def check_scene_units() -> dict:
    """Scene-level check: units must be METRIC / METERS, scale_length == 1.0.

    Returns {'ok': bool, 'issues': list[str]}.
    Called directly from the UI panel — not a BaseCheck subclass.
    """
    scene = bpy.context.scene
    us = scene.unit_settings
    issues = []
    if us.system != 'METRIC':
        issues.append(f"System: {us.system} (need METRIC)")
    elif us.length_unit != 'METERS':
        issues.append(f"Unit: {us.length_unit} (need METERS)")
    if abs(us.scale_length - 1.0) > 1e-4:
        issues.append(f"Scale Length: {us.scale_length:.4f} (need 1.0)")
    return {'ok': len(issues) == 0, 'issues': issues}


def _get_offset(offset: float, obj) -> float:
    # Clamp scale influence: prevent face fills from exploding on objects with
    # large non-applied scale (e.g. modelled in mm → scale=1000 in Blender).
    scale = sum(obj.scale[:]) / 3
    scale = max(0.01, min(scale, 2.0))
    return max(0.000001, offset) / 100 * scale


def _triangulate_polygon(bm, polygons_idx: List[int]) -> List:
    bm_copy = bm.copy()
    bm_copy.faces.ensure_lookup_table()
    polygons = [bm_copy.faces[idx] for idx in polygons_idx]
    new_faces = bmesh.ops.triangulate(
        bm_copy, faces=polygons, quad_method="BEAUTY", ngon_method="BEAUTY"
    )
    verts_idx = [vert.index for face in new_faces["faces"] for vert in face.verts]
    bm_copy.free()
    bm.verts.ensure_lookup_table()
    return [bm.verts[idx] for idx in verts_idx]


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
    rx = p2[0] - p1[0];  ry = p2[1] - p1[1]
    sx = p4[0] - p3[0];  sy = p4[1] - p3[1]
    rxs = cross2d((rx, ry), (sx, sy))
    if abs(rxs) < 1e-10:
        return False  # parallel or collinear
    qpx = p3[0] - p1[0];  qpy = p3[1] - p1[1]
    t = cross2d((qpx, qpy), (sx, sy)) / rxs
    u = cross2d((qpx, qpy), (rx, ry)) / rxs
    eps = 1e-9
    return eps < t < 1.0 - eps and eps < u < 1.0 - eps


def _uv_tris_truly_overlap(t1, t2) -> bool:
    """True if two UV triangles genuinely overlap (not just share an edge).

    Covers three cases:
    1. Any vertex of t1 is strictly inside t2 (and vice-versa).
    2. Exact-duplicate / stacked triangles — centroid test.
    3. X-crossing: edges of t1 and t2 cross without any vertex containment.
    """
    a1, b1, c1 = t1
    a2, b2, c2 = t2
    # Case 1 — vertex containment
    for p in (a1, b1, c1):
        if _uv_point_in_tri_strict(p, a2, b2, c2):
            return True
    for p in (a2, b2, c2):
        if _uv_point_in_tri_strict(p, a1, b1, c1):
            return True
    # Case 2 — centroid check (handles perfectly stacked duplicates)
    mid1 = ((a1[0] + b1[0] + c1[0]) / 3, (a1[1] + b1[1] + c1[1]) / 3)
    if _uv_point_in_tri_strict(mid1, a2, b2, c2):
        return True
    mid2 = ((a2[0] + b2[0] + c2[0]) / 3, (a2[1] + b2[1] + c2[1]) / 3)
    if _uv_point_in_tri_strict(mid2, a1, b1, c1):
        return True
    # Case 3 — edge-edge intersection (X-crossing)
    edges1 = ((a1, b1), (b1, c1), (c1, a1))
    edges2 = ((a2, b2), (b2, c2), (c2, a2))
    for e1 in edges1:
        for e2 in edges2:
            if _seg_intersect_2d(e1[0], e1[1], e2[0], e2[1]):
                return True
    return False


def _uv_grid_candidates(tri_uvs: list, tri_poly_buf: list,
                        grid_size: int = 64, tri_island: list = None):
    """2D spatial-hash broad-phase for UV triangle overlap detection.

    BVHTree.overlap() does not detect overlaps for coplanar (z=0) triangles
    because it requires 3D volume intersection.  This function builds a 2D
    grid and returns candidate pairs purely from 2D bounding-box overlap,
    leaving the exact test to _uv_tris_truly_overlap.

    Returns a set of (i, j) pairs where i < j and triangles i, j belong to
    different polygons (and different UV islands when tri_island is provided).

    Args:
        tri_uvs:     Per-triangle UV coordinates — list of ((u0,v0),(u1,v1),(u2,v2)).
        tri_poly_buf: Per-triangle polygon index.
        grid_size:   Spatial grid resolution (higher = fewer false candidates).
        tri_island:  Optional per-triangle island ID list.  When provided,
                     intra-island pairs are excluded at build time, dramatically
                     reducing output size on packed UV layouts (>99% reduction).
    """
    n = len(tri_uvs)
    if n == 0:
        return set()

    # Global UV bounding box
    u_lo = v_lo = float("inf")
    u_hi = v_hi = float("-inf")
    for tri in tri_uvs:
        for u, v in tri:
            if u < u_lo: u_lo = u
            if u > u_hi: u_hi = u
            if v < v_lo: v_lo = v
            if v > v_hi: v_hi = v

    span_u = u_hi - u_lo
    span_v = v_hi - v_lo
    if span_u < 1e-12 or span_v < 1e-12:
        # Degenerate layout — fall back to brute force
        candidates: set = set()
        for i in range(n):
            for j in range(i + 1, n):
                if tri_poly_buf[i] != tri_poly_buf[j]:
                    if not tri_island or tri_island[i] != tri_island[j]:
                        candidates.add((i, j))
        return candidates

    inv_u = (grid_size - 1) / span_u
    inv_v = (grid_size - 1) / span_v

    # Build grid: cell key → list of triangle indices
    grid: dict = {}
    for i, tri in enumerate(tri_uvs):
        us = [p[0] for p in tri]
        vs = [p[1] for p in tri]
        gx0 = int((min(us) - u_lo) * inv_u)
        gx1 = int((max(us) - u_lo) * inv_u)
        gy0 = int((min(vs) - v_lo) * inv_v)
        gy1 = int((max(vs) - v_lo) * inv_v)
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                cell = gx * grid_size + gy
                if cell not in grid:
                    grid[cell] = []
                grid[cell].append(i)

    # Collect unique inter-polygon (and inter-island) pairs from cells
    candidates = set()
    for cell_tris in grid.values():
        nc = len(cell_tris)
        if nc < 2:
            continue
        for a in range(nc):
            for b in range(a + 1, nc):
                i, j = cell_tris[a], cell_tris[b]
                if i > j:
                    i, j = j, i
                if tri_poly_buf[i] == tri_poly_buf[j]:
                    continue
                if tri_island and tri_island[i] == tri_island[j]:
                    continue
                candidates.add((i, j))
    return candidates


def _uv_grid_candidates_fast(
    u_min: list, v_min: list, u_max: list, v_max: list,
    tri_poly: list, tri_island: list, grid_size: int = 128,
):
    """Faster variant of _uv_grid_candidates that takes pre-computed AABB lists.

    Accepts Python lists (not nested UV tuples) so the caller can use numpy
    to build them at C speed and only pay one .tolist() conversion.
    """
    n = len(u_min)
    if n == 0:
        return set()

    # Global bbox from pre-computed lists (min/max on Python lists is C-level)
    u_lo = min(u_min);  u_hi = max(u_max)
    v_lo = min(v_min);  v_hi = max(v_max)
    span_u = u_hi - u_lo
    span_v = v_hi - v_lo

    if span_u < 1e-12 or span_v < 1e-12:
        candidates: set = set()
        for i in range(n):
            for j in range(i + 1, n):
                if tri_poly[i] != tri_poly[j]:
                    if not tri_island or tri_island[i] != tri_island[j]:
                        candidates.add((i, j))
        return candidates

    inv_u = (grid_size - 1) / span_u
    inv_v = (grid_size - 1) / span_v

    grid: dict = {}
    for i in range(n):
        gx0 = int((u_min[i] - u_lo) * inv_u)
        gx1 = int((u_max[i] - u_lo) * inv_u)
        gy0 = int((v_min[i] - v_lo) * inv_v)
        gy1 = int((v_max[i] - v_lo) * inv_v)
        for gx in range(gx0, gx1 + 1):
            for gy in range(gy0, gy1 + 1):
                key = gx * grid_size + gy
                lst = grid.get(key)
                if lst is None:
                    grid[key] = [i]
                else:
                    lst.append(i)

    candidates = set()
    add = candidates.add
    for cell_tris in grid.values():
        nc = len(cell_tris)
        if nc < 2:
            continue
        for a in range(nc):
            ia = cell_tris[a]
            for b in range(a + 1, nc):
                ib = cell_tris[b]
                i, j = (ia, ib) if ia < ib else (ib, ia)
                if tri_poly[i] == tri_poly[j]:
                    continue
                if tri_island and tri_island[i] == tri_island[j]:
                    continue
                add((i, j))
    return candidates


def _fill_uv_flat_from_bm(bm, n_loops: int) -> List[float]:
    """Build a flat UV array indexed by mesh loop index from bmesh.

    Used as a fallback when me.uv_layers.active.data is empty (edit mode):
    in EDIT mode the UV data lives in the bmesh, not in the mesh data object.
    Returns an empty list when no active UV layer is found in the bmesh.
    """
    uv_layer = bm.loops.layers.uv.active
    if not uv_layer:
        return []
    flat = [0.0] * (n_loops * 2)
    for face in bm.faces:
        for loop in face.loops:
            li = loop.index
            if li < n_loops:
                uv = loop[uv_layer].uv
                flat[li * 2]     = uv.x
                flat[li * 2 + 1] = uv.y
    return flat


def _detect_uv_islands(me, bm=None):
    """Union-Find UV island detection — fully bmesh-based.

    Returns list of (poly_indices: list[int], u_min, v_min, u_max, v_max).
    Two polygons are in the same island when they share a UV edge —
    same UV coordinates at both endpoints (no seam).

    Result is cached by (mesh pointer, loop count) so multiple checkers
    share one computation per update cycle.

    bm is required: all data reads use bmesh to avoid race conditions
    during OBJECT↔EDIT mode transitions where me.* collections can be
    in a transient state (len() non-zero but foreach_get sees 0 elements).
    """
    if bm is None or not me.uv_layers.active or not me.polygons:
        return []
    if len(me.polygons) > _UV_ISLAND_MAX_POLYS:
        return []

    uv_layer = bm.loops.layers.uv.active
    if not uv_layer:
        return []

    n_loops = len(me.loops)
    cache_key = (me.as_pointer(), n_loops)
    if cache_key in _uv_island_cache:
        return _uv_island_cache[cache_key]

    # ── Build all data from bmesh — no me.* foreach_get ────────────────────
    bm.faces.ensure_lookup_table()
    n_polys = len(bm.faces)

    # lu: loop_index → rounded (u, v) tuple
    # lv: loop_index → vertex_index
    lu: dict = {}
    lv: dict = {}
    for face in bm.faces:
        for loop in face.loops:
            li = loop.index
            uv = loop[uv_layer].uv
            lu[li] = (round(uv.x, 6), round(uv.y, 6))
            lv[li] = loop.vert.index

    # ── Union-Find with path compression ────────────────────────────────────
    parent = list(range(n_polys))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Half-edge → list of (poly_idx, uv_at_v0, uv_at_v1)
    # Canonical key: smaller vertex first so opposite halves share the key.
    edge_map = defaultdict(list)
    for face in bm.faces:
        pi = face.index
        loops = face.loops
        lt = len(loops)
        for i in range(lt):
            loop0 = loops[i]
            loop1 = loops[(i + 1) % lt]
            li0, li1 = loop0.index, loop1.index
            v0, v1 = lv[li0], lv[li1]
            u0, u1 = lu[li0], lu[li1]
            if v0 < v1:
                edge_map[(v0, v1)].append((pi, u0, u1))
            else:
                edge_map[(v1, v0)].append((pi, u1, u0))

    for entries in edge_map.values():
        if len(entries) < 2:
            continue
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                pa, ua0, ua1 = entries[i]
                pb, ub0, ub1 = entries[j]
                if ua0 == ub0 and ua1 == ub1:
                    union(pa, pb)

    islands_map = defaultdict(list)
    for pi in range(n_polys):
        islands_map[find(pi)].append(pi)

    result = []
    for polys in islands_map.values():
        u_min = v_min = float('inf')
        u_max = v_max = float('-inf')
        for pi in polys:
            face = bm.faces[pi]
            for loop in face.loops:
                u, v = lu[loop.index]
                if u < u_min: u_min = u
                if u > u_max: u_max = u
                if v < v_min: v_min = v
                if v > v_max: v_max = v
        result.append((polys, u_min, v_min, u_max, v_max))

    _uv_island_cache[cache_key] = result
    return result


# ── Canonical EDIT-mode UV/topology snapshot ─────────────────────────────────
# In EDIT mode me.* is stale (Blender writes the original mesh back on mode
# exit) and me loop indices do NOT match BMesh loop order — mixing the two
# produced wrong UV data after any topology edit.  Every EDIT-mode UV read
# must come from ONE consistent BMesh walk; this helper is that walk.
#
# The snapshot is cached per update cycle (cleared in update_datas() alongside
# the island caches) so the O(n_loops) Python walk runs once per check cycle,
# not once per UV check.

_edit_uv_cache: dict = {}


def _edit_uv_data(bm):
    """Walk the live edit-BMesh in face order, assigning sequential loop
    positions (also written to l.index so calc_loop_triangles() results map
    onto the same ordering).

    Returns a dict of numpy arrays:
      uv         (n_loops, 2)  float32 — active UV layer, loop order
      loop_vert  (n_loops,)    int32   — vert index per loop
      loop_face  (n_loops,)    int32   — face index per loop
      face_start (n_faces,)    int32
      face_len   (n_faces,)    int32
      face_mat   (n_faces,)    int32   — material_index per face
      tri_loop   (n_tris, 3)   int32   — loop positions (this ordering)
      tri_vert   (n_tris, 3)   int32   — vert indices per triangle
      co         (n_verts, 3)  float32 — local coords, indexed by vert index
    or None when no active UV layer.
    """
    import numpy as np
    uv_layer = bm.loops.layers.uv.active
    if uv_layer is None:
        return None

    # NOTE: BMLoopSeq has no len() — loop count is derived from the walk below.
    # The cache is cleared at the start of every update cycle (update_datas),
    # so the key only needs to separate objects within one cycle.
    cache_key = (id(bm), len(bm.verts), len(bm.edges), len(bm.faces))
    cached = _edit_uv_cache.get(cache_key)
    if cached is not None:
        return cached

    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    bm.verts.index_update()
    bm.faces.index_update()

    uv_l:    list = []
    lv:      list = []
    lf:      list = []
    face_start: list = []
    face_len:   list = []
    face_mat:   list = []
    pos = 0
    for fi, f in enumerate(bm.faces):
        face_start.append(pos)
        face_mat.append(f.material_index)
        n = 0
        for l in f.loops:
            uv = l[uv_layer].uv
            uv_l.append(uv.x)
            uv_l.append(uv.y)
            lv.append(l.vert.index)
            lf.append(fi)
            l.index = pos
            pos += 1
            n += 1
        face_len.append(n)

    uv = np.array(uv_l, dtype=np.float32).reshape(-1, 2)
    loop_vert = np.array(lv, dtype=np.int32)
    loop_face = np.array(lf, dtype=np.int32)

    tris = bm.calc_loop_triangles()
    tri_loop = np.array([[t0.index, t1.index, t2.index]
                         for t0, t1, t2 in tris], dtype=np.int32)
    tri_vert = np.array([[t0.vert.index, t1.vert.index, t2.vert.index]
                         for t0, t1, t2 in tris], dtype=np.int32)

    n_verts = len(bm.verts)
    # BMVertSeq has no foreach_get (5.x) — plain walk, same cost class as above
    co = np.array([v.co[:] for v in bm.verts], dtype=np.float32).reshape(n_verts, 3)

    snap = {
        'uv': uv,
        'loop_vert': loop_vert,
        'loop_face': loop_face,
        'face_start': np.array(face_start, dtype=np.int32),
        'face_len': np.array(face_len, dtype=np.int32),
        'face_mat': np.array(face_mat, dtype=np.int32),
        'tri_loop': tri_loop,
        'tri_vert': tri_vert,
        'co': co,
        'n_faces': len(bm.faces),
        'n_loops': pos,
        'n_verts': n_verts,
    }
    _edit_uv_cache[cache_key] = snap
    return snap




def _get_uv_np(me, bm=None):
    """Return UV coordinates as a numpy array of shape (n_loops, 2), float32.

    Works in both OBJECT mode (C-level foreach_get) and EDIT mode (BMesh
    snapshot — me.uv data is stale in EDIT, see _edit_uv_data).
    Returns None when UV data is unavailable.

    OBJECT mode: me.uv_layers.active.data has n_loops items → foreach_get.
    EDIT mode:   canonical BMesh walk (_edit_uv_data) — the loop ordering is
    the BMesh face/loop order, and ALL other EDIT-mode reads must use the
    same ordering (callers get it from _edit_uv_data too).
    """
    import numpy as np
    if not me.uv_layers.active:
        return None
    n_loops  = len(me.loops)
    uv_data  = me.uv_layers.active.data

    if len(uv_data) == n_loops and not me.is_editmode:
        # OBJECT mode: fast C-level read
        uv_flat = np.empty(n_loops * 2, dtype=np.float32)
        uv_data.foreach_get("uv", uv_flat)
        return uv_flat.reshape(n_loops, 2)

    # EDIT mode — canonical BMesh snapshot (me.* is stale here)
    if bm is None:
        return None
    snap = _edit_uv_data(bm)
    if snap is None:
        return None
    return snap['uv']


def _uv_island_membership(me, max_polys: int, bm=None):
    """Union-Find UV island detection — me.* foreach_get for bulk data reads.

    Returns (poly_to_island: list[int], flat_uvs: list[float],
             poly_start: list[int], poly_total: list[int])
    or None when the poly limit is exceeded.

    Isolated from _uv_island_cache so that UVPaddingCheck can use a higher
    poly limit without polluting the shared cache used by UVUDIMBounds.
    OBJECT mode reads use me.* foreach_get (C-level bulk copy) for a 10–20×
    speedup; EDIT mode reads come from the canonical _edit_uv_data snapshot.
    """
    if bm is None:
        return None

    # ── EDIT mode: everything from the canonical BMesh snapshot ──────────────
    # me.* is stale in EDIT and me loop indices don't match BMesh order —
    # mixing them produced wrong islands after any topology edit.
    if me.is_editmode:
        snap = _edit_uv_data(bm)
        if snap is None:
            return None
        n_polys = snap['n_faces']
        if n_polys > max_polys:
            return None
        n_loops = snap['n_loops']
        if n_loops == 0:
            return None
        cache_key = (me.as_pointer(), 'EDIT', n_polys, n_loops,
                     me.uv_layers.active.name if me.uv_layers.active else '')
        cached = _uv_membership_cache.get(cache_key)
        if cached is not None:
            return cached
        flat_uvs  = snap['uv'].ravel().tolist()
        lv        = snap['loop_vert'].tolist()
        poly_start = snap['face_start'].tolist()
        poly_total = snap['face_len'].tolist()
    else:
        n_polys = len(me.polygons)
        if n_polys > max_polys:
            return None
        if not me.uv_layers.active:
            return None
        n_loops   = len(me.loops)
        uv_data   = me.uv_layers.active.data

        # ── Per-update cache (cleared in update_datas()) ─────────────────────
        # Multiple UV checks (overlap, micro_shell, padding) call this function
        # for the same mesh in one update cycle. Cache the result to avoid
        # O(n_loops) Union-Find work being repeated 3× per update.
        cache_key = (me.as_pointer(), n_loops, me.uv_layers.active.name)
        cached = _uv_membership_cache.get(cache_key)
        if cached is not None:
            return cached

        # OBJECT mode: fast C-level bulk read.
        flat_uvs = [0.0] * (n_loops * 2)
        uv_data.foreach_get("uv", flat_uvs)

        lv = [0] * n_loops
        me.loops.foreach_get("vertex_index", lv)

        poly_start = [0] * n_polys
        me.polygons.foreach_get("loop_start", poly_start)

        poly_total = [0] * n_polys
        me.polygons.foreach_get("loop_total", poly_total)

    lu = tuple(
        (round(flat_uvs[i * 2], 6), round(flat_uvs[i * 2 + 1], 6))
        for i in range(n_loops)
    )

    parent = list(range(n_polys))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edge_map: dict = defaultdict(list)
    for pi in range(n_polys):
        ls, lt = poly_start[pi], poly_total[pi]
        for i in range(lt):
            li0 = ls + i
            li1 = ls + (i + 1) % lt
            v0, v1 = lv[li0], lv[li1]
            u0, u1 = lu[li0], lu[li1]
            if v0 < v1:
                edge_map[(v0, v1)].append((pi, u0, u1))
            else:
                edge_map[(v1, v0)].append((pi, u1, u0))

    for entries in edge_map.values():
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                pa, ua0, ua1 = entries[i]
                pb, ub0, ub1 = entries[j]
                if ua0 == ub0 and ua1 == ub1:
                    ra, rb = find(pa), find(pb)
                    if ra != rb:
                        parent[ra] = rb

    root_to_idx: dict = {}
    poly_to_island = [0] * n_polys
    for pi in range(n_polys):
        r = find(pi)
        if r not in root_to_idx:
            root_to_idx[r] = len(root_to_idx)
        poly_to_island[pi] = root_to_idx[r]

    result = (poly_to_island, flat_uvs, poly_start, poly_total)
    _uv_membership_cache[cache_key] = result
    return result


class BaseCheck(ABC):
    def __init__(self, parent):
        self._parent = parent
        self._count = 0
        self._gpu_dirty = True
        self._uv_gpu_dirty = True
        self._ignored = False   # set by Ignore List — suppresses count + GPU draw

    @property
    def count(self) -> int:
        return 0 if self._ignored else self._count

    @abstractmethod
    def set_datas(self) -> None:
        pass

    @abstractmethod
    def get_edges(self, offset: float) -> Tuple:
        pass

    def get_faces(self, offset: float) -> Tuple:
        return (), []

    def get_points(self, offset: float) -> Tuple:
        return ()

    def get_uv_faces(self) -> Tuple:
        """UV-space face coords for IMAGE_EDITOR drawing."""
        return (), []

    def get_uv_edges(self) -> Tuple:
        """UV-space edge coords for IMAGE_EDITOR drawing."""
        return ()

    def get_select_data(self) -> Tuple:
        """Return (element_type, indices) for the Edit-mode Select operator.

        element_type is 'FACE', 'EDGE', or 'VERT'.
        Returns (None, []) when this check has no meaningful 3-D selection.
        """
        return (None, [])


class MainGeo(BaseCheck):
    def __init__(self, parent):
        super().__init__(parent)
        self._verts_idx: List[int] = []
        self._indices: List[Tuple[int, int, int]] = []
        self._edges_idx: List[int] = []

    def get_faces(self, offset: float):
        bm = self._parent.bm_object
        bm.verts.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        for idx in self._verts_idx:
            v = bm.verts[idx]
            p = wm @ v.co
            coords.append((p.x + v.normal.x * _offset,
                            p.y + v.normal.y * _offset,
                            p.z + v.normal.z * _offset))
        return tuple(coords), self._indices

    def get_edges(self, offset: float):
        bm = self._parent.bm_object
        bm.edges.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        for e_idx in self._edges_idx:
            for v in bm.edges[e_idx].verts:
                p = wm @ v.co
                coords.append((p.x + v.normal.x * _offset,
                                p.y + v.normal.y * _offset,
                                p.z + v.normal.z * _offset))
        return tuple(coords)


class Triangles(MainGeo):
    def __init__(self, parent):
        super().__init__(parent)
        self._faces_idx: List[int] = []

    def set_datas(self):
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        self._verts_idx.clear()
        self._indices.clear()
        self._edges_idx.clear()
        self._faces_idx = []
        faces = [f for f in bm.faces if len(f.edges) == 3]
        self._count = len(faces)
        self._faces_idx = [f.index for f in faces]
        self._verts_idx = [v.index for f in faces for v in f.verts]
        vc = len(self._verts_idx)
        self._indices = [(i, i + 1, i + 2) for i in range(0, vc, 3)]
        self._edges_idx = [e.index for f in faces for e in f.edges]

    def get_select_data(self):
        return ('FACE', self._faces_idx)


class Ngons(MainGeo):
    # Fan-triangulating thousands of ngons in EDIT mode is pointless — cap it.
    _EDIT_GPU_MAX_FACES: int = 20_000

    def __init__(self, parent):
        super().__init__(parent)
        self._faces_idx: List[int] = []

    def set_datas(self):
        import numpy as np
        self._verts_idx.clear()
        self._indices.clear()
        self._edges_idx.clear()
        self._faces_idx = []

        me = self._parent._object.data

        # In EDIT mode me.* lags behind the edit-BMesh (writeback happens on
        # mode exit) — count from BMesh so live fixes clear the counter, same
        # as the Triangles check.
        if me.is_editmode:
            bm = self._parent.bm_object
            bm.faces.ensure_lookup_table()
            bad_faces = [f for f in bm.faces if len(f.verts) > 4]
            self._count = len(bad_faces)
            if not self._count:
                return
            self._faces_idx = [f.index for f in bad_faces]
            if len(bad_faces) <= self._EDIT_GPU_MAX_FACES:
                verts_list: List[int] = []
                indices_list = []
                tri_base = 0
                for f in bad_faces:
                    fv = [v.index for v in f.verts]
                    for k in range(1, len(fv) - 1):
                        verts_list.extend((fv[0], fv[k], fv[k + 1]))
                        indices_list.append((tri_base, tri_base + 1, tri_base + 2))
                        tri_base += 3
                self._verts_idx = verts_list
                self._indices = indices_list
                self._edges_idx = [e.index for f in bad_faces for e in f.edges]
            return

        n_polys = len(me.polygons)
        if n_polys == 0:
            self._count = 0
            return

        # Detect ngons at C level — no Python face iteration needed.
        # loop_total > 4 means 5+ edges → ngon.
        poly_total = np.empty(n_polys, dtype=np.int32)
        me.polygons.foreach_get("loop_total", poly_total)
        ngon_idx = np.where(poly_total > 4)[0]
        self._count = len(ngon_idx)

        if not self._count:
            return

        self._faces_idx = ngon_idx.tolist()

        # ── GPU data: fan-triangulation via me.* (no bm.copy() overhead) ──────
        # _triangulate_polygon copies the entire BMesh — prohibitively slow on
        # 100k+ meshes even when there are only a handful of ngons.
        # Fan triangulation (v0,v1,v2), (v0,v2,v3), … is correct for convex
        # and most concave pipeline ngons; beauty-triangulate is not needed for
        # a simple red-highlight overlay.
        n_loops = len(me.loops)
        ps = np.empty(n_polys, dtype=np.int32)
        me.polygons.foreach_get("loop_start", ps)
        lv_arr = np.empty(n_loops, dtype=np.int32)
        me.loops.foreach_get("vertex_index", lv_arr)

        verts_list: List[int] = []
        indices_list = []
        tri_base = 0
        for fi in self._faces_idx:
            ls  = int(ps[fi])
            lt  = int(poly_total[fi])
            v0  = int(lv_arr[ls])
            for k in range(1, lt - 1):
                verts_list.append(v0)
                verts_list.append(int(lv_arr[ls + k]))
                verts_list.append(int(lv_arr[ls + k + 1]))
                indices_list.append((tri_base, tri_base + 1, tri_base + 2))
                tri_base += 3
        self._verts_idx = verts_list
        self._indices   = indices_list

        # Edge indices: only the small set of ngon faces — BMesh is fine here
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        faces = [bm.faces[i] for i in self._faces_idx]
        self._edges_idx = [e.index for f in faces for e in f.edges]

    def get_select_data(self):
        return ('FACE', self._faces_idx)


class NonManifold(BaseCheck):
    """Non-manifold edge detector.

    Two distinct cases are tracked separately:

    * T-junction edges  (link_faces > 2) — true structural non-manifold that
      breaks subdivision, Boolean ops and some exporters.  These drive ``count``
      and therefore the BLOCKER threshold.

    * Wire edges  (link_faces == 0) — leftover edges after internal-face deletion
      (common pipeline optimisation).  They are visualised in the viewport but do
      NOT contribute to ``count`` so they never raise a false BLOCKER.

    Open-border edges (link_faces == 1) are intentional in many assets and are
    handled separately by ``BoundaryEdges`` (WARNING).
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._tjunction_idx: List[int] = []   # link_faces > 2  → BLOCKER
        self._wire_idx:      List[int] = []   # link_faces == 0 → visualise only

    @property
    def count(self) -> int:
        if self._ignored:
            return 0
        # Only T-junctions count toward the BLOCKER threshold.
        # Wire edges are shown in the viewport but never block export.
        return len(self._tjunction_idx)

    @property
    def metric_text(self) -> str:
        if self._wire_idx:
            return f"+ {len(self._wire_idx)} wire"
        return ""

    def set_datas(self):
        bm = self._parent.bm_object
        bm.edges.ensure_lookup_table()
        self._tjunction_idx = []
        self._wire_idx      = []
        for e in bm.edges:
            nf = len(e.link_faces)
            if nf > 2:
                self._tjunction_idx.append(e.index)
            elif nf == 0:
                self._wire_idx.append(e.index)

    def _edge_coords(self, indices, bm, wm, offset):
        coords = []
        for e_idx in indices:
            for v in bm.edges[e_idx].verts:
                p = wm @ v.co
                coords.append((p.x + v.normal.x * offset,
                                p.y + v.normal.y * offset,
                                p.z + v.normal.z * offset))
        return coords

    def get_edges(self, offset: float):
        bm  = self._parent.bm_object
        obj = self._parent._object
        wm  = obj.matrix_world
        _offset = _get_offset(offset, obj)
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        # Both T-junctions and wire edges are highlighted in the viewport.
        coords = self._edge_coords(self._tjunction_idx, bm, wm, _offset)
        coords += self._edge_coords(self._wire_idx,      bm, wm, _offset)
        return tuple(coords)

    def get_select_data(self):
        # Select all problematic edges so the artist can review & clean up.
        return ('EDGE', self._tjunction_idx + self._wire_idx)


class Poles(BaseCheck):
    def __init__(self, parent):
        super().__init__(parent)
        self._e_poles_idx: Set[int] = set()
        self._n_poles_idx: Set[int] = set()
        self._more_poles_idx: Set[int] = set()

    @property
    def count(self) -> int:
        if self._ignored:
            return 0
        return len(self._e_poles_idx) + len(self._n_poles_idx) + len(self._more_poles_idx)

    def set_datas(self):
        import numpy as np
        me = self._parent._object.data

        self._e_poles_idx.clear()
        self._n_poles_idx.clear()
        self._more_poles_idx.clear()

        # In EDIT mode me.* lags behind the edit-BMesh (writeback happens on
        # mode exit) — read topology from BMesh so live fixes stay interactive.
        if me.is_editmode:
            bm = self._parent.bm_object
            bm.verts.ensure_lookup_table()
            bm.edges.ensure_lookup_table()
            n_verts = len(bm.verts)
            n_edges = len(bm.edges)
            if n_verts == 0 or n_edges == 0:
                self._count = 0
                return
            ev_list: List[int] = []
            fc_list: List[int] = []
            for e in bm.edges:
                ev_list.append(e.verts[0].index)
                ev_list.append(e.verts[1].index)
                fc_list.append(len(e.link_faces))
            ev = np.array(ev_list, dtype=np.int32).reshape(n_edges, 2)
            # Faces per edge: the BMesh knows directly — no loop bincount needed.
            edge_face_count = np.array(fc_list, dtype=np.int32)
        else:
            n_verts = len(me.vertices)
            n_edges = len(me.edges)
            n_loops = len(me.loops)
            if n_verts == 0 or n_edges == 0:
                self._count = 0
                return

            # Edge → (vert0, vert1) — C-level bulk read
            ev = np.empty(n_edges * 2, dtype=np.int32)
            me.edges.foreach_get("vertices", ev)
            ev = ev.reshape(n_edges, 2)

            # Face count per edge: count how many loops reference each edge index.
            # Each polygon loop references exactly one edge, so bincount gives the
            # number of faces that share each edge.
            el = np.empty(n_loops, dtype=np.int32)
            me.loops.foreach_get("edge_index", el)
            edge_face_count = np.bincount(el, minlength=n_edges)

        # Boundary edges: used by ≤1 face (open border or isolated edge)
        bnd_mask = edge_face_count <= 1
        bnd_ev   = ev[bnd_mask]           # (n_boundary, 2)

        # Boundary vertices: adjacent to at least one boundary edge
        bv = np.zeros(n_verts, dtype=bool)
        if len(bnd_ev):
            bv[bnd_ev[:, 0]] = True
            bv[bnd_ev[:, 1]] = True

        # Valence (edge-count) per vertex
        valence = np.bincount(ev.ravel(), minlength=n_verts)

        # Classify interior vertices only (skip boundary verts — their reduced
        # valence is topologically expected, not a pole).
        interior = ~bv
        n_mask    = interior & (valence == 3)
        e_mask    = interior & (valence == 5)
        more_mask = interior & (valence >  5)

        self._n_poles_idx    = set(np.where(n_mask)[0].tolist())
        self._e_poles_idx    = set(np.where(e_mask)[0].tolist())
        self._more_poles_idx = set(np.where(more_mask)[0].tolist())
        self._count = len(self._n_poles_idx) + len(self._e_poles_idx) + len(self._more_poles_idx)

    def get_edges(self, offset: float) -> Tuple:
        return ()

    def get_points(self, offset: float):
        bm = self._parent.bm_object
        bm.verts.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        idx_set = self._e_poles_idx | self._n_poles_idx | self._more_poles_idx
        coords = []
        for idx in idx_set:
            v = bm.verts[idx]
            p = wm @ v.co
            coords.append((p.x + v.normal.x * _offset,
                           p.y + v.normal.y * _offset,
                           p.z + v.normal.z * _offset))
        return tuple(coords)

    @property
    def metric_text(self) -> str:
        parts = []
        if self._n_poles_idx:
            parts.append(f"N:{len(self._n_poles_idx)}")
        if self._e_poles_idx:
            parts.append(f"E:{len(self._e_poles_idx)}")
        if self._more_poles_idx:
            parts.append(f"★:{len(self._more_poles_idx)}")
        return "Poles " + "  ".join(parts) if parts else ""

    def get_select_data(self):
        return ('VERT', list(self._e_poles_idx | self._n_poles_idx | self._more_poles_idx))


class ZeroAreaFaces(BaseCheck):
    def __init__(self, parent):
        super().__init__(parent)
        self._faces_idx: List[int] = []

    def set_datas(self):
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        self._faces_idx = [f.index for f in bm.faces if f.calc_area() < 1e-10]
        self._count = len(self._faces_idx)

    def get_faces(self, offset: float):
        if not self._faces_idx:
            return (), []
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords, indices, vmap, idx = [], [], {}, 0
        for fidx in self._faces_idx:
            fv = []
            for v in bm.faces[fidx].verts:
                if v.index not in vmap:
                    vmap[v.index] = idx
                    idx += 1
                    p = wm @ v.co
                    coords.append((p.x + v.normal.x * _offset,
                                   p.y + v.normal.y * _offset,
                                   p.z + v.normal.z * _offset))
                fv.append(vmap[v.index])
            for i in range(1, len(fv) - 1):
                indices.append((fv[0], fv[i], fv[i + 1]))
        return tuple(coords), indices

    def get_edges(self, offset: float):
        # Zero-area faces have zero-length edges — nothing to draw here.
        return ()

    def get_points(self, offset: float):
        """Draw a visible marker at each degenerate face's centroid.

        Zero-area faces can't be seen as face fills or edges because their
        vertices are co-located.  A large point at the centroid is the only
        reliable way to show them in the viewport.

        IMPORTANT: f.normal is (0,0,0) for zero-area faces because there is no
        area from which to derive a normal.  We fall back to the average vertex
        normal (computed from adjacent non-degenerate faces) so the point gets a
        valid offset away from the surface.  If vertex normals are also zero we
        use the global +Z direction as a last resort.
        """
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        obj = self._parent._object
        wm  = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        for fidx in self._faces_idx:
            f   = bm.faces[fidx]
            ctr = f.calc_center_median()
            p   = wm @ ctr
            # Average vertex normals — they are non-zero even for degenerate faces
            # because Blender derives them from the surrounding valid geometry.
            verts = f.verts
            nv = max(1, len(verts))
            nx = sum(v.normal.x for v in verts) / nv
            ny = sum(v.normal.y for v in verts) / nv
            nz = sum(v.normal.z for v in verts) / nv
            mag = (nx * nx + ny * ny + nz * nz) ** 0.5
            if mag < 1e-6:          # absolute fallback: push along world +Z
                nx, ny, nz = 0.0, 0.0, 1.0
            coords.append((p.x + nx * _offset,
                           p.y + ny * _offset,
                           p.z + nz * _offset))
        return tuple(coords)

    def get_select_data(self):
        # Select vertices — zero-area face fills are invisible (co-located verts),
        # but vertex dots are always visible in Edit Mode.
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        vert_indices = list({
            v.index
            for fidx in self._faces_idx
            for v in bm.faces[fidx].verts
        })
        return ('VERT', vert_indices)


class NonAppliedTransform(BaseCheck):
    def __init__(self, parent):
        super().__init__(parent)
        self._issues: List[str] = []
        self._bbox: Tuple = ()

    def set_datas(self):
        obj = self._parent._object
        self._issues.clear()
        self._bbox = ()
        for i, r in enumerate(obj.rotation_euler):
            if abs(r) > 0.001:
                self._issues.append(f"R[{i}]={math.degrees(r):.1f}°")
        self._count = 1 if self._issues else 0
        if self._issues:
            mw = obj.matrix_world
            corners = [mw @ mathutils.Vector(c) for c in obj.bound_box]
            edge_idx = [0,1,1,2,2,3,3,0, 4,5,5,6,6,7,7,4, 0,4,1,5,2,6,3,7]
            self._bbox = tuple((corners[i].x, corners[i].y, corners[i].z) for i in edge_idx)

    @property
    def description(self):
        return "; ".join(self._issues) if self._issues else "OK"

    def get_edges(self, offset: float):
        return self._bbox

    def get_points(self, offset: float):
        return ()


class Scale(BaseCheck):
    """Scale != 1.0 по любой оси — bbox-маркер, толстая линия."""

    def __init__(self, parent):
        super().__init__(parent)
        self._bbox: Tuple = ()

    def set_datas(self):
        obj = self._parent._object
        has_issue = any(abs(s - 1.0) > 0.001 for s in obj.scale)
        self._count = 1 if has_issue else 0
        self._bbox = ()
        if has_issue:
            mw = obj.matrix_world
            corners = [mw @ mathutils.Vector(c) for c in obj.bound_box]
            edge_idx = [0,1,1,2,2,3,3,0, 4,5,5,6,6,7,7,4, 0,4,1,5,2,6,3,7]
            self._bbox = tuple((corners[i].x, corners[i].y, corners[i].z) for i in edge_idx)

    def get_edges(self, offset: float):
        return self._bbox

    def get_points(self, offset: float):
        return ()


class ZFighting(BaseCheck):
    """Coplanar face overlap — intra-object (self) and inter-object (other tracked meshes).

    Intra detection: BVHTree.overlap(self) — faces within the same mesh.
    Inter detection: run by MeshCheck._run_inter_object_z_fighting() after all
    intra checks complete; results injected via _inter_faces_idx / _inter_object_names.

    count = len(intra) + len(inter) so the panel always reflects the full picture.
    metric_text: "Z-Fight: 4 self + 2 inter (wheel_rim)"
    """

    # Guard: skip intra BVH on very dense meshes to avoid long stalls
    _MAX_FACES_INTRA: int = 200_000

    def __init__(self, parent):
        super().__init__(parent)
        self._intra_faces_idx: List[int] = []
        self._inter_faces_idx: Set[int]  = set()
        self._inter_object_names: Set[str] = set()
        self._edges_idx: List[int] = []

    # Override count so inter results are included even after set_datas()
    @property
    def count(self) -> int:
        if self._ignored:
            return 0
        return len(self._intra_faces_idx) + len(self._inter_faces_idx)

    def set_datas(self):
        from mathutils.bvhtree import BVHTree
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()

        # Clear all state (including any previous inter results)
        self._intra_faces_idx = []
        self._inter_faces_idx = set()
        self._inter_object_names = set()
        self._edges_idx = []
        self.metric_text = ""

        if len(bm.faces) > self._MAX_FACES_INTRA:
            return

        # ── Intra-object: self-overlap via BVH ──────────────────────────────
        # Three-stage false-positive elimination:
        #
        # Stage 1 — signed dot (no abs): only same-winding coplanar faces.
        #   Removing abs() discards opposite-winding pairs (inner/outer shell
        #   of a closed mesh, e.g. fuselage skin panels) which caused thousands
        #   of false positives with the original abs() test.
        #
        # Stage 2 — adjacency skip: faces sharing a vertex are neighbouring on
        #   the surface.  On smooth-shaded meshes their normals converge to the
        #   same value even though the faces don't overlap.
        #
        # Stage 3 — 0.1 mm world-space centroid gate: truly duplicated faces
        #   have centroid distance ≈ 0 (sub-micron for exact copies).
        #   1 mm was too loose: small internal-detail faces (area ratio 40×)
        #   barely touching a larger structural face at ~0.98 mm triggered
        #   false positives.  0.1 mm eliminates those while keeping all
        #   real duplicates (which sit at < 1 μm).
        #
        wm        = self._parent._object.matrix_world
        sl        = bpy.context.scene.unit_settings.scale_length or 1.0
        threshold = 0.0001 / sl         # 0.1 mm in Blender world units

        bvh = BVHTree.FromBMesh(bm, epsilon=0.0001)
        eps_normal = 0.99
        intra: Set[int] = set()
        for idx1, idx2 in bvh.overlap(bvh):
            if idx1 >= idx2:
                continue
            f1, f2 = bm.faces[idx1], bm.faces[idx2]
            # Stage 1 — same winding only
            if f1.normal.dot(f2.normal) <= eps_normal:
                continue
            # Stage 2 — skip adjacent faces
            verts1 = {v.index for v in f1.verts}
            if any(v.index in verts1 for v in f2.verts):
                continue
            # Stage 3 — centroid distance ≤ 1 mm (world space)
            c1 = wm @ f1.calc_center_median()
            c2 = wm @ f2.calc_center_median()
            if (c1 - c2).length > threshold:
                continue
            intra.add(idx1)
            intra.add(idx2)

        self._intra_faces_idx = list(intra)
        self._rebuild_edges()
        self._update_metric_text()

    # ── Called by MeshCheck._run_inter_object_z_fighting() ──────────────────
    def add_inter_results(self, face_indices: Set[int], obj_name: str):
        """Inject inter-object Z-fighting results from manager.py."""
        self._inter_faces_idx.update(face_indices)
        self._inter_object_names.add(obj_name)
        self._rebuild_edges()
        self._update_metric_text()
        self._gpu_dirty = True

    def _rebuild_edges(self):
        bm = self._parent.bm_object
        all_faces = set(self._intra_faces_idx) | self._inter_faces_idx
        self._edges_idx = list(
            {e.index for fidx in all_faces for e in bm.faces[fidx].edges}
        )

    def _update_metric_text(self):
        n_intra = len(self._intra_faces_idx)
        n_inter = len(self._inter_faces_idx)
        if n_intra == 0 and n_inter == 0:
            self.metric_text = ""
            return
        parts = []
        if n_intra:
            parts.append(f"{n_intra} self")
        if n_inter:
            objs = ", ".join(sorted(self._inter_object_names))
            parts.append(f"{n_inter} inter ({objs})")
        self.metric_text = "Z-Fight: " + " + ".join(parts)

    def get_edges(self, offset: float):
        if not self._edges_idx:
            return ()
        bm = self._parent.bm_object
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        for e_idx in self._edges_idx:
            for v in bm.edges[e_idx].verts:
                p = wm @ v.co
                coords.append((p.x + v.normal.x * _offset,
                               p.y + v.normal.y * _offset,
                               p.z + v.normal.z * _offset))
        return tuple(coords)

    def get_select_data(self):
        return ('FACE', list(set(self._intra_faces_idx) | self._inter_faces_idx))


class NamingCheck(BaseCheck):
    def __init__(self, parent):
        super().__init__(parent)
        self._results: List = []   # List[ValidationResult]

    @property
    def results(self) -> List:
        return self._results

    def set_datas(self) -> None:
        from .naming import NamingValidator, WARNING, ERROR, get_active_policy
        self._results.clear()
        obj = self._parent._object
        if obj.type != "MESH":
            self._count = 0
            return

        # Build policy: addon prefs base + inline panel fields
        try:
            addon_name = __name__.rsplit(".", 1)[0]
            prefs = bpy.context.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None
        policy = get_active_policy(prefs)

        try:
            mc = bpy.context.window_manager.mesh_check_props
            pref = mc.obj_required_prefix.strip().lower()
            suf  = mc.obj_required_suffix.strip().lower()
            if pref and pref not in policy["object"]["required_prefixes"]:
                policy["object"]["required_prefixes"].append(pref)
            if suf and suf not in policy["object"]["required_suffixes"]:
                policy["object"]["required_suffixes"].append(suf)
        except Exception:
            pass

        self._results = NamingValidator.validate_object(obj, policy=policy)
        # count = blocking issues only (WARNING + ERROR); INFO doesn't drive status
        self._count = sum(1 for r in self._results if r.severity in (WARNING, ERROR))

    def get_edges(self, offset: float) -> Tuple:
        return ()

    def get_points(self, offset: float) -> Tuple:
        """Mark objects with WARNING/ERROR as a point above origin."""
        if not self._results:
            return ()
        from .naming import WARNING, ERROR
        if not any(r.severity in (WARNING, ERROR) for r in self._results):
            return ()
        obj = self._parent._object
        loc = obj.matrix_world.translation
        _offset = _get_offset(offset * 2, obj)
        return ((loc.x, loc.y, loc.z + _offset),)


class MaterialCheck(BaseCheck):
    def set_datas(self):
        self._count = sum(
            1 for slot in self._parent._object.material_slots
            if slot.material and not slot.material.name.lower().endswith("_mat")
        )

    def get_edges(self, offset: float):
        return ()

    def get_points(self, offset: float):
        return ()


class MatAssignment(BaseCheck):
    """Каждый слот должен иметь материал; объект не должен быть без слотов."""

    def set_datas(self):
        slots = self._parent._object.material_slots
        self._count = 1 if not slots else sum(1 for s in slots if s.material is None)

    def get_edges(self, offset: float):
        return ()

    def get_points(self, offset: float):
        return ()


class MatNaming(BaseCheck):
    """Material names must not contain Blender auto-numbering (.001, .002 ...).

    Catches stale default material copies that were never renamed — a common
    pipeline mistake that breaks shader assignment automation downstream.
    """

    _RE_NUMBERING = re.compile(r'\.\d{3,}$')

    def __init__(self, parent):
        super().__init__(parent)
        self._issues: List[str] = []

    def set_datas(self):
        self._issues = []
        for slot in self._parent._object.material_slots:
            mat = slot.material
            if mat is None:
                continue
            if self._RE_NUMBERING.search(mat.name):
                self._issues.append(mat.name)
        self._count = len(self._issues)

    @property
    def metric_text(self) -> str:
        if not self._issues:
            return ""
        n = len(self._issues)
        first = self._issues[0]
        return f"Mat numbering: {first}" + (f" +{n - 1}" if n > 1 else "")

    def get_edges(self, offset: float):
        return ()

    def get_points(self, offset: float):
        return ()


class ColNaming(BaseCheck):
    """Коллекции объекта: нейминг через NamingValidator (configurable policy).

    _grp больше не хардкод — суффикс задаётся через preferences.
    Scene root пропускается по ссылке; системные коллекции — по skip_names.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._results: List = []   # List[ValidationResult]

    @property
    def results(self) -> List:
        return self._results

    def set_datas(self):
        from .naming import NamingValidator, WARNING, ERROR, get_active_policy, NAMING_RULES
        self._results.clear()
        obj = self._parent._object
        try:
            scene_root = bpy.context.scene.collection
        except Exception:
            scene_root = None

        # Build policy: addon prefs base + inline panel fields
        try:
            addon_name = __name__.rsplit(".", 1)[0]
            prefs = bpy.context.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None
        policy = get_active_policy(prefs)

        try:
            mc = bpy.context.window_manager.mesh_check_props
            pref = mc.col_required_prefix.strip().lower()
            suf  = mc.col_required_suffix.strip().lower()
            if pref and pref not in policy["collection"]["required_prefixes"]:
                policy["collection"]["required_prefixes"].append(pref)
            if suf and suf not in policy["collection"]["required_suffixes"]:
                policy["collection"]["required_suffixes"].append(suf)
        except Exception:
            pass

        skip_lower = NAMING_RULES["collection"].get("skip_names", set())
        # deduplicate: each collection reported only once per checker
        seen: set = set()
        for col in obj.users_collection:
            if col is scene_root:
                continue
            if col.name.lower() in skip_lower:
                continue
            if col.name in seen:
                continue
            seen.add(col.name)
            self._results.extend(NamingValidator.validate_collection(col, policy=policy))

        self._count = sum(1 for r in self._results if r.severity in (WARNING, ERROR))

    def get_edges(self, offset: float):
        return ()

    def get_points(self, offset: float):
        return ()


class UVSingleSet(BaseCheck):
    """Ровно один UV-сет — не больше и не меньше."""

    def __init__(self, parent):
        super().__init__(parent)
        self._bbox: Tuple = ()
        self.metric_text: str = ""

    def set_datas(self):
        obj = self._parent._object
        me  = obj.data
        n   = len(me.uv_layers)
        if n == 1:
            self._count      = 0
            self._bbox       = ()
            self.metric_text = ""
            return
        self._count = 1
        if n == 0:
            self.metric_text = "No UV map"
        else:
            names = ", ".join(l.name for l in me.uv_layers)
            self.metric_text = f"{n} UV maps: {names}"
        mw = obj.matrix_world
        corners = [mw @ mathutils.Vector(c) for c in obj.bound_box]
        edge_idx = [0,1,1,2,2,3,3,0, 4,5,5,6,6,7,7,4, 0,4,1,5,2,6,3,7]
        self._bbox = tuple((corners[i].x, corners[i].y, corners[i].z) for i in edge_idx)

    def get_edges(self, offset: float):
        return self._bbox

    def get_points(self, offset: float):
        return ()



class UVOverlapCheck(BaseCheck):
    """UV-overlap: island filter + 2D grid broad-phase + exact triangle-triangle test.

    Pipeline:
      1. Build UV island membership (Union-Find).  Triangles within the same
         island share a connected UV surface and cannot overlap each other —
         skipping intra-island pairs eliminates >99% of candidates on typical
         packed UV layouts.
      2. 2D spatial grid broad-phase (_uv_grid_candidates) for remaining pairs.
      3. AABB pre-filter: eliminates ~85% of remaining grid candidates.
      4. Exact _uv_tris_truly_overlap test on the surviving ~1% of pairs.

    BVHTree was dropped — it performs 3D volume intersection and returns zero
    results for coplanar (z=0) UV triangles.

    Note: intra-island self-intersections (manually folded islands) are not
    detected; inter-island overlaps (the common pipeline problem) are fully covered.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._overlap_tri_uvs: List = []

    def set_datas(self):
        me = self._parent._object.data
        self._overlap_tri_uvs.clear()
        self._count = 0
        if not me.uv_layers.active:
            return

        # UV layer existence check via BMesh (avoids stale me.uv_layers in edit mode)
        bm = self._parent.bm_object
        if not bm.loops.layers.uv.active:
            return

        # ── Data reads via numpy foreach_get (C-level, no Python tri loop) ──────
        import numpy as np
        if me.is_editmode:
            # EDIT mode: canonical BMesh snapshot (me.* is stale, me loop
            # indices don't match BMesh loop order).
            snap = _edit_uv_data(bm)
            if snap is None:
                return
            tri_loop_np = snap['tri_loop']
            n_tris = len(tri_loop_np)
            if n_tris == 0 or n_tris > _UV_OVERLAP_MAX_TRIS:
                return
            tri_poly_np = snap['loop_face'][tri_loop_np[:, 0]]
            uv_np = snap['uv']
        else:
            me.calc_loop_triangles()
            n_tris = len(me.loop_triangles)
            if n_tris == 0:
                return
            if n_tris > _UV_OVERLAP_MAX_TRIS:
                return

            tri_loop_np = np.empty(n_tris * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("loops", tri_loop_np)
            tri_loop_np = tri_loop_np.reshape(n_tris, 3)

            tri_poly_np = np.empty(n_tris, dtype=np.int32)
            me.loop_triangles.foreach_get("polygon_index", tri_poly_np)

            # UV read: C-level in OBJECT mode
            uv_np = _get_uv_np(me, bm=bm)
            if uv_np is None:
                return

        # Per-triangle UV vertices (fancy indexing — fast C-level gather)
        uv0 = uv_np[tri_loop_np[:, 0]]   # (n_tris, 2)
        uv1 = uv_np[tri_loop_np[:, 1]]   # (n_tris, 2)
        uv2 = uv_np[tri_loop_np[:, 2]]   # (n_tris, 2)

        # Per-triangle AABB (vectorised) — convert to Python lists once for the
        # grid phase (Python list element access is faster than numpy scalar access).
        u_min_l = np.minimum(np.minimum(uv0[:, 0], uv1[:, 0]), uv2[:, 0]).tolist()
        v_min_l = np.minimum(np.minimum(uv0[:, 1], uv1[:, 1]), uv2[:, 1]).tolist()
        u_max_l = np.maximum(np.maximum(uv0[:, 0], uv1[:, 0]), uv2[:, 0]).tolist()
        v_max_l = np.maximum(np.maximum(uv0[:, 1], uv1[:, 1]), uv2[:, 1]).tolist()

        tri_poly_list = tri_poly_np.tolist()   # int list for fast Python lookup

        # Stage 1 — island membership (shared cache hit if other UV checks ran first)
        tri_island_list: List = []
        membership = _uv_island_membership(me, _UV_PADDING_MAX_POLYS, bm=self._parent.bm_object)
        if membership:
            poly_to_island = membership[0]
            n_p2i = len(poly_to_island)
            p2i_np = np.array(poly_to_island, dtype=np.int32)
            valid  = tri_poly_np < n_p2i
            isl_np = np.where(valid, p2i_np[tri_poly_np.clip(0, n_p2i - 1)], -1)
            tri_island_list = isl_np.tolist()

        # Stage 2 — 2D grid broad-phase using pre-computed AABB lists
        candidates = _uv_grid_candidates_fast(
            u_min_l, v_min_l, u_max_l, v_max_l,
            tri_poly_list, tri_island_list if tri_island_list else None,
            grid_size=128,
        )

        flagged_polys:    Set[int] = set()
        flagged_tri_idxs: Set[int] = set()

        # Build UV tuples lazily — only for candidate pairs, not for all n_tris.
        # For well-packed UV this is <1% of triangles; avoids the full O(n) loop.
        _uv_cache: dict = {}   # tri_index → ((u0,v0),(u1,v1),(u2,v2))

        def get_tri_uvs(k):
            t = _uv_cache.get(k)
            if t is None:
                t = ((float(uv0[k, 0]), float(uv0[k, 1])),
                     (float(uv1[k, 0]), float(uv1[k, 1])),
                     (float(uv2[k, 0]), float(uv2[k, 1])))
                _uv_cache[k] = t
            return t

        for i, j in candidates:
            # AABB pre-filter — Python float list access, no numpy overhead
            if (u_max_l[i] < u_min_l[j] or u_max_l[j] < u_min_l[i] or
                    v_max_l[i] < v_min_l[j] or v_max_l[j] < v_min_l[i]):
                continue
            if _uv_tris_truly_overlap(get_tri_uvs(i), get_tri_uvs(j)):
                flagged_polys.add(tri_poly_list[i])
                flagged_polys.add(tri_poly_list[j])
                flagged_tri_idxs.add(i)
                flagged_tri_idxs.add(j)

        self._overlap_tri_uvs = [get_tri_uvs(k) for k in flagged_tri_idxs]
        self._count = len(flagged_polys)

    def get_edges(self, offset: float):
        return ()

    def get_uv_faces(self) -> Tuple:
        if not self._overlap_tri_uvs:
            return (), []
        coords = []
        indices = []
        for tri in self._overlap_tri_uvs:
            base = len(coords)
            coords.extend((u, v, 0.0) for u, v in tri)
            indices.append((base, base + 1, base + 2))
        return tuple(coords), indices

    def get_uv_edges(self) -> Tuple:
        if not self._overlap_tri_uvs:
            return ()
        coords = []
        for tri in self._overlap_tri_uvs:
            for i in range(3):
                u1, v1 = tri[i]
                u2, v2 = tri[(i + 1) % 3]
                coords.append((u1, v1, 0.0))
                coords.append((u2, v2, 0.0))
        return tuple(coords)


class UVMicroShellCheck(BaseCheck):
    """Detects UV islands whose total UV area is below a minimum threshold.

    A 'micro shell' is an entire UV island that is too small to receive
    meaningful texture detail — typically collapsed or forgotten islands left
    over after UV packing.  Counting individual small triangles (the old
    approach) produced massive false-positives on dense meshes because normal
    islands contain many thin triangles.

    Algorithm:
      1. Build island membership via _uv_island_membership.
      2. Sum UV-triangle areas per island.
      3. Flag islands with total area < _MICRO_SHELL_ISLAND_AREA.
      Fallback (mesh > _UV_MICRO_SHELL_MAX_POLYS): per-triangle check with the
      near-zero _MICRO_SHELL_UV_AREA threshold (degenerate UV only).

    count = number of flagged UV islands.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._micro_tri_uvs: List = []

    def set_datas(self):
        me = self._parent._object.data
        self._micro_tri_uvs.clear()
        self._count = 0
        if not me.uv_layers.active:
            return

        bm = self._parent.bm_object
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            return

        # ── Triangle index buffers — allocated as numpy directly ──────────────
        # Avoids the slow Python-list → numpy conversion for large meshes.
        import numpy as np
        if me.is_editmode:
            # EDIT mode: canonical BMesh snapshot (me.* is stale here).
            snap = _edit_uv_data(bm)
            if snap is None:
                return
            tri_loop_np = snap['tri_loop']
            tri_poly_np = snap['loop_face'][tri_loop_np[:, 0]]
            n_tris = len(tri_loop_np)
            if n_tris == 0:
                return
        else:
            me.calc_loop_triangles()
            n_tris = len(me.loop_triangles)
            if n_tris == 0:
                return

            tri_loop_np = np.empty(n_tris * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("loops", tri_loop_np)     # C-level, no Python iter

            tri_poly_np = np.empty(n_tris, dtype=np.int32)
            me.loop_triangles.foreach_get("polygon_index", tri_poly_np)

        # ── Island-based detection (fully vectorised) ──────────────────────────
        # All reads go through me.* foreach_get into numpy; no Python loop over
        # triangles.  uv_np is read here independently (not from flat_uvs cache)
        # so we get float32 numpy indexing for free.
        membership = _uv_island_membership(me, _UV_MICRO_SHELL_MAX_POLYS, bm=bm)
        if membership is not None:
            poly_to_island, _flat_uvs_unused, _ps, _pt = membership
            n_polys_p2i = len(poly_to_island)
            n_islands    = (max(poly_to_island) + 1) if poly_to_island else 0

            # Read UVs into numpy for fast indexed access
            uv_np = _get_uv_np(me, bm=bm)
            if uv_np is None:
                return
            n_loops = len(uv_np)

            tri_l  = tri_loop_np.reshape(n_tris, 3)
            pi_arr = tri_poly_np                              # (n_tris,)

            # Filter triangles whose poly index is within bounds
            valid  = pi_arr < n_polys_p2i
            if not valid.any():
                return

            pi_v   = pi_arr[valid]
            tri_lv = tri_l[valid]

            # Per-triangle island index
            p2i_arr = np.array(poly_to_island, dtype=np.int32)
            ii_arr  = p2i_arr[pi_v]                          # (n_valid_tris,)

            # UV triangle vertices
            uv0 = uv_np[tri_lv[:, 0]]
            uv1 = uv_np[tri_lv[:, 1]]
            uv2 = uv_np[tri_lv[:, 2]]
            a = uv1 - uv0;  b = uv2 - uv0
            tri_areas = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) * 0.5

            # Sum areas per island (bincount with float weights)
            island_area = np.bincount(ii_arr, weights=tri_areas.astype(np.float64),
                                      minlength=n_islands)

            micro_mask_isl = island_area < _MICRO_SHELL_ISLAND_AREA
            micro_islands_arr = np.where(micro_mask_isl)[0]
            self._count = len(micro_islands_arr)

            if self._count:
                micro_isl_set = set(micro_islands_arr.tolist())
                tri_is_micro  = np.isin(ii_arr, micro_islands_arr)
                mu0 = uv0[tri_is_micro];  mu1 = uv1[tri_is_micro];  mu2 = uv2[tri_is_micro]
                self._micro_tri_uvs = [
                    ((float(mu0[i, 0]), float(mu0[i, 1])),
                     (float(mu1[i, 0]), float(mu1[i, 1])),
                     (float(mu2[i, 0]), float(mu2[i, 1])))
                    for i in range(len(mu0))
                ]
            return

        # ── Fallback: per-triangle (mesh > _UV_MICRO_SHELL_MAX_POLYS) ─────────
        # tri_loop_np is already a numpy array — zero-copy reshape.
        uv_np = _get_uv_np(me, bm=bm)
        if uv_np is None:
            return

        tri_l = tri_loop_np.reshape(n_tris, 3)       # free reshape, no copy
        uv0 = uv_np[tri_l[:, 0]];  uv1 = uv_np[tri_l[:, 1]];  uv2 = uv_np[tri_l[:, 2]]
        a = uv1 - uv0;  b = uv2 - uv0
        areas = np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) * 0.5

        micro_mask = areas < _MICRO_SHELL_UV_AREA
        if not micro_mask.any():
            self._count = 0
            return

        micro_idx  = np.where(micro_mask)[0]
        micro_poly = set(tri_poly_np[micro_idx].tolist())
        micro_tris = [
            ((float(uv0[i, 0]), float(uv0[i, 1])),
             (float(uv1[i, 0]), float(uv1[i, 1])),
             (float(uv2[i, 0]), float(uv2[i, 1])))
            for i in micro_idx
        ]
        self._micro_tri_uvs = micro_tris
        self._count = len(micro_poly)

    def get_edges(self, offset: float):
        return ()

    def get_uv_faces(self) -> Tuple:
        if not self._micro_tri_uvs:
            return (), []
        coords = []
        indices = []
        for tri in self._micro_tri_uvs:
            base = len(coords)
            coords.extend((u, v, 0.0) for u, v in tri)
            indices.append((base, base + 1, base + 2))
        return tuple(coords), indices

    def get_uv_edges(self) -> Tuple:
        if not self._micro_tri_uvs:
            return ()
        coords = []
        for tri in self._micro_tri_uvs:
            for i in range(3):
                u1, v1 = tri[i]
                u2, v2 = tri[(i + 1) % 3]
                coords.append((u1, v1, 0.0))
                coords.append((u2, v2, 0.0))
        return tuple(coords)


class UVTexelDensity(BaseCheck):
    """Texel density in px/cm using a configurable reference texture size.

    Formula (from Texel Density Checker addon):
        TD = tex_size × √uv_area / (√world_area_m² × 100 × scale_length)

    When a target TD is set in preferences, count = 1 if deviation exceeds
    the configured tolerance; otherwise count is always 0 (informational).
    """

    _TD_TEX_SIZES = {'0': 512, '1': 1024, '2': 2048, '3': 4096}

    def __init__(self, parent):
        super().__init__(parent)
        self._density: float = 0.0
        self._uv_area: float = 0.0
        self._world_area: float = 0.0

    @property
    def metric_text(self) -> str:
        if self._world_area < 1e-10:
            return "Texel Density: N/A"
        try:
            addon_name = __name__.rsplit(".", 1)[0]
            prefs = bpy.context.preferences.addons[addon_name].preferences
            target_td = getattr(prefs, 'uv_td_target', 0.0)
        except Exception:
            target_td = 0.0
        if target_td > 0.0:
            return f"TD: {self._density:.2f} / {target_td:.2f} px/cm"
        return f"TD: {self._density:.2f} px/cm"

    def set_datas(self):
        me = self._parent._object.data
        obj = self._parent._object
        self._uv_area = 0.0
        self._world_area = 0.0
        self._density = 0.0
        self._count = 0

        if not me.uv_layers.active or not me.polygons:
            return

        # ── UV layer existence check via BMesh (race-condition safe) ──────────
        bm = self._parent.bm_object
        if not bm.loops.layers.uv.active:
            return

        # ── All data reads via me.* foreach_get into numpy arrays (fully vectorized) ──
        # TD is an aggregate scalar — small transient inconsistency in edit mode is acceptable.
        import numpy as np

        if me.is_editmode:
            # EDIT mode: canonical BMesh snapshot (me.* is stale here).
            snap = _edit_uv_data(bm)
            if snap is None:
                return
            tri_l = snap['tri_loop']
            tri_v = snap['tri_vert']
            co_np = snap['co']
            uv_np = snap['uv']
            n_tris = len(tri_l)
            if n_tris == 0:
                return
        else:
            me.calc_loop_triangles()
            n_tris = len(me.loop_triangles)
            if n_tris == 0:
                return

            # C-level bulk reads directly into numpy buffers
            uv_np = _get_uv_np(me, bm=bm)
            if uv_np is None:
                return

            n_verts = len(me.vertices)
            co_np = np.empty(n_verts * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co_np)
            co_np = co_np.reshape(n_verts, 3)

            tri_l = np.empty(n_tris * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("loops", tri_l)
            tri_l = tri_l.reshape(n_tris, 3)

            tri_v = np.empty(n_tris * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("vertices", tri_v)
            tri_v = tri_v.reshape(n_tris, 3)

        # ── UV area — vectorized 2D cross product ─────────────────────────────
        uv0 = uv_np[tri_l[:, 0]]   # (n_tris, 2)
        uv1 = uv_np[tri_l[:, 1]]
        uv2 = uv_np[tri_l[:, 2]]
        a_uv = uv1 - uv0;  b_uv = uv2 - uv0
        uv_area = float(np.abs(a_uv[:, 0] * b_uv[:, 1] - a_uv[:, 1] * b_uv[:, 0]).sum()) * 0.5

        # ── World area — vectorized cross product with world matrix ───────────
        wm = obj.matrix_world
        wm33 = np.array([[wm[0][0], wm[0][1], wm[0][2]],
                         [wm[1][0], wm[1][1], wm[1][2]],
                         [wm[2][0], wm[2][1], wm[2][2]]], dtype=np.float32)
        v0 = co_np[tri_v[:, 0]];  v1 = co_np[tri_v[:, 1]];  v2 = co_np[tri_v[:, 2]]
        e1 = (v1 - v0) @ wm33.T   # (n_tris, 3) — edge vectors in world space
        e2 = (v2 - v0) @ wm33.T
        cx = e1[:, 1] * e2[:, 2] - e1[:, 2] * e2[:, 1]
        cy = e1[:, 2] * e2[:, 0] - e1[:, 0] * e2[:, 2]
        cz = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
        world_area = float(np.sqrt(cx * cx + cy * cy + cz * cz).sum()) * 0.5

        self._world_area = world_area
        self._uv_area = uv_area

        if world_area < 1e-10 or uv_area < 1e-10:
            return

        # ── Preferences ─────────────────────────────────────────────────────
        try:
            addon_name = __name__.rsplit(".", 1)[0]
            prefs = bpy.context.preferences.addons[addon_name].preferences
            tex_size  = self._TD_TEX_SIZES.get(getattr(prefs, 'uv_td_texture_size', '2'), 2048)
            target_td = getattr(prefs, 'uv_td_target',    0.0)
            tolerance = getattr(prefs, 'uv_td_tolerance', 20.0) / 100.0
        except Exception:
            tex_size  = 2048
            target_td = 0.0
            tolerance = 0.20

        scale_length = bpy.context.scene.unit_settings.scale_length
        if scale_length < 1e-10:
            scale_length = 1.0

        # TD (px/cm) = tex_size × √uv_area / (√world_area_m² × 100 × scale_length)
        self._density = (tex_size * math.sqrt(uv_area)) / (math.sqrt(world_area) * 100.0 * scale_length)

        if target_td > 0.0:
            deviation = abs(self._density - target_td) / target_td
            self._count = 1 if deviation > tolerance else 0

    def get_edges(self, offset: float) -> Tuple:
        return ()

    def get_points(self, offset: float) -> Tuple:
        return ()


class UVStretch(BaseCheck):
    """UV stretch: detects faces where UV angles deviate significantly from 3D mesh angles.

    Algorithm from ZenUV (stretch_map.py): for each loop, compare the angle at the
    vertex in 3D space (loop.calc_angle()) with the same angle in UV space.
    Large difference → that face is stretched / squashed in the UV layout.

    count = number of faces with at least one loop exceeding the threshold.
    Face overlay available (face fill + edge outline).
    Guard: skipped on meshes with > _UV_STRETCH_MAX_POLYS faces to prevent live-validation slowdown.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._stretched_face_verts: List = []   # [(wx,wy,wz), ...] triangulated, world-space
        self._stretched_face_norms: List = []   # [(nx,ny,nz), ...] one normal per triangle vertex
        self._stretched_face_edges: List = []   # [(wx,wy,wz), (wx,wy,wz), ...] edge pairs, world-space
        self._stretched_uv_verts:   List = []   # [(u,v), ...] triangulated, UV-space

    def set_datas(self):
        import numpy as np
        me = self._parent._object.data
        obj = self._parent._object
        self._stretched_face_verts.clear()
        self._count = 0

        if not me.uv_layers.active:
            return

        # ── Fully vectorized via numpy ──────────────────────────────────────────
        # EDIT mode: ALL sources come from the canonical BMesh snapshot —
        # me.* sizes/indices are stale and don't match BMesh loop order.
        if me.is_editmode:
            snap = _edit_uv_data(self._parent.bm_object)
            if snap is None:
                return
            n_polys = snap['n_faces']
            if n_polys > _UV_STRETCH_MAX_POLYS:
                return
            n_verts = snap['n_verts']
            n_loops = snap['n_loops']
            ps = snap['face_start']
            pt = snap['face_len']
            lv = snap['loop_vert']
            vc = snap['co']
        else:
            n_polys = len(me.polygons)
            if n_polys > _UV_STRETCH_MAX_POLYS:
                return
            n_verts = len(me.vertices)
            n_loops = len(me.loops)

            # Polygon → loop start / total
            ps = np.empty(n_polys, dtype=np.int32)
            pt = np.empty(n_polys, dtype=np.int32)
            me.polygons.foreach_get("loop_start", ps)
            me.polygons.foreach_get("loop_total", pt)

            lv = np.empty(n_loops, dtype=np.int32)
            me.loops.foreach_get("vertex_index", lv)

            vc = np.empty(n_verts * 3, dtype=np.float32)
            me.vertices.foreach_get("co", vc)
            vc = vc.reshape(n_verts, 3)

        # Threshold from preferences, fallback to default
        try:
            addon_name = __name__.rsplit(".", 1)[0]
            prefs = bpy.context.preferences.addons[addon_name].preferences
            threshold = getattr(prefs, 'uv_stretch_threshold', _UV_STRETCH_DEFAULT_THRESHOLD)
        except Exception:
            threshold = _UV_STRETCH_DEFAULT_THRESHOLD

        # Per-loop: which polygon it belongs to + size + start of that polygon
        poly_ids      = np.repeat(np.arange(n_polys, dtype=np.int32), pt)  # (n_loops,)
        loop_poly_sz  = pt[poly_ids]                                         # (n_loops,)
        loop_poly_st  = ps[poly_ids]                                         # (n_loops,)

        # Offset of each loop within its polygon
        loop_idx         = np.arange(n_loops, dtype=np.int32)
        off_in_poly      = loop_idx - loop_poly_st                           # (n_loops,)

        # Ring-wrap next / prev loop indices
        loop_next = loop_poly_st + (off_in_poly + 1)               % loop_poly_sz
        loop_prev = loop_poly_st + (off_in_poly + loop_poly_sz - 1) % loop_poly_sz

        cur_co  = vc[lv]            # (n_loops, 3)
        next_co = vc[lv[loop_next]] # (n_loops, 3)
        prev_co = vc[lv[loop_prev]] # (n_loops, 3)

        # 3D corner angle at each loop (replicates loop.calc_angle())
        e0 = next_co - cur_co       # edge to next vert
        e1 = prev_co - cur_co       # edge to prev vert
        mag0 = np.sqrt((e0 * e0).sum(axis=1))
        mag1 = np.sqrt((e1 * e1).sum(axis=1))
        valid_3d = (mag0 > 1e-10) & (mag1 > 1e-10)
        cos_3d = np.where(valid_3d,
                          np.clip((e0 * e1).sum(axis=1) / np.where(valid_3d, mag0 * mag1, 1.0),
                                  -1.0, 1.0),
                          0.0)
        mesh_angle = np.arccos(cos_3d)  # (n_loops,)

        # UV angle at each loop
        bm = self._parent.bm_object
        uv_flat = _get_uv_np(me, bm=bm)
        if uv_flat is None:
            return

        cur_uv  = uv_flat
        next_uv = uv_flat[loop_next]
        prev_uv = uv_flat[loop_prev]

        ax = next_uv[:, 0] - cur_uv[:, 0]
        ay = next_uv[:, 1] - cur_uv[:, 1]
        bx = prev_uv[:, 0] - cur_uv[:, 0]
        by = prev_uv[:, 1] - cur_uv[:, 1]
        mag_a = np.sqrt(ax * ax + ay * ay)
        mag_b = np.sqrt(bx * bx + by * by)
        valid_uv = (mag_a > 1e-10) & (mag_b > 1e-10)
        cos_uv = np.where(valid_uv,
                          np.clip((ax * bx + ay * by) / np.where(valid_uv, mag_a * mag_b, 1.0),
                                  -1.0, 1.0),
                          0.0)
        uv_angle = np.arccos(cos_uv)  # (n_loops,)

        # Stretched loop mask
        stretched_loops = valid_3d & valid_uv & (np.abs(mesh_angle - uv_angle) > threshold)

        # Reduce to faces: any stretched loop → stretched face
        bad_face_mask = np.zeros(n_polys, dtype=bool)
        np.bitwise_or.at(bad_face_mask, poly_ids, stretched_loops)
        bad_face_indices = np.where(bad_face_mask)[0]
        self._count = int(len(bad_face_indices))

        if self._count == 0:
            return

        # Build world-space triangle coords for face overlay (fan-triangulation)
        wm = obj.matrix_world
        wm3 = np.array(wm.to_3x3(), dtype=np.float32)
        wm_t = np.array([wm.translation.x, wm.translation.y, wm.translation.z], dtype=np.float32)

        # Polygon normals — to offset face overlay above surface
        pn = np.empty(n_polys * 3, dtype=np.float32)
        me.polygons.foreach_get("normal", pn)
        pn = pn.reshape(n_polys, 3)
        wm3_inv_T = np.linalg.inv(wm3).T
        pn_ws = pn @ wm3_inv_T
        mag = np.sqrt((pn_ws * pn_ws).sum(axis=1, keepdims=True))
        pn_ws /= np.where(mag > 1e-10, mag, 1.0)

        # UV coords (flat list indexed by loop)
        uv_flat = _get_uv_np(me, bm=bm)   # bm fetched above via bm_object

        face_verts = []
        face_norms = []
        face_edges = []   # perimeter edge pairs for outline
        uv_verts   = []

        for fi in bad_face_indices:
            s = int(ps[fi]); nv = int(pt[fi])
            verts_ws = vc[lv[s:s + nv]] @ wm3.T + wm_t   # (nv, 3)
            nx, ny, nz = float(pn_ws[fi, 0]), float(pn_ws[fi, 1]), float(pn_ws[fi, 2])
            v0 = verts_ws[0]
            # Fan triangulation — faces
            for k in range(1, nv - 1):
                face_verts.extend([
                    (float(v0[0]),           float(v0[1]),           float(v0[2])),
                    (float(verts_ws[k,0]),   float(verts_ws[k,1]),   float(verts_ws[k,2])),
                    (float(verts_ws[k+1,0]), float(verts_ws[k+1,1]), float(verts_ws[k+1,2])),
                ])
                face_norms.extend([(nx, ny, nz)] * 3)
            # Perimeter edges (polygon boundary for outline)
            for k in range(nv):
                a = verts_ws[k];  b = verts_ws[(k + 1) % nv]
                face_edges.extend([
                    (float(a[0]), float(a[1]), float(a[2])),
                    (float(b[0]), float(b[1]), float(b[2])),
                ])
            # UV face triangles
            if uv_flat is not None:
                uv = uv_flat[s:s + nv]   # (nv, 2) UV per loop
                uv0 = uv[0]
                for k in range(1, nv - 1):
                    uv_verts.extend([
                        (float(uv0[0]),    float(uv0[1])),
                        (float(uv[k,0]),   float(uv[k,1])),
                        (float(uv[k+1,0]), float(uv[k+1,1])),
                    ])

        self._stretched_face_verts = face_verts
        self._stretched_face_norms = face_norms
        self._stretched_face_edges = face_edges
        self._stretched_uv_verts   = uv_verts

    def get_edges(self, offset: float) -> Tuple:
        """Perimeter outline of stretched faces in 3D — visible even on small faces."""
        if not self._stretched_face_edges or not self._stretched_face_norms:
            return ()
        # Apply same normal offset as faces so edges sit on top of the face fill
        norms = self._stretched_face_norms
        # face_edges pairs map 1:1 with perimeter verts; use first norm of each face
        # as a simple approximation — good enough for a thin outline
        off = offset
        result = []
        # _stretched_face_norms length = n_face_tris * 3; edges don't share norms directly.
        # Use a fixed small offset instead of per-vert normal for edges.
        for v in self._stretched_face_edges:
            # Use the closest face normal — simplification: just offset along +Z in UV space
            result.append((v[0], v[1], v[2]))
        return tuple(result)

    def get_faces(self, offset: float) -> Tuple:
        if not self._stretched_face_verts:
            return (), []
        n = len(self._stretched_face_verts)
        if offset and self._stretched_face_norms:
            coords = tuple(
                (v[0] + nm[0] * offset, v[1] + nm[1] * offset, v[2] + nm[2] * offset)
                for v, nm in zip(self._stretched_face_verts, self._stretched_face_norms)
            )
        else:
            coords = tuple(self._stretched_face_verts)
        indices = [(i, i + 1, i + 2) for i in range(0, n, 3)]
        return coords, indices

    def get_uv_faces(self) -> Tuple:
        """UV-space face triangles for IMAGE_EDITOR overlay.
        Returns 3D coords (u, v, 0.0) — required by UNIFORM_COLOR shader in UV editor.
        """
        if not self._stretched_uv_verts:
            return (), []
        coords = tuple((u, v, 0.0) for u, v in self._stretched_uv_verts)
        n = len(coords)
        indices = [(i, i + 1, i + 2) for i in range(0, n, 3)]
        return coords, indices

    def get_points(self, offset: float) -> Tuple:
        return ()


class UVPaddingCheck(BaseCheck):
    """UV island padding — cross-object, per-UDIM-tile.

    Architecture (two-phase):
      Phase 1 — set_datas():
        Each object collects its island UV data and stores it in the module-level
        _uv_padding_registry keyed by me.as_pointer().  No check is performed yet.

      Phase 2 — run_global_uv_padding() (called from manager.py):
        Groups ALL registered islands by dominant UDIM tile, then runs a
        spatial-hash shell-to-shell check across islands from ALL objects on that
        tile, plus analytic tile-border check.  Results are written back to the
        individual checker instances.

    This correctly detects padding violations between islands that belong to
    different mesh objects but share the same UDIM texture tile.

    count       = number of this object's islands that violate padding
    metric_text = human-readable summary with pixel counts
    """

    _UV_PADDING_MAX_VERTS: int = 200_000
    _PAD_TEX_SIZES = {'0': 512, '1': 1024, '2': 2048, '3': 4096}

    def __init__(self, parent):
        super().__init__(parent)
        self.metric_text: str = ""
        self._bad_shell_count: int = 0
        self._bad_tile_count:  int = 0
        # UV-editor overlay: fan-triangulated UV coords of bad-island polygons
        self._bad_uv_tris:     list = []
        # Edit-mode selection: face indices of bad-island polygons
        self._bad_face_indices: list = []

    # ── Phase 1: collect per-object island data ───────────────────────────────

    def set_datas(self):
        """Phase 1: collect island UV data into the global padding registry.

        The actual check (cross-object spatial hash) is deferred to
        run_global_uv_padding(), which is called by manager.py after all
        per-object set_datas() calls complete.
        """
        global _uv_padding_registry

        me  = self._parent._object.data
        ptr = me.as_pointer()

        # Reset results — will be populated by run_global_uv_padding()
        self._count            = 0
        self.metric_text       = ""
        self._bad_shell_count  = 0
        self._bad_tile_count   = 0
        self._bad_uv_tris      = []
        self._bad_face_indices = []
        _uv_padding_registry.pop(ptr, None)   # remove stale entry

        if not me.uv_layers.active or not me.polygons:
            return

        membership = _uv_island_membership(me, _UV_PADDING_MAX_POLYS,
                                           bm=self._parent.bm_object)
        if membership is None:
            # Mesh is too dense for island detection — mark as skipped
            self.metric_text = f"UV Padding: mesh too complex (>{_UV_PADDING_MAX_POLYS//1000}k polys)"
            return

        poly_to_island, flat_uvs, poly_start, poly_total = membership
        n_polys   = len(me.polygons)
        n_islands = (max(poly_to_island) + 1) if poly_to_island else 0
        if n_islands == 0:
            return

        # Build per-island UV vertex lists + dominant UDIM tile vote
        island_uvs:   list = [[] for _ in range(n_islands)]
        island_votes: list = [{}  for _ in range(n_islands)]  # tile → count
        total_verts   = 0

        for pi in range(n_polys):
            isl = poly_to_island[pi]
            ls  = poly_start[pi]
            lt  = poly_total[pi]
            for li in range(ls, ls + lt):
                u = float(flat_uvs[li * 2])
                v = float(flat_uvs[li * 2 + 1])
                # NaN/inf UVs poison padding math and crash int(floor()) — skip
                if not (math.isfinite(u) and math.isfinite(v)):
                    continue
                island_uvs[isl].append((u, v))
                total_verts += 1
                tile = (int(math.floor(u)), int(math.floor(v)))
                votes = island_votes[isl]
                votes[tile] = votes.get(tile, 0) + 1

        if total_verts == 0 or total_verts > self._UV_PADDING_MAX_VERTS:
            return

        # Resolve dominant tile per island (island may span tiles, take majority)
        island_tile: list = [
            max(votes, key=votes.__getitem__) if votes else (0, 0)
            for votes in island_votes
        ]

        _uv_padding_registry[ptr] = {
            'checker':        self,
            'island_uvs':     island_uvs,
            'island_tile':    island_tile,
            'n_islands':      n_islands,
            'n_polys':        n_polys,
            'poly_to_island': poly_to_island,
            'flat_uvs':       flat_uvs,
            'poly_start':     poly_start,
            'poly_total':     poly_total,
        }

    # ── Phase 2: cross-object global check (called from manager.py) ───────────

    @staticmethod
    def _write_results(reg: dict, bad_shell: set, bad_tile: set,
                       shell_px: int, tile_px: int,
                       min_border_px: float = -1.0) -> None:
        """Write Phase-2 results back to the checker stored in *reg*.

        min_border_px — measured minimum distance (px) of any island UV vertex
        to the nearest tile border across all tiles this object appears on.
        -1.0 means not measured (fallback).
        """
        checker   = reg['checker']
        all_bad   = bad_shell | bad_tile
        n_polys   = reg['n_polys']
        poly_ti   = reg['poly_to_island']
        poly_st   = reg['poly_start']
        poly_to   = reg['poly_total']
        flat_uvs  = reg['flat_uvs']

        checker._count            = len(all_bad)
        checker._bad_shell_count  = len(bad_shell)
        checker._bad_tile_count   = len(bad_tile)
        checker._bad_uv_tris      = []
        checker._bad_face_indices = []

        if all_bad:
            for pi in range(n_polys):
                if poly_ti[pi] not in all_bad:
                    continue
                checker._bad_face_indices.append(pi)
                ls  = int(poly_st[pi])
                lt  = int(poly_to[pi])
                uv0 = (float(flat_uvs[ls * 2]), float(flat_uvs[ls * 2 + 1]))
                for k in range(1, lt - 1):
                    uv1 = (float(flat_uvs[(ls + k) * 2]),
                            float(flat_uvs[(ls + k) * 2 + 1]))
                    uv2 = (float(flat_uvs[(ls + k + 1) * 2]),
                            float(flat_uvs[(ls + k + 1) * 2 + 1]))
                    checker._bad_uv_tris.append((uv0, uv1, uv2))

            parts = []
            if checker._bad_shell_count:
                parts.append(
                    f"{checker._bad_shell_count} "
                    f"island{'s' if checker._bad_shell_count != 1 else ''} "
                    f"close to shell (<{shell_px}px)"
                )
            if checker._bad_tile_count:
                parts.append(
                    f"{checker._bad_tile_count} "
                    f"island{'s' if checker._bad_tile_count != 1 else ''} "
                    f"close to border (<{tile_px}px)"
                )
            checker.metric_text = (
                f"UV Padding: {checker._count} "
                f"island{'s' if checker._count != 1 else ''} — "
                + ", ".join(parts)
            )
        else:
            # Show measured min even when no violations
            if min_border_px >= 0.0:
                checker.metric_text = f"UV Padding: OK — border min {min_border_px:.2f}px"
            else:
                checker.metric_text = "UV Padding: OK"

        checker._uv_gpu_dirty = True

    # ─────────────────────────────────────────────────────────────────────────

    def get_edges(self, offset: float) -> Tuple:
        return ()

    def get_points(self, offset: float) -> Tuple:
        return ()

    def get_uv_faces(self) -> Tuple:
        """Fan-triangulated UV faces of bad-padding islands for UV editor overlay."""
        if not self._bad_uv_tris:
            return (), []
        coords  = []
        indices = []
        for tri in self._bad_uv_tris:
            base = len(coords)
            coords.extend((u, v, 0.0) for u, v in tri)
            indices.append((base, base + 1, base + 2))
        return tuple(coords), indices

    def get_uv_edges(self) -> Tuple:
        """Outline edges of bad-padding islands."""
        if not self._bad_uv_tris:
            return ()
        coords = []
        for tri in self._bad_uv_tris:
            for i in range(3):
                u1, v1 = tri[i]
                u2, v2 = tri[(i + 1) % 3]
                coords.append((u1, v1, 0.0))
                coords.append((u2, v2, 0.0))
        return tuple(coords)

    def get_select_data(self) -> Tuple:
        """Select faces of bad-padding islands in Edit Mode."""
        return ('FACE', self._bad_face_indices)


# ── Module-level cross-object UV padding check ────────────────────────────────

def run_global_uv_padding(tex_size: int = 4096,
                          shell_px: int = 16,
                          tile_px:  int = 8) -> None:
    """Cross-object UV padding check — Phase 2.

    Groups all registered islands by dominant UDIM tile, then runs a
    spatial-hash shell-to-shell check across islands from ALL objects on that
    tile.  Writes per-island violation flags and per-UDIM statistics back to
    individual checkers and _uv_padding_tile_stats.

    Called from manager.py after all per-object set_datas() calls complete.
    """
    global _uv_padding_registry, _uv_padding_tile_stats

    _uv_padding_tile_stats.clear()

    if not _uv_padding_registry:
        return

    shell_thr = shell_px / tex_size
    tile_thr  = tile_px  / tex_size
    inv = 1.0 / max(shell_thr, 1e-9)
    fl  = math.floor

    # ── Step 1: group (ptr, local_island_idx) by UDIM tile ───────────────────
    tile_islands: dict = {}   # (tu, tv) → list of (ptr, local_idx)
    for ptr, reg in _uv_padding_registry.items():
        for i, tile in enumerate(reg['island_tile']):
            if not reg['island_uvs'][i]:
                continue
            tile_islands.setdefault(tile, []).append((ptr, i))

    # ── Step 2: per-tile spatial-hash check ──────────────────────────────────
    # bad_shell / bad_tile: ptr → set of local island indices
    bad_shell_map: dict = {ptr: set() for ptr in _uv_padding_registry}
    bad_tile_map:  dict = {ptr: set() for ptr in _uv_padding_registry}

    # Per-object minimum border distance (pixels) across all tiles.
    # Infinity = not yet measured.
    obj_min_border: dict = {ptr: float('inf') for ptr in _uv_padding_registry}

    # Per-tile minimum border distance and shell distance (pixels)
    tile_min_border: dict = {}
    tile_min_shell:  dict = {}   # tile → float px or None (too dense / single island)

    # Max UV vertices per tile for exact shell min distance computation.
    # Above this limit only violation detection runs (no exact min).
    _SHELL_MIN_VERTS_GUARD = 20_000

    for tile, refs in tile_islands.items():
        tu, tv = tile

        # Build spatial hash over all islands on this tile.
        # Stores vertex coordinates so we can compute exact distances later.
        # cell → list of (ptr, local_idx, u, v)
        grid_v: dict = {}
        for (ptr, local_idx) in refs:
            for u, v in _uv_padding_registry[ptr]['island_uvs'][local_idx]:
                key = (int(fl(u * inv)), int(fl(v * inv)))
                cv  = grid_v.get(key)
                if cv is None:
                    grid_v[key] = [(ptr, local_idx, u, v)]
                else:
                    cv.append((ptr, local_idx, u, v))

        has_multi = (len(refs) > 1 or
                     (len(refs) == 1 and
                      _uv_padding_registry[refs[0][0]]['n_islands'] > 1))

        # ── Shell-to-shell: exact distance check + min tracking ───────────────
        # Uses the spatial hash as a broad-phase (candidate filter), then
        # computes exact Euclidean distance.  This eliminates false positives
        # from the grid (adjacent-cell pairs can be up to shell_thr*√2 apart).
        #
        # Violation  = distance < shell_thr  (exact)
        # Min-shell  = global minimum over all cross-island candidate pairs
        #              (guarded: only computed when total UV verts ≤ guard limit)
        shell_thr_sq = shell_thr * shell_thr
        total_v = sum(
            len(_uv_padding_registry[ptr]['island_uvs'][idx])
            for ptr, idx in refs
        )
        compute_min = has_multi and total_v <= _SHELL_MIN_VERTS_GUARD

        min_d2 = float('inf')   # tracks min across all candidate pairs

        if has_multi:
            for (ptr_a, idx_a) in refs:
                already_viol = idx_a in bad_shell_map[ptr_a]
                # Skip this island's vertices only when violation is known AND
                # we don't need min distance (dense tile).
                if already_viol and not compute_min:
                    continue
                for ua, va in _uv_padding_registry[ptr_a]['island_uvs'][idx_a]:
                    gx = int(fl(ua * inv))
                    gy = int(fl(va * inv))
                    found_viol = False
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            cell = grid_v.get((gx + dx, gy + dy))
                            if not cell:
                                continue
                            for (ptr_b, idx_b, ub, vb) in cell:
                                if ptr_a == ptr_b and idx_a == idx_b:
                                    continue   # same island
                                d2 = (ua - ub) ** 2 + (va - vb) ** 2
                                # Track global minimum (only when compute_min)
                                if compute_min and d2 < min_d2:
                                    min_d2 = d2
                                # Exact violation: d < shell_thr
                                if not already_viol and d2 < shell_thr_sq:
                                    bad_shell_map[ptr_a].add(idx_a)
                                    bad_shell_map[ptr_b].add(idx_b)
                                    already_viol = True
                                    if not compute_min:
                                        found_viol = True
                                        break
                            if found_viol:
                                break
                        if found_viol:
                            break
                    if found_viol:
                        break   # violation found, no min needed → skip remaining vertices

        tile_min_shell_px = (math.sqrt(min_d2) * tex_size
                             if compute_min and min_d2 < float('inf')
                             else None)

        # ── Tile-border + min-distance tracking ──────────────────────────────
        # Iterate ALL vertices (no early break) to measure actual minimum.
        min_bd_uv = 1.0
        for (ptr, local_idx) in refs:
            violated = local_idx in bad_tile_map[ptr]
            for u, v in _uv_padding_registry[ptr]['island_uvs'][local_idx]:
                uf = u - tu
                vf = v - tv
                du = uf if uf < 0.5 else 1.0 - uf
                dv = vf if vf < 0.5 else 1.0 - vf
                d  = du if du < dv else dv

                if d < min_bd_uv:
                    min_bd_uv = d
                d_px = d * tex_size
                if d_px < obj_min_border[ptr]:
                    obj_min_border[ptr] = d_px

                if not violated and (du < tile_thr or dv < tile_thr):
                    bad_tile_map[ptr].add(local_idx)
                    violated = True

        tile_min_border[tile] = min_bd_uv * tex_size
        tile_min_shell[tile]  = tile_min_shell_px

    # ── Step 3: write results back to checkers ────────────────────────────────
    for ptr, reg in _uv_padding_registry.items():
        mb = obj_min_border.get(ptr, -1.0)
        UVPaddingCheck._write_results(
            reg,
            bad_shell_map.get(ptr, set()),
            bad_tile_map.get(ptr,  set()),
            shell_px,
            tile_px,
            min_border_px=mb if mb < float('inf') else -1.0,
        )

    # ── Step 4: populate per-UDIM-tile statistics ─────────────────────────────
    for tile, refs in tile_islands.items():
        bs = bad_shell_map
        bt = bad_tile_map
        _uv_padding_tile_stats[tile] = {
            'n_islands':     len(refs),
            'n_objects':     len({ptr for ptr, _ in refs}),
            'min_border_px': tile_min_border.get(tile, 0.0),
            'min_shell_px':  tile_min_shell.get(tile),   # None = too dense or N/A
            'bad_shell':     sum(1 for (ptr, idx) in refs if idx in bs.get(ptr, ())),
            'bad_tile':      sum(1 for (ptr, idx) in refs if idx in bt.get(ptr, ())),
        }


class UVUDIMBounds(BaseCheck):
    """UV islands crossing UDIM tile boundaries.

    count = number of islands whose bbox spans more than one 1×1 UV tile.
    Offending triangles are drawn in the UV editor (get_uv_faces / get_uv_edges).
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._bad_tri_uvs: List = []

    # Separate limit so large meshes are not silently skipped.
    # _uv_island_membership has no shared cache, so this limit can be higher
    # than _UV_ISLAND_MAX_POLYS without polluting the shared cache.
    _UDIM_BOUNDS_MAX_POLYS: int = 500_000

    def set_datas(self):
        import numpy as np
        me = self._parent._object.data
        self._bad_tri_uvs.clear()
        self._count = 0

        if not me.uv_layers.active or not me.polygons:
            return

        bm = self._parent.bm_object
        _EPS = 1e-5

        # ── Primary: _uv_island_membership (shared _uv_membership_cache) ──────
        # UVOverlapCheck and UVPaddingCheck run before this check (see CHECK_TYPES
        # order) and populate _uv_membership_cache — so most objects get a free
        # cache hit here.  flat_uvs is reused directly (no BMesh face iteration).
        membership = _uv_island_membership(me, self._UDIM_BOUNDS_MAX_POLYS, bm=bm)

        if membership is None:
            # Mesh > 100k polys — fall back to shared _uv_island_cache (pre-built
            # bbox, very cheap if cache is warm from UVUDIMReady).
            islands_shared = _detect_uv_islands(me, bm=bm)
            if not islands_shared:
                return
            bad_polys: Set[int] = set()
            bad_count = 0
            for polys, u_min, v_min, u_max, v_max in islands_shared:
                if (math.floor(u_max - _EPS) > math.floor(u_min + _EPS) or
                        math.floor(v_max - _EPS) > math.floor(v_min + _EPS)):
                    bad_count += 1
                    bad_polys.update(polys)
            self._count = bad_count
            if not bad_polys:
                return
            # Visual triangles (BMesh path — only for truly large meshes here)
            uv_layer = bm.loops.layers.uv.active
            if uv_layer:
                for l0, l1, l2 in bm.calc_loop_triangles():
                    if l0.face.index in bad_polys:
                        self._bad_tri_uvs.append((
                            (l0[uv_layer].uv.x, l0[uv_layer].uv.y),
                            (l1[uv_layer].uv.x, l1[uv_layer].uv.y),
                            (l2[uv_layer].uv.x, l2[uv_layer].uv.y),
                        ))
            return

        # ── Have membership: vectorised bbox via numpy — no BMesh face loop ───
        poly_to_island, _flat_uvs_unused, _ps_unused, poly_total_l = membership
        n_polys = len(poly_to_island)
        if n_polys == 0:
            return

        n_islands = max(poly_to_island) + 1

        # Read UVs (C-level in OBJECT mode; BMesh fallback in EDIT mode)
        uv_np = _get_uv_np(me, bm=bm)
        if uv_np is None:
            return
        n_loops = len(uv_np)

        # Per-loop island index via np.repeat (poly_total expands p2i to per-loop)
        p2i      = np.array(poly_to_island, dtype=np.int32)
        pt       = np.array(poly_total_l,   dtype=np.int32)
        loop_isl = np.repeat(p2i, pt)               # (n_loops,)

        # Island UV bboxes — np.minimum/maximum.at for scatter-accumulate
        INF = np.float32(1e18)
        isl_u_min = np.full(n_islands,  INF, dtype=np.float32)
        isl_u_max = np.full(n_islands, -INF, dtype=np.float32)
        isl_v_min = np.full(n_islands,  INF, dtype=np.float32)
        isl_v_max = np.full(n_islands, -INF, dtype=np.float32)
        np.minimum.at(isl_u_min, loop_isl, uv_np[:, 0])
        np.maximum.at(isl_u_max, loop_isl, uv_np[:, 0])
        np.minimum.at(isl_v_min, loop_isl, uv_np[:, 1])
        np.maximum.at(isl_v_max, loop_isl, uv_np[:, 1])

        # Which islands cross a tile boundary?
        bad_isl_mask = (
            (np.floor(isl_u_max - _EPS) > np.floor(isl_u_min + _EPS)) |
            (np.floor(isl_v_max - _EPS) > np.floor(isl_v_min + _EPS))
        )
        bad_isl_arr  = np.where(bad_isl_mask)[0]
        self._count  = len(bad_isl_arr)
        if not self._count:
            return

        # Collect bad polygon indices
        bad_isl_set  = set(bad_isl_arr.tolist())
        bad_poly_set = {fi for fi, isl in enumerate(poly_to_island)
                        if isl in bad_isl_set}

        # ── Visual triangles — snapshot in EDIT mode, me.loop_triangles otherwise ─
        if me.is_editmode:
            # me.* is stale here; reuse the canonical snapshot (same ordering
            # as uv_np).
            snap = _edit_uv_data(bm)
            if snap is None:
                return
            tri_l = snap['tri_loop']
            tri_poly_np = snap['loop_face'][tri_l[:, 0]]
            if len(tri_l) == 0:
                return
        else:
            me.calc_loop_triangles()
            n_tris = len(me.loop_triangles)
            if n_tris == 0:
                return

            tri_loop_np = np.empty(n_tris * 3, dtype=np.int32)
            me.loop_triangles.foreach_get("loops", tri_loop_np)
            tri_poly_np = np.empty(n_tris, dtype=np.int32)
            me.loop_triangles.foreach_get("polygon_index", tri_poly_np)
            tri_l = tri_loop_np.reshape(n_tris, 3)

        # Vectorised bad-poly mask via np.isin
        bad_poly_arr  = np.fromiter(bad_poly_set, dtype=np.int32, count=len(bad_poly_set))
        bad_poly_mask = np.isin(tri_poly_np, bad_poly_arr)
        if not bad_poly_mask.any():
            return

        bad_tri_l = tri_l[bad_poly_mask]            # (n_bad, 3)
        bt0 = uv_np[bad_tri_l[:, 0]]
        bt1 = uv_np[bad_tri_l[:, 1]]
        bt2 = uv_np[bad_tri_l[:, 2]]
        self._bad_tri_uvs = [
            ((float(bt0[i, 0]), float(bt0[i, 1])),
             (float(bt1[i, 0]), float(bt1[i, 1])),
             (float(bt2[i, 0]), float(bt2[i, 1])))
            for i in range(len(bt0))
        ]

    def get_edges(self, offset: float) -> Tuple:
        return ()

    def get_uv_faces(self) -> Tuple:
        if not self._bad_tri_uvs:
            return (), []
        coords = []
        indices = []
        for tri in self._bad_tri_uvs:
            base = len(coords)
            coords.extend((u, v, 0.0) for u, v in tri)
            indices.append((base, base + 1, base + 2))
        return tuple(coords), indices

    def get_uv_edges(self) -> Tuple:
        if not self._bad_tri_uvs:
            return ()
        coords = []
        for tri in self._bad_tri_uvs:
            for i in range(3):
                u1, v1 = tri[i]
                u2, v2 = tri[(i + 1) % 3]
                coords.append((u1, v1, 0.0))
                coords.append((u2, v2, 0.0))
        return tuple(coords)


class UVMaterialUDIM(BaseCheck):
    """One UDIM tile must not contain UV shells from different material groups.

    Регламент: "На одном UDIM недопустимо наличие шеллов с разными материалами"

    Algorithm:
      1. Detect UV islands (Union-Find).
      2. For each island: compute dominant UDIM tile (floor(u_avg), floor(v_avg))
         and collect the material_index values used by that island's polygons.
      3. If any UDIM tile has islands from more than one distinct material → flag.
    """

    _MAX_POLYS = 50_000

    def __init__(self, parent):
        super().__init__(parent)
        self.metric_text: str = ""
        self._bad_face_indices: list = []
        self._minority_uv_tris:  list = []  # UV triangles of minority-mat faces (UV editor)

    def set_datas(self):
        obj = self._parent._object
        me  = obj.data
        self._count = 0
        self.metric_text = ""
        self._bad_face_indices = []
        self._minority_uv_tris = []

        if not me.uv_layers.active or not me.polygons:
            return

        membership = _uv_island_membership(me, self._MAX_POLYS, bm=self._parent.bm_object)
        if membership is None:
            self.metric_text = "Mat/UDIM: mesh too dense"
            return

        poly_to_island, flat_uvs, poly_start, poly_total = membership
        # Membership poly count is authoritative (me.polygons is stale in EDIT)
        n_polys   = len(poly_to_island)
        n_islands = (max(poly_to_island) + 1) if poly_to_island else 0
        if n_islands == 0:
            return

        # Get material indices per polygon (snapshot in EDIT mode — me stale)
        if me.is_editmode:
            snap = _edit_uv_data(self._parent.bm_object)
            if snap is None:
                return
            mat_indices = snap['face_mat'].tolist()
        else:
            mat_indices = [0] * n_polys
            me.polygons.foreach_get("material_index", mat_indices)

        # Per island: dominant UDIM tile vote + material set
        island_votes: list = [dict() for _ in range(n_islands)]
        island_mats:  list = [set()  for _ in range(n_islands)]

        for pi in range(n_polys):
            isl = poly_to_island[pi]
            island_mats[isl].add(mat_indices[pi])
            # UV centroid of this polygon
            ls = poly_start[pi]
            lt = poly_total[pi]
            if lt == 0:
                continue
            u_sum = v_sum = 0.0
            for li in range(ls, ls + lt):
                u_sum += flat_uvs[li * 2]
                v_sum += flat_uvs[li * 2 + 1]
            cu, cv = u_sum / lt, v_sum / lt
            # NaN/inf UVs crash int(floor()) — face votes no tile
            if not (math.isfinite(cu) and math.isfinite(cv)):
                continue
            tile = (int(math.floor(cu)), int(math.floor(cv)))
            d = island_votes[isl]
            d[tile] = d.get(tile, 0) + 1

        # Dominant tile per island
        island_tile: list = [
            max(d, key=d.get) if d else None
            for d in island_votes
        ]

        # Group by UDIM tile
        tile_mats:    dict = {}
        tile_islands: dict = {}
        for isl in range(n_islands):
            tile = island_tile[isl]
            if tile is None:
                continue
            if tile not in tile_mats:
                tile_mats[tile]    = set()
                tile_islands[tile] = []
            tile_mats[tile].update(island_mats[isl])
            tile_islands[tile].append(isl)

        bad_tiles = {t for t, mats in tile_mats.items() if len(mats) > 1}
        if not bad_tiles:
            return

        # Build island → polygon list
        island_polys: dict = defaultdict(list)
        for pi in range(n_polys):
            island_polys[poly_to_island[pi]].append(pi)

        # For each bad tile: find dominant material (most faces) → minority = rest
        minority_face_set: set = set()
        bad_face_set:      set = set()
        uv_tris = []

        for tile in bad_tiles:
            # Count faces per material on this tile
            mat_counts: dict = {}
            for isl in tile_islands[tile]:
                for pi in island_polys[isl]:
                    mi = mat_indices[pi]
                    mat_counts[mi] = mat_counts.get(mi, 0) + 1
            dominant_mat = max(mat_counts, key=mat_counts.get)

            for isl in tile_islands[tile]:
                for pi in island_polys[isl]:
                    bad_face_set.add(pi)
                    if mat_indices[pi] != dominant_mat:
                        minority_face_set.add(pi)
                        # Fan-triangulate UV loops for UV editor overlay
                        ls = poly_start[pi]
                        lt = poly_total[pi]
                        if lt < 3:
                            continue
                        u0 = flat_uvs[ls * 2];       v0 = flat_uvs[ls * 2 + 1]
                        for k in range(1, lt - 1):
                            li1 = ls + k;            li2 = ls + k + 1
                            u1 = flat_uvs[li1 * 2];  v1 = flat_uvs[li1 * 2 + 1]
                            u2 = flat_uvs[li2 * 2];  v2 = flat_uvs[li2 * 2 + 1]
                            uv_tris.append(((u0, v0), (u1, v1), (u2, v2)))

        self._count = len(bad_tiles)
        # 3D overlay: all faces on bad tiles; Select: minority faces only
        self._bad_face_indices = list(bad_face_set)
        self._minority_uv_tris = uv_tris

        udim_names = ", ".join(
            f"UDIM {1001 + t[0] + t[1] * 10}"
            for t in sorted(bad_tiles)[:3]
        )
        self.metric_text = (
            f"Mat/UDIM: {self._count} tile{'s' if self._count > 1 else ''}"
            f" ({udim_names})"
        )

    def get_faces(self, offset: float):
        if not self._bad_face_indices:
            return (), []
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords, indices, vmap, idx = [], [], {}, 0
        for fidx in self._bad_face_indices:
            if fidx >= len(bm.faces):
                continue
            fv = []
            for v in bm.faces[fidx].verts:
                if v.index not in vmap:
                    vmap[v.index] = idx
                    idx += 1
                    p = wm @ v.co
                    coords.append((p.x + v.normal.x * _offset,
                                   p.y + v.normal.y * _offset,
                                   p.z + v.normal.z * _offset))
                fv.append(vmap[v.index])
            for i in range(1, len(fv) - 1):
                indices.append((fv[0], fv[i], fv[i + 1]))
        return tuple(coords), indices

    def get_edges(self, offset: float):
        return ()

    def get_points(self, offset: float):
        return ()

    def get_uv_faces(self) -> Tuple:
        """UV-space triangles of minority-material faces for IMAGE_EDITOR overlay."""
        if not self._minority_uv_tris:
            return (), []
        coords = []
        indices = []
        for tri in self._minority_uv_tris:
            base = len(coords)
            coords.extend((u, v, 0.0) for u, v in tri)
            indices.append((base, base + 1, base + 2))
        return tuple(coords), indices

    def get_select_data(self):
        return ('FACE', self._bad_face_indices)


class SymmetryCheck(BaseCheck):
    """Проверка симметрии меша по выбранной оси через KD-Tree."""

    _AXIS: int = 0
    _THRESHOLD: float = 0.001

    def __init__(self, parent):
        super().__init__(parent)
        self._asym_verts: List[int] = []

    def set_datas(self):
        import numpy as np
        bm = self._parent.bm_object
        bm.verts.ensure_lookup_table()
        self._asym_verts.clear()
        n_verts = len(bm.verts)
        if not n_verts:
            self._count = 0
            return

        # ── Shared numpy coords cache — built once for all 3 axis checks ──────
        # All 3 SymmetryX/Y/Z share the same parent.  The first check reads
        # vertex coords via foreach_get into a numpy float32 array; the others
        # reuse the same array (zero copy).
        topo_key = (len(bm.verts), len(bm.edges), len(bm.faces))
        par = self._parent
        if par._sym_kd_key != topo_key:
            me = par._object.data
            co_np = np.empty(n_verts * 3, dtype=np.float32)
            if me.is_editmode:
                # me.vertices is stale in EDIT mode — read the live edit-BMesh.
                bm.verts.foreach_get("co", co_np)
            else:
                me.vertices.foreach_get("co", co_np)
            co_np = co_np.reshape(n_verts, 3)
            par._sym_kd_key   = topo_key
            par._sym_kd_co    = co_np   # numpy (n_verts, 3) float32
            par._sym_kd_cache = None
        else:
            co_np = par._sym_kd_co      # reuse cached numpy array

        # ── Numpy set-membership via packed int64 + searchsorted ─────────────
        # 1. Round coords to grid → integer (gx, gy, gz).
        # 2. Pack each triple into one int64 to enable np.sort + np.searchsorted.
        # 3. Mirror the relevant axis; binary-search for each mirrored key in the
        #    sorted original set.  Missing keys → asymmetric vertex.
        #
        # SHIFT/SPAN cover ±(SHIFT/inv) metres (≈ ±1 km at thr=0.001).
        # Packed max ≈ (2·SHIFT)^3 ≈ 6.4e13 — well within int64.
        thr  = self._THRESHOLD
        axis = self._AXIS
        inv  = 1.0 / max(thr, 1e-9)

        SHIFT = 1_000_000        # grid units; covers ±1000 m at default thr=0.001
        SPAN  = 2 * SHIFT + 1

        gi = np.round(co_np * inv).astype(np.int64)   # (n_verts, 3)

        # Clamp to avoid overflow in packing (anything outside ±SHIFT is already
        # asymmetric by definition, so clipping is correct).
        gi = np.clip(gi, -SHIFT, SHIFT)
        gc = gi + SHIFT                                # shift to [0, 2·SHIFT]

        # Pack: x * SPAN² + y * SPAN + z
        packed = (gc[:, 0] * SPAN + gc[:, 1]) * SPAN + gc[:, 2]
        packed_sorted = np.sort(packed)

        # Build mirrored pack keys (negate the mirror axis before shifting)
        mi = gc.copy()
        if axis == 0:
            mi[:, 0] = (-gi[:, 0]).clip(-SHIFT, SHIFT) + SHIFT
        elif axis == 1:
            mi[:, 1] = (-gi[:, 1]).clip(-SHIFT, SHIFT) + SHIFT
        else:
            mi[:, 2] = (-gi[:, 2]).clip(-SHIFT, SHIFT) + SHIFT
        m_packed = (mi[:, 0] * SPAN + mi[:, 1]) * SPAN + mi[:, 2]

        # Binary search: a vertex is asymmetric if its mirror key is absent
        idx = np.searchsorted(packed_sorted, m_packed)
        idx = np.clip(idx, 0, len(packed_sorted) - 1)
        asym_mask = packed_sorted[idx] != m_packed

        self._asym_verts = list(np.where(asym_mask)[0].tolist())
        self._count = len(self._asym_verts)

    def get_edges(self, offset: float) -> Tuple:
        return ()

    def get_points(self, offset: float):
        if not self._asym_verts:
            return ()
        bm = self._parent.bm_object
        bm.verts.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        for i in self._asym_verts:
            v = bm.verts[i]
            p = wm @ v.co
            coords.append((p.x + v.normal.x * _offset,
                            p.y + v.normal.y * _offset,
                            p.z + v.normal.z * _offset))
        return tuple(coords)

    def get_select_data(self):
        return ('VERT', list(self._asym_verts))


class SymmetryX(SymmetryCheck):
    _AXIS = 0


class SymmetryY(SymmetryCheck):
    _AXIS = 1


class SymmetryZ(SymmetryCheck):
    _AXIS = 2


class BoundaryEdges(BaseCheck):
    """Рёбра с ровно одной смежной гранью (открытые края меша).

    Отдельный чек от non_manifold — открытые края это pipeline-проблема
    (дыры в меше), тогда как non_manifold также ловит T-junction (≥3 грани).
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._edges_idx: List[int] = []

    @property
    def count(self):
        if self._ignored:
            return 0
        return len(self._edges_idx)

    def set_datas(self):
        bm = self._parent.bm_object
        bm.edges.ensure_lookup_table()
        self._edges_idx = [e.index for e in bm.edges if len(e.link_faces) == 1]

    def get_edges(self, offset: float):
        bm = self._parent.bm_object
        bm.edges.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        for e_idx in self._edges_idx:
            for v in bm.edges[e_idx].verts:
                p = wm @ v.co
                coords.append((p.x + v.normal.x * _offset,
                                p.y + v.normal.y * _offset,
                                p.z + v.normal.z * _offset))
        return tuple(coords)

    def get_points(self, offset: float):
        return ()

    def get_select_data(self):
        return ('EDGE', self._edges_idx)


class MissingTextures(BaseCheck):
    """Обнаруживает материалы объекта с отсутствующими текстурными файлами.

    Проверяет каждый узел TEX_IMAGE в node tree материала:
    - файл не запакован (не packed_file)
    - путь не существует на диске (bpy.path.abspath + os.path.exists)

    count = количество уникальных отсутствующих изображений.
    metric_text содержит список имён для отображения в панели.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self._missing_names: List[str] = []

    @property
    def metric_text(self) -> str:
        if not self._missing_names:
            return ''
        names = ', '.join(self._missing_names[:3])
        suffix = f' +{len(self._missing_names) - 3}' if len(self._missing_names) > 3 else ''
        return f"Missing tex: {names}{suffix}"

    def set_datas(self):
        import os
        obj = self._parent._object
        seen: Set[str] = set()
        missing: List[str] = []
        for slot in obj.material_slots:
            mat = slot.material
            if not mat or not mat.use_nodes:
                continue
            for node in mat.node_tree.nodes:
                if node.type != 'TEX_IMAGE':
                    continue
                img = node.image
                if img is None or img.name in seen:
                    continue
                seen.add(img.name)
                if img.packed_file:
                    continue          # packed — always available
                if not img.filepath:
                    continue          # generated / render result — skip
                if not os.path.exists(bpy.path.abspath(img.filepath)):
                    missing.append(img.name)
        self._missing_names = missing
        self._count = len(missing)

    def get_edges(self, offset: float):
        return ()

    def get_points(self, offset: float):
        if self._count == 0:
            return ()
        obj = self._parent._object
        loc = obj.matrix_world.translation
        _offset = _get_offset(offset * 3, obj)
        return ((loc.x, loc.y, loc.z + _offset),)


class IsolatedVertices(BaseCheck):
    """Vertices not connected to any edge — cleanup issue."""

    def __init__(self, parent):
        super().__init__(parent)
        self._vert_idx: List[int] = []

    def set_datas(self):
        bm = self._parent.bm_object
        bm.verts.ensure_lookup_table()
        self._vert_idx = [v.index for v in bm.verts if not v.link_edges]
        self._count = len(self._vert_idx)

    def get_edges(self, offset: float):
        return ()

    def get_points(self, offset: float):
        if not self._vert_idx:
            return ()
        bm = self._parent.bm_object
        bm.verts.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        for idx in self._vert_idx:
            if idx < len(bm.verts):
                v = bm.verts[idx]
                p = wm @ v.co
                coords.append((p.x + v.normal.x * _offset,
                               p.y + v.normal.y * _offset,
                               p.z + v.normal.z * _offset))
        return tuple(coords)

    def get_select_data(self):
        return ('VERT', self._vert_idx)


class DuplicateVertices(BaseCheck):
    """Overlapping vertices within 0.1 mm — would merge on Merge by Distance.

    Only flags doubles WITHIN one connected shell (island of the edge graph).
    Coincident verts belonging to different shells (bolted plates, stacked
    parts joined into one object) are intentional hard-surface practice —
    merging them would weld separate shells, so they are NOT flagged.
    """

    _MERGE_DIST = 1e-5  # 0.01 mm — only catches truly coincident verts, not just close ones

    def __init__(self, parent):
        super().__init__(parent)
        self._dup_idx: List[int] = []
        self._dup_pair_idx: List[int] = []   # flagged verts ∪ their merge targets

    @staticmethod
    def _vert_islands(bm) -> list:
        """Union-find over the edge graph → island id per vert index."""
        parent = list(range(len(bm.verts)))

        def find(x: int) -> int:
            root = x
            while parent[root] != root:
                root = parent[root]
            while parent[x] != root:      # path compression
                parent[x], x = root, parent[x]
            return root

        for e in bm.edges:
            a, b = e.verts[0].index, e.verts[1].index
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        return [find(i) for i in range(len(parent))]

    def set_datas(self):
        bm = self._parent.bm_object
        self._dup_idx = []
        self._dup_pair_idx = []
        if not bm.verts:
            self._count = 0
            return
        result = bmesh.ops.find_doubles(bm, verts=list(bm.verts), dist=self._MERGE_DIST)
        targetmap = result['targetmap']
        if not targetmap:
            self._count = 0
            return
        islands = self._vert_islands(bm)
        self._dup_idx = [v.index for v, t in targetmap.items()
                         if islands[v.index] == islands[t.index]]
        self._count = len(self._dup_idx)
        if self._count:
            # Both pair members are needed for select/fix — merging with only
            # half of each pair selected would be a no-op.
            same_island = [(v, t) for v, t in targetmap.items()
                           if islands[v.index] == islands[t.index]]
            self._dup_pair_idx = sorted({*(v.index for v, _ in same_island),
                                         *(t.index for _, t in same_island)})

    def get_edges(self, offset: float) -> Tuple:
        return ()

    def get_points(self, offset: float):
        if not self._dup_idx:
            return ()
        bm = self._parent.bm_object
        bm.verts.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        for idx in self._dup_idx:
            if idx < len(bm.verts):
                v = bm.verts[idx]
                p = wm @ v.co
                coords.append((p.x + v.normal.x * _offset,
                               p.y + v.normal.y * _offset,
                               p.z + v.normal.z * _offset))
        return tuple(coords)

    def get_select_data(self):
        return ('VERT', self._dup_pair_idx or self._dup_idx)


class FaceAspectRatio(BaseCheck):
    """Quad faces whose aspect ratio exceeds the threshold.

    Aspect ratio = avg_longer_pair / avg_shorter_pair for the two pairs of
    opposite edges in a quad.  Only quads are checked; tris and ngons skipped.
    Threshold is read from prefs.face_aspect_ratio_threshold (default 6.0).
    """

    _DEFAULT_THRESHOLD = 6.0

    def __init__(self, parent):
        super().__init__(parent)
        self._bad_face_indices: List[int] = []
        self._bad_edge_coords:  tuple = ()

    def set_datas(self):
        bm  = self._parent.bm_object
        obj = self._parent._object
        wm  = obj.matrix_world

        try:
            addon_name = __name__.rsplit(".", 1)[0]
            prefs = bpy.context.preferences.addons[addon_name].preferences
            threshold = float(getattr(prefs, 'face_aspect_ratio_threshold',
                                      self._DEFAULT_THRESHOLD))
        except Exception:
            threshold = self._DEFAULT_THRESHOLD

        bad_indices: List[int] = []
        raw_verts:   list = []        # flat: v0 v1 v2 v3 per face (world-space + normal offset)

        bm.faces.ensure_lookup_table()
        offset = _get_offset(0.03, obj)

        for face in bm.faces:
            loops = face.loops
            if len(loops) != 4:
                continue
            v0, v1, v2, v3 = (l.vert.co for l in loops)
            e0 = (v0 - v1).length
            e1 = (v1 - v2).length
            e2 = (v2 - v3).length
            e3 = (v3 - v0).length
            avg_a = (e0 + e2) * 0.5
            avg_b = (e1 + e3) * 0.5
            if avg_a < 1e-10 or avg_b < 1e-10:
                continue
            ratio = avg_a / avg_b if avg_a > avg_b else avg_b / avg_a
            if ratio <= threshold:
                continue
            bad_indices.append(face.index)
            fn = face.normal
            nx, ny, nz = fn.x * offset, fn.y * offset, fn.z * offset
            for lp in loops:
                p = wm @ lp.vert.co
                raw_verts.append((p.x + nx, p.y + ny, p.z + nz))

        # Build edge-pair list (4 edges per quad, each as two endpoint tuples)
        pairs: list = []
        for fi in range(len(bad_indices)):
            b = fi * 4
            for i in range(4):
                pairs.append(raw_verts[b + i])
                pairs.append(raw_verts[b + (i + 1) % 4])

        self._count             = len(bad_indices)
        self._bad_face_indices  = bad_indices
        self._bad_edge_coords   = tuple(pairs)

    def get_edges(self, offset: float):
        return self._bad_edge_coords

    def get_points(self, offset: float):
        return ()

    def get_select_data(self):
        return ('FACE', self._bad_face_indices)


class ModifierStack(BaseCheck):
    """Unapplied modifiers on the object. Only Armature is excluded (cannot be applied)."""

    # Modifiers that are intentionally kept unapplied (non-destructive pipeline)
    _IGNORE_TYPES = frozenset({'ARMATURE'})

    def __init__(self, parent):
        super().__init__(parent)
        self._bbox: Tuple = ()

    def set_datas(self):
        obj = self._parent._object
        bad_mods = [m.name for m in obj.modifiers if m.type not in self._IGNORE_TYPES]
        self._count = len(bad_mods)
        self._bbox = ()
        if bad_mods:
            mw = obj.matrix_world
            corners = [mw @ mathutils.Vector(c) for c in obj.bound_box]
            edge_idx = [0,1,1,2,2,3,3,0, 4,5,5,6,6,7,7,4, 0,4,1,5,2,6,3,7]
            self._bbox = tuple((corners[i].x, corners[i].y, corners[i].z) for i in edge_idx)
            names = ", ".join(bad_mods[:3])
            if len(bad_mods) > 3:
                names += f" (+{len(bad_mods) - 3})"
            self.metric_text = f"Modifiers: {names}"
        else:
            self.metric_text = ""

    def get_edges(self, offset: float):
        return self._bbox

    def get_points(self, offset: float):
        return ()




class OriginAtZero(BaseCheck):
    """Object origin (pivot point) is not at world zero (0, 0, 0)."""

    _THRESHOLD = 0.001

    def __init__(self, parent):
        super().__init__(parent)
        self._bbox: Tuple = ()

    def set_datas(self):
        obj = self._parent._object
        # Use world-space translation so parented objects are checked correctly.
        # obj.location is the LOCAL offset relative to the parent and can be
        # (0, 0, 0) even when the world position is far from the origin.
        mw  = obj.matrix_world
        loc = mw.translation          # mathutils.Vector — world position of the origin
        has_issue = (abs(loc.x) > self._THRESHOLD or
                     abs(loc.y) > self._THRESHOLD or
                     abs(loc.z) > self._THRESHOLD)
        self._count = 1 if has_issue else 0
        self._bbox = ()
        if has_issue:
            corners = [mw @ mathutils.Vector(c) for c in obj.bound_box]
            edge_idx = [0,1,1,2,2,3,3,0, 4,5,5,6,6,7,7,4, 0,4,1,5,2,6,3,7]
            self._bbox = tuple((corners[i].x, corners[i].y, corners[i].z) for i in edge_idx)
            self.metric_text = f"Origin: ({loc.x:.3f}, {loc.y:.3f}, {loc.z:.3f})"
        else:
            self.metric_text = ""

    def get_edges(self, offset: float):
        return self._bbox

    def get_points(self, offset: float):
        return ()


def build_material_udim_map(obj, bm) -> dict:
    """Build a dict mapping material name → set of (tile_u, tile_v) UDIM tile coords.

    tile_u = floor(u), tile_v = floor(v)
    UDIM number = 1001 + tile_u + tile_v * 10

    Uses numpy foreach_get for fast bulk reads (avoids Python BMesh loop on large meshes).
    Falls back to bmesh loop in EDIT mode (bm required for race-condition safety).
    """
    import numpy as np
    me = obj.data
    if not bm or not me.uv_layers.active:
        return {}

    slots = obj.material_slots
    n_slots = len(slots)

    # In EDIT mode we must read UV from bmesh (me.loops don't reflect live edits)
    if me.is_editmode:
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            return {}
        mat_tiles: dict = {}
        bm.faces.ensure_lookup_table()
        for face in bm.faces:
            mi = face.material_index
            mat_name = slots[mi].material.name if (mi < n_slots and slots[mi].material) else "(no material)"
            if mat_name not in mat_tiles:
                mat_tiles[mat_name] = set()
            face_tiles = mat_tiles[mat_name]
            for loop in face.loops:
                uv = loop[uv_layer].uv
                # NaN/inf UVs (degenerate geometry) crash int(floor()) — skip them
                if not (math.isfinite(uv.x) and math.isfinite(uv.y)):
                    continue
                face_tiles.add((int(math.floor(uv.x)), int(math.floor(uv.y))))
        return mat_tiles

    # ── OBJECT mode: fully vectorized ──────────────────────────────────────────
    n_polys = len(me.polygons)
    n_loops = len(me.loops)
    if n_polys == 0 or n_loops == 0:
        return {}

    # UV coordinates (tile index = floor)
    uv_flat = _get_uv_np(me, bm=bm)
    if uv_flat is None:
        return {}
    # NaN/inf UVs (degenerate geometry) crash the int conversion below —
    # drop the affected loops instead of killing the whole map.
    finite = np.isfinite(uv_flat).all(axis=1)
    if not finite.all():
        uv_flat = uv_flat[finite]
        if uv_flat.shape[0] == 0:
            return {}
    tile_u = np.floor(uv_flat[:, 0]).astype(np.int32)
    tile_v = np.floor(uv_flat[:, 1]).astype(np.int32)

    # Material index per polygon → expand to loop level
    mi_poly = np.empty(n_polys, dtype=np.int32)
    me.polygons.foreach_get("material_index", mi_poly)
    pt = np.empty(n_polys, dtype=np.int32)
    me.polygons.foreach_get("loop_total", pt)
    mi_loop = np.repeat(mi_poly, pt)[finite]   # (n_loops,) material index per loop

    # Build slot_index → mat_name mapping
    slot_names = []
    for i in range(n_slots):
        slot = slots[i]
        slot_names.append(slot.material.name if slot.material else "(no material)")
    # Clamp indices to valid range
    mi_loop_clamped = np.clip(mi_loop, 0, max(n_slots - 1, 0))
    if n_slots == 0:
        mat_names_per_loop = ["(no material)"] * n_loops
    else:
        mat_names_per_loop = [slot_names[i] for i in mi_loop_clamped.tolist()]

    # Pack (mat_idx, tile_u, tile_v) into a single int64 for fast 1-D np.unique.
    # tile_u / tile_v are clamped to [-32768, 32767] (16-bit signed).
    # mat_idx fits in the upper 32 bits.
    tile_u_c = np.clip(tile_u, -32768, 32767).astype(np.int64) + 32768   # 0..65535
    tile_v_c = np.clip(tile_v, -32768, 32767).astype(np.int64) + 32768   # 0..65535
    packed   = (mi_loop_clamped.astype(np.int64) << 32) | (tile_u_c << 16) | tile_v_c
    unique_packed = np.unique(packed)   # 1-D sort — much faster than 2-D

    mat_tiles: dict = {}
    for combo in unique_packed.tolist():
        tv_val  = (combo        & 0xFFFF) - 32768
        tu_val  = ((combo >> 16) & 0xFFFF) - 32768
        mi_idx  = combo >> 32
        mn = slot_names[mi_idx] if mi_idx < n_slots else "(no material)"
        entry = mat_tiles.get(mn)
        if entry is None:
            mat_tiles[mn] = {(tu_val, tv_val)}
        else:
            entry.add((tu_val, tv_val))

    return mat_tiles


class UnusedData(BaseCheck):
    """Detects unused/stale mesh data that is safe to remove.

    Tracked items:
    * Empty vertex groups — groups where every vertex has weight 0 (or no
      vertices are assigned at all).  Common after rigging experiments,
      copy-paste from other assets, or ZBrush round-trips.
    * Custom mesh attributes — non-standard, non-UV attributes that were
      likely left by geometry nodes, scripts or external tools.

    ``count`` = empty vgroups + custom attrs → drives WARNING threshold.
    ``metric_text`` breaks the total down by type.
    """

    # Attribute names that Blender creates internally — never flag these.
    _BUILTIN_ATTRS: frozenset = frozenset({
        'position', 'sharp_face', 'sharp_edge', 'material_index',
        'crease_vert', 'crease_edge',
        '.corner_vert', '.corner_edge', '.edge_verts', '.poly_edge_offset',
        '.poly_edge_indices', '.sculpt_face_set',
        'custom_normal',
        # Legacy mesh properties stored as attributes since Blender 4.0/4.1 —
        # these ARE mesh data (UV seams! bevel weights!), never flag them.
        'uv_seam', 'bevel_weight_vert', 'bevel_weight_edge', 'mask',
    })

    # Guard: skip per-vertex group scan on very heavy meshes
    _MAX_VERTS_VGROUP_SCAN: int = 300_000

    def __init__(self, parent):
        super().__init__(parent)
        self._empty_vgroups: List[str] = []
        self._custom_attrs:  List[str] = []

    @property
    def count(self) -> int:
        if self._ignored:
            return 0
        return len(self._empty_vgroups) + len(self._custom_attrs)

    @property
    def metric_text(self) -> str:
        parts = []
        if self._empty_vgroups:
            n = len(self._empty_vgroups)
            parts.append(f"{n} vgroup{'s' if n > 1 else ''}")
        if self._custom_attrs:
            n = len(self._custom_attrs)
            parts.append(f"{n} attr{'s' if n > 1 else ''}")
        return "  ·  ".join(parts) if parts else ""

    def set_datas(self):
        obj = self._parent._object
        me  = obj.data

        # ── 1. Empty vertex groups ─────────────────────────────────────────
        self._empty_vgroups = []
        if obj.vertex_groups:
            n_verts = len(me.vertices)
            if n_verts <= self._MAX_VERTS_VGROUP_SCAN:
                # Single pass: collect group indices that have any weight > 0
                weighted: set = set()
                for v in me.vertices:
                    for ge in v.groups:
                        if ge.weight > 1e-6:
                            weighted.add(ge.group)
                self._empty_vgroups = [
                    vg.name for vg in obj.vertex_groups
                    if vg.index not in weighted
                ]
            # Meshes above the guard get a lightweight fallback:
            # flag groups that have literally no vertex assignments at all
            else:
                assigned: set = set()
                for v in me.vertices:
                    for ge in v.groups:
                        assigned.add(ge.group)
                self._empty_vgroups = [
                    vg.name for vg in obj.vertex_groups
                    if vg.index not in assigned
                ]

        # ── 2. Custom mesh attributes ──────────────────────────────────────
        self._custom_attrs = []
        uv_names    = {uv.name for uv in me.uv_layers}
        color_names = {ca.name for ca in me.color_attributes} \
                      if hasattr(me, 'color_attributes') else set()

        for attr in me.attributes:
            name = attr.name
            if name in self._BUILTIN_ATTRS:
                continue
            if name.startswith('.'):          # Blender internal
                continue
            if name in uv_names:              # UV maps shown elsewhere
                continue
            if name in color_names:           # color attributes — separate check later
                continue
            self._custom_attrs.append(name)

    def get_edges(self, offset: float):
        # Unused data has no geometry to highlight in the 3D viewport.
        return ()

    def get_select_data(self):
        # No geometry index to select — names are shown via metric_text
        return (None, [])


class MeshDataNaming(BaseCheck):
    """Mesh datablock must not keep Blender auto-names ('Mesh.101').

    Valid when the datablock is named exactly like its object, or ends with
    one of the configured mesh suffixes (Preferences → Naming Policy →
    Mesh Data, default '_mesh').  Fix renames the datablock to
    <object root> + first mesh suffix, stripping the object suffix
    (e.g. object 'body_geo' → mesh 'body_mesh')."""

    _DEFAULT_SUFFIXES = ("_mesh",)

    def __init__(self, parent):
        super().__init__(parent)
        self._mesh_name: str = ""
        self._target:    str = ""

    # ── policy helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _prefs():
        try:
            addon = bpy.context.preferences.addons.get(__name__.rsplit(".", 1)[0])
            if addon is None:   # legacy installs key prefs by short name
                for key in bpy.context.preferences.addons.keys():
                    if key.endswith(".stukach"):
                        addon = bpy.context.preferences.addons.get(key)
                        break
            return addon.preferences if addon else None
        except Exception:
            return None

    @classmethod
    def _mesh_suffixes(cls) -> List[str]:
        suffixes = []
        # Inline panel field takes priority (first = used by Fix)
        try:
            mc = bpy.context.window_manager.mesh_check_props
            inline = getattr(mc, "mesh_required_suffix", "").strip()
            if inline:
                suffixes.append(inline)
        except Exception:
            pass
        prefs = cls._prefs()
        if prefs and getattr(prefs, "mesh_naming_suffixes", None):
            for e in prefs.mesh_naming_suffixes:
                v = e.value.strip()
                if v and v not in suffixes:
                    suffixes.append(v)
        return suffixes or list(cls._DEFAULT_SUFFIXES)

    @classmethod
    def _target_name(cls, obj) -> str:
        """<object name minus object suffix> + first mesh suffix."""
        from .naming import NAMING_RULES
        name = obj.name
        low = name.lower()
        obj_suffixes = [s.lower() for s in
                        NAMING_RULES.get("object", {}).get("allowed_suffixes", [])]
        prefs = cls._prefs()
        if prefs and getattr(prefs, "naming_suffixes", None):
            obj_suffixes = [e.value.strip().lower()
                            for e in prefs.naming_suffixes] + obj_suffixes
        for s in obj_suffixes:
            if s and low.endswith(s) and len(name) > len(s):
                return name[:-len(s)] + cls._mesh_suffixes()[0]
        return name + cls._mesh_suffixes()[0]

    # ── check ──────────────────────────────────────────────────────────────
    def set_datas(self) -> None:
        obj = self._parent._object
        if obj.type != "MESH":
            self._count = 0
            return
        self._mesh_name = obj.data.name
        name_l = self._mesh_name.lower()
        if name_l == obj.name.lower():
            self._count = 0
            self._target = ""
            return
        if any(name_l.endswith(s.lower()) for s in self._mesh_suffixes()):
            self._count = 0
            self._target = ""
            return
        self._count = 1
        self._target = self._target_name(obj)

    @property
    def metric_text(self) -> str:
        if self._count and self._target:
            return f"{self._mesh_name}  →  {self._target}"
        return self._mesh_name

    def get_edges(self, offset: float):
        return ()

    def get_points(self, offset: float):
        return ()

    def get_faces(self, offset: float):
        return ()

    def get_select_data(self):
        # Nothing selectable — the fix renames the datablock
        return (None, [])


# ─── MAYA v1.1.0 PARITY CHECKS (reference: STUKACH_Maya snapshot checks) ──────


class _EdgeOverlay:
    """Shared GPU edge draw for checks tracking an ``_edges_idx`` list."""

    def get_edges(self, offset: float):
        idx = getattr(self, "_edges_idx", None)
        if not idx:
            return ()
        bm = self._parent.bm_object
        bm.edges.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        for e_idx in idx:
            for v in bm.edges[e_idx].verts:
                p = wm @ v.co
                coords.append((p.x + v.normal.x * _offset,
                               p.y + v.normal.y * _offset,
                               p.z + v.normal.z * _offset))
        return tuple(coords)


class _FanFaceOverlay:
    """Shared GPU face draw (fan triangulation) for checks tracking ``_faces_idx``."""

    def get_faces(self, offset: float):
        idx = getattr(self, "_faces_idx", None)
        if not idx:
            return (), []
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()
        obj = self._parent._object
        wm = obj.matrix_world
        _offset = _get_offset(offset, obj)
        coords = []
        indices = []
        base = 0
        for f_idx in idx:
            fv = [v.index for v in bm.faces[f_idx].verts]
            for k in range(1, len(fv) - 1):
                for vi in (fv[0], fv[k], fv[k + 1]):
                    v = bm.verts[vi]
                    p = wm @ v.co
                    coords.append((p.x + v.normal.x * _offset,
                                   p.y + v.normal.y * _offset,
                                   p.z + v.normal.z * _offset))
                indices.append((base, base + 1, base + 2))
                base += 3
        return tuple(coords), indices


class Lamina(_EdgeOverlay, _FanFaceOverlay, BaseCheck):
    """Lamina faces — zero-thickness geometry folded onto itself.

    Maya isLamina() analog: the face contour traverses the same edge twice
    or repeats a vertex, so the face has no thickness.  Breaks booleans,
    subdivision and exporters."""

    def __init__(self, parent):
        super().__init__(parent)
        self._faces_idx: List[int] = []
        self._edges_idx: List[int] = []

    def set_datas(self):
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        self._faces_idx = []
        bad_edges = set()
        for f in bm.faces:
            vs = [v.index for v in f.verts]
            n = len(vs)
            ekeys = []
            for i in range(n):
                a, b = vs[i], vs[(i + 1) % n]
                ekeys.append((a, b) if a < b else (b, a))
            if len(set(vs)) < n or len(set(ekeys)) < n:
                self._faces_idx.append(f.index)
                bad_edges.update(e.index for e in f.edges)
        self._count = len(self._faces_idx)
        self._edges_idx = sorted(bad_edges)

    def get_select_data(self):
        return ('FACE', self._faces_idx)


class ZeroLengthEdges(_EdgeOverlay, BaseCheck):
    """Edges of (near-)zero length — degenerate geometry from merges/booleans."""

    _TOL = 1e-8

    def __init__(self, parent):
        super().__init__(parent)
        self._edges_idx: List[int] = []

    def set_datas(self):
        bm = self._parent.bm_object
        bm.edges.ensure_lookup_table()
        self._edges_idx = [e.index for e in bm.edges
                           if e.calc_length() <= self._TOL]
        self._count = len(self._edges_idx)

    def get_select_data(self):
        return ('EDGE', self._edges_idx)


class SharpEdgesNotHard(_EdgeOverlay, BaseCheck):
    """Sharp edges (dihedral angle >= 30°) that are NOT marked sharp.

    Smooth shading across a sharp corner produces shading artifacts — such
    edges must be marked sharp (or handled by custom normals).  Listing every
    marked sharp edge is meaningless on hardsurf, so only the MISSED ones are
    flagged.  Maya v1.1.0 HardEdges parity."""

    ANGLE_THRESHOLD_DEG = 30.0

    def __init__(self, parent):
        super().__init__(parent)
        self._edges_idx: List[int] = []

    def set_datas(self):
        bm = self._parent.bm_object
        bm.edges.ensure_lookup_table()
        threshold = math.radians(self.ANGLE_THRESHOLD_DEG)
        self._edges_idx = []
        for e in bm.edges:
            if not e.smooth or not e.is_manifold:
                continue
            angle = e.calc_face_angle(0.0)
            if angle >= threshold:
                self._edges_idx.append(e.index)
        self._count = len(self._edges_idx)

    def get_select_data(self):
        return ('EDGE', self._edges_idx)


class Starlike(_EdgeOverlay, _FanFaceOverlay, BaseCheck):
    """Non-starlike faces — polygon outline self-intersects.

    Maya isStarlike() analog: the contour is projected onto the face plane
    (dominant normal axis dropped) and non-adjacent segments are tested for
    intersection.  Triangles cannot self-intersect and never flag."""

    def __init__(self, parent):
        super().__init__(parent)
        self._faces_idx: List[int] = []
        self._edges_idx: List[int] = []

    @staticmethod
    def _outline_crosses(pts):
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
                # touching / collinear cases (pinch vertices, T-spikes)
                if d1 == 0 and on_seg(b1, b2, a1):
                    return True
                if d2 == 0 and on_seg(b1, b2, a2):
                    return True
                if d3 == 0 and on_seg(a1, a2, b1):
                    return True
                if d4 == 0 and on_seg(a1, a2, b2):
                    return True
        return False

    def set_datas(self):
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        self._faces_idx = []
        self._edges_idx = []
        # Ownership: more specific degenerate checks claim the face first
        # (both run earlier in CHECK_TYPES, so their indices are fresh).
        # Starlike reports only what they left — one defect, one finding.
        claimed = set()
        mc_props = bpy.context.window_manager.mesh_check_props
        for key in ("zero_area", "lamina"):
            if not getattr(mc_props, key, False):
                continue
            other = self._parent._checks.get(key)
            if other is not None:
                claimed.update(getattr(other, "_faces_idx", []) or [])
        for f in bm.faces:
            if f.index in claimed:
                continue
            if len(f.verts) < 4:
                continue
            n = f.normal
            if n.length_squared < 1e-20:
                # Degenerate Newell normal (symmetric bowtie cancels out) —
                # project along the flattest vertex axis instead.  One ~zero
                # spread = planar face (fine, axis == its normal); two = the
                # contour is a line — zero-area, another check's domain.
                spreads = [max(v.co[k] for v in f.verts) - min(v.co[k] for v in f.verts)
                           for k in range(3)]
                if sum(1 for s in spreads if s <= 1e-12) >= 2:
                    continue
                ax = min(range(3), key=lambda k: spreads[k])
            else:
                ax = max(range(3), key=lambda k: abs(n[k]))
            keep = [k for k in range(3) if k != ax]
            pts = [(v.co[keep[0]], v.co[keep[1]]) for v in f.verts]
            if (self._outline_crosses(pts)
                    or self._has_zero_edge(pts)
                    or not self._centroid_sees_all(pts)):
                self._faces_idx.append(f.index)
                self._edges_idx.extend(e.index for e in f.edges)
        self._count = len(self._faces_idx)
        self._edges_idx = list(dict.fromkeys(self._edges_idx))

    @staticmethod
    def _has_zero_edge(pts):
        """Zero-length edge in the contour (consecutive coincident verts —
        a 'stitched' face).  Maya treats such faces as non-starlike."""
        n = len(pts)
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            if (x2 - x1) ** 2 + (y2 - y1) ** 2 <= 1e-12:
                return True
        return False

    @staticmethod
    def _centroid_sees_all(pts):
        """Maya isStarlike() parity: the vertex-averaged centroid must lie
        inside the polygon AND on the inner side of every edge (i.e. the
        whole outline is visible from it).  Concave faces whose centroid
        falls outside — or that it cannot fully see — are non-starlike,
        exactly like Maya flags them."""
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

        # centroid must be inside the polygon (ray casting)
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

        # centroid must see every edge: inner side of each edge line
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            cr = (x2 - x1) * (cy - y1) - (y2 - y1) * (cx - x1)
            if cr * orient < -1e-12:
                return False
        return True

    def get_select_data(self):
        return ('FACE', self._faces_idx)


class MissingUVs(_FanFaceOverlay, BaseCheck):
    """Faces without usable UV mapping (Maya unmapped-face analog).

    No UV layer at all flags every face; with a layer present, faces whose
    loops all sit at (0, 0) are unmapped leftovers (geometry added after
    the unwrap)."""

    _ZERO_SQ = 1e-12

    def __init__(self, parent):
        super().__init__(parent)
        self._faces_idx: List[int] = []

    def set_datas(self):
        bm = self._parent.bm_object
        bm.faces.ensure_lookup_table()
        uvl = bm.loops.layers.uv.active
        if uvl is None and len(bm.loops.layers.uv):
            uvl = bm.loops.layers.uv[0]
        if uvl is None:
            self._faces_idx = list(range(len(bm.faces)))
        else:
            zs = self._ZERO_SQ
            self._faces_idx = [f.index for f in bm.faces
                               if all(l[uvl].uv.length_squared <= zs for l in f.loops)]
        self._count = len(self._faces_idx)

    def get_edges(self, offset: float):
        return ()

    def get_select_data(self):
        return ('FACE', self._faces_idx)


class DuplicatedNames(BaseCheck):
    """Exact object name used by more than one object in the scene.

    Inside one .blend names are unique — duplicates appear with linked
    libraries (same name from different sources) and break export and
    pipeline collection.  Maya v1.1.0 DuplicatedNames parity."""

    def __init__(self, parent):
        super().__init__(parent)
        self._metric = ""

    def set_datas(self):
        obj = self._parent._object
        self._count = 0
        self._metric = ""
        try:
            scene_objs = bpy.context.scene.objects
        except Exception:
            return
        name = obj.name
        n = sum(1 for o in scene_objs if o.name == name)
        if n > 1:
            self._count = 1
            self._metric = f"'{name}' used by {n} objects"

    @property
    def metric_text(self) -> str:
        return self._metric

    def get_edges(self, offset: float):
        return ()


class TrailingNumbers(BaseCheck):
    """Object name ends with digits (Cube.001-style leftovers)."""

    _RE_TRAILING = re.compile(r'\d+$')

    def set_datas(self):
        obj = self._parent._object
        self._count = 1 if self._RE_TRAILING.search(obj.name) else 0

    def get_edges(self, offset: float):
        return ()


class UncenteredPivots(BaseCheck):
    """Pivot further than 5% of the bbox diagonal from the bbox center.

    Compared against the bbox CENTER — comparing against the world origin
    was the Maya-version bug that flagged every placed object."""

    _THRESHOLD = 0.05   # fraction of the bbox diagonal

    def __init__(self, parent):
        super().__init__(parent)
        self._bbox: Tuple = ()
        self._pct = 0.0

    def set_datas(self):
        obj = self._parent._object
        self._count = 0
        self._pct = 0.0
        self._bbox = ()
        mw = obj.matrix_world
        corners = [mw @ mathutils.Vector(c) for c in obj.bound_box]
        xs = [c.x for c in corners]
        ys = [c.y for c in corners]
        zs = [c.z for c in corners]
        diag = math.sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2 +
                         (max(zs) - min(zs)) ** 2)
        if diag < 1e-9:
            return
        pivot = mw.translation
        dist = math.sqrt((pivot.x - (min(xs) + max(xs)) / 2) ** 2 +
                         (pivot.y - (min(ys) + max(ys)) / 2) ** 2 +
                         (pivot.z - (min(zs) + max(zs)) / 2) ** 2)
        if dist > diag * self._THRESHOLD:
            self._count = 1
            self._pct = dist / diag * 100.0
            edge_idx = [0, 1, 1, 2, 2, 3, 3, 0, 4, 5, 5, 6, 6, 7, 7, 4,
                        0, 4, 1, 5, 2, 6, 3, 7]
            self._bbox = tuple((corners[i].x, corners[i].y, corners[i].z)
                               for i in edge_idx)

    @property
    def metric_text(self) -> str:
        return f"pivot off-center by {self._pct:.1f}% of bbox" if self._count else ""

    def get_edges(self, offset: float):
        return self._bbox


class ParentGeometry(BaseCheck):
    """Object parented under another MESH object — breaks export hierarchies."""

    def __init__(self, parent):
        super().__init__(parent)
        self._parent_name = ""

    def set_datas(self):
        p = self._parent._object.parent
        bad = p is not None and p.type == 'MESH'
        self._count = 1 if bad else 0
        self._parent_name = p.name if bad else ""

    @property
    def metric_text(self) -> str:
        return f"parented under mesh '{self._parent_name}'" if self._count else ""

    def get_edges(self, offset: float):
        return ()


CHECK_TYPES = {
    "triangles":             Triangles,
    "ngons":                 Ngons,
    "non_manifold":          NonManifold,
    "boundary_edges":        BoundaryEdges,
    "poles":                 Poles,
    "zero_area":             ZeroAreaFaces,
    "isolated_verts":        IsolatedVertices,
    "duplicate_verts":       DuplicateVertices,
    "face_aspect_ratio":     FaceAspectRatio,
    "non_applied_transform": NonAppliedTransform,
    "scale":                 Scale,
    "modifier_stack":        ModifierStack,
    "origin_at_zero":        OriginAtZero,
    "z_fighting":            ZFighting,
    "obj_naming":            NamingCheck,
    "col_naming":            ColNaming,
    "mesh_data_naming":      MeshDataNaming,
    "mat_suffix":            MaterialCheck,
    "mat_assignment":        MatAssignment,
    "mat_numbering":         MatNaming,
    "missing_textures":      MissingTextures,
    "uv_single_set":         UVSingleSet,
    "uv_overlap":            UVOverlapCheck,
    "uv_micro_shell":        UVMicroShellCheck,
    "uv_texel_density":      UVTexelDensity,
    "uv_stretch":            UVStretch,
    "uv_padding":            UVPaddingCheck,
    "uv_udim_bounds":        UVUDIMBounds,
    "uv_material_udim":      UVMaterialUDIM,
    "symmetry_x":            SymmetryX,
    "symmetry_y":            SymmetryY,
    "symmetry_z":            SymmetryZ,
    "unused_data":           UnusedData,
    # MAYA v1.1.0 parity
    "lamina":                Lamina,
    "zero_length_edges":     ZeroLengthEdges,
    "sharp_edges_not_hard":  SharpEdgesNotHard,
    "starlike":              Starlike,
    "missing_uvs":           MissingUVs,
    "duplicated_names":      DuplicatedNames,
    "trailing_numbers":      TrailingNumbers,
    "uncentered_pivots":     UncenteredPivots,
    "parent_geometry":       ParentGeometry,
}

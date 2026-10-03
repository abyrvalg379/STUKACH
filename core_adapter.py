# -*- coding: utf-8 -*-
"""Blender adapter: Mesh (OBJECT mode) -> stukach_core.MeshSnapshot.

Stage-2 of the strangler: builds the DCC-free core snapshot from a bpy Mesh
with numpy foreach_get reads.  The pure-geometry rules (triangles, ngons,
zero_area, poles, boundary_edges, isolated_verts, zero_length_edges,
face_aspect_ratio, lamina, starlike, missing_uvs, duplicate_verts) are
computed by the core from this snapshot and are parity-proven against the
addon checks by the smoke core_parity step (19/19 gate).

lamina/starlike fields stay neutral placeholders: since stage-2 tranche 2
the core computes both from the contour geometry, the adapter flags are
informational only.
"""
import numpy


# Checks whose detection runs in the vendored core (updated per tranche).
# The CHECKS.md "Core" column is driven by this set via the smoke dump —
# name matches with core RULES are NOT delegation evidence.
CORE_DELEGATED = frozenset({
    "non_manifold", "lamina", "starlike", "duplicate_verts",
    "symmetry_x", "symmetry_y", "symmetry_z",
    "duplicated_names", "trailing_numbers", "parent_geometry",
    "uv_single_set", "uv_udim_bounds", "uv_micro_shell",
})


def build_snapshot(me, node: str = "", shape: str = "",
                   parent_types=None, scene=None):
    """Build a stukach_core MeshSnapshot from a bpy Mesh (OBJECT mode data)."""
    from . import _core

    uv_set_count = len(me.uv_layers)

    n_verts = len(me.vertices)
    co = numpy.empty(n_verts * 3, dtype=numpy.float64)
    me.vertices.foreach_get("co", co)
    points = [tuple(p) for p in co.reshape(-1, 3)]

    n_faces = len(me.polygons)
    face_verts = [tuple(p.vertices) for p in me.polygons]
    face_area = [p.area for p in me.polygons]

    n_edges = len(me.edges)
    ev = numpy.empty(n_edges * 2, dtype=numpy.int64)
    me.edges.foreach_get("vertices", ev)
    edges = [(int(ev[i]), int(ev[i + 1])) for i in range(0, n_edges * 2, 2)]

    # connected-face counts from face corner walks (same walk as core
    # MeshSnapshot.edge_faces, so non_manifold/lamina parity is preserved)
    edge_conn = [0] * n_edges
    edge_lookup = {(a, b) if a < b else (b, a): i for i, (a, b) in enumerate(edges)}
    for verts in face_verts:
        n = len(verts)
        for i in range(n):
            a, b = verts[i], verts[(i + 1) % n]
            eid = edge_lookup.get((a, b) if a < b else (b, a))
            if eid is not None:
                edge_conn[eid] += 1

    # first UV layer, flat per-face tuples; None when the mesh has no UV layer
    if me.uv_layers.active:
        uvs = numpy.empty(len(me.loops) * 2, dtype=numpy.float64)
        me.uv_layers.active.data.foreach_get("uv", uvs)
        face_uvs = []
        for p in me.polygons:
            start, total = p.loop_start, p.loop_total
            face_uvs.append(tuple(uvs[start * 2:(start + total) * 2].tolist()))
    else:
        face_uvs = [None] * n_faces

    # neutral placeholders — lamina/starlike core rules must stay DISABLED on
    # this snapshot until the adapter computes real flags (stage-2 tranche 2)
    return _core.MeshSnapshot(
        node=node or (me.name if not shape else shape),
        shape=shape or node,
        short_name=node,
        shape_short=shape,
        points=points,
        face_verts=face_verts,
        face_area=face_area,
        face_lamina=[False] * n_faces,
        face_starlike=[True] * n_faces,
        face_uvs=face_uvs,
        edges=edges,
        edge_smooth=[False] * n_edges,
        edge_conn=edge_conn,
        parent_types=list(parent_types or []),
        scene=dict(scene or {}),
        uv_set_count=uv_set_count,
    )


def build_snapshot_from_bm(bm, node: str = "", shape: str = "",
                           parent_types=None, scene=None):
    """BMesh variant for EDIT mode (me.* is stale there).  Reads the same
    data the OBJECT-mode adapter does, straight off the live BMesh."""
    from . import _core

    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()

    points = [(v.co.x, v.co.y, v.co.z) for v in bm.verts]
    face_verts = [tuple(v.index for v in f.verts) for f in bm.faces]
    face_area = [f.calc_area() for f in bm.faces]
    edges = [(e.verts[0].index, e.verts[1].index) for e in bm.edges]
    edge_conn = [len(e.link_faces) for e in bm.edges]

    uvl = bm.loops.layers.uv.active
    if uvl is None and len(bm.loops.layers.uv):
        uvl = bm.loops.layers.uv[0]
    if uvl is not None:
        face_uvs = []
        for f in bm.faces:
            face_uvs.append(tuple(c for l in f.loops for c in (l[uvl].uv.x, l[uvl].uv.y)))
    else:
        face_uvs = [None] * len(bm.faces)

    return _core.MeshSnapshot(
        node=node or shape,
        shape=shape,
        short_name=node,
        shape_short=shape,
        points=points,
        face_verts=face_verts,
        face_area=face_area,
        face_lamina=[False] * len(bm.faces),
        face_starlike=[True] * len(bm.faces),
        face_uvs=face_uvs,
        edges=edges,
        edge_smooth=[e.smooth for e in bm.edges],
        edge_conn=edge_conn,
        parent_types=list(parent_types or []),
        scene=dict(scene or {}),
        uv_set_count=len(bm.loops.layers.uv),
    )

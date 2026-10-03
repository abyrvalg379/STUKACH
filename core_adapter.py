# -*- coding: utf-8 -*-
"""Blender adapter: Mesh (OBJECT mode) -> stukach_core.MeshSnapshot.

Stage-2 tranche 1 of the strangler: builds the DCC-free core snapshot from a
bpy Mesh with numpy foreach_get reads.  Parity-proven rules (see the smoke
core_parity step): triangles, ngons, zero_area, poles, boundary_edges,
isolated_verts, zero_length_edges, face_aspect_ratio.

NOT covered yet (do not enable these core rules on this snapshot):
  * lamina / starlike — Blender computes them from BMesh, not Mesh; the
    adapter fills neutral placeholders,
  * missing_uvs — the addon's semantics (all-loops-at-0,0 counts as missing)
    is richer than the core's None-only rule,
  * duplicate_verts — the core degrades to clean without scipy, which stock
    Blender does not ship.
"""
import numpy


def build_snapshot(me, node: str = "", shape: str = ""):
    """Build a stukach_core MeshSnapshot from a bpy Mesh (OBJECT mode data)."""
    from . import _core

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
    )

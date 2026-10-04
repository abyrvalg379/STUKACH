# -*- coding: utf-8 -*-
"""Core data model: DCC-neutral mesh snapshot and findings.

Element addressing is index-based: a Finding carries (element_type, index)
pairs — "face", "edge", "vert".  Native component strings ("mesh.f[3]",
"mesh.vtx[7]") are rendered by the DCC adapter, never by the core.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# severity vocabulary (shared with both DCC layers)
ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"


@dataclass
class Finding:
    """One rule result for one object.  None-returns from evaluators mean clean.

    owner is set by scene-scope rules (run_scene_checks): the key of the
    snapshot mapping the finding belongs to; object-scope rules leave it
    empty — the finding belongs to the snapshot it was evaluated on."""
    rule: str
    severity: str
    count: int
    elements: List[Tuple[str, int]] = field(default_factory=list)
    metric: str = ""          # short human hint, optional
    owner: str = ""


@dataclass
class MeshSnapshot:
    """Immutable per-mesh snapshot — one DCC traversal feeds every check.

    Index space is adapter-owned (Maya: faceId/edgeId/vertId; Blender: loop-
    derived indices).  The core never talks back to the DCC.  String fields
    (node/shape) are opaque adapter labels used only for messages."""
    node: str = ""
    shape: str = ""
    short_name: str = ""
    shape_short: str = ""
    namespace: str = ""
    layers: List[str] = field(default_factory=list)

    points: List[Tuple[float, float, float]] = field(default_factory=list)
    face_verts: List[Tuple[int, ...]] = field(default_factory=list)   # face → corner verts
    face_area: List[float] = field(default_factory=list)              # face → area (0 = not requested)
    face_lamina: List[bool] = field(default_factory=list)             # face → lamina flag
    face_starlike: List[bool] = field(default_factory=list)           # face → starlike flag
    face_uvs: List[Optional[Tuple[float, ...]]] = field(default_factory=list)  # face → flat uv pairs or None

    edges: List[Tuple[int, int]] = field(default_factory=list)        # edge → (v0, v1)
    edge_smooth: List[bool] = field(default_factory=list)
    edge_conn: List[int] = field(default_factory=list)                # edge → connected face count
    face_smooth: List[bool] = field(default_factory=list)             # face → smooth shading flag (empty = not reported)
    custom_normal_driven: Optional[bool] = None                       # True = shading is custom-normal driven (sharp flags meaningless)

    world_matrix: Tuple[float, ...] = ()
    rotate_pivot: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    parent_types: List[str] = field(default_factory=list)             # adapter node types of parents
    uv_set_count: Optional[int] = None                                # None = adapter didn't report
    local_matrix: Tuple[float, ...] = ()                              # object's own (basis) transform, flat 4x4
    face_mat: List[int] = field(default_factory=list)                 # face → material index (empty = not reported)
    material_names: List[str] = field(default_factory=list)           # material slot names (empty = not reported)

    scene: Dict = field(default_factory=dict)   # e.g. {"short_names": {name: count}}

    # ── lazy adjacency (shared by all checks of one snapshot) ──
    _vert_edges: Optional[Dict[int, List[int]]] = field(
        default=None, init=False, repr=False, compare=False)
    _vert_faces: Optional[Dict[int, List[int]]] = field(
        default=None, init=False, repr=False, compare=False)
    _edge_faces: Optional[Dict[int, List[int]]] = field(
        default=None, init=False, repr=False, compare=False)

    def vert_edges(self) -> Dict[int, List[int]]:
        """vert → [edge, ...]"""
        if self._vert_edges is None:
            m: Dict[int, List[int]] = {}
            for eid, (a, b) in enumerate(self.edges):
                m.setdefault(a, []).append(eid)
                m.setdefault(b, []).append(eid)
            self._vert_edges = m
        return self._vert_edges

    def vert_faces(self) -> Dict[int, List[int]]:
        """vert → [face, ...] (distinct faces containing the vertex)"""
        if self._vert_faces is None:
            m: Dict[int, List[int]] = {}
            for fid, verts in enumerate(self.face_verts):
                for v in set(verts):
                    m.setdefault(v, []).append(fid)
            self._vert_faces = m
        return self._vert_faces

    def edge_faces(self) -> Dict[int, List[int]]:
        """edge → [face, ...] — from face corner walks (wire edges absent)."""
        if self._edge_faces is None:
            pairs: Dict[Tuple[int, int], int] = {}
            for eid, (a, b) in enumerate(self.edges):
                pairs[(a, b) if a < b else (b, a)] = eid
            m: Dict[int, List[int]] = {}
            for fid, verts in enumerate(self.face_verts):
                n = len(verts)
                for i in range(n):
                    a, b = verts[i], verts[(i + 1) % n]
                    eid = pairs.get((a, b) if a < b else (b, a))
                    if eid is not None:
                        m.setdefault(eid, []).append(fid)
            self._edge_faces = m
        return self._edge_faces


def edge_length(points, edge: Tuple[int, int]) -> float:
    a, b = points[edge[0]], points[edge[1]]
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5

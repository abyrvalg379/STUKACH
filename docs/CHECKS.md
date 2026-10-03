# Checker reference

Generated from the code registries — do not edit by hand.
Regenerate: run the smoke test, then `python tests/gen_checkers_doc.py`.

## Core rules (stukach_core) — 24

DCC-free rules shared by every STUKACH build. Severity is decided by
the registry; each DCC layer maps the verdicts onto its own UI.

| Rule | Severity | Defaults | Description |
|---|---|---|---|
| `triangles` | WARNING | — | Triangular faces where the pipeline expects quads. |
| `ngons` | BLOCKER | — | Faces with more than four vertices (n-gons). |
| `non_manifold` | BLOCKER | — | Non-manifold EDGES only (Blender-parity semantics). |
| `zero_area` | BLOCKER | threshold=1e-10 | Degenerate faces below the area *threshold* — collapsed geometry. |
| `poles` | INFO | — | N-poles (3 edges) and E-poles (5+) on INTERIOR vertices only. |
| `isolated_verts` | WARNING | — | Vertices connected to neither an edge nor a face — cleanup leftovers. |
| `boundary_edges` | WARNING | — | Edges with exactly one adjacent face — open borders of the shell. |
| `duplicate_verts` | BLOCKER | merge_dist=1e-05 | Overlapping vertices within *merge_dist* that belong to ONE shell. |
| `lamina` | BLOCKER | — | Lamina faces — the contour repeats a vertex or traverses the same edge twice, so the face has zero thickness (isLamina analog, computed). |
| `zero_length_edges` | BLOCKER | tol=1e-08 | Edges at or below the length *tol* — degenerate geometry from merges/booleans. |
| `starlike` | WARNING | zero_area_threshold=1e-10 | Non-starlike faces (quads and n-gons; tris cannot self-intersect). |
| `missing_uvs` | WARNING | zero_sq=1e-12 | Faces without usable UV mapping: no layer at all (adapter passes None), or every loop of the face sits at (0, 0) — unmapped leftovers. |
| `uv_single_set` | WARNING | expected=1 | Exactly one UV set on the mesh (extra sets double the texture work; none at all is missing_uvs' territory — this rule just counts sets). |
| `uv_udim_bounds` | BLOCKER | eps=1e-05 | UV islands whose bbox spans more than one 1x1 UDIM tile — such shells land on several tiles and break single-tile texture assignments. |
| `uv_micro_shell` | WARNING | island_area=1e-05 | UV islands whose total UV area is below *island_area* — collapsed or forgotten shells too small to receive meaningful texture detail (≈ 6px x 6px at 2048 for the default threshold). |
| `face_aspect_ratio` | INFO | threshold=6.0 | Quad faces whose aspect ratio exceeds *threshold* (tris/ngons skip). |
| `symmetry_x` | INFO | axis=0, threshold=0.001 | A vertex is asymmetric when its mirror key is absent. |
| `symmetry_y` | INFO | axis=1, threshold=0.001 | A vertex is asymmetric when its mirror key is absent. |
| `symmetry_z` | INFO | axis=2, threshold=0.001 | A vertex is asymmetric when its mirror key is absent. |
| `duplicated_names` | BLOCKER | — | Short name used by more than one node in the scene (FBX/AYON killers). |
| `shape_names` | WARNING | — | Shape node must be named '<transform>Shape' (Maya convention). |
| `trailing_numbers` | WARNING | — | Name ends with digits (pCube1-style leftovers). |
| `uncentered_pivots` | INFO | threshold=0.05 | Rotate pivot far from the bbox center (fraction of bbox diagonal). |
| `parent_geometry` | WARNING | — | Mesh parented under another mesh — breaks export hierarchies. |

## Addon checks (Blender) — 42

The full checker set of the Blender addon. Checks marked *core* run
their detection in stukach_core (shared verbatim with the Maya build
via the parity gate in the smoke test).

| Check | Severity | Category | Core | Description |
|---|---|---|---|---|
| `boundary_edges` | INFO | TOPOLOGY |  | Рёбра с ровно одной смежной гранью (открытые края меша). |
| `col_naming` | WARNING | NAMING |  | Коллекции объекта: нейминг через NamingValidator (configurable policy). |
| `duplicate_verts` | BLOCKER | TOPOLOGY | core | Overlapping vertices within 0.1 mm — would merge on Merge by Distance. |
| `duplicated_names` | BLOCKER | NAMING | core | Exact object name used by more than one object in the scene. |
| `face_aspect_ratio` | INFO | TOPOLOGY |  | Quad faces whose aspect ratio exceeds the threshold. |
| `isolated_verts` | WARNING | TOPOLOGY |  | Vertices not connected to any edge — cleanup issue. |
| `lamina` | BLOCKER | TOPOLOGY | core | Lamina faces — zero-thickness geometry folded onto itself. |
| `mat_assignment` | BLOCKER | MATERIALS |  | Каждый слот должен иметь материал; объект не должен быть без слотов. |
| `mat_numbering` | WARNING | NAMING |  | Material names must not contain Blender auto-numbering (.001, .002 ...). |
| `mat_suffix` | WARNING | MATERIALS |  | Material names must end with the configured suffix (default '_mat'). |
| `mesh_data_naming` | WARNING | NAMING |  | Mesh datablock must not keep Blender auto-names ('Mesh.101'). |
| `missing_textures` | BLOCKER | MATERIALS |  | Обнаруживает материалы объекта с отсутствующими текстурными файлами. |
| `missing_uvs` | WARNING | UV |  | Faces without usable UV mapping (Maya unmapped-face analog). |
| `modifier_stack` | WARNING | TRANSFORMS |  | Unapplied modifiers on the object. |
| `ngons` | BLOCKER | TOPOLOGY |  | Faces with more than four vertices (n-gons). |
| `non_applied_transform` | BLOCKER | TRANSFORMS |  | Object carries rotation/scale that should be applied to the mesh. |
| `non_manifold` | BLOCKER | TOPOLOGY | core | Non-manifold edge detector. |
| `obj_naming` | WARNING | NAMING |  | Object names: hygiene rules + the naming contract (stukach_core.naming). |
| `origin_at_zero` | INFO | TRANSFORMS |  | Object origin (pivot point) is not at world zero (0, 0, 0). |
| `parent_geometry` | WARNING | TRANSFORMS | core | Object parented under another MESH object — breaks export hierarchies. |
| `poles` | INFO | TOPOLOGY |  | Pole vertices (3 or 5+ connected edges) on interior geometry. |
| `scale` | BLOCKER | TRANSFORMS |  | Scale != 1.0 по любой оси — bbox-маркер, толстая линия. |
| `sharp_edges_not_hard` | WARNING | TOPOLOGY |  | Sharp edges (dihedral angle >= 30°) that are NOT marked sharp. |
| `starlike` | WARNING | TOPOLOGY | core | Non-starlike faces — polygon outline self-intersects. |
| `symmetry_x` | INFO | SYMMETRY | core | Asymmetric vertices on the X axis — mirror position missing. |
| `symmetry_y` | INFO | SYMMETRY | core | Asymmetric vertices on the Y axis — mirror position missing. |
| `symmetry_z` | INFO | SYMMETRY | core | Asymmetric vertices on the Z axis — mirror position missing. |
| `trailing_numbers` | WARNING | NAMING | core | Object name ends with digits (Cube.001-style leftovers). |
| `triangles` | INFO | TOPOLOGY |  | Triangulated faces — the pipeline expects quads. |
| `uncentered_pivots` | INFO | TRANSFORMS |  | Pivot further than 5% of the bbox diagonal from the bbox center. |
| `unused_data` | WARNING | CLEANUP |  | Detects unused/stale mesh data that is safe to remove. |
| `uv_material_udim` | BLOCKER | UV |  | One UDIM tile must not contain UV shells from different material groups. |
| `uv_micro_shell` | WARNING | UV | core | Detects UV islands whose total UV area is below a minimum threshold. |
| `uv_overlap` | BLOCKER | UV |  | UV-overlap: island filter + 2D grid broad-phase + exact triangle-triangle test. |
| `uv_padding` | INFO | UV |  | UV island padding — cross-object, per-UDIM-tile. |
| `uv_single_set` | WARNING | UV | core | Ровно один UV-сет — не больше и не меньше. |
| `uv_stretch` | WARNING | UV |  | UV stretch: detects faces where UV angles deviate significantly from 3D mesh angles. |
| `uv_texel_density` | INFO | UV |  | Texel density in px/cm using a configurable reference texture size. |
| `uv_udim_bounds` | BLOCKER | UV | core | UV islands crossing UDIM tile boundaries. |
| `z_fighting` | BLOCKER | TOPOLOGY |  | Coplanar face overlap — intra-object (self) and inter-object (other tracked meshes). |
| `zero_area` | BLOCKER | TOPOLOGY |  | Degenerate faces with (near-)zero area — collapsed geometry. |
| `zero_length_edges` | BLOCKER | TOPOLOGY |  | Edges of (near-)zero length — degenerate geometry from merges/booleans. |

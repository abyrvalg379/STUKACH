# -*- coding:utf-8 -*-
import bpy
import bmesh
import gpu
import json as _json
from gpu_extras.batch import batch_for_shader
from .core import CHECK_TYPES


# ── Session log ──────────────────────────────────────────────────────────────
# All addon diagnostics go here (print + in-memory ring + session file), so
# post-mortem debugging does not depend on the console being open. The ring is
# what 'Copy Debug Info' puts on the clipboard.

import time as _time
import os as _os
import platform as _platform
import tempfile as _tempfile
from collections import deque as _deque

LOG_RING: _deque = _deque(maxlen=40)
_LOG_PATH: str = _os.path.join(_tempfile.gettempdir(), "stukach.log")


def alog(msg: str) -> None:
    """Report an addon diagnostic: console + ring buffer + session log file.

    Never raises — logging must not be able to take the addon down."""
    try:
        line = f"[AssetChecker] {_time.strftime('%H:%M:%S')}  {msg}"
        print(line)
        LOG_RING.append(line)
        path = _LOG_PATH
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        if _os.path.getsize(path) > 262_144:   # crude rotation at ~256 KB
            _os.replace(path, path + ".old")
    except Exception:
        pass


def get_debug_info() -> str:
    """One-clipboard diagnostic snapshot: versions, session state, recent log."""
    import bpy
    lines = [
        f"STUKACH v{get_addon_version()}",
        f"Blender {bpy.app.version_string} | {_platform.system()} {_platform.release()} | Python {_platform.python_version()}",
        f"Mode: {bpy.context.object.mode if bpy.context.object else '?'} | Scope: {MeshCheck._scope} | Tracked: {len(MeshCheck.objects)}",
        "Active validator: " + (__import__("getpass").getuser()),
        "Active checks: " + (", ".join(c for c in _AC_CHECK_PROPS
                                        if getattr(bpy.context.window_manager.mesh_check_props, c, False)) or "none"),
        "--- recent log ---",
    ]
    lines.extend(LOG_RING or ["(empty)"])
    lines.append(f"Session log file: {_LOG_PATH}")
    return "\n".join(lines)


def _apply_obj_ignore(checker, obj, name: str) -> None:
    """Set or clear the ``_ignored`` flag on *checker* based on the object's ignore list.

    Always resets the flag first so that un-ignoring a check (removing it from
    the JSON list) is reflected immediately without a separate cleanup pass.

    Hot path: if ``_ac_ignore`` is not set or the check name is not even present
    as a substring, we skip JSON parsing entirely.
    """
    import json as _j
    checker._ignored = False           # always reset so un-ignore works
    raw = obj.get("_ac_ignore", "")
    if not raw or name not in raw:     # fast path — nothing to ignore
        return
    try:
        if name in _j.loads(raw):
            checker._ignored = True
    except Exception:
        pass


class MeshCheckObject:
    MESH_DATAS = ('verts', 'edges', 'faces')

    # A single check slower than this logs a SLOW line (stall diagnostics)
    _SLOW_CHECK_WARN: float = 0.3

    # Checks whose results depend only on UV data, not 3-D topology.
    # update_datas() skips these when topo changed but UV didn't, and vice-versa.
    _UV_CHECKS = frozenset({
        'uv_overlap', 'uv_padding', 'uv_micro_shell', 'uv_texel_density',
        'uv_stretch', 'uv_single_set', 'uv_udim_bounds',
    })

    # Checks whose results depend on the object's world transform (location /
    # rotation / scale), not on mesh topology or UV data.  They re-run whenever
    # the transform key changes, independently of topo/UV flags.
    _TRANSFORM_CHECKS = frozenset({
        'origin_at_zero', 'non_applied_transform', 'scale',
        'uncentered_pivots',
    })

    def __init__(self, obj):
        self._object = obj
        self._bm_object = None
        self._bm_owned = False   # True only for bmesh.new() copies we must free
        self._verts = self._edges = self._faces = self._tris = 0
        self._checks = {name: cls(self) for name, cls in CHECK_TYPES.items()}
        self._mesh_key: tuple = ()   # (n_verts, n_edges, n_faces) — topology dirty flag
        self._uv_key:   tuple = ()   # sampled UV hash — UV-coords dirty flag
        self._transform_key: tuple = ()  # (loc, rot, scale) — transform dirty flag
        self._name_key: tuple = ()   # (obj.name, mesh data name) — rename dirty flag
        self._mat_udim_map: dict = {}
        # Shared KD-tree for SymmetryX / SymmetryY / SymmetryZ (built once per topology change)
        self._sym_kd_key:   tuple = ()
        self._sym_kd_cache  = None   # mathutils.kdtree.KDTree
        self._sym_kd_co           = None   # numpy (n_verts, 3) float32, rebuilt per topology  # mat_name → set of (tile_u, tile_v)
        self._init_object()

    @staticmethod
    def _sample_transform_key(obj) -> tuple:
        """Cheap transform dirty-detector: packs world position + local rot/scale.

        World translation (matrix_world.translation) is used for the location
        component so that moving a parent also triggers re-evaluation of child
        objects (e.g. origin_at_zero on parented meshes).
        Local rotation_euler and scale are kept as-is — their world equivalents
        can be derived from matrix_world but these are sufficient for the
        non_applied_transform / scale checks which only inspect local values.
        """
        loc = obj.matrix_world.translation   # world position of the origin
        rot = obj.rotation_euler
        scl = obj.scale
        return (round(loc.x, 5), round(loc.y, 5), round(loc.z, 5),
                round(rot.x, 5), round(rot.y, 5), round(rot.z, 5),
                round(scl.x, 5), round(scl.y, 5), round(scl.z, 5))

    def _init_object(self):
        bm = self.set_bm_object()
        self._name_key      = (self._object.name, self._object.data.name)
        self._mesh_key      = (len(bm.verts), len(bm.edges), len(bm.faces))
        self._uv_key        = self._sample_uv_key(bm)
        self._transform_key = self._sample_transform_key(self._object)
        self.update_datas(bm)

    @staticmethod
    def _sample_uv_key(bm) -> tuple:
        """Cheap UV dirty-detector: samples UV coords from ~16 faces.

        Returns a tuple that changes whenever UV coordinates change, without
        reading the entire UV array.  False-negative rate is negligible for
        real packing / unwrap operations.
        """
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            return (0,)
        n = len(bm.faces)
        if n == 0:
            return (0,)
        bm.faces.ensure_lookup_table()
        step = max(1, n // 16)
        xsum = 0
        for i in range(0, n, step):
            face = bm.faces[i]
            if face.loops:
                uv = face.loops[0][uv_layer].uv
                xsum ^= hash((round(uv.x, 5), round(uv.y, 5)))
        return (n, uv_layer.name, xsum)

    def _drop_cached_bm(self):
        """Drop the cached bmesh.  Call .free() ONLY on our own bmesh.new()
        copies — an edit-mode wrapper may point at an edit-BMesh Blender has
        already freed (mode toggle / undo); even touching it segfaults in a
        way try/except cannot catch (crash tb3_21692, 2026-09-17)."""
        bm = self._bm_object
        if bm is not None and self._bm_owned:
            try:
                bm.free()
            except Exception:
                pass
        self._bm_object = None
        self._bm_owned = False

    def set_bm_object(self):
        me = self._object.data
        if me.is_editmode:
            # The edit-BMesh is owned by Blender — hand out a transient
            # wrapper for THIS call only.  Never cache it: it dies with the
            # edit session (mode toggle / undo), and a stale wrapper frees
            # freed memory.
            return bmesh.from_edit_mesh(me)
        self._drop_cached_bm()
        bm = bmesh.new()
        bm.from_mesh(me)
        self._bm_object = bm
        self._bm_owned = True
        return bm

    def update_datas(self, bm, *, uv_changed: bool = True, topo_changed: bool = True,
                     transform_changed: bool = True):
        mc = bpy.context.window_manager.mesh_check_props

        if topo_changed:
            for d in self.MESH_DATAS:
                setattr(self, f"_{d}", len(getattr(bm, d)))
            # Faster than bm.calc_loop_triangles() which builds 200k+ Python objects
            import numpy as _np
            _me = self._object.data
            _n_polys = len(_me.polygons)
            if _n_polys > 0:
                _pt = _np.empty(_n_polys, dtype=_np.int32)
                _me.polygons.foreach_get("loop_total", _pt)
                self._tris = int((_pt - 2).sum())
            else:
                self._tris = 0
            del _np, _me, _n_polys

        from .core import (_uv_island_cache, _uv_membership_cache,
                           _edit_uv_cache, build_material_udim_map)
        _uv_island_cache.clear()
        _uv_membership_cache.clear()
        _edit_uv_cache.clear()

        # Always rebuild material→UDIM map so the UV panel stays in sync
        # regardless of which checks are active.
        try:
            self._mat_udim_map = build_material_udim_map(self._object, bm)
        except Exception as e:
            alog(f"[AssetChecker] mat_udim_map error: {e}")
        UVCheckGPU._mat_highlight_dirty = True

        ran_uv_padding = False
        # Stall diagnostics: name the exact check that burns the main thread
        # (a >=5s total block gets the window closed by Windows).
        import time as _time
        from .properties import category_enabled
        for name, checker in self._checks.items():
            if not getattr(mc, name, False) or not category_enabled(name):
                continue
            is_uv        = name in self._UV_CHECKS
            is_transform = name in self._TRANSFORM_CHECKS
            if is_uv and not uv_changed:
                continue
            if is_transform and not transform_changed:
                continue
            if not is_uv and not is_transform and not topo_changed:
                continue
            _t0 = _time.monotonic()
            try:
                checker.set_datas()
                _apply_obj_ignore(checker, self._object, name)
                checker._gpu_dirty = True
                checker._uv_gpu_dirty = True
                if name == 'uv_padding':
                    ran_uv_padding = True
            except Exception as e:
                alog(f"[AssetChecker] Error in {name}: {e}")
            _dt = _time.monotonic() - _t0
            if _dt >= self._SLOW_CHECK_WARN:
                alog(f"[AssetChecker] SLOW check: {name} on {self._object.name} {_dt:.2f}s")

        # Re-run global padding after this object's UV data is refreshed
        if ran_uv_padding:
            try:
                MeshCheck._run_global_uv_padding()
            except Exception as e:
                alog(f"[AssetChecker] Global UV padding (live) error: {e}")

    @property
    def bm_object(self):
        me = self._object.data
        if me.is_editmode:
            # Transient wrapper — see set_bm_object.  A cached one may dangle
            # after a mode toggle or undo.
            return bmesh.from_edit_mesh(me)
        if self._bm_object is None:
            self.set_bm_object()
        return self._bm_object

    @property
    def stats(self):
        return self._verts, self._edges, self._faces, self._tris

    def is_updated_datas(self, bm):
        return any(getattr(self, f"_{d}") != len(getattr(bm, d)) for d in self.MESH_DATAS)


def auto_advance(context):
    """Jump to the next issue after a successful fix (Preferences toggle).

    Only in Object Mode — fixes that leave the user in Edit Mode keep them
    there (the edit flow is the user's, not ours).
    """
    try:
        prefs = bpy.context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        if not prefs.advance_after_fix or context.mode != 'OBJECT':
            return
        bpy.ops.asset_checker.next_issue()
    except Exception:
        pass


class ViewportHUD:
    """Corner HUD in the 3D viewport: validation status line + the focused
    finding (set by Sel / Next Issue), so small defects are identifiable
    without reading the panel.  The finding line auto-fades after a few
    seconds — it must not hang on screen forever."""

    handler = None
    FINDING_TTL = 5.0      # seconds the finding line stays on screen

    @classmethod
    def register(cls):
        if cls.handler is None:
            cls.handler = bpy.types.SpaceView3D.draw_handler_add(
                cls.draw, (), 'WINDOW', 'POST_PIXEL')

    @classmethod
    def unregister(cls):
        if cls.handler is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(cls.handler, 'WINDOW')
            except Exception:
                pass
            cls.handler = None

    @staticmethod
    def _draw_line(text, color, y):
        import blf
        font_id = 0
        blf.size(font_id, 13)
        blf.position(font_id, 14, y, 0)
        blf.color(font_id, *color)
        blf.draw(font_id, text)

    @classmethod
    def draw(cls):
        import blf
        ctx = bpy.context
        try:
            mc = ctx.window_manager.mesh_check_props
        except Exception:
            return
        if not mc.check_data:
            return
        try:
            prefs = ctx.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        except Exception:
            return
        if not prefs.show_viewport_hud:
            return

        from .ui import _compute_asset_summary, _get_asset_status, CHECK_SEVERITY
        from .properties import _CHECK_LABELS, category_enabled, pretty_name

        status = _get_asset_status(mc)
        colors = {
            "ready":    (0.45, 0.80, 0.40, 0.9),
            "warning":  (0.95, 0.78, 0.25, 0.9),
            "critical": (0.95, 0.30, 0.25, 0.9),
            "none":     (0.65, 0.65, 0.65, 0.7),
        }

        # Line 1 — status (only when there is something validated)
        if MeshCheck.objects:
            summary = _compute_asset_summary(mc)
            cls._draw_line(
                f"STUKACH · {status.upper()} · {summary['total_blockers']}B / {summary['total_warnings']}W",
                colors.get(status, colors["none"]), 20)

        # Line 2 — the focused finding (set by Sel / Next Issue): shown for a
        # few seconds with a fade-out, never hanging on screen.
        finding = getattr(MeshCheck, "_hud_finding", None)
        age = _time.monotonic() - getattr(MeshCheck, "_hud_finding_at", 0.0)
        if finding and age < cls.FINDING_TTL:
            obj_name, check_name, count = finding
            if not category_enabled(check_name):
                return
            label = _CHECK_LABELS.get(check_name, pretty_name(check_name))
            sev = CHECK_SEVERITY.get(check_name, "WARNING")
            base = colors.get("critical" if sev == "BLOCKER" else "warning",
                              colors["warning"])
            fade = max(0.0, min(1.0, (cls.FINDING_TTL - age) / 1.5))
            cls._draw_line(
                f"{obj_name} · {label} · {count}",
                (base[0], base[1], base[2], base[3] * fade),
                40)


class MeshCheckGPU:
    _handler = None
    _shader = None
    _batch_cache: dict = {}

    _FACE_OVERLAY_CHECKS = {'zero_area', 'triangles', 'ngons', 'uv_stretch',
                            'uv_material_udim', 'lamina', 'starlike', 'missing_uvs'}
    _THICK_LINE_CHECKS   = {'non_applied_transform', 'scale',
                            'modifier_stack', 'origin_at_zero',
                            'uncentered_pivots'}

    @classmethod
    def get_shader(cls):
        if cls._shader is None:
            cls._shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        return cls._shader

    @classmethod
    def setup_handler(cls):
        if not cls._handler:
            cls._handler = bpy.types.SpaceView3D.draw_handler_add(
                cls.draw, (), 'WINDOW', 'POST_VIEW'
            )

    @classmethod
    def remove_handler(cls):
        if cls._handler:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(cls._handler, 'WINDOW')
            except Exception:
                pass
            finally:
                cls._handler = None
        cls._batch_cache.clear()

    @classmethod
    def _rebuild_checker_batches(cls, checker, check, prefs, offset, pt_offset):
        shader = cls.get_shader()
        entry = {'offset': offset, 'pt_offset': pt_offset}

        # Ignored checks get empty batches — no overlay, no wasted GPU bandwidth.
        if getattr(checker, '_ignored', False):
            entry['edge'] = entry['face'] = entry['point'] = None
            cls._batch_cache[id(checker)] = entry
            checker._gpu_dirty = False
            return

        coords = checker.get_edges(offset)
        entry['edge'] = (
            batch_for_shader(shader, 'LINES', {"pos": coords}) if coords else None
        )

        if check in cls._FACE_OVERLAY_CHECKS:
            faces, face_idx = checker.get_faces(offset)
            entry['face'] = (
                batch_for_shader(shader, 'TRIS', {"pos": faces}, indices=face_idx)
                if (faces and face_idx) else None
            )
        else:
            entry['face'] = None

        pts = checker.get_points(pt_offset)
        entry['point'] = (
            batch_for_shader(shader, 'POINTS', {"pos": pts}) if pts else None
        )

        cls._batch_cache[id(checker)] = entry
        checker._gpu_dirty = False

    @staticmethod
    def remap_color(prefs, check):
        c = getattr(prefs, f"{check}_color", (1.0, 0.0, 0.0))
        return (*c[:3], getattr(prefs, 'edges_alpha', 1.0))

    @classmethod
    def draw(cls):
        ctx = bpy.context
        if not ctx.object:
            return

        mc = ctx.window_manager.mesh_check_props
        addon_name = __name__.rsplit(".", 1)[0]
        try:
            prefs = ctx.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None
        if not prefs or not MeshCheck.objects:
            gpu.state.depth_test_set('NONE')
            return

        # Viewport x-ray makes the walls themselves transparent — occlusion
        # against them is meaningless, overlay stays see-through there.
        xray_vp = bool(ctx.space_data.shading.show_xray)
        # prefs.overlay_xray (default ON): faces/points always visible through
        # walls.  OFF: solid walls occlude marks on far-side geometry.
        xray_marks = xray_vp or getattr(prefs, 'overlay_xray', True)

        offset = prefs.faces_offset
        pt_offset = prefs.points_offset
        shader = cls.get_shader()
        shader.bind()

        try:
            # Self-heal: a dead reference that slipped past the depsgraph purge
            # would log a draw error on every redraw — drop it here instead.
            MeshCheck._purge_dead_objects()
            from .properties import category_enabled
            for check in mc.checker_options:
                if not getattr(mc, check, False) or not category_enabled(check):
                    continue
                for mc_obj in MeshCheck.objects.values():
                    checker = mc_obj._checks.get(check)
                    if not checker:
                        continue
                    try:
                        cid = id(checker)
                        cached = cls._batch_cache.get(cid)

                        if (checker._gpu_dirty or cached is None
                                or cached['offset'] != offset
                                or cached['pt_offset'] != pt_offset):
                            cls._rebuild_checker_batches(checker, check, prefs, offset, pt_offset)
                            cached = cls._batch_cache[cid]

                        color = cls.remap_color(prefs, check)

                        if cached['face']:
                            shader.uniform_float("color", (*color[:3], prefs.faces_alpha))
                            gpu.state.blend_set("ALPHA")
                            gpu.state.face_culling_set('NONE')
                            gpu.state.depth_test_set('NONE' if xray_marks else 'LESS')
                            cached['face'].draw(shader)

                        if cached['edge']:
                            w = 4.0 if check in cls._THICK_LINE_CHECKS else prefs.edges_width
                            shader.uniform_float("color", color)
                            gpu.state.blend_set("ALPHA")
                            gpu.state.line_width_set(w)
                            # Set explicitly per batch: a previous face batch
                            # must not leak its NONE state into edges.
                            if check == 'z_fighting':
                                # Interior duplicates are buried between
                                # coplanar walls — x-ray marks keep them visible.
                                gpu.state.depth_test_set('NONE' if xray_marks else 'LESS')
                            else:
                                gpu.state.depth_test_set('NONE' if xray_vp else 'LESS')
                            cached['edge'].draw(shader)

                        if cached['point']:
                            shader.uniform_float("color", color)
                            gpu.state.point_size_set(prefs.point_size)
                            gpu.state.depth_test_set('NONE' if xray_marks else 'LESS')
                            cached['point'].draw(shader)

                    except Exception as e:
                        alog(f"[AssetChecker] Draw error in {check}: {e}")
        finally:
            # Always restore GPU state so Blender's own rendering is not affected.
            gpu.state.blend_set("NONE")
            gpu.state.depth_test_set('NONE')
            gpu.state.line_width_set(1.0)
            gpu.state.point_size_set(1.0)


class UVCheckGPU:
    """Draw handler для IMAGE_EDITOR — UV-оверлеи оверлапов и микрошеллов."""

    _handler = None
    _shader = None
    _batch_cache: dict = {}
    _UV_OVERLAY_CHECKS = {'uv_overlap', 'uv_micro_shell', 'uv_udim_bounds', 'uv_padding',
                          'uv_stretch', 'uv_material_udim'}

    # Material→UDIM highlight state
    _mat_highlight_batch = None
    _mat_highlight_key   = None   # (mat_name, frozenset of tiles) — rebuild when changed
    _mat_highlight_dirty = False  # set True by update_datas() to force rebuild

    @classmethod
    def get_shader(cls):
        if cls._shader is None:
            cls._shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        return cls._shader

    @classmethod
    def setup_handler(cls):
        if not cls._handler:
            cls._handler = bpy.types.SpaceImageEditor.draw_handler_add(
                cls.draw, (), 'WINDOW', 'POST_VIEW'
            )

    @classmethod
    def remove_handler(cls):
        if cls._handler:
            try:
                bpy.types.SpaceImageEditor.draw_handler_remove(cls._handler, 'WINDOW')
            except Exception:
                pass
            finally:
                cls._handler = None
        cls._batch_cache.clear()
        cls._mat_highlight_batch = None
        cls._mat_highlight_key   = None

    @classmethod
    def _rebuild_checker_uv_batches(cls, checker):
        """Build and cache UV face/edge batches for one checker."""
        if getattr(checker, '_ignored', False):
            cls._batch_cache[id(checker)] = {'face': None, 'edge': None}
            checker._uv_gpu_dirty = False
            return
        shader = cls.get_shader()
        faces, face_idx = checker.get_uv_faces()
        edges = checker.get_uv_edges()
        cls._batch_cache[id(checker)] = {
            'face': (
                batch_for_shader(shader, 'TRIS', {"pos": faces}, indices=face_idx)
                if (faces and face_idx) else None
            ),
            'edge': (
                batch_for_shader(shader, 'LINES', {"pos": edges}) if edges else None
            ),
        }
        checker._uv_gpu_dirty = False

    @classmethod
    def draw(cls):
        ctx = bpy.context
        mc = ctx.window_manager.mesh_check_props
        if not MeshCheck.objects:
            return
        # Self-heal, same as the 3D draw handler: drop dead references before
        # the batches are rebuilt for them.
        MeshCheck._purge_dead_objects()
        if not MeshCheck.objects:
            return

        addon_name = __name__.rsplit(".", 1)[0]
        try:
            prefs = ctx.preferences.addons[addon_name].preferences
        except Exception:
            return

        shader = cls.get_shader()
        shader.bind()
        from .properties import category_enabled

        for check in cls._UV_OVERLAY_CHECKS:
            if not getattr(mc, check, False) or not category_enabled(check):
                continue
            for mc_obj in MeshCheck.objects.values():
                checker = mc_obj._checks.get(check)
                if not checker:
                    continue

                cid = id(checker)
                if cls._batch_cache.get(cid) is None or checker._uv_gpu_dirty:
                    cls._rebuild_checker_uv_batches(checker)
                cached = cls._batch_cache[cid]

                if checker.count == 0:
                    continue

                color = MeshCheckGPU.remap_color(prefs, check)

                if cached['face']:
                    face_color = (*color[:3], prefs.faces_alpha)
                    shader.uniform_float("color", face_color)
                    gpu.state.blend_set("ALPHA")
                    cached['face'].draw(shader)

                if cached['edge']:
                    shader.uniform_float("color", color)
                    gpu.state.blend_set("ALPHA")
                    gpu.state.line_width_set(prefs.edges_width)
                    cached['edge'].draw(shader)

        gpu.state.blend_set("NONE")
        gpu.state.line_width_set(1.0)

        # ── Material→UDIM highlight ──────────────────────────────────────────
        selected_mat = mc.mat_udim_selected if hasattr(mc, 'mat_udim_selected') else ""
        if selected_mat:
            tiles: set = set()
            for mc_obj in MeshCheck.objects.values():
                tiles.update(mc_obj._mat_udim_map.get(selected_mat, set()))

            if tiles:
                new_key = (selected_mat, frozenset(tiles))
                if cls._mat_highlight_key != new_key or cls._mat_highlight_dirty:
                    coords = []
                    for tile_u, tile_v in tiles:
                        x0, y0 = float(tile_u),       float(tile_v)
                        x1, y1 = float(tile_u) + 1.0, float(tile_v) + 1.0
                        # Rectangle outline as 4 line segments (8 points)
                        coords.extend([
                            (x0, y0, 0.0), (x1, y0, 0.0),
                            (x1, y0, 0.0), (x1, y1, 0.0),
                            (x1, y1, 0.0), (x0, y1, 0.0),
                            (x0, y1, 0.0), (x0, y0, 0.0),
                        ])
                    cls._mat_highlight_batch = batch_for_shader(
                        shader, 'LINES', {"pos": coords})
                    cls._mat_highlight_key   = new_key
                    cls._mat_highlight_dirty = False

                if cls._mat_highlight_batch:
                    shader.uniform_float("color", (1.0, 0.6, 0.0, 1.0))  # orange
                    gpu.state.blend_set("ALPHA")
                    gpu.state.line_width_set(3.0)
                    cls._mat_highlight_batch.draw(shader)
                    gpu.state.line_width_set(1.0)
                    gpu.state.blend_set("NONE")


class MeshCheck:
    _mode = ""
    _scope: str = "SELECTED"          # "SELECTED" | "SCENE" | "COLLECTION"
    _scope_collection: str = ""       # collection name when scope == "COLLECTION"
    objects = {}
    hierarchy_result = None            # HierarchyResult | None — set by scan_hierarchy operator
    _hier_collapsed_roots: set = set() # root names collapsed in the per-asset section view
    _hier_expanded_rules: set = set()  # rule groups expanded in the Issues-only view
    _state_restored: bool = False      # True after load_post restores settings; cleared on Run
    _scene_stale:   bool = False       # True when SCENE/COLLECTION has untracked objects
    _last_live_populate: float = 0.0   # monotonic timestamp — throttle for Live auto-add
    _next_issue_ptr: int = 0           # cycling pointer for the Next Issue operator

    @staticmethod
    def poll():
        mc = bpy.context.window_manager.mesh_check_props
        return mc.check_data and any(getattr(mc, p, False) for p in mc.checker_options)

    @classmethod
    def reset_mesh_check(cls):
        cls._mode = ""
        cls.objects.clear()
        cls._live_dirty.clear()
        cls._live_repopulate = False
        cls._inter_zf_pending = False
        cls._validation_queue.clear()
        cls._next_issue_ptr = 0
        MeshCheckGPU._batch_cache.clear()
        UVCheckGPU._batch_cache.clear()
        from .core import (_uv_island_cache, _uv_membership_cache,
                           _edit_uv_cache,
                           _uv_padding_registry, _uv_padding_tile_stats)
        _uv_island_cache.clear()
        _uv_membership_cache.clear()
        _edit_uv_cache.clear()
        _uv_padding_registry.clear()
        _uv_padding_tile_stats.clear()

    @classmethod
    def add_scene_objects(cls, wm=None):
        """Track every mesh object in the active scene.

        *wm* — optional WindowManager for progress reporting.
        When provided, calls wm.progress_begin / progress_update / progress_end
        so Blender shows OS-level progress (title-bar + taskbar) during heavy scans.
        """
        mesh_objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
        total = len(mesh_objs)
        if wm is not None and total:
            wm.progress_begin(0, total)
        for i, obj in enumerate(mesh_objs):
            if obj not in cls.objects:
                try:
                    cls.objects[obj] = MeshCheckObject(obj)
                except Exception as e:
                    alog(f"[AssetChecker] Error adding {obj.name}: {e}")
            if wm is not None:
                wm.progress_update(i + 1)
        if wm is not None and total:
            wm.progress_end()
        try:
            cls._run_inter_object_z_fighting()
        except Exception as e:
            alog(f"[AssetChecker] Inter-object Z-fighting error: {e}")
        try:
            cls._run_global_uv_padding()
        except Exception as e:
            alog(f"[AssetChecker] Global UV padding error: {e}")

    @classmethod
    def add_collection_objects_from(cls, col, wm=None):
        """Track every mesh object in *col* (includes sub-collections via all_objects).

        *wm* — optional WindowManager for progress reporting.
        """
        mesh_objs = [o for o in col.all_objects if o.type == "MESH"]
        total = len(mesh_objs)
        if wm is not None and total:
            wm.progress_begin(0, total)
        for i, obj in enumerate(mesh_objs):
            if obj not in cls.objects:
                try:
                    cls.objects[obj] = MeshCheckObject(obj)
                except Exception as e:
                    alog(f"[AssetChecker] Error adding {obj.name}: {e}")
            if wm is not None:
                wm.progress_update(i + 1)
        if wm is not None and total:
            wm.progress_end()
        try:
            cls._run_inter_object_z_fighting()
        except Exception as e:
            alog(f"[AssetChecker] Inter-object Z-fighting error: {e}")
        try:
            cls._run_global_uv_padding()
        except Exception as e:
            alog(f"[AssetChecker] Global UV padding error: {e}")

    @classmethod
    def set_mode(cls, s):
        cls._mode = s

    @classmethod
    def add_mesh_check_object(cls):
        for o in bpy.context.selected_objects:
            if o.type == "MESH" and o not in cls.objects:
                cls.objects[o] = MeshCheckObject(o)
        # Re-run inter-object Z-fighting when tracked set changes
        try:
            cls._run_inter_object_z_fighting()
        except Exception as e:
            alog(f"[AssetChecker] Inter-object Z-fighting error: {e}")

    @classmethod
    def remove_mesh_check_object(cls, o):
        if o in cls.objects:
            mc_obj = cls.objects[o]
            cls._live_dirty.discard(mc_obj)
            mc_obj._drop_cached_bm()
            for checker in mc_obj._checks.values():
                MeshCheckGPU._batch_cache.pop(id(checker), None)
                UVCheckGPU._batch_cache.pop(id(checker), None)
            del cls.objects[o]
            # Its old overlap partners may now be clean — inter Z-fighting
            # needs a re-run once the live queue drains.
            cls._inter_zf_pending = True

    @classmethod
    def _purge_dead_objects(cls):
        """Drop tracked objects deleted from the scene (dead RNA references).

        Safe to call from any entry point (depsgraph callback, draw handler) —
        every consumer of MeshCheck.objects would otherwise trip over the dead
        reference one by one.
        """
        for o in list(cls.objects.keys()):
            try:
                o.name
            except ReferenceError:
                cls.remove_mesh_check_object(o)

    @classmethod
    def reset_mc_objects(cls):
        for mc_obj in cls.objects.values():
            mc_obj._drop_cached_bm()
        cls.objects.clear()
        cls._live_dirty.clear()
        cls._live_repopulate = False
        cls._validation_queue.clear()
        MeshCheckGPU._batch_cache.clear()
        UVCheckGPU._batch_cache.clear()
        cls._repopulate_by_scope()

    @classmethod
    def _purge_stale_callbacks(cls):
        """Remove ALL asset_checker depsgraph handlers — including ones left over
        from previous addon reloads that were never properly unregistered.
        They share the same __qualname__ but are different function objects.
        """
        handlers = bpy.app.handlers.depsgraph_update_post
        stale = [
            h for h in handlers
            if getattr(h, '__qualname__', '') == cls.callback.__qualname__
        ]
        for h in stale:
            try:
                handlers.remove(h)
            except Exception:
                pass

    @classmethod
    def add_callback(cls):
        # Purge any stale callbacks from previous reloads before adding ours.
        cls._purge_stale_callbacks()
        cls._repopulate_by_scope()
        bpy.app.handlers.depsgraph_update_post.append(cls.callback)

    @classmethod
    def _repopulate_by_scope(cls):
        """Re-add objects according to the current validation scope."""
        if cls._scope == "SCENE":
            cls.add_scene_objects()
        elif cls._scope == "COLLECTION" and cls._scope_collection:
            col = bpy.data.collections.get(cls._scope_collection)
            if col:
                cls.add_collection_objects_from(col)
            else:
                cls.add_mesh_check_object()
        else:
            cls.add_mesh_check_object()

    @classmethod
    def remove_callback(cls):
        cls._purge_stale_callbacks()
        cls.reset_mesh_check()

    # Guard for inter-object Z-fighting: skip if total faces exceed this limit
    _INTER_Z_FIGHT_MAX_TOTAL_FACES: int = 500_000

    @classmethod
    def _run_inter_object_z_fighting(cls):
        """Detect Z-fighting between pairs of tracked objects (world space).

        Builds a world-space BVHTree for every tracked mesh, then tests all
        O(n²) pairs.  Only coplanar face pairs (normal dot > 0.99) are flagged.
        Results are injected into each object's ZFighting checker via
        checker.add_inter_results().
        """
        mc = bpy.context.window_manager.mesh_check_props
        if not getattr(mc, 'z_fighting', False):
            return

        from mathutils.bvhtree import BVHTree

        pairs = []
        for obj, mc_obj in cls.objects.items():
            if mc_obj._checks.get('z_fighting') is None:
                continue
            try:
                _ = obj.name   # ReferenceError if the object was deleted
            except ReferenceError:
                continue
            pairs.append((obj, mc_obj))
        if len(pairs) < 2:
            return

        # Performance guard
        total_faces = sum(len(mc_obj.bm_object.faces) for _, mc_obj in pairs)
        if total_faces > cls._INTER_Z_FIGHT_MAX_TOTAL_FACES:
            return

        # Build world-space BVH for each object
        def _world_bvh(mc_obj):
            bm  = mc_obj.bm_object
            mw  = mc_obj._object.matrix_world
            if not bm.faces:
                return None
            bm.faces.ensure_lookup_table()
            bm.verts.ensure_lookup_table()
            verts_ws       = [mw @ v.co for v in bm.verts]
            face_vert_idx  = [[v.index for v in f.verts] for f in bm.faces]
            try:
                return BVHTree.FromPolygons(verts_ws, face_vert_idx, epsilon=0.0001)
            except Exception:
                return None

        bvh_list = [(obj, mc_obj, _world_bvh(mc_obj)) for obj, mc_obj in pairs]
        eps_normal = 0.99

        for i in range(len(bvh_list)):
            obj_a, mc_a, bvh_a = bvh_list[i]
            if bvh_a is None:
                continue
            checker_a = mc_a._checks['z_fighting']
            bm_a  = mc_a.bm_object
            rot_a = obj_a.matrix_world.to_3x3().normalized()

            for j in range(i + 1, len(bvh_list)):
                obj_b, mc_b, bvh_b = bvh_list[j]
                if bvh_b is None:
                    continue
                checker_b = mc_b._checks['z_fighting']
                bm_b  = mc_b.bm_object
                rot_b = obj_b.matrix_world.to_3x3().normalized()

                try:
                    overlapping = bvh_a.overlap(bvh_b)
                except Exception:
                    continue

                # Same three-stage filter used for intra-object detection:
                # 1. Same winding only (signed dot, not abs) — removes
                #    inner/outer shell pairs and faces at a geometry-
                #    intersection interface pointing in opposite directions.
                # 2. Centroid ≤ 1 mm world-space — removes geometry that
                #    physically passes through another object (the face
                #    centroids are far apart even though BVH volumes overlap).
                sl        = bpy.context.scene.unit_settings.scale_length or 1.0
                threshold = 0.0001 / sl     # 0.1 mm — same gate as intra-object

                mw_a = obj_a.matrix_world
                mw_b = obj_b.matrix_world

                inter_a: set = set()
                inter_b: set = set()
                for idx_a, idx_b in overlapping:
                    n_a = (rot_a @ bm_a.faces[idx_a].normal).normalized()
                    n_b = (rot_b @ bm_b.faces[idx_b].normal).normalized()
                    # Stage 1 — same winding
                    if n_a.dot(n_b) <= eps_normal:
                        continue
                    # Stage 2 — centroids within 1 mm (world space)
                    ca = mw_a @ bm_a.faces[idx_a].calc_center_median()
                    cb = mw_b @ bm_b.faces[idx_b].calc_center_median()
                    if (ca - cb).length > threshold:
                        continue
                    inter_a.add(idx_a)
                    inter_b.add(idx_b)

                if inter_a:
                    checker_a.add_inter_results(inter_a, obj_b.name)
                if inter_b:
                    checker_b.add_inter_results(inter_b, obj_a.name)

    @classmethod
    def _run_global_uv_padding(cls) -> None:
        """Cross-object UV padding check — Phase 2.

        Called after all per-object uv_padding set_datas() calls complete.
        Reads prefs, then delegates to core.run_global_uv_padding().
        """
        try:
            mc = bpy.context.window_manager.mesh_check_props
        except Exception:
            return
        if not getattr(mc, 'uv_padding', False):
            return
        from .core import run_global_uv_padding, UVPaddingCheck
        addon_name = __name__.rsplit(".", 1)[0]
        try:
            prefs    = bpy.context.preferences.addons[addon_name].preferences
            tex_size = UVPaddingCheck._PAD_TEX_SIZES.get(
                getattr(prefs, 'uv_padding_texture_size', '3'), 4096)
            shell_px = prefs.uv_padding_shell_px
            tile_px  = prefs.uv_padding_tile_px
        except Exception:
            tex_size, shell_px, tile_px = 4096, 16, 8
        run_global_uv_padding(tex_size=tex_size, shell_px=shell_px, tile_px=tile_px)

    @classmethod
    def update_mc_object_datas(cls, name):
        from .properties import category_enabled
        if not category_enabled(name):
            return
        for mc_obj in cls.objects.values():
            checker = mc_obj._checks.get(name)
            if checker:
                try:
                    me = mc_obj._object.data
                except ReferenceError:
                    cls.remove_mesh_check_object(mc_obj._object)
                    continue
                try:
                    # The mesh may have been edited by a fix operator since the
                    # cached bmesh was built — refresh it, or set_datas() would
                    # recompute on stale geometry and keep the old count.
                    new_key = (len(me.vertices), len(me.edges), len(me.polygons))
                    if new_key != mc_obj._mesh_key:
                        mc_obj._mesh_key = new_key
                        bm = mc_obj.set_bm_object()
                        mc_obj._uv_key = MeshCheckObject._sample_uv_key(bm)
                    checker.set_datas()
                    _apply_obj_ignore(checker, mc_obj._object, name)
                    checker._gpu_dirty = True
                    checker._uv_gpu_dirty = True
                except Exception as e:
                    alog(f"[AssetChecker] Update error in {name}: {e}")

        # Inter-object Z-fighting (runs after all intra checks complete)
        if name == "z_fighting":
            try:
                cls._run_inter_object_z_fighting()
            except Exception as e:
                alog(f"[AssetChecker] Inter-object Z-fighting error: {e}")

        # Cross-object UV padding (runs after all per-object set_datas complete)
        if name == "uv_padding":
            try:
                cls._run_global_uv_padding()
            except Exception as e:
                alog(f"[AssetChecker] Global UV padding error: {e}")

        # Sync the outliner quarantine collection after naming check
        if name == "obj_naming":
            try:
                from .naming import NamingMarker
                mc = bpy.context.window_manager.mesh_check_props
                if getattr(mc, "obj_naming", False):
                    problem_objs = [
                        obj for obj, mc_obj in cls.objects.items()
                        if mc_obj._checks.get("obj_naming")
                        and mc_obj._checks["obj_naming"].count > 0
                    ]
                    NamingMarker.update(problem_objs)
            except Exception as e:
                alog(f"[AssetChecker] NamingMarker update error: {e}")

    @staticmethod
    def callback(scene):
        ctx = bpy.context
        if not ctx.object:
            ctx.window_manager.mesh_check_props.check_data = False
            # Deleting the active object leaves no context object — purging
            # here too, or dead references survive until the next event and
            # the overlay / inter-object Z-fighting spam errors on redraw.
            if MeshCheck._mode == "OBJECT":
                MeshCheck._purge_dead_objects()
            return
        mc = ctx.window_manager.mesh_check_props
        m = ctx.object.mode
        if m != MeshCheck._mode:
            MeshCheck.set_mode(m)
            MeshCheck.reset_mc_objects()
        if m == "OBJECT":
            if MeshCheck._scope == "SELECTED":
                # Track only selected objects; auto-remove when deselected
                if any(o.type == "MESH" and o not in MeshCheck.objects
                       for o in ctx.selected_objects):
                    MeshCheck.add_mesh_check_object()
                for o in list(MeshCheck.objects.keys()):
                    try:
                        if not o.select_get():
                            MeshCheck.remove_mesh_check_object(o)
                    except ReferenceError:
                        MeshCheck.remove_mesh_check_object(o)
            else:
                # SCENE / COLLECTION: keep all tracked objects; only purge deleted ones
                for o in list(MeshCheck.objects.keys()):
                    try:
                        o.select_get()  # raises ReferenceError if the object was deleted
                    except ReferenceError:
                        MeshCheck.remove_mesh_check_object(o)

                # Stale detection: compare expected mesh count vs currently tracked
                # (skipped while progressive validation is still filling the list)
                try:
                    if not MeshCheck._validation_queue:
                        if MeshCheck._scope == "SCENE":
                            expected = sum(1 for o in ctx.scene.objects
                                           if o.type == "MESH")
                        else:
                            col = bpy.data.collections.get(MeshCheck._scope_collection)
                            expected = sum(1 for o in col.all_objects
                                           if o.type == "MESH") if col else 0
                        if expected != len(MeshCheck.objects):
                            if getattr(mc, 'live_update', False):
                                # Live: auto-track new objects.  The heavy part
                                # (MeshCheckObject init runs every enabled check)
                                # is deferred to the timer.
                                MeshCheck._live_repopulate = True
                                MeshCheck._schedule_live_flush()
                            else:
                                MeshCheck._scene_stale = True
                        else:
                            MeshCheck._scene_stale = False
                except Exception:
                    pass

            # Live: mesh edits in OBJECT mode (applied transforms/modifiers,
            # join, delete, booleans…).  Only flag changed objects here —
            # the bmesh rebuild + re-check run in the deferred timer.
            if getattr(mc, 'live_update', False):
                for o, mc_obj in MeshCheck.objects.items():
                    try:
                        me = o.data
                        if (len(me.vertices), len(me.edges), len(me.polygons)) != mc_obj._mesh_key:
                            MeshCheck._live_dirty.add(mc_obj)
                        elif (o.name, me.name) != mc_obj._name_key:
                            # Renames are cheap to detect but drive the naming
                            # checks — re-check via the deferred flush.
                            MeshCheck._live_dirty.add(mc_obj)
                    except ReferenceError:
                        continue
                if MeshCheck._live_dirty:
                    # Overlap sets changed (new/edited geometry) — refresh
                    # inter-object Z-fighting after the per-object queue drains.
                    MeshCheck._inter_zf_pending = True
                    MeshCheck._schedule_live_flush()

            # Transform dirty check — cheap matrix reads, safe to run inline.
            # Re-run origin/rotation/scale checks when the object's
            # location/rotation/scale changes without topology change.
            # Guarded by Live: with Live off results stay as of the last RUN
            # (the panel shows the "Scene changed" hint instead).
            if getattr(mc, 'live_update', False):
                for o, mc_obj in MeshCheck.objects.items():
                    try:
                        new_tk = MeshCheckObject._sample_transform_key(o)
                        if new_tk != mc_obj._transform_key:
                            mc_obj._transform_key = new_tk
                            # A moved object changes every overlap it
                            # participates in — inter Z-fighting is stale now.
                            MeshCheck._inter_zf_pending = True
                            mc_obj.update_datas(
                                mc_obj.bm_object,
                                uv_changed=False,
                                topo_changed=False,
                                transform_changed=True,
                            )
                    except Exception as e:
                        alog(f"[AssetChecker] transform dirty check {o.name}: {e}")
                # The transform path runs inline — nothing else schedules the
                # deferred flush that drains the pending inter-Z-fighting pass.
                if MeshCheck._inter_zf_pending:
                    MeshCheck._schedule_live_flush()

        elif m == "EDIT" and MeshCheck.poll() and getattr(mc, 'live_update', False):
            # Only flag objects with geometry updates — the heavy BMesh work
            # runs in the deferred timer (_live_flush).  Building/reading
            # edit-BMeshes and re-running checks inside the depsgraph callback
            # crashed Blender (mid-undo / mid-operator access).
            deps = ctx.evaluated_depsgraph_get()
            for o, mc_obj in MeshCheck.objects.items():
                # Updates for one object arrive in arbitrary order and may be
                # selection/transform-only.  Scan ALL of them for a geometry
                # update — stopping at the first non-geometry entry silently
                # skipped the live refresh for some edit ops (n-gon dissolves
                # stayed stale while tris-to-quads refreshed).
                geo = False
                try:
                    for u in deps.updates:
                        oid = u.id.original
                        if oid == o or oid == o.data:
                            geo = geo or u.is_updated_geometry
                except ReferenceError:
                    # Object deleted from the outliner while in edit mode
                    MeshCheck.remove_mesh_check_object(o)
                    continue
                if geo:
                    MeshCheck._live_dirty.add(mc_obj)
            if MeshCheck._live_dirty:
                MeshCheck._inter_zf_pending = True
                MeshCheck._schedule_live_flush()

    # ── Deferred live refresh ─────────────────────────────────────────────────
    # bpy.app.timers runs at safe points of the main loop: outside depsgraph
    # evaluation, outside operators and undo — heavy mesh work is crash-free
    # there, while the depsgraph handler only collects what changed.

    _live_flush_pending: bool = False
    _live_dirty: set = set()      # MeshCheckObject refs needing re-check
    _live_repopulate: bool = False
    # Inter-object Z-fighting overlap sets are stale (move/edit/delete) —
    # re-run once the live queue drains.
    _inter_zf_pending: bool = False

    @classmethod
    def _schedule_live_flush(cls):
        if not cls._live_flush_pending:
            cls._live_flush_pending = True
            try:
                bpy.app.timers.register(cls._live_flush, first_interval=0.05)
            except Exception:
                # Already registered (race) or timers unavailable — the pending
                # flag may now be out of sync; reset it, next event re-schedules.
                cls._live_flush_pending = False

    # Max objects re-checked per timer tick — keeps the UI responsive when a
    # single action touches many tracked objects (e.g. join of a large scene).
    _LIVE_FLUSH_BATCH: int = 8

    # Stall diagnostics: an object pass / whole batch slower than these logs a
    # SLOW line.  Windows closes the window after >=5s without message pump —
    # these thresholds flag the burners long before that.
    _SLOW_PASS_WARN: float = 0.5
    _SLOW_BATCH_WARN: float = 1.0

    _status_clear_at = None

    @classmethod
    def _status_clear(cls):
        """Clear the completion status-bar text a few seconds after RUN."""
        if cls._status_clear_at is not None and _time.monotonic() >= cls._status_clear_at - 0.4:
            try:
                bpy.context.workspace.status_text_set(None)
            except Exception:
                pass
            cls._status_clear_at = None
        return None

    # ── Progressive validation (Scene / Collection scope) ─────────────────────
    # Scene-wide RUN used to build every MeshCheckObject synchronously — the
    # UI froze for the whole pass.  Instead the objects are queued and built
    # in small timer batches; counters fill in as the queue drains.
    _validation_queue: list = []

    @classmethod
    def start_progressive_validation(cls, objects):
        cls.objects.clear()
        cls._live_dirty.clear()
        MeshCheckGPU._batch_cache.clear()
        UVCheckGPU._batch_cache.clear()
        cls._validation_queue = [o for o in objects if o not in cls.objects]
        if cls._validation_queue:
            cls._schedule_validation_flush()

    _validation_flush_pending: bool = False

    @classmethod
    def _schedule_validation_flush(cls):
        if not cls._validation_flush_pending:
            cls._validation_flush_pending = True
            try:
                bpy.app.timers.register(cls._validation_flush, first_interval=0.05)
            except Exception:
                cls._validation_flush_pending = False

    @classmethod
    def _validation_flush(cls):
        cls._validation_flush_pending = False
        # Same modal-operator hazard as _live_flush: MeshCheckObject init
        # reads the live edit-BMesh.
        try:
            win = bpy.context.window
            if win is not None and win.modal_operators:
                cls._validation_flush_pending = True
                return 0.1
        except Exception:
            pass
        try:
            mc = getattr(bpy.context.window_manager, 'mesh_check_props', None)
            batch = 6
            while cls._validation_queue and batch > 0:
                o = cls._validation_queue.pop(0)
                try:
                    o.name    # ReferenceError if deleted while queued
                except ReferenceError:
                    continue
                cls.objects[o] = MeshCheckObject(o)
                batch -= 1
                # Progress for the panel slider
                if mc is not None:
                    total = len(cls.objects) + len(cls._validation_queue)
                    if total:
                        mc.validation_progress = len(cls.objects) / total
            if cls._validation_queue:
                cls._schedule_validation_flush()
            else:
                cls._scene_stale = False
                if mc is not None:
                    mc.validation_progress = 1.0
                # Completion report in the status bar, auto-clears after ~4s
                try:
                    from .properties import category_enabled
                    issues = 0
                    for o_ in cls.objects.values():
                        for name_, chk_ in o_._checks.items():
                            if getattr(mc, name_, False) and category_enabled(name_):
                                issues += chk_.count
                    text = (f"STUKACH: {issues} issues in {len(cls.objects)} objects")
                    bpy.context.workspace.status_text_set(text)
                    cls._status_clear_at = _time.monotonic() + 4.0
                    if not bpy.app.timers.is_registered(cls._status_clear):
                        bpy.app.timers.register(cls._status_clear, first_interval=4.5)
                except Exception as e:
                    alog(f"[AssetChecker] status report: {e}")
        except Exception as e:
            alog(f"[AssetChecker] validation flush error: {e}")
        return None

    @classmethod
    def _live_flush(cls):
        cls._live_flush_pending = False
        # A modal operator mid-run (e.g. vert_slide with Auto Merge) leaves the
        # live edit-BMesh and its CustomData layers in flux — touching them
        # from this timer segfaults inside BM_data_layer_add (2026-09-26).
        # Wait the operator out; the pending flag stays set so nothing
        # double-schedules the flush while we wait.
        try:
            win = bpy.context.window
            if win is not None and win.modal_operators:
                cls._live_flush_pending = True
                return 0.1
        except Exception:
            pass
        try:
            mc = getattr(bpy.context.window_manager, 'mesh_check_props', None)
            if mc is None or not mc.check_data:
                cls._live_dirty.clear()
                cls._live_repopulate = False
                return None

            if cls._live_repopulate:
                cls._live_repopulate = False
                import time as _time
                now = _time.monotonic()
                if now - cls._last_live_populate > 1.0:
                    cls._last_live_populate = now
                    try:
                        cls._repopulate_by_scope()
                        cls._scene_stale = False
                    except Exception as e:
                        alog(f"[AssetChecker] live repopulate: {e}")
                else:
                    cls._live_repopulate = True      # still throttled — retry
                    cls._scene_stale = True
                    cls._schedule_live_flush()

            processed = 0
            import time as _time
            _batch_t0 = _time.monotonic()
            for mc_obj in list(cls._live_dirty):
                if processed >= cls._LIVE_FLUSH_BATCH:
                    break
                cls._live_dirty.discard(mc_obj)
                processed += 1
                try:
                    o = mc_obj._object
                    o.name    # ReferenceError if the object was deleted
                except ReferenceError:
                    continue
                _t0 = _time.monotonic()
                try:
                    bm = mc_obj.set_bm_object()      # fresh from mesh / edit-mesh
                    mc_obj._mesh_key = (len(bm.verts), len(bm.edges), len(bm.faces))
                    mc_obj._uv_key = MeshCheckObject._sample_uv_key(bm)
                    mc_obj._name_key = (o.name, o.data.name)
                    mc_obj.update_datas(bm)
                except ReferenceError:
                    continue
                except Exception as e:
                    name = getattr(mc_obj._object, 'name', '?')
                    alog(f"[AssetChecker] live flush {name}: {e}")
                _dt = _time.monotonic() - _t0
                if _dt >= cls._SLOW_PASS_WARN:
                    alog(f"[AssetChecker] SLOW live pass: "
                         f"{getattr(mc_obj._object, 'name', '?')} {_dt:.2f}s")

            _batch_dt = _time.monotonic() - _batch_t0
            if _batch_dt >= cls._SLOW_BATCH_WARN and processed:
                alog(f"[AssetChecker] SLOW live flush: {processed} object(s) "
                     f"{_batch_dt:.2f}s")

            # More left in the queue — keep the loop going on the next tick.
            if cls._live_dirty:
                cls._schedule_live_flush()
            else:
                # Inter-object Z-fighting: transforms/edits/deletes invalidated
                # the old overlap sets — refresh them once the per-object
                # queue has drained (this debounces continuous drags too).
                if cls._inter_zf_pending:
                    cls._inter_zf_pending = False
                    if getattr(mc, 'z_fighting', False):
                        for mc_obj in cls.objects.values():
                            checker = mc_obj._checks.get('z_fighting')
                            if checker:
                                checker.clear_inter_results()
                        try:
                            cls._run_inter_object_z_fighting()
                        except Exception as e:
                            alog(f"[AssetChecker] live inter Z-fighting: {e}")
                # Hierarchy auto-acceptance: while Live is on and a scan exists,
                # re-scan as soon as the scene fingerprint changes — keeps the
                # hierarchy report fresh after FBX imports, renames, reparents.
                try:
                    cls._rescan_hierarchy_if_stale(mc)
                except Exception as e:
                    alog(f"[AssetChecker] hierarchy auto-scan: {e}")
        except Exception as e:
            alog(f"[AssetChecker] live flush error: {e}")
        return None

    @classmethod
    def _rescan_hierarchy_if_stale(cls, mc) -> bool:
        """Re-run the hierarchy scan in Live mode when the scene changed.

        Cheap (O(N) name/type/parent tuples, no mesh access) and only fires
        when a previous scan exists and live_update is enabled.  Returns True
        when a re-scan happened.
        """
        if not getattr(mc, 'live_update', False):
            return False
        result = cls.hierarchy_result
        if result is None:
            return False
        from .naming import HierarchyValidator
        if not HierarchyValidator.is_stale(result):
            return False

        addon_name = __name__.rsplit(".", 1)[0]
        try:
            prefs = bpy.context.preferences.addons[addon_name].preferences
        except Exception:
            prefs = None
        cls.hierarchy_result = HierarchyValidator.scan_scene(prefs=prefs)
        return True


# ── Session state persistence ─────────────────────────────────────────────────
# Check-enable flags + scope are serialised to scene["_ac_state"] on every save
# and restored on load_post.  Validation *results* are never persisted — the user
# just presses Run again; the check selection is already pre-filled.

_AC_STATE_KEY = "_ac_state"

_ADDON_VERSION_CACHE = None


def get_addon_version() -> str:
    """Extension version from blender_manifest.toml (cached, no bl_info)."""
    global _ADDON_VERSION_CACHE
    if _ADDON_VERSION_CACHE is None:
        try:
            import tomllib
            from pathlib import Path
            manifest = Path(__file__).parent / "blender_manifest.toml"
            with open(manifest, "rb") as fh:
                _ADDON_VERSION_CACHE = tomllib.load(fh).get("version", "?")
        except Exception:
            _ADDON_VERSION_CACHE = "?"
    return _ADDON_VERSION_CACHE

# BoolProperty / StringProperty identifiers to include in the snapshot
_AC_CHECK_PROPS: frozenset = frozenset({
    'non_manifold', 'boundary_edges', 'isolated_verts', 'triangles', 'ngons',
    'poles', 'zero_area', 'z_fighting',
    'duplicate_verts', 'face_aspect_ratio',
    'non_applied_transform', 'scale', 'origin_at_zero', 'modifier_stack',
    'symmetry_x', 'symmetry_y', 'symmetry_z',
    'uv_single_set', 'uv_overlap', 'uv_micro_shell', 'uv_texel_density',
    'uv_stretch', 'uv_padding', 'uv_udim_bounds', 'uv_material_udim',
    'obj_naming', 'col_naming', 'mesh_data_naming', 'mat_numbering',
    'mat_suffix', 'mat_assignment', 'missing_textures',
    'unused_data',
    'lamina', 'zero_length_edges', 'sharp_edges_not_hard', 'starlike',
    'missing_uvs', 'duplicated_names', 'trailing_numbers',
    'uncentered_pivots', 'parent_geometry',
})
_AC_UI_PROPS: frozenset = frozenset({
    'cat_topology_open', 'cat_transforms_open', 'cat_symmetry_open',
    'cat_uv_open', 'cat_naming_open', 'cat_materials_open',
    'cat_cleanup_open',
    'obj_list_open', 'uv_td_scope_active',
    'hierarchy_block_open', 'live_update',
    'obj_required_prefix', 'obj_required_suffix',
    'col_required_prefix', 'col_required_suffix',
    'mesh_required_suffix',
})
_AC_ALL_PROPS: frozenset = _AC_CHECK_PROPS | _AC_UI_PROPS


@bpy.app.handlers.persistent
def _ac_save_pre(*args):
    """Serialize check-enable flags + scope to scene["_ac_state"] before save."""
    try:
        scene = getattr(bpy.context, 'scene', None)
        if scene is None:
            return
        wm = getattr(bpy.context, 'window_manager', None)
        if wm is None or not hasattr(wm, 'mesh_check_props'):
            return
        mc = wm.mesh_check_props

        state: dict = {}
        for key in _AC_ALL_PROPS:
            try:
                state[key] = getattr(mc, key)
            except Exception:
                pass

        # Scope is intentionally NOT persisted — it always resets to SELECTED on Run.
        scene[_AC_STATE_KEY] = _json.dumps(state, ensure_ascii=False)
    except Exception as e:
        alog(f"[AssetChecker] save_pre error: {e}")


@bpy.app.handlers.persistent
def _ac_load_post(*args):
    """Restore check-enable flags + scope from scene["_ac_state"] after load."""
    apply_startup_mode()
    try:
        scene = getattr(bpy.context, 'scene', None)
        if scene is None:
            return
        raw = scene.get(_AC_STATE_KEY)
        if not raw:
            return

        state = _json.loads(raw)

        wm = getattr(bpy.context, 'window_manager', None)
        if wm is None or not hasattr(wm, 'mesh_check_props'):
            return
        mc = wm.mesh_check_props

        restored = 0
        for key, val in state.items():
            if key.startswith('__') or key not in _AC_ALL_PROPS:
                continue
            try:
                setattr(mc, key, val)
                restored += 1
            except Exception:
                pass

        MeshCheck._state_restored = True
        apply_startup_mode()   # the startup pref wins over the saved mode
        alog(f"[AssetChecker] Settings restored from '{scene.name}' ({restored} props).")
    except Exception as e:
        alog(f"[AssetChecker] load_post error: {e}")


def apply_startup_mode() -> None:
    """Force the 'Start in Coordinator Mode' preference onto live session
    state. Runs at register and on every file load — a curator workstation
    opens in Coordinator Mode regardless of what the file had saved."""
    try:
        from .properties import _get_addon_prefs   # local: avoid import cycle
        prefs = _get_addon_prefs(bpy.context)
        if prefs is None:
            return
        wm = getattr(bpy.context, "window_manager", None)
        if wm is None or not hasattr(wm, "mesh_check_props"):
            return
        wm.mesh_check_props.coordinator_mode = bool(
            getattr(prefs, "start_in_coordinator", False))
    except Exception as e:
        alog(f"apply_startup_mode: {e}")


def register_state_handlers() -> None:
    """Register save_pre / load_post handlers (idempotent)."""
    apply_startup_mode()
    if _ac_save_pre not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(_ac_save_pre)
    if _ac_load_post not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_ac_load_post)


def unregister_state_handlers() -> None:
    """Remove save_pre / load_post handlers (idempotent)."""
    if _ac_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(_ac_save_pre)
    if _ac_load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_ac_load_post)

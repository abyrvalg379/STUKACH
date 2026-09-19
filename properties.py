# -*- coding:utf-8 -*-
import bpy
from .manager import alog
import bmesh
import csv
import json
import os
import tempfile
from datetime import datetime
from bpy.types import PropertyGroup, Menu
from bpy.props import (BoolProperty, EnumProperty, StringProperty,
                       FloatProperty, FloatVectorProperty)

CHECK_CATEGORIES = {
    "TOPOLOGY":   ("non_manifold", "boundary_edges", "isolated_verts", "duplicate_verts",
                   "face_aspect_ratio",
                   "triangles", "ngons", "poles",
                   "zero_area", "z_fighting",
                   "lamina", "zero_length_edges", "starlike", "sharp_edges_not_hard"),
    "TRANSFORMS": ("non_applied_transform", "scale", "origin_at_zero", "modifier_stack",
                   "uncentered_pivots", "parent_geometry"),
    "SYMMETRY":   ("symmetry_x", "symmetry_y", "symmetry_z"),
    "UV":         ("uv_single_set", "uv_overlap", "uv_micro_shell",
                   "uv_texel_density", "uv_stretch", "uv_padding",
                   "uv_udim_bounds", "uv_material_udim", "missing_uvs"),
    "NAMING":     ("obj_naming", "col_naming", "mat_numbering", "mesh_data_naming",
                   "duplicated_names", "trailing_numbers"),
    "MATERIALS":  ("mat_suffix", "mat_assignment", "missing_textures"),
    "CLEANUP":    ("unused_data",),
}

_CAT_ICONS = {
    "TOPOLOGY":   "MESH_DATA",
    "TRANSFORMS": "ARROW_LEFTRIGHT",
    "SYMMETRY":   "MOD_MIRROR",
    "UV":         "UV",
    "NAMING":     "OUTLINER_OB_EMPTY",
    "MATERIALS":  "MATERIAL",
    "CLEANUP":    "BRUSH_DATA",
}

# Custom display labels — overrides auto-generated text for specific checks
# Acronyms that must not be title-cased by pretty_name() ('uv_overlap' →
# 'UV Overlap', not 'Uv Overlap').
_ACRONYMS = {"uv": "UV", "td": "TD", "id": "ID"}


def pretty_name(key: str) -> str:
    """Human-readable check/category name with correct acronyms."""
    words = key.replace("_", " ").title()
    fixed = []
    for w in words.split():
        low = w.lower()
        if low in _ACRONYMS:
            fixed.append(_ACRONYMS[low])
        elif low.startswith("udim"):
            fixed.append("UDIM" + w[4:])
        else:
            fixed.append(w)
    return " ".join(fixed)


_CHECK_LABELS: dict = {
    "obj_naming":         "Object Name",
    "mesh_data_naming":   "Mesh Data Name",
    "col_naming":         "Group Name",
    "z_fighting":         "Z-Fighting",
    "face_aspect_ratio":  "Face Aspect Ratio",
    "uv_material_udim":   "Uv Material Udim",
    "mat_numbering":      "Mat Numbering",
    "missing_uvs":        "Missing UVs",
}


def enable_depsgraph_handler(self, context):
    from .manager import MeshCheck
    if self.check_data:
        if context.object is None:
            self.check_data = False
            self.show_overlay = False
            return
        # Always start fresh in SELECTED scope when pressing Run.
        # Scene / Collection scope is an explicit expansion — not a persistent state.
        MeshCheck._scope = "SELECTED"
        MeshCheck._scope_collection = ""
        MeshCheck.reset_mesh_check()
        MeshCheck.set_mode(context.object.mode)
        MeshCheck.add_callback()
    else:
        MeshCheck.remove_callback()


def update_overlay(self, context):
    from .manager import MeshCheck, MeshCheckGPU, UVCheckGPU
    self.check_data = self.show_overlay
    if self.show_overlay:
        MeshCheck._state_restored = False   # settings consumed — clear the banner
        if context.object is None:
            self.show_overlay = False
            return
        MeshCheckGPU.setup_handler()
        UVCheckGPU.setup_handler()
    else:
        MeshCheckGPU.remove_handler()
        UVCheckGPU.remove_handler()


def mc_object_datas_updater(attr):
    def updater(self, context):
        from .manager import MeshCheck
        if getattr(self, attr):
            MeshCheck.update_mc_object_datas(attr)
        return None
    return updater


# ── Check presets (v1.4.1) ────────────────────────────────────────────────────
# Named sets of enabled checks, stored in AddonPreferences (per Blender
# install, survive .blend switches).  Parity with the Maya version's
# save/load/delete presets.

# Static items for the object-list check filter (built once)
_CHECK_FILTER_ITEMS: list = []


def _check_filter_items(self, context):
    global _CHECK_FILTER_ITEMS
    if not _CHECK_FILTER_ITEMS:
        items = [("__all__", "All checks", "Show all tracked objects")]
        for cat, checks in CHECK_CATEGORIES.items():
            for c in checks:
                label = _CHECK_LABELS.get(c, pretty_name(c))
                items.append((c, label, f"Objects with '{label}' issues"))
        _CHECK_FILTER_ITEMS = items
    return _CHECK_FILTER_ITEMS


def _get_addon_prefs(context):
    # Extensions register preferences under the FULL module name
    # ("bl_ext.user_default.stukach"); the rsplit prefix is a legacy fallback.
    mod_name = __name__
    for key in (mod_name, mod_name.rsplit(".", 1)[0]):
        try:
            return context.preferences.addons[key].preferences
        except Exception:
            continue
    return None


# ── Check presets v2 (v1.5.0) — native Blender preset system ─────────────────
# Presets are .py files under presets/asset_checker/ (Blender's standard
# preset framework).  A preset captures the check toggles AND the inline
# naming policy fields.  Files are plain text — easy to share with the team
# (export/import operators below).

# Check props captured by "Save Preset" (+ naming fields, same mc group)
_PRESET_VALUE_KEYS = (
    # check toggles — kept in sync with manager._AC_CHECK_PROPS
    'non_manifold', 'boundary_edges', 'isolated_verts', 'triangles', 'ngons',
    'poles', 'zero_area', 'z_fighting', 'duplicate_verts', 'face_aspect_ratio',
    'non_applied_transform', 'scale', 'origin_at_zero', 'modifier_stack',
    'symmetry_x', 'symmetry_y', 'symmetry_z',
    'uv_single_set', 'uv_overlap', 'uv_micro_shell', 'uv_texel_density',
    'uv_stretch', 'uv_padding', 'uv_udim_bounds', 'uv_material_udim',
    'obj_naming', 'col_naming', 'mesh_data_naming',
    'mat_suffix', 'mat_assignment', 'missing_textures', 'unused_data',
    'lamina', 'zero_length_edges', 'sharp_edges_not_hard', 'starlike',
    'missing_uvs', 'duplicated_names', 'trailing_numbers',
    'uncentered_pivots', 'parent_geometry',
    # inline naming policy
    'obj_required_prefix', 'obj_required_suffix',
    'col_required_prefix', 'col_required_suffix',
    'mesh_required_suffix',
)


def _preset_dir():
    import os
    return bpy.utils.user_resource('SCRIPTS',
                                   path=os.path.join("presets", "asset_checker"),
                                   create=True)


class ASSET_CHECKER_MT_presets(bpy.types.Menu):
    """Check preset dropdown (native preset framework)"""
    bl_label = "Check Presets"
    preset_subdir = "asset_checker"
    preset_operator = "script.execute_preset"

    def draw(self, _context):
        bpy.types.Menu.draw_preset(self, _context)
        layout = self.layout
        layout.separator()
        layout.operator("asset_checker.preset_import", icon="IMPORT")


class ASSET_CHECKER_OT_preset_add(bpy.types.Operator):
    """Save the current check set (toggles + naming fields) as a preset"""
    bl_idname = "asset_checker.preset_add"
    bl_label = "Save Check Preset"
    bl_options = {'REGISTER'}

    name: StringProperty(name="Name")

    def invoke(self, context, _event):
        self.name = prefs_preset_active_name(context) or ""
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, _context):
        self.layout.prop(self, "name")

    def execute(self, context):
        import os
        name = (self.name or "").strip()
        if not name:
            self.report({'WARNING'}, "Type a preset name")
            return {'CANCELLED'}
        mc = context.window_manager.mesh_check_props
        lines = ["import bpy",
                 "mc = bpy.context.window_manager.mesh_check_props"]
        for key in _PRESET_VALUE_KEYS:
            lines.append(f"mc.{key} = {getattr(mc, key, False)!r}")
        dst = os.path.join(_preset_dir(), name + ".py")
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        prefs = _get_addon_prefs(context)
        if prefs:
            prefs.preset_active = name
        self.report({'INFO'}, f"Saved preset '{name}'")
        return {'FINISHED'}


def prefs_preset_active_name(context):
    prefs = _get_addon_prefs(context)
    return prefs.preset_active if prefs else ""


class ASSET_CHECKER_OT_preset_remove(bpy.types.Operator):
    """Remove a saved check preset file"""
    bl_idname = "asset_checker.preset_remove"
    bl_label = "Remove Check Preset"
    bl_options = {'REGISTER'}

    name: StringProperty(
        name="Name",
        description="Preset name to remove (empty = last applied)",
    )

    def invoke(self, context, _event):
        if not self.name:
            self.name = prefs_preset_active_name(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, _context):
        self.layout.prop(self, "name")

    def execute(self, context):
        import os
        name = (self.name or "").strip()
        path = os.path.join(_preset_dir(), name + ".py")
        if not name or not os.path.isfile(path):
            self.report({'WARNING'}, f"Preset '{name}' not found")
            return {'CANCELLED'}
        os.remove(path)
        prefs = _get_addon_prefs(context)
        if prefs and prefs.preset_active == name:
            prefs.preset_active = ""
        self.report({'INFO'}, f"Removed preset '{name}'")
        return {'FINISHED'}


class ASSET_CHECKER_OT_preset_export(bpy.types.Operator):
    """Export a check preset as a .py file — share it with the team"""
    bl_idname = "asset_checker.preset_export"
    bl_label = "Export Preset"
    bl_options = {'REGISTER'}

    name: StringProperty(options={'HIDDEN'})
    filepath: StringProperty(subtype='FILE_PATH', options={'HIDDEN'})

    def invoke(self, context, _event):
        if not self.name:
            self.report({'WARNING'}, "No preset to export")
            return {'CANCELLED'}
        import os
        self.filepath = os.path.join(_preset_dir(), self.name + ".py")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        import os, shutil
        src = os.path.join(_preset_dir(), self.name + ".py")
        if not os.path.isfile(src):
            self.report({'ERROR'}, f"Preset file not found: {src}")
            return {'CANCELLED'}
        dst = bpy.path.abspath(self.filepath)
        shutil.copyfile(src, dst)
        self.report({'INFO'}, f"Exported preset '{self.name}' → {dst}")
        return {'FINISHED'}


class ASSET_CHECKER_MT_preset_export(bpy.types.Menu):
    """Per-preset export entries"""
    bl_label = "Export Preset"

    def draw(self, context):
        import os
        layout = self.layout
        files = sorted(f for f in os.listdir(_preset_dir()) if f.endswith(".py"))
        if not files:
            layout.label(text="No presets saved", icon="INFO")
            return
        for f in files:
            op = layout.operator("asset_checker.preset_export",
                                 text=f"'{f[:-3]}'")
            op.name = f[:-3]


class ASSET_CHECKER_OT_preset_import(bpy.types.Operator):
    """Import a check preset from a .py file"""
    bl_idname = "asset_checker.preset_import"
    bl_label = "Import Preset"
    bl_options = {'REGISTER'}

    filepath: StringProperty(subtype='FILE_PATH', options={'HIDDEN'})
    filter_glob: StringProperty(default="*.py", options={'HIDDEN'})

    def invoke(self, context, _event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        import os, shutil
        src = bpy.path.abspath(self.filepath)
        if not os.path.isfile(src):
            self.report({'ERROR'}, f"File not found: {src}")
            return {'CANCELLED'}
        dst = os.path.join(_preset_dir(), os.path.basename(src))
        shutil.copyfile(src, dst)
        self.report({'INFO'}, f"Imported preset '{os.path.basename(src)}'")
        return {'FINISHED'}


# ── UV map naming / rename (v1.5.0, PROKLADKA-style DCC conventions) ─────────
_UV_NAME_CACHE: list = []


def _uv_rename_items(self, context):
    """Rename target dropdown: DCC-canonical names first, then every UV name
    detected on tracked objects."""
    global _UV_NAME_CACHE
    canonical = [
        ("UVMap", "UVMap (Blender)", "Blender default UV map name"),
        ("map1",  "map1 (Maya)",     "Maya default UV set name"),
        ("uv",    "uv (Houdini)",    "Houdini default uv attribute name"),
    ]
    seen = {key for key, _l, _d in canonical}
    detected = []
    try:
        from .manager import MeshCheck
        for obj in MeshCheck.objects:
            try:
                uvl = obj.data.uv_layers
            except (ReferenceError, AttributeError):
                continue
            for layer in uvl:
                if layer.name not in seen:
                    seen.add(layer.name)
                    detected.append((layer.name, f"{layer.name} (detected)",
                                     "Found on validated objects"))
    except Exception:
        pass
    _UV_NAME_CACHE = canonical + detected
    return _UV_NAME_CACHE


def update_face_orientation(self, context):
    """Mirror of Blender's built-in Face Orientation viewport overlay.

    Pure view helper — no validation, no counters.  Keeps every VIEW_3D
    space in sync so the panel is the single place to toggle check views.
    """
    enabled = self.face_orientation
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.overlay.show_face_orientation = enabled


def update_obj_naming(self, context):
    """Custom updater for obj_naming: clears NamingMarker when check is disabled."""
    from .manager import MeshCheck
    if self.obj_naming:
        MeshCheck.update_mc_object_datas("obj_naming")
        # NamingMarker.update() is called inside update_mc_object_datas
    else:
        try:
            from .naming import NamingMarker
            NamingMarker.clear()
        except Exception:
            pass


class ASSET_CHECKER_OT_select_check_elements(bpy.types.Operator):
    """Switch to Edit Mode and select the mesh elements flagged by this check"""
    bl_idname  = "asset_checker.select_check_elements"
    bl_label   = "Select Issues in Edit Mode"
    bl_options = {'REGISTER', 'UNDO'}

    obj_name:   StringProperty(options={'HIDDEN'})
    check_name: StringProperty(options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode in {'OBJECT', 'EDIT_MESH'}

    def execute(self, context):
        from .manager import MeshCheck

        obj = bpy.data.objects.get(self.obj_name)
        if obj is None:
            self.report({'WARNING'}, f"Object '{self.obj_name}' not found")
            return {'CANCELLED'}

        mc_obj = MeshCheck.objects.get(obj)
        if mc_obj is None:
            self.report({'WARNING'}, "Object not tracked — run validation first")
            return {'CANCELLED'}

        checker = mc_obj._checks.get(self.check_name)
        if checker is None or checker.count == 0:
            return {'CANCELLED'}

        element_type, indices = checker.get_select_data()
        if element_type is None or not indices:
            self.report({'INFO'}, "No selectable 3D elements for this check")
            return {'CANCELLED'}

        # Make active, enter Edit mode
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = obj
        obj.select_set(True)
        if context.mode != 'EDIT_MESH':
            bpy.ops.object.mode_set(mode='EDIT')

        bm = bmesh.from_edit_mesh(obj.data)

        # Deselect everything
        for v in bm.verts: v.select = False
        for e in bm.edges: e.select = False
        for f in bm.faces: f.select = False

        bm.select_flush(False)

        if element_type == 'VERT':
            bpy.ops.mesh.select_mode(type='VERT')
            bm.verts.ensure_lookup_table()
            for idx in indices:
                if 0 <= idx < len(bm.verts):
                    bm.verts[idx].select = True
        elif element_type == 'EDGE':
            bpy.ops.mesh.select_mode(type='EDGE')
            bm.edges.ensure_lookup_table()
            for idx in indices:
                if 0 <= idx < len(bm.edges):
                    bm.edges[idx].select = True
        elif element_type == 'FACE':
            bpy.ops.mesh.select_mode(type='FACE')
            bm.faces.ensure_lookup_table()
            for idx in indices:
                if 0 <= idx < len(bm.faces):
                    bm.faces[idx].select = True

        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data, loop_triangles=False, destructive=False)

        # Zoom viewport to the selected elements so the user can immediately
        # see where the problem is, especially important for zero-area faces
        # whose markers can be hard to spot manually.
        try:
            bpy.ops.view3d.view_selected()
        except Exception:
            pass

        return {'FINISHED'}


class MESH_CHECK_OT_toggle_category(bpy.types.Operator):
    """Включить / выключить все чеки категории"""
    bl_idname = "mesh_check.toggle_category"
    bl_label = "Toggle Category"
    bl_options = {'REGISTER', 'UNDO'}

    category: StringProperty()

    def execute(self, context):
        mc = context.window_manager.mesh_check_props
        checks = CHECK_CATEGORIES.get(self.category, ())
        any_on = any(getattr(mc, c, False) for c in checks if hasattr(mc, c))
        for c in checks:
            if hasattr(mc, c):
                setattr(mc, c, not any_on)
        return {'FINISHED'}


class ASSET_CHECKER_OT_set_td_target(bpy.types.Operator):
    """Set the Texel Density target value from a preset"""
    bl_idname = "asset_checker.set_td_target"
    bl_label  = "Set TD Target"
    bl_options = {'REGISTER', 'UNDO'}

    td_value: FloatProperty(name="TD Value", default=10.24, min=0.0, max=500.0)

    def execute(self, context):
        addon_name = __name__.rsplit(".", 1)[0]
        try:
            prefs = context.preferences.addons[addon_name].preferences
            prefs.uv_td_target = self.td_value
        except Exception as e:
            self.report({'WARNING'}, f"Could not set TD target: {e}")
            return {'CANCELLED'}
        # Re-run TD check to update counts with new target
        from .manager import MeshCheck
        MeshCheck.update_mc_object_datas("uv_texel_density")
        return {'FINISHED'}


class ASSET_CHECKER_OT_check_naming(bpy.types.Operator):
    """Run naming validation for all tracked objects using current prefix / suffix settings"""
    bl_idname = "asset_checker.check_naming"
    bl_label  = "Check Naming"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        from .manager import MeshCheck
        return bool(MeshCheck.objects)

    def execute(self, context):
        from .manager import MeshCheck
        mc = context.window_manager.mesh_check_props
        # Enable the checks so results are visible in the panel
        mc.obj_naming = True
        mc.col_naming = True
        # Force re-run (set_datas picks up the new prefix/suffix values)
        MeshCheck.update_mc_object_datas("obj_naming")
        MeshCheck.update_mc_object_datas("col_naming")
        return {'FINISHED'}


class ASSET_CHECKER_OT_highlight_mat_udim(bpy.types.Operator):
    """Highlight UDIM tiles used by this material in the UV Editor (click again to deselect)"""
    bl_idname  = "asset_checker.highlight_mat_udim"
    bl_label   = "Highlight Material UDIMs"
    bl_options = {'REGISTER'}

    mat_name: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        mc = context.window_manager.mesh_check_props
        # Toggle: clicking the same material deselects it
        mc.mat_udim_selected = "" if mc.mat_udim_selected == self.mat_name else self.mat_name
        # Redraw all UV editors
        for area in context.screen.areas:
            if area.type == 'IMAGE_EDITOR':
                area.tag_redraw()
        return {'FINISHED'}


# ── Auto-fix helpers ─────────────────────────────────────────────────────────

# Maps check_name → fix operator bl_idname.
# Used by draw_options() to show a Fix button when issues are found.
_FIX_OPERATORS: dict = {
    "non_applied_transform": "asset_checker.fix_transforms",
    "scale":                 "asset_checker.fix_scale",
    "origin_at_zero":        "asset_checker.fix_origin",
    "modifier_stack":        "asset_checker.fix_modifier_stack",
    "isolated_verts":        "asset_checker.fix_merge_by_distance",
    "duplicate_verts":       "asset_checker.fix_merge_by_distance",
    "zero_area":             "asset_checker.fix_zero_area",
    "mat_numbering":         "asset_checker.fix_mat_numbering",
    "uv_single_set":         "asset_checker.fix_uv_single_set",
    "obj_naming":            "asset_checker.fix_naming",
    "mat_suffix":            "asset_checker.fix_mat_suffix",
    "unused_data":           "asset_checker.fix_unused_data",
    "mesh_data_naming":      "asset_checker.fix_mesh_data_naming",
    "sharp_edges_not_hard":  "asset_checker.fix_sharp_edges",
    "lamina":                "asset_checker.fix_lamina",
}


def _problem_objects(check_name):
    """Yield (obj, mc_obj) pairs where *check_name* has count > 0."""
    from .manager import MeshCheck
    for obj, mc_obj in MeshCheck.objects.items():
        ch = mc_obj._checks.get(check_name)
        if ch and ch.count > 0:
            yield obj, mc_obj


def _ensure_accessible(context, obj) -> tuple:
    """Make *obj* active, visible, and selectable for fix operators.

    Returns a state tuple to pass to _restore_accessible().
    Works correctly in SCENE / COLLECTION scope where objects may not
    be selected (select_get() == False) or may be hidden in the viewport.
    """
    state = (obj.hide_viewport, obj.hide_select)
    obj.hide_viewport = False
    obj.hide_select   = False
    try:
        context.view_layer.objects.active = obj
        obj.select_set(True)
    except Exception:
        pass
    return state


def _restore_accessible(obj, state: tuple) -> None:
    """Restore visibility / select state saved by _ensure_accessible()."""
    try:
        obj.select_set(False)
    except Exception:
        pass
    obj.hide_viewport, obj.hide_select = state


def _ensure_visible(obj) -> tuple:
    """Lighter variant: make *obj* visible only (for EDIT-mode fix operators).

    Returns state tuple for _restore_visible().
    """
    state = (obj.hide_viewport, obj.hide_select)
    obj.hide_viewport = False
    obj.hide_select   = False
    return state


def _restore_visible(obj, state: tuple) -> None:
    """Restore visibility state saved by _ensure_visible()."""
    obj.hide_viewport, obj.hide_select = state


# ── Fix: Apply Rotation ───────────────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_transforms(bpy.types.Operator):
    """Apply rotation to all tracked objects with non-applied rotation"""
    bl_idname  = "asset_checker.fix_transforms"
    bl_label   = "Fix: Apply Rotation"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        fixed = 0
        for obj, _ in list(_problem_objects("non_applied_transform")):
            state = _ensure_accessible(context, obj)
            try:
                with context.temp_override(active_object=obj,
                                           selected_objects=[obj],
                                           selected_editable_objects=[obj]):
                    bpy.ops.object.transform_apply(rotation=True)
                fixed += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_transforms {obj.name}: {e}")
            finally:
                _restore_accessible(obj, state)
        MeshCheck.update_mc_object_datas("non_applied_transform")
        self.report({'INFO'}, f"Applied rotation to {fixed} object(s)")
        return {'FINISHED'}


# ── Fix: Apply Scale ──────────────────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_scale(bpy.types.Operator):
    """Apply scale to all tracked objects with non-unit scale"""
    bl_idname  = "asset_checker.fix_scale"
    bl_label   = "Fix: Apply Scale"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        fixed = 0
        for obj, _ in list(_problem_objects("scale")):
            state = _ensure_accessible(context, obj)
            try:
                with context.temp_override(active_object=obj,
                                           selected_objects=[obj],
                                           selected_editable_objects=[obj]):
                    bpy.ops.object.transform_apply(scale=True)
                fixed += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_scale {obj.name}: {e}")
            finally:
                _restore_accessible(obj, state)
        MeshCheck.update_mc_object_datas("scale")
        self.report({'INFO'}, f"Applied scale to {fixed} object(s)")
        return {'FINISHED'}


# ── Fix: Merge by Distance ────────────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_merge_by_distance(bpy.types.Operator):
    """Merge vertices by distance to remove isolated verts and near-duplicates"""
    bl_idname  = "asset_checker.fix_merge_by_distance"
    bl_label   = "Fix: Merge by Distance"
    bl_options = {'REGISTER', 'UNDO'}

    threshold: FloatProperty(
        name="Merge Distance",
        default=0.0001, min=0.0, max=1.0,
        description="Maximum distance between vertices to merge",
    )

    def execute(self, context):
        from .manager import MeshCheck
        fixed = 0
        prev_active = context.view_layer.objects.active

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj, _ in list(_problem_objects("isolated_verts")):
            state = _ensure_visible(obj)
            try:
                context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.mesh.remove_doubles(threshold=self.threshold)
                bpy.ops.object.mode_set(mode='OBJECT')
                obj.select_set(False)
                fixed += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_merge {obj.name}: {e}")
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception:
                    pass
            finally:
                _restore_visible(obj, state)

        # duplicate_verts: merge ONLY the flagged pairs.  Different shells with
        # coincident verts are intentional (not flagged) — a blanket merge here
        # would weld them, so the selection is restricted to the check results.
        merged_objs = 0
        for obj, mc_obj in list(_problem_objects("duplicate_verts")):
            checker = mc_obj._checks.get("duplicate_verts")
            pair_idx = list(getattr(checker, '_dup_pair_idx', []) or [])
            if not pair_idx:
                continue
            state = _ensure_visible(obj)
            try:
                context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.mode_set(mode='EDIT')
                bm = bmesh.from_edit_mesh(obj.data)
                bm.verts.ensure_lookup_table()
                for v in bm.verts:
                    v.select_set(v.index in set(pair_idx))
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data)
                bpy.ops.mesh.remove_doubles(threshold=self.threshold)
                bpy.ops.object.mode_set(mode='OBJECT')
                obj.select_set(False)
                merged_objs += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_merge(dup) {obj.name}: {e}")
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception:
                    pass
            finally:
                _restore_visible(obj, state)

        try:
            if prev_active:
                context.view_layer.objects.active = prev_active
        except Exception:
            pass

        if merged_objs:
            MeshCheck.update_mc_object_datas("duplicate_verts")
        MeshCheck.update_mc_object_datas("isolated_verts")
        self.report({'INFO'},
                    f"Merged by distance on {fixed + merged_objs} object(s)")
        return {'FINISHED'}


# ── Fix: Auto-rename objects ──────────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_naming(bpy.types.Operator):
    """Auto-fix object names: lowercase, strip forbidden chars, apply prefix/suffix"""
    bl_idname  = "asset_checker.fix_naming"
    bl_label   = "Fix: Auto-rename"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import re
        from .manager import MeshCheck
        mc     = context.window_manager.mesh_check_props
        prefix = mc.obj_required_prefix.strip()
        suffix = mc.obj_required_suffix.strip()
        fixed  = 0

        for obj, _ in list(_problem_objects("obj_naming")):
            name = obj.name
            name = name.lower()
            name = re.sub(r'[^a-z0-9_]', '_', name)
            name = re.sub(r'_+', '_', name).strip('_') or "unnamed"
            if prefix and not name.startswith(prefix):
                name = prefix + name
            if suffix and not name.endswith(suffix):
                name = name + suffix
            if name != obj.name:
                obj.name = name
                fixed += 1

        MeshCheck.update_mc_object_datas("obj_naming")
        self.report({'INFO'}, f"Renamed {fixed} object(s)")
        return {'FINISHED'}


# ── Fix: Apply Location (origin to zero) ─────────────────────────────────────
class ASSET_CHECKER_OT_fix_origin(bpy.types.Operator):
    """Apply location to all tracked objects whose origin is not at world zero.
    Bakes the current world-space position into the mesh vertices so the object
    stays in place visually while obj.location resets to (0, 0, 0)."""
    bl_idname  = "asset_checker.fix_origin"
    bl_label   = "Fix: Apply Location"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        fixed = 0
        for obj, _ in list(_problem_objects("origin_at_zero")):
            state = _ensure_accessible(context, obj)
            try:
                with context.temp_override(active_object=obj,
                                           selected_objects=[obj],
                                           selected_editable_objects=[obj]):
                    bpy.ops.object.transform_apply(location=True)
                fixed += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_origin {obj.name}: {e}")
            finally:
                _restore_accessible(obj, state)
        MeshCheck.update_mc_object_datas("origin_at_zero")
        self.report({'INFO'}, f"Applied location to {fixed} object(s)")
        return {'FINISHED'}


# ── Fix: Apply All Modifiers ──────────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_modifier_stack(bpy.types.Operator):
    """Apply all non-Armature modifiers on all tracked objects with modifier issues"""
    bl_idname  = "asset_checker.fix_modifier_stack"
    bl_label   = "Fix: Apply Modifiers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        fixed = 0
        prev_active = context.view_layer.objects.active

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj, _ in list(_problem_objects("modifier_stack")):
            state = _ensure_accessible(context, obj)
            try:
                mods_to_apply = [m.name for m in obj.modifiers
                                 if m.type not in {'ARMATURE'}]
                for mod_name in mods_to_apply:
                    if mod_name not in obj.modifiers:
                        continue
                    with context.temp_override(active_object=obj,
                                               selected_objects=[obj],
                                               selected_editable_objects=[obj]):
                        bpy.ops.object.modifier_apply(modifier=mod_name)
                fixed += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_modifier_stack {obj.name}: {e}")
            finally:
                _restore_accessible(obj, state)

        try:
            if prev_active:
                context.view_layer.objects.active = prev_active
        except Exception:
            pass

        MeshCheck.update_mc_object_datas("modifier_stack")
        self.report({'INFO'}, f"Applied modifiers on {fixed} object(s)")
        return {'FINISHED'}


# ── Fix: Add _mat suffix ──────────────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_mat_suffix(bpy.types.Operator):
    """Add _mat suffix to all materials that are missing it"""
    bl_idname  = "asset_checker.fix_mat_suffix"
    bl_label   = "Fix: Add _mat Suffix"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        fixed     = 0
        seen_mats: set = set()
        for obj, _ in list(_problem_objects("mat_suffix")):
            for slot in obj.material_slots:
                mat = slot.material
                if mat and id(mat) not in seen_mats and not mat.name.endswith("_mat"):
                    mat.name = mat.name + "_mat"
                    seen_mats.add(id(mat))
                    fixed += 1

        from .manager import MeshCheck
        MeshCheck.update_mc_object_datas("mat_suffix")
        self.report({'INFO'}, f"Added _mat suffix to {fixed} material(s)")
        return {'FINISHED'}


# ── Collapse / Expand all objects in the list ────────────────────────────────
class ASSET_CHECKER_OT_collapse_objects(bpy.types.Operator):
    """Collapse all expanded objects in the list (click again to expand all)"""
    bl_idname  = "asset_checker.collapse_objects"
    bl_label   = "Collapse / Expand All"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from .manager import MeshCheck
        objects = list(MeshCheck.objects.keys())
        if not objects:
            return {'CANCELLED'}
        # If any object is expanded → collapse all; otherwise expand all
        def _stat(o):
            try:
                return bool(o.mesh_check_statistics)
            except ReferenceError:
                return False

        any_open = any(_stat(o) for o in objects)
        for o in objects:
            try:
                o.mesh_check_statistics = not any_open
            except Exception:
                pass
        return {'FINISHED'}


# ── Fix: Delete Zero-area Faces ───────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_zero_area(bpy.types.Operator):
    """Delete degenerate (zero-area) faces detected by the Zero Area check"""
    bl_idname  = "asset_checker.fix_zero_area"
    bl_label   = "Fix: Delete Zero-area Faces"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        fixed = 0
        prev_active = context.view_layer.objects.active
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj, mc_obj in list(_problem_objects("zero_area")):
            checker = mc_obj._checks.get("zero_area")
            face_idx = set(getattr(checker, '_faces_idx', []) or [])
            if not face_idx:
                continue
            state = _ensure_visible(obj)
            try:
                context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.mode_set(mode='EDIT')
                bm = bmesh.from_edit_mesh(obj.data)
                bm.faces.ensure_lookup_table()
                for f in bm.faces:
                    f.select_set(f.index in face_idx)
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data)
                bpy.ops.mesh.delete(type='FACE')
                bpy.ops.object.mode_set(mode='OBJECT')
                obj.select_set(False)
                fixed += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_zero_area {obj.name}: {e}")
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception:
                    pass
            finally:
                _restore_visible(obj, state)

        try:
            if prev_active:
                context.view_layer.objects.active = prev_active
        except Exception:
            pass

        MeshCheck.update_mc_object_datas("zero_area")
        self.report({'INFO'}, f"Deleted zero-area faces on {fixed} object(s)")
        return {'FINISHED'}


# ── Fix: Lamina faces ─────────────────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_lamina(bpy.types.Operator):
    """Delete lamina (zero-thickness) faces detected by the Lamina check"""
    bl_idname  = "asset_checker.fix_lamina"
    bl_label   = "Fix: Delete Lamina Faces"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        fixed = 0
        prev_active = context.view_layer.objects.active
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj, mc_obj in list(_problem_objects("lamina")):
            checker = mc_obj._checks.get("lamina")
            face_idx = set(getattr(checker, '_faces_idx', []) or [])
            if not face_idx:
                continue
            state = _ensure_visible(obj)
            try:
                context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.mode_set(mode='EDIT')
                bm = bmesh.from_edit_mesh(obj.data)
                bm.faces.ensure_lookup_table()
                for f in bm.faces:
                    f.select_set(f.index in face_idx)
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data)
                bpy.ops.mesh.delete(type='FACE')
                bpy.ops.object.mode_set(mode='OBJECT')
                obj.select_set(False)
                fixed += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_lamina {obj.name}: {e}")
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception:
                    pass
            finally:
                _restore_visible(obj, state)

        try:
            if prev_active:
                context.view_layer.objects.active = prev_active
        except Exception:
            pass

        MeshCheck.update_mc_object_datas("lamina")
        self.report({'INFO'}, f"Deleted lamina faces on {fixed} object(s)")
        return {'FINISHED'}


# ── Fix: Mark sharp edges ─────────────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_sharp_edges(bpy.types.Operator):
    """Mark flagged edges (dihedral >= 30° left smooth) as sharp"""
    bl_idname  = "asset_checker.fix_sharp_edges"
    bl_label   = "Fix: Mark Edges Sharp"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        fixed = 0
        prev_active = context.view_layer.objects.active
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        for obj, mc_obj in list(_problem_objects("sharp_edges_not_hard")):
            checker = mc_obj._checks.get("sharp_edges_not_hard")
            edge_idx = set(getattr(checker, '_edges_idx', []) or [])
            if not edge_idx:
                continue
            state = _ensure_visible(obj)
            try:
                context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.mode_set(mode='EDIT')
                bm = bmesh.from_edit_mesh(obj.data)
                bm.edges.ensure_lookup_table()
                for e in bm.edges:
                    e.select_set(e.index in edge_idx)
                bm.select_flush_mode()
                bmesh.update_edit_mesh(obj.data)
                bpy.ops.mesh.mark_sharp()
                bpy.ops.object.mode_set(mode='OBJECT')
                obj.select_set(False)
                # Sharpness is an attribute — vert/edge/face counts are
                # unchanged, so the cached object-mode BMesh would look fresh
                # to the mesh-key dirty check and keep reporting the old count.
                mc_obj._drop_cached_bm()
                mc_obj._mesh_key = ()
                fixed += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_sharp_edges {obj.name}: {e}")
                try:
                    bpy.ops.object.mode_set(mode='OBJECT')
                except Exception:
                    pass
            finally:
                _restore_visible(obj, state)

        try:
            if prev_active:
                context.view_layer.objects.active = prev_active
        except Exception:
            pass

        MeshCheck.update_mc_object_datas("sharp_edges_not_hard")
        self.report({'INFO'}, f"Marked sharp edges on {fixed} object(s)")
        return {'FINISHED'}


# ── Fix: Rename numbered materials ────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_mat_numbering(bpy.types.Operator):
    """Rename materials with Blender auto-numbering (.001) to clean base names.
    If the base name is taken, a numeric tail is replaced by '_v2', '_v3', ..."""
    bl_idname  = "asset_checker.fix_mat_numbering"
    bl_label   = "Fix: Rename Numbered Materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import re
        from .manager import MeshCheck
        renamed = 0
        pattern = re.compile(r'\.\d{3}$')
        taken = {m.name for m in bpy.data.materials}

        for obj, mc_obj in list(_problem_objects("mat_numbering")):
            checker = mc_obj._checks.get("mat_numbering")
            for mat_name in list(getattr(checker, '_issues', []) or []):
                mat = bpy.data.materials.get(mat_name)
                if mat is None or not pattern.search(mat.name):
                    continue
                base = pattern.sub('', mat.name)
                new_name = base
                n = 2
                while new_name in taken and new_name != mat.name:
                    new_name = f"{base}_v{n}"
                    n += 1
                if new_name == mat.name:
                    continue
                mat.name = new_name
                taken.add(new_name)
                renamed += 1

        MeshCheck.update_mc_object_datas("mat_numbering")
        self.report({'INFO'}, f"Renamed {renamed} material(s)")
        return {'FINISHED'}


# ── Fix: Remove extra UV sets ─────────────────────────────────────────────────
class ASSET_CHECKER_OT_fix_uv_single_set(bpy.types.Operator):
    """Remove extra UV sets — keep only the active one"""
    bl_idname  = "asset_checker.fix_uv_single_set"
    bl_label   = "Fix: Keep Active UV Set Only"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        fixed = 0
        for obj, mc_obj in list(_problem_objects("uv_single_set")):
            uvl = obj.data.uv_layers
            if len(uvl) <= 1:
                continue
            active = uvl.active
            for u in list(uvl):
                if u != active:
                    uvl.remove(u)
            fixed += 1

        if fixed:
            MeshCheck.update_mc_object_datas("uv_single_set")
        self.report({'INFO'}, f"Removed extra UV sets on {fixed} object(s)")
        return {'FINISHED'}


# ── Fix: All fixable checks in a category ────────────────────────────────────
class ASSET_CHECKER_OT_fix_category(bpy.types.Operator):
    """Run all available auto-fixes for this category"""
    bl_idname  = "asset_checker.fix_category"
    bl_label   = "Fix Category"
    bl_options = {'REGISTER', 'UNDO'}

    category: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        from .manager import MeshCheck
        mc     = context.window_manager.mesh_check_props
        checks = CHECK_CATEGORIES.get(self.category, ())
        ran    = 0

        for check in checks:
            fix_idname = _FIX_OPERATORS.get(check)
            if not fix_idname or not getattr(mc, check, False):
                continue
            has_issues = any(
                mc_obj._checks.get(check) and mc_obj._checks[check].count > 0
                for mc_obj in MeshCheck.objects.values()
            )
            if not has_issues:
                continue
            try:
                # e.g. "asset_checker.fix_scale" → bpy.ops.asset_checker.fix_scale()
                mod, op = fix_idname.split(".", 1)
                getattr(getattr(bpy.ops, mod), op)()
                ran += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_category {check}: {e}")

        self.report({'INFO'}, f"Ran {ran} fix(es) in {self.category}")
        return {'FINISHED'}


# ── Export Report ─────────────────────────────────────────────────────────────

def _get_check_count_for_export(mc_obj, check_name: str) -> int:
    """Return count for a single check on a single MeshCheckObject (0 if absent)."""
    ch = mc_obj._checks.get(check_name)
    return ch.count if ch else 0


def _get_check_detail(mc_obj, check_name: str) -> str:
    """Return metric_text if available, otherwise empty string."""
    ch = mc_obj._checks.get(check_name)
    if ch is None:
        return ""
    return getattr(ch, "metric_text", "") or ""


class ASSET_CHECKER_OT_export_report(bpy.types.Operator):
    """Export STUKACH validation results to JSON, CSV, or HTML"""
    bl_idname  = "asset_checker.export_report"
    bl_label   = "Export Report"
    bl_options = {'REGISTER'}

    fmt: EnumProperty(
        name="Format",
        items=[
            ('JSON', "JSON", "Machine-readable, ideal for Shotgrid / Ftrack / pipeline tools"),
            ('CSV',  "CSV",  "Spreadsheet / task-tracker format"),
            ('HTML', "HTML", "Dark-theme human-readable report, open in any browser"),
        ],
        default='HTML',
    )

    # File dialog properties
    filepath: StringProperty(
        subtype='FILE_PATH',
        default="",
        description="Output file path for the report",
    )
    filter_glob: StringProperty(
        default="*.html;*.json;*.csv",
        options={'HIDDEN'},
    )

    # ── Internal helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _auto_path(ext: str) -> str:
        """Return default output path next to the .blend (or temp dir if unsaved)."""
        blend_path = bpy.data.filepath
        if blend_path:
            base = os.path.splitext(blend_path)[0]
            return f"{base}_report.{ext}"
        tmp = tempfile.gettempdir()
        return os.path.join(tmp, f"stukach_report.{ext}")

    # ── invoke: open file-save dialog ─────────────────────────────────────────

    def invoke(self, context, event):
        from .manager import MeshCheck
        if not MeshCheck.objects:
            self.report({'WARNING'}, "No validated objects — run STUKACH first")
            return {'CANCELLED'}

        ext = self.fmt.lower()

        # Pre-fill path and restrict browser to matching extension
        if not self.filepath or not self.filepath.lower().endswith(f".{ext}"):
            self.filepath = self._auto_path(ext)
        self.filter_glob = f"*.{ext}"

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    @staticmethod
    def _build_report(context) -> dict:
        """Assemble a structured report dict from MeshCheck.objects."""
        from .manager import MeshCheck, get_addon_version
        from .ui import CHECK_SEVERITY, _get_asset_status, _compute_asset_summary

        mc = context.window_manager.mesh_check_props

        # Summary
        summary_data = _compute_asset_summary(mc)
        status_str   = _get_asset_status(mc).upper()

        objects_list = []
        for obj, mc_obj in MeshCheck.objects.items():
            try:
                obj_name = obj.name
            except ReferenceError:
                continue
            checks_list = []
            for cat_name, cat_checks in CHECK_CATEGORIES.items():
                for check in cat_checks:
                    if not getattr(mc, check, False):
                        continue
                    count = _get_check_count_for_export(mc_obj, check)
                    if count == 0:
                        continue
                    detail = _get_check_detail(mc_obj, check)
                    checks_list.append({
                        "category": cat_name,
                        "check":    check,
                        "severity": CHECK_SEVERITY.get(check, "WARNING"),
                        "count":    count,
                        "detail":   detail,
                    })
            objects_list.append({
                "name":   obj_name,
                "checks": checks_list,
            })

        preset_name = "—"
        ignored_lines = []
        prefs = _get_addon_prefs(context)
        if prefs and prefs.preset_active:
            preset_name = prefs.preset_active
        for obj, mc_obj in MeshCheck.objects.items():
            try:
                ignored = get_obj_ignore_list(obj)
            except ReferenceError:
                continue
            if ignored:
                ignored_lines.append(f"{obj.name}: {', '.join(sorted(ignored))}")

        return {
            "tool":    "STUKACH · Pipeline Snitch System",
            "version": get_addon_version(),
            "scene":   context.scene.name,
            "file":    bpy.data.filepath or "(unsaved)",
            "date":    datetime.now().isoformat(timespec='seconds'),
            "scope":   MeshCheck._scope,
            "preset":  preset_name,
            "ignored": ignored_lines,
            "hierarchy": _hierarchy_report_block(),
            "summary": {
                "status":       status_str,
                "objects":      summary_data["obj_count"],
                "blockers":     summary_data["total_blockers"],
                "warnings":     summary_data["total_warnings"],
                "total_issues": summary_data["total_issues"],
            },
            "objects": objects_list,
        }

    # ── Writers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _write_json(report: dict, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _write_csv(report: dict, path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["scene", "file", "date", "scope",
                        "status", "objects", "blockers", "warnings"])
            s = report["summary"]
            w.writerow([report["scene"], report["file"], report["date"], report["scope"],
                        s["status"], s["objects"], s["blockers"], s["warnings"]])
            w.writerow([])
            w.writerow(["object", "category", "check", "severity", "count", "detail"])
            for obj in report["objects"]:
                for ch in obj["checks"]:
                    w.writerow([
                        obj["name"],
                        ch["category"],
                        ch["check"],
                        ch["severity"],
                        ch["count"],
                        ch.get("detail", ""),
                    ])

            # Hierarchy scan issues (same tabular shape, category = HIERARCHY)
            h = report.get("hierarchy")
            if h:
                w.writerow([])
                w.writerow(["hierarchy scan", "", "", "",
                            f"{h['errors']} errors / {h['warnings']} warnings",
                            f"{h['roots']} root(s), {h['scanned']} object(s) scanned"])
                for issue in h["issues"]:
                    w.writerow([
                        issue["object"],
                        "HIERARCHY",
                        issue["rule"],
                        issue["severity"],
                        1,
                        issue["message"],
                    ])

    @staticmethod
    def _write_html(report: dict, path: str) -> None:
        s = report["summary"]
        status_color = {"CRITICAL": "#e84040", "WARNING": "#e8a040", "READY": "#40c070"}.get(
            s["status"], "#aaaaaa"
        )

        rows_html = ""
        for obj in report["objects"]:
            for ch in obj["checks"]:
                sev_color = "#e84040" if ch["severity"] == "BLOCKER" else "#e8a040"
                rows_html += (
                    f"<tr>"
                    f"<td>{obj['name']}</td>"
                    f"<td>{ch['category']}</td>"
                    f"<td>{ch['check'].replace('_', ' ')}</td>"
                    f"<td style='color:{sev_color};font-weight:bold'>{ch['severity']}</td>"
                    f"<td style='text-align:center'>{ch['count']}</td>"
                    f"<td>{ch.get('detail','')}</td>"
                    f"</tr>\n"
                )
        if not rows_html:
            rows_html = "<tr><td colspan='6' style='color:#40c070;text-align:center'>No issues found — pipeline clean ✓</td></tr>"

        # ── Hierarchy scan section (separate table under the checks) ──────
        h = report.get("hierarchy")
        hierarchy_html = ""
        if h:
            if h["issues"]:
                h_rows = ""
                for issue in h["issues"]:
                    sev_color = "#e84040" if issue["severity"] == "ERROR" else "#e8a040"
                    h_rows += (
                        f"<tr>"
                        f"<td>{issue['object']}</td>"
                        f"<td style='color:{sev_color};font-weight:bold'>{issue['severity']}</td>"
                        f"<td>{issue['rule']}</td>"
                        f"<td>{issue['message']}</td>"
                        f"</tr>\n"
                    )
                hierarchy_html = (
                    "<h2 style='color:#fff;font-size:15px;margin-top:24px'>Hierarchy Scan</h2>"
                    f"<div class='subtitle'>{h['roots']} root(s) · {h['scanned']} object(s) · "
                    f"{h['errors']} error(s) · {h['warnings']} warning(s)</div>"
                    "<table><thead><tr><th>Object</th><th>Severity</th><th>Rule</th><th>Detail</th></tr></thead>"
                    f"<tbody>{h_rows}</tbody></table>"
                )
            else:
                hierarchy_html = (
                    "<h2 style='color:#fff;font-size:15px;margin-top:24px'>Hierarchy Scan</h2>"
                    f"<div class='subtitle' style='color:#40c070'>Clean — {h['roots']} root(s), "
                    f"{h['scanned']} object(s) ✓</div>"
                )

        # ── Fix-first verdict section (blockers/warnings by priority) ──────
        flat = []
        for obj in report["objects"]:
            for ch in obj["checks"]:
                if ch["count"] > 0 and ch["severity"] in ("BLOCKER", "WARNING"):
                    flat.append((ch["severity"], ch["check"], obj["name"], ch["count"]))
        fix_first_html = ""
        if flat:
            items = []
            blockers = sorted((f for f in flat if f[0] == "BLOCKER"), key=lambda t: -t[3])
            warns = sorted((f for f in flat if f[0] == "WARNING"), key=lambda t: -t[3])
            for sev, chk, name, cnt in blockers[:8]:
                items.append(f"<li><span style='color:#e84040;font-weight:bold'>[{cnt}]</span> "
                             f"{chk.replace('_', ' ')} — {name}</li>")
            if len(blockers) > 8:
                items.append(f"<li style='color:#888'>…and {len(blockers) - 8} more</li>")
            for sev, chk, name, cnt in warns[:5]:
                items.append(f"<li><span style='color:#e8a040;font-weight:bold'>[{cnt}]</span> "
                             f"{chk.replace('_', ' ')} — {name}</li>")
            if len(warns) > 5:
                items.append(f"<li style='color:#888'>…and {len(warns) - 5} more</li>")
            fix_first_html = ("<div style='background:#252525;border:1px solid #333;"
                              "border-left:4px solid #e84040;border-radius:6px;"
                              "padding:10px 16px;margin-bottom:20px'>"
                              "<div style='color:#fff;font-size:12px;font-weight:bold;"
                              "text-transform:uppercase;letter-spacing:.5px;margin-bottom:6px'>"
                              "Fix first</div>"
                              "<ul style='margin-left:18px;line-height:1.7'>"
                              + "".join(items) + "</ul></div>")

        if report.get("ignored"):
            ign = "<br>".join(report["ignored"])
            ignored_html = (f"<div class='meta' style='margin-top:0'>"
                            f"<div><div class='label'>Ignored checks</div>"
                            f"<div class='value' style='font-size:12px'>{ign}</div></div></div>")
        else:
            ignored_html = ""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>STUKACH Report – {report['scene']}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#1a1a1a;color:#d0d0d0;font-family:'Segoe UI',Arial,sans-serif;font-size:13px;padding:24px}}
  h1{{color:#ffffff;font-size:22px;margin-bottom:4px}}
  .subtitle{{color:#888;font-size:11px;margin-bottom:20px}}
  .meta{{display:flex;gap:24px;margin-bottom:20px;flex-wrap:wrap}}
  .meta div{{background:#252525;border:1px solid #333;border-radius:6px;padding:8px 14px}}
  .meta .label{{color:#888;font-size:10px;text-transform:uppercase;letter-spacing:.5px}}
  .meta .value{{color:#fff;font-size:15px;font-weight:bold;margin-top:2px}}
  .status{{color:{status_color};font-size:18px;font-weight:bold}}
  table{{width:100%;border-collapse:collapse;margin-top:12px}}
  th{{background:#2a2a2a;color:#aaa;font-size:11px;text-transform:uppercase;
      letter-spacing:.5px;padding:8px 10px;text-align:left;border-bottom:2px solid #333}}
  td{{padding:7px 10px;border-bottom:1px solid #2a2a2a;vertical-align:top}}
  tr:hover td{{background:#232323}}
  .footer{{margin-top:16px;color:#555;font-size:10px;text-align:right}}
</style>
</head>
<body>
<h1>STUKACH · Pipeline Snitch Report</h1>
<div class="subtitle">{report['tool']} v{report['version']}</div>

<div class="meta">
  <div><div class="label">Status</div><div class="value status">{s['status']}</div></div>
  <div><div class="label">Scene</div><div class="value">{report['scene']}</div></div>
  <div><div class="label">Scope</div><div class="value">{report['scope']}</div></div>
  <div><div class="label">Objects</div><div class="value">{s['objects']}</div></div>
  <div><div class="label">Blockers</div><div class="value" style="color:#e84040">{s['blockers']}</div></div>
  <div><div class="label">Warnings</div><div class="value" style="color:#e8a040">{s['warnings']}</div></div>
  <div><div class="label">Preset</div><div class="value">{report['preset']}</div></div>
  <div><div class="label">Date</div><div class="value">{report['date']}</div></div>
</div>
{ignored_html}
{fix_first_html}

<table>
<thead>
  <tr>
    <th>Object</th><th>Category</th><th>Check</th>
    <th>Severity</th><th>Count</th><th>Detail</th>
  </tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>

{hierarchy_html}

<div class="footer">
  File: {report['file']}<br>
  Generated by STUKACH · Pipeline Snitch System
</div>
</body>
</html>"""
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    # ── execute ────────────────────────────────────────────────────────────────

    def execute(self, context):
        from .manager import MeshCheck
        if not MeshCheck.objects:
            self.report({'WARNING'}, "No validated objects — run STUKACH first")
            return {'CANCELLED'}

        # Use filepath from file dialog; fall back to auto-path if called directly
        ext  = self.fmt.lower()
        path = self.filepath if self.filepath else self._auto_path(ext)

        # Ensure correct extension when user typed a path without one
        if not path.lower().endswith(f".{ext}"):
            path = f"{os.path.splitext(path)[0]}.{ext}"

        report = self._build_report(context)

        try:
            if self.fmt == 'JSON':
                self._write_json(report, path)
            elif self.fmt == 'CSV':
                self._write_csv(report, path)
            else:
                self._write_html(report, path)
        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {e}")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Saved: {path}")
        return {'FINISHED'}


# ── Batch / Scene-wide validation operators ───────────────────────────────────
class ASSET_CHECKER_OT_validate_scene(bpy.types.Operator):
    """Validate all mesh objects in the current scene"""
    bl_idname  = "asset_checker.validate_scene"
    bl_label   = "Validate Scene"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from .manager import MeshCheck, MeshCheckGPU, UVCheckGPU
        wm = context.window_manager
        mc = wm.mesh_check_props
        if not mc.show_overlay:
            mc.show_overlay = True
        # Always ensure GPU handlers are up (covers post-reload where _handler=None
        # but show_overlay was already True so update_overlay never fired)
        MeshCheckGPU.setup_handler()
        UVCheckGPU.setup_handler()
        MeshCheck._scope = "SCENE"
        MeshCheck._scope_collection = ""
        MeshCheck._scene_stale = False
        MeshCheckGPU._batch_cache.clear()
        UVCheckGPU._batch_cache.clear()
        # Progressive: queue the objects — MeshCheckObject instances are built
        # in small timer batches so the UI keeps breathing on large scenes.
        MeshCheck.start_progressive_validation(
            [o for o in context.scene.objects if o.type == "MESH"])

        return {'FINISHED'}


class ASSET_CHECKER_OT_validate_collection(bpy.types.Operator):
    """Validate all mesh objects in the active collection"""
    bl_idname  = "asset_checker.validate_collection"
    bl_label   = "Validate Collection"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return context.collection is not None

    def execute(self, context):
        from .manager import MeshCheck, MeshCheckGPU, UVCheckGPU
        wm  = context.window_manager
        mc  = wm.mesh_check_props
        col = context.collection
        if not mc.show_overlay:
            mc.show_overlay = True
        MeshCheckGPU.setup_handler()
        UVCheckGPU.setup_handler()
        MeshCheck._scope = "COLLECTION"
        MeshCheck._scope_collection = col.name
        MeshCheck._scene_stale = False
        MeshCheckGPU._batch_cache.clear()
        UVCheckGPU._batch_cache.clear()
        MeshCheck.start_progressive_validation(
            [o for o in col.all_objects if o.type == "MESH"])

        return {'FINISHED'}


class ASSET_CHECKER_OT_copy_debug_info(bpy.types.Operator):
    """Copy diagnostic info to the clipboard: versions, session state,
    active checks and the recent addon log. Attach it to bug reports."""
    bl_idname  = "asset_checker.copy_debug_info"
    bl_label   = "Copy Debug Info"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from .manager import get_debug_info
        context.window_manager.clipboard = get_debug_info()
        self.report({'INFO'}, "Debug info copied to clipboard")
        return {'FINISHED'}


class ASSET_CHECKER_OT_clear_validation(bpy.types.Operator):
    """Clear all validated objects and switch back to Selection mode"""
    bl_idname  = "asset_checker.clear_validation"
    bl_label   = "Clear"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from .manager import MeshCheck
        MeshCheck._scope = "SELECTED"
        MeshCheck._scope_collection = ""
        MeshCheck.reset_mesh_check()
        return {'FINISHED'}


# ── Copy Summary — compact validation report to clipboard ────────────────────

# ── UV map renaming ───────────────────────────────────────────────────────────

class ASSET_CHECKER_OT_uv_rename(bpy.types.Operator):
    """Rename UV maps on all validated objects to the selected name.
    Blender deduplicates name collisions with a .001 suffix."""
    bl_idname  = "asset_checker.uv_rename"
    bl_label   = "Rename UV Maps"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        mc = context.window_manager.mesh_check_props
        target = mc.uv_rename_target
        if not target:
            self.report({'WARNING'}, "No target name selected")
            return {'CANCELLED'}

        if mc.uv_rename_all_scene:
            objects = [o for o in context.scene.objects if o.type == 'MESH']
        else:
            objects = list(MeshCheck.objects)

        renamed_layers = 0
        touched = 0
        suffixed = 0
        for obj in objects:
            try:
                uvl = obj.data.uv_layers
            except (ReferenceError, AttributeError):
                continue
            if len(uvl) == 0:
                continue
            obj_touched = False
            for layer in list(uvl):
                if layer.name == target:
                    continue
                layer.name = target
                if layer.name.startswith(target):
                    renamed_layers += 1
                    obj_touched = True
                    if layer.name != target:
                        suffixed += 1     # Blender deduped: target.001
            if obj_touched:
                touched += 1

        if renamed_layers == 0:
            self.report({'INFO'}, f"All UV maps already named '{target}'")
            return {'FINISHED'}

        msg = f"Renamed {renamed_layers} UV layer(s) on {touched} object(s) → '{target}'"
        if suffixed:
            msg += f" ({suffixed} deduplicated with suffix)"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


def _validator_label() -> str:
    """Display name for reports: Preferences field, fallback to OS login."""
    import getpass
    prefs = _get_addon_prefs(bpy.context)
    name = (getattr(prefs, "validator_name", "") or "").strip() if prefs else ""
    return name or getpass.getuser()


def _hierarchy_report_block():
    """Hierarchy scan snapshot for reports — None when never scanned.
    Respects per-node ignores (single source of truth for all consumers)."""
    from .manager import MeshCheck
    from .naming import hierarchy_effective_issues
    hier = MeshCheck.hierarchy_result
    if hier is None:
        return None
    eff = hierarchy_effective_issues(hier)
    return {
        "roots":   len(hier.asset_roots),
        "scanned": hier.objects_scanned,
        "errors":   sum(1 for i in eff if i.severity == "ERROR"),
        "warnings": sum(1 for i in eff if i.severity == "WARNING"),
        "issues": [
            {"object": i.obj_name, "severity": i.severity,
             "rule": i.rule, "message": i.message}
            for i in eff
        ],
    }


def _hierarchy_verdict() -> str:
    """'BLOCKED' / 'REVIEW' / 'CLEAN' / '' (no scan)."""
    block = _hierarchy_report_block()
    if block is None:
        return ""
    if block["errors"]:
        return "BLOCKED"
    if block["warnings"]:
        return "REVIEW"
    return "CLEAN"


class ASSET_CHECKER_OT_copy_summary(bpy.types.Operator):
    """Copy a compact validation summary to the clipboard"""
    bl_idname  = "asset_checker.copy_summary"
    bl_label   = "Copy Summary"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from .manager import MeshCheck, get_addon_version
        from .ui import CHECK_SEVERITY
        mc = context.window_manager.mesh_check_props

        lines = [f"STUKACH v{get_addon_version()} — validation summary"]
        n_tracked = len(MeshCheck.objects)
        obj_word = "object" if n_tracked == 1 else "objects"
        scope = MeshCheck._scope
        if scope == "SCENE":
            lines.append(f"scope: SCENE ({n_tracked} {obj_word})")
        elif scope == "COLLECTION":
            lines.append(f"scope: {MeshCheck._scope_collection} ({n_tracked} {obj_word})")
        else:
            lines.append(f"scope: SELECTION ({n_tracked} {obj_word})")

        rows = []
        total_b = total_w = 0
        for o, mc_obj in MeshCheck.objects.items():
            try:
                o.name
            except ReferenceError:
                continue
            b = w = 0
            worst = None
            for chk_name, checker in mc_obj._checks.items():
                if not getattr(mc, chk_name, False):
                    continue
                c = checker.count
                if c <= 0:
                    continue
                if CHECK_SEVERITY.get(chk_name, "INFO") == "BLOCKER":
                    b += c
                else:
                    w += c
                if worst is None or c > worst[0]:
                    worst = (c, chk_name)
            total_b += b
            total_w += w
            if b or w:
                rows.append((b, w, o.name, worst))
        rows.sort(key=lambda t: (-t[0], -t[1], t[2]))

        from datetime import datetime as _dt

        hier_verdict = _hierarchy_verdict()
        hier_block = _hierarchy_report_block()

        if mc.coordinator_mode:
            # Coordinator report — verdict for the rework task (Cerebro etc.)
            status = "READY" if not total_b and not total_w else ("BLOCKED" if total_b else "REVIEW")
            if hier_verdict == "BLOCKED":
                status = "BLOCKED"
            elif hier_verdict == "REVIEW" and status == "READY":
                status = "REVIEW"
            b_word = "blocker" if total_b == 1 else "blockers"
            w_word = "warning" if total_w == 1 else "warnings"
            lines[0] = (f"STUKACH v{get_addon_version()} — VALIDATION: {status} "
                        f"({total_b} {b_word}, {total_w} {w_word})")
            if total_b:
                lines.append("")
                lines.append("BLOCKERS (fix first):")
                blockers = [r for r in rows if r[0] > 0]
                for b, w, name, worst in blockers[:10]:
                    line = f"  {name}: {b}B"
                    if worst:
                        line += f" (top: {worst[1]})"
                    lines.append(line)
                if len(blockers) > 10:
                    lines.append(f"  …and {len(blockers) - 10} more objects")
            if total_w:
                lines.append("")
                lines.append("WARNINGS:")
                warns = [r for r in rows if r[0] == 0 and r[1] > 0]
                for b, w, name, worst in warns[:10]:
                    line = f"  {name}: {w}W"
                    if worst:
                        line += f" (top: {worst[1]})"
                    lines.append(line)
                if len(warns) > 10:
                    lines.append(f"  …and {len(warns) - 10} more objects")
        else:
            b_word = "blocker" if total_b == 1 else "blockers"
            w_word = "warning" if total_w == 1 else "warnings"
            lines.append(f"issues: {total_b} {b_word}, {total_w} {w_word}")
            for b, w, name, worst in rows[:10]:
                line = f"  {name}: {b}B/{w}W"
                if worst:
                    line += f" (top: {worst[1]})"
                lines.append(line)
            if len(rows) > 10:
                lines.append(f"  …and {len(rows) - 10} more objects")

        # Hierarchy scan — one compact line (artist), full section (coordinator)
        if hier_block is not None:
            if mc.coordinator_mode:
                lines.append("")
                lines.append(f"HIERARCHY: {hier_verdict} "
                             f"({hier_block['errors']} errors, {hier_block['warnings']} warnings, "
                             f"{hier_block['roots']} root(s), {hier_block['scanned']} obj)")
                if hier_block["issues"]:
                    for i in hier_block["issues"][:5]:
                        lines.append(f"  {i['object']}: {i['message']}")
                    if len(hier_block["issues"]) > 5:
                        lines.append(f"  …and {len(hier_block['issues']) - 5} more")
            elif hier_block["errors"] or hier_block["warnings"]:
                lines.append(f"hierarchy: {hier_block['errors']} errors, "
                             f"{hier_block['warnings']} warnings")
            else:
                lines.append(f"hierarchy: clean ({hier_block['roots']} roots, "
                             f"{hier_block['scanned']} obj)")

        lines.append(f"Validated by: {_validator_label()} | "
                     f"{_dt.now().strftime('%Y-%m-%d %H:%M')} | Blender {bpy.app.version_string}")

        context.window_manager.clipboard = "\n".join(lines)
        self.report({'INFO'}, f"Summary copied ({len(rows)} objects with issues)")
        return {'FINISHED'}


class ASSET_CHECKER_OT_next_issue(bpy.types.Operator):
    """Jump to the next object with issues — selects and frames it in the viewport"""
    bl_idname  = "asset_checker.next_issue"
    bl_label   = "Next Issue"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from .manager import MeshCheck
        mc = context.window_manager.mesh_check_props

        # Problem objects in stable worst-first order
        problems = []
        for o, mc_obj in MeshCheck.objects.items():
            try:
                o.name
            except ReferenceError:
                continue
            total = 0
            worst = None      # (count, check_name)
            for chk_name, checker in mc_obj._checks.items():
                if not getattr(mc, chk_name, False):
                    continue
                c = checker.count
                if c > 0:
                    total += c
                    if worst is None or c > worst[0]:
                        worst = (c, chk_name)
            if total > 0:
                problems.append((-total, o.name, o, worst))

        # Hierarchy findings participate too — objects whose ONLY problems are
        # hierarchy issues (they may not even be tracked by the checker).
        # Per-node ignores respected.
        hier = MeshCheck.hierarchy_result
        if hier is not None:
            from .naming import hierarchy_effective_issues
            hier_by_obj: dict = {}
            for issue in hierarchy_effective_issues(hier):
                if issue.obj_name != "[scene]":
                    hier_by_obj[issue.obj_name] = hier_by_obj.get(issue.obj_name, 0) + 1
            known = {name for _, name, _, _ in problems}
            for name, n in hier_by_obj.items():
                if name in known:
                    continue
                obj = bpy.data.objects.get(name)
                if obj is not None:
                    problems.append((-n, name, obj, (n, "hierarchy")))

        if not problems:
            self.report({'INFO'}, "No issues found — mesh is clean")
            return {'CANCELLED'}

        problems.sort(key=lambda t: (t[0], t[1]))
        idx = MeshCheck._next_issue_ptr % len(problems)
        MeshCheck._next_issue_ptr = idx + 1
        neg_total, name, o, worst = problems[idx]

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        o.select_set(True)
        context.view_layer.objects.active = o

        # Frame it in every 3D viewport
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    region = next((rg for rg in area.regions
                                   if rg.type == 'WINDOW'), None)
                    if region is None:
                        continue
                    with context.temp_override(window=window, area=area,
                                               region=region):
                        try:
                            bpy.ops.view3d.view_selected()
                        except Exception:
                            pass

        msg = f"[{idx + 1}/{len(problems)}] {name}: {-neg_total} issue(s)"
        if worst:
            msg += f" — top: {worst[1]} ({worst[0]})"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ── Fix: Remove unused data ───────────────────────────────────────────────────

class ASSET_CHECKER_OT_fix_unused_data(bpy.types.Operator):
    """Clean up data flagged by the Unused Data check: removes empty vertex
    groups and custom attributes left by geometry nodes / external tools.
    Built-in attributes (uv_seam, bevel weights…) are never touched, and
    instance_* attributes are skipped on objects with a Geometry Nodes
    modifier — the nodes may still read them."""
    bl_idname  = "asset_checker.fix_unused_data"
    bl_label   = "Fix: Remove Unused Data"
    bl_options = {'REGISTER', 'UNDO'}

    def _build_plan(self):
        """Collect deletable attrs: [(obj_name, me_users, [attr_names])].

        instance_* attrs on objects with a Geometry Nodes modifier are
        skipped — the nodes read attributes by name and would silently
        change behaviour.  Returns (plan, gn_skipped_count).
        """
        plan = []
        gn_skipped = 0
        for obj, mc_obj in _problem_objects("unused_data"):
            checker = mc_obj._checks.get("unused_data")
            if not checker or not checker._custom_attrs:
                continue
            has_gn = any(m.type == 'NODES' for m in obj.modifiers)
            deletable = []
            for name in checker._custom_attrs:
                if has_gn and name.startswith("instance_"):
                    gn_skipped += 1
                else:
                    deletable.append(name)
            if deletable:
                plan.append((obj.name, obj.data.users, deletable))
        return plan, gn_skipped

    def invoke(self, context, _event):
        self._plan, self._gn_skipped = self._build_plan()
        if not self._plan:
            if self._gn_skipped:
                self.report({'INFO'},
                            f"Nothing safe to delete — {self._gn_skipped} "
                            f"instance_* attr(s) are used by Geometry Nodes")
            else:
                self.report({'INFO'}, "Nothing to clean")
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=430)

    def draw(self, _context):
        col = self.layout.column(align=True)
        n_attrs = sum(len(a) for _, _, a in self._plan)
        col.label(text=f"Delete {n_attrs} attribute(s) on {len(self._plan)} object(s)?")
        col.label(text="Empty vertex groups are removed too.")
        if self._gn_skipped:
            col.label(text=f"Skipped {self._gn_skipped} instance_* attr(s) — Geometry Nodes may read them.",
                      icon="INFO")
        shared = [n for n, u, _ in self._plan if u > 1]
        if shared:
            col.label(text=f"Shared mesh data ({', '.join(shared[:3])}): applies to all linked objects.",
                      icon="LINKED")

    def execute(self, context):
        from .manager import MeshCheck
        if not getattr(self, '_plan', None):
            # Direct/script call without the dialog — build the plan here
            self._plan, self._gn_skipped = self._build_plan()
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        removed_vgroups = 0
        removed_attrs = 0
        shared_hits = []

        # 1. Empty vertex groups
        for obj, mc_obj in list(_problem_objects("unused_data")):
            checker = mc_obj._checks.get("unused_data")
            if not checker:
                continue
            state = _ensure_visible(obj)
            try:
                for vg_name in list(checker._empty_vgroups):
                    vg = obj.vertex_groups.get(vg_name)
                    if vg:
                        obj.vertex_groups.remove(vg)
                        removed_vgroups += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_unused_data(vgroups) {obj.name}: {e}")
            finally:
                _restore_visible(obj, state)

        # 2. Custom attributes — only what was confirmed in the dialog
        for obj_name, me_users, attr_names in self._plan:
            obj = bpy.data.objects.get(obj_name)
            if obj is None:
                continue
            me = obj.data
            state = _ensure_visible(obj)
            try:
                for name in attr_names:
                    attr = me.attributes.get(name)
                    if attr is not None:
                        me.attributes.remove(attr)
                        removed_attrs += 1
            except Exception as e:
                alog(f"[AssetChecker] fix_unused_data {obj_name}: {e}")
            finally:
                _restore_visible(obj, state)
            if me_users > 1:
                shared_hits.append(obj_name)

        MeshCheck.update_mc_object_datas("unused_data")

        msg = f"Removed {removed_attrs} attribute(s), {removed_vgroups} empty vgroup(s)."
        if self._gn_skipped:
            msg += f"  Skipped {self._gn_skipped} GN-linked instance_* attr(s)."
        if shared_hits:
            msg += f"  Shared meshes updated: {', '.join(shared_hits[:5])}"
        self.report({'INFO'}, msg)
        return {'FINISHED'}


# ── Fix: Rename mesh data blocks ─────────────────────────────────────────────

class ASSET_CHECKER_OT_fix_mesh_data_naming(bpy.types.Operator):
    """Rename mesh data blocks to match their object:
    <object root> + first mesh suffix (object suffix stripped, e.g.
    object 'body_geo' → mesh 'body_mesh').  The suffix is configurable in
    Preferences → Naming Policy → Mesh Data."""
    bl_idname  = "asset_checker.fix_mesh_data_naming"
    bl_label   = "Fix: Rename Mesh Data"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck
        renamed = []
        for obj, mc_obj in list(_problem_objects("mesh_data_naming")):
            checker = mc_obj._checks.get("mesh_data_naming")
            if not checker or not checker._target:
                continue
            old = obj.data.name
            try:
                obj.data.name = checker._target
            except Exception as e:
                alog(f"[AssetChecker] fix_mesh_data_naming {obj.name}: {e}")
                continue
            renamed.append(f"{old} → {obj.data.name}")

        MeshCheck.update_mc_object_datas("mesh_data_naming")

        if renamed:
            preview = "; ".join(renamed[:5])
            more = f" (+{len(renamed) - 5} more)" if len(renamed) > 5 else ""
            self.report({'INFO'}, f"Renamed {len(renamed)} mesh data block(s): {preview}{more}")
        else:
            self.report({'INFO'}, "Nothing to rename")
        return {'FINISHED'}


# ── Pre-flight Export ─────────────────────────────────────────────────────────

class ASSET_CHECKER_OT_preflight_export(bpy.types.Operator):
    """Run STUKACH pre-flight check, then open the export dialog.
    CRITICAL issues block export; warnings require confirmation."""
    bl_idname  = "asset_checker.preflight_export"
    bl_label   = "Pre-flight Export"
    bl_options = {'REGISTER'}

    fmt: EnumProperty(
        name="Format",
        items=[('FBX', 'FBX',          'Export as FBX (.fbx)'),
               ('USD', 'USD (USDC)',   'Export as Universal Scene Description')],
        default='FBX',
    )

    # Per-invocation state (Python instance attrs, not RNA — intentional)
    _blocker_count: int = 0
    _warning_count: int = 0
    _is_blocked:   bool = False
    _issues:       list = []   # [(severity, display_label, n_objects), ...]

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _gather_issues(mc) -> list:
        """Return sorted list of (severity, label, n_objects) for all active checks
        that have at least one issue across tracked objects."""
        from .manager import MeshCheck
        from .ui import CHECK_SEVERITY

        tally: dict = {}   # check_name → n objects affected
        for obj, mc_obj in MeshCheck.objects.items():
            try:
                obj.name  # ReferenceError if deleted
            except ReferenceError:
                continue
            for check, checker in mc_obj._checks.items():
                if not getattr(mc, check, False):
                    continue
                if checker.count > 0:
                    tally[check] = tally.get(check, 0) + 1

        issues = []
        for check, n_objs in tally.items():
            sev   = CHECK_SEVERITY.get(check, 'WARNING')
            label = _CHECK_LABELS.get(check, pretty_name(check))
            issues.append((sev, label, n_objs))

        # BLOCKER first, then WARNING; alphabetical within group
        issues.sort(key=lambda x: (0 if x[0] == 'BLOCKER' else 1, x[1]))
        return issues

    def _refresh(self, mc) -> None:
        self._issues        = self._gather_issues(mc)
        self._blocker_count = sum(1 for sev, _, _ in self._issues if sev == 'BLOCKER')
        self._warning_count = sum(1 for sev, _, _ in self._issues if sev != 'BLOCKER')
        self._is_blocked    = bool(self._blocker_count)

    # ── Blender operator methods ──────────────────────────────────────────────

    def invoke(self, context, event):
        from .manager import MeshCheck
        mc = context.window_manager.mesh_check_props

        if not MeshCheck.objects:
            self.report({'WARNING'}, "No validation results — run STUKACH first")
            return {'CANCELLED'}

        self._refresh(mc)

        if self._is_blocked:
            # Popup only — no OK/Cancel, no execute() call
            return context.window_manager.invoke_popup(self, width=390)
        if self._warning_count:
            # Dialog with OK (→ execute) / Cancel
            return context.window_manager.invoke_props_dialog(self, width=390)

        # All clean — open export immediately
        return self._open_export(context)

    def draw(self, context):
        layout = self.layout

        # Header row
        hdr = layout.row()
        if self._is_blocked:
            hdr.alert = True
            hdr.label(
                text=f"Export blocked — {self._blocker_count} critical issue(s)",
                icon="CANCEL",
            )
        else:
            hdr.label(
                text=f"{self._warning_count} warning(s) — export anyway?",
                icon="ERROR",
            )

        # Issue list
        if self._issues:
            box = layout.box()
            col = box.column(align=True)
            for sev, label, n_objs in self._issues:
                row = col.row()
                icon  = "CANCEL" if sev == "BLOCKER" else "DOT"
                noun  = "object" if n_objs == 1 else "objects"
                row.label(text=f"{label}:  {n_objs} {noun}", icon=icon)

        # Footer hint for blocked state
        if self._is_blocked:
            layout.separator(factor=0.5)
            foot = layout.row()
            foot.enabled = False
            foot.label(text="Fix all critical issues before exporting", icon="INFO")

    def execute(self, context):
        # Re-check in case scene changed while dialog was open
        mc = context.window_manager.mesh_check_props
        self._refresh(mc)
        if self._is_blocked:
            self.report(
                {'ERROR'},
                f"Export blocked — {self._blocker_count} critical issue(s) remain",
            )
            return {'CANCELLED'}
        return self._open_export(context)

    def _open_export(self, context):
        try:
            if self.fmt == 'FBX':
                bpy.ops.export_scene.fbx('INVOKE_DEFAULT')
            else:
                bpy.ops.wm.usd_export('INVOKE_DEFAULT')
        except Exception as e:
            self.report({'ERROR'}, f"Export dialog failed: {e}")
            return {'CANCELLED'}
        return {'FINISHED'}


# ── Ignore List helpers ───────────────────────────────────────────────────────

_AC_IGNORE_KEY = "_ac_ignore"


def get_obj_ignore_list(obj) -> set:
    """Return the set of check names permanently ignored on *obj*.

    Reads from the ``_ac_ignore`` custom property (JSON list).
    Returns an empty set when nothing is ignored.
    """
    raw = obj.get(_AC_IGNORE_KEY, "")
    if not raw:
        return set()
    try:
        return set(json.loads(raw))
    except Exception:
        return set()


def set_obj_ignore_list(obj, ignore_set: set) -> None:
    """Persist *ignore_set* as a custom property on *obj*.

    Passing an empty set removes the property entirely
    (keeps Custom Properties panel tidy).
    """
    if ignore_set:
        obj[_AC_IGNORE_KEY] = json.dumps(sorted(ignore_set), ensure_ascii=False)
    elif _AC_IGNORE_KEY in obj:
        del obj[_AC_IGNORE_KEY]


class ASSET_CHECKER_OT_toggle_ignore(bpy.types.Operator):
    """Permanently ignore / un-ignore this check result on this object.
    The decision is stored in the object's custom properties and survives save/reload."""
    bl_idname  = "asset_checker.toggle_ignore"
    bl_label   = "Ignore / Un-ignore Check"
    bl_options = {'REGISTER', 'UNDO'}

    obj_name:   StringProperty(options={'HIDDEN'})
    check_name: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj_name)
        if obj is None:
            self.report({'WARNING'}, f"Object '{self.obj_name}' not found")
            return {'CANCELLED'}

        ignored = get_obj_ignore_list(obj)
        adding  = self.check_name not in ignored

        if adding:
            ignored.add(self.check_name)
        else:
            ignored.discard(self.check_name)

        set_obj_ignore_list(obj, ignored)

        # Re-run the affected check so the overlay + count update immediately
        from .manager import MeshCheck
        MeshCheck.update_mc_object_datas(self.check_name)

        verb = "Ignored" if adding else "Restored"
        self.report({'INFO'}, f"{verb}: {self.check_name} on '{obj.name}'")
        return {'FINISHED'}


class ASSET_CHECKER_OT_clear_ignore_object(bpy.types.Operator):
    """Remove all ignored checks from this object and re-run them."""
    bl_idname  = "asset_checker.clear_ignore_object"
    bl_label   = "Clear Ignores (Object)"
    bl_options = {'REGISTER', 'UNDO'}

    obj_name: StringProperty(options={'HIDDEN'})

    def execute(self, context):
        obj = bpy.data.objects.get(self.obj_name)
        if obj is None:
            return {'CANCELLED'}

        ignored = get_obj_ignore_list(obj)
        if not ignored:
            return {'CANCELLED'}

        set_obj_ignore_list(obj, set())

        # Re-run all previously ignored checks
        from .manager import MeshCheck
        for check_name in ignored:
            MeshCheck.update_mc_object_datas(check_name)

        self.report({'INFO'}, f"Cleared {len(ignored)} ignored check(s) on '{obj.name}'")
        return {'FINISHED'}


class ASSET_CHECKER_OT_clear_all_ignores(bpy.types.Operator):
    """Remove ALL ignored checks from ALL tracked objects."""
    bl_idname  = "asset_checker.clear_all_ignores"
    bl_label   = "Clear All Ignores"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .manager import MeshCheck

        cleared:    set = set()
        total_objs: int = 0

        for obj in list(MeshCheck.objects.keys()):
            try:
                ignored = get_obj_ignore_list(obj)
            except ReferenceError:
                continue
            if not ignored:
                continue
            cleared.update(ignored)
            set_obj_ignore_list(obj, set())
            total_objs += 1

        for check_name in cleared:
            MeshCheck.update_mc_object_datas(check_name)

        self.report({'INFO'}, f"Cleared ignores on {total_objs} object(s)")
        return {'FINISHED'}


# ── Coordinator Mode helpers ──────────────────────────────────────────────────

_AC_CHECKPOINT_KEY = "_ac_checkpoint"


def _compute_current_results(mc) -> dict:
    """Snapshot current validation results into a serialisable dict.

    Returns:
        {
          "objects":  {name: {check: count, "_total": N}},
          "totals":   {"total": N, "blockers": N, "by_category": {cat: N}},
        }
    """
    from .manager import MeshCheck
    from .ui import CHECK_SEVERITY

    obj_results: dict = {}
    for obj, mc_obj in MeshCheck.objects.items():
        try:
            name = obj.name
        except ReferenceError:
            continue
        obj_data: dict = {}
        total = 0
        for check, chk in mc_obj._checks.items():
            if getattr(mc, check, False) and chk.count > 0:
                obj_data[check] = chk.count
                total += chk.count
        obj_data["_total"] = total
        obj_results[name] = obj_data

    # Per-category totals
    by_category: dict = {}
    for cat, checks in CHECK_CATEGORIES.items():
        by_category[cat] = sum(
            obj_results[nm].get(chk, 0)
            for nm in obj_results
            for chk in checks
        )

    total    = sum(d.get("_total", 0) for d in obj_results.values())
    blockers = sum(
        cnt
        for d in obj_results.values()
        for chk, cnt in d.items()
        if chk != "_total" and CHECK_SEVERITY.get(chk) == "BLOCKER"
    )

    return {
        "objects": obj_results,
        "totals": {
            "total":       total,
            "blockers":    blockers,
            "by_category": by_category,
        },
    }


class ASSET_CHECKER_OT_save_checkpoint(bpy.types.Operator):
    """Save current validation results as a coordinator checkpoint.
    The checkpoint is stored inside the .blend file and survives save/reload."""
    bl_idname  = "asset_checker.save_checkpoint"
    bl_label   = "Save Checkpoint"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        from .manager import MeshCheck
        return bool(MeshCheck.objects)

    def execute(self, context):
        mc   = context.window_manager.mesh_check_props
        data = _compute_current_results(mc)
        data["timestamp"] = datetime.now().strftime("%Y-%m-%d  %H:%M")
        context.scene[_AC_CHECKPOINT_KEY] = json.dumps(data, ensure_ascii=False)
        n_obj    = len(data["objects"])
        n_issues = data["totals"]["total"]
        self.report({'INFO'},
                    f"Checkpoint saved — {n_obj} object(s), {n_issues} issue(s)")
        return {'FINISHED'}


class ASSET_CHECKER_OT_clear_checkpoint(bpy.types.Operator):
    """Remove the saved coordinator checkpoint from this .blend file."""
    bl_idname  = "asset_checker.clear_checkpoint"
    bl_label   = "Clear Checkpoint"
    bl_options = {'REGISTER'}

    def execute(self, context):
        if _AC_CHECKPOINT_KEY in context.scene:
            del context.scene[_AC_CHECKPOINT_KEY]
        self.report({'INFO'}, "Checkpoint cleared")
        return {'FINISHED'}


class ASSET_CHECKER_OT_load_checkpoint(bpy.types.Operator):
    """Load a checkpoint from a STUKACH JSON report file.

    Use this in FBX-based pipelines: the artist exports a JSON report
    alongside the FBX, the coordinator loads it here as the comparison baseline.
    Accepts both checkpoint JSON and full validation report JSON formats."""
    bl_idname   = "asset_checker.load_checkpoint"
    bl_label    = "Load Checkpoint from File"
    bl_options  = {'REGISTER'}

    filepath:    StringProperty(subtype='FILE_PATH', options={'HIDDEN'})
    filter_glob: StringProperty(default="*.json", options={'HIDDEN'})

    def invoke(self, context, event):
        # Pre-fill directory from current blend file location
        blend = bpy.data.filepath
        if blend:
            import os
            self.filepath = os.path.dirname(blend) + os.sep
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.report({'ERROR'}, f"Cannot read file: {e}")
            return {'CANCELLED'}

        cp = self._to_checkpoint_fmt(data)
        if cp is None:
            self.report({'ERROR'}, "Unrecognised JSON format — expected STUKACH report or checkpoint")
            return {'CANCELLED'}

        context.scene[_AC_CHECKPOINT_KEY] = json.dumps(cp, ensure_ascii=False)
        n_obj    = len(cp['objects'])
        n_issues = cp['totals']['total']
        self.report({'INFO'},
                    f"Checkpoint loaded — {n_obj} object(s), {n_issues} issue(s)  [{cp['timestamp']}]")
        return {'FINISHED'}

    @staticmethod
    def _to_checkpoint_fmt(data: dict):
        """Convert STUKACH JSON to internal checkpoint format.

        Handles two inputs:
        1. Checkpoint JSON  — objects is a dict {name: {check: count}}
        2. Report JSON      — objects is a list [{name, checks:[{check, count}]}]

        Returns checkpoint dict or None if the format is unrecognised.
        """
        from .ui import CHECK_SEVERITY

        # ── Already a checkpoint (dict-style objects) ────────────────────────
        if (isinstance(data.get("objects"), dict)
                and "totals" in data):
            return data

        # ── Report format (list-style objects) ───────────────────────────────
        obj_list = data.get("objects")
        if not isinstance(obj_list, list):
            return None

        obj_results: dict = {}
        by_category: dict = {cat: 0 for cat in CHECK_CATEGORIES}
        total    = 0
        blockers = 0

        for obj_data in obj_list:
            name = obj_data.get("name", "")
            if not name:
                continue
            chk_dict: dict = {}
            obj_total = 0
            for chk in obj_data.get("checks", []):
                check_name = chk.get("check", "")
                count      = int(chk.get("count", 0))
                cat        = chk.get("category", "")
                if not check_name or count == 0:
                    continue
                chk_dict[check_name] = count
                obj_total += count
                total     += count
                if CHECK_SEVERITY.get(check_name) == "BLOCKER":
                    blockers += count
                if cat in by_category:
                    by_category[cat] += count
            chk_dict["_total"] = obj_total
            obj_results[name]  = chk_dict

        # Normalise timestamp (ISO "2026-05-21T10:30:00" → "2026-05-21  10:30")
        ts = data.get("date", data.get("timestamp", ""))
        if "T" in ts:
            date_part, time_part = ts.split("T", 1)
            ts = f"{date_part}  {time_part[:5]}"   # "YYYY-MM-DD  HH:MM"
        if not ts:
            ts = datetime.now().strftime("%Y-%m-%d  %H:%M")

        return {
            "timestamp": ts,
            "_source":   "report",          # loaded from JSON report, not live session
            "objects":   obj_results,
            "totals": {
                "total":       total,
                "blockers":    blockers,
                "by_category": by_category,
            },
        }


# ─────────────────────────────────────────────────────────────────────────────

class MeshCheckProperties(PropertyGroup):
    check_data:   BoolProperty(name="Check Data",   default=False, update=enable_depsgraph_handler)
    show_overlay: BoolProperty(name="Show Overlay", default=False, update=update_overlay)

    # Coordinator Mode toggle
    coordinator_mode: BoolProperty(
        name="Coordinator Mode",
        default=False,
        description="Switch to coordinator view — compare current results vs saved checkpoint",
    )

    # Live mode — auto re-run checks without pressing Run again
    live_update: BoolProperty(
        name="Live",
        default=False,
        description="Auto re-run checks when meshes change (object mode edits, "
                    "applied modifiers, new scene objects) — no manual re-run needed",
    )

    # View helper — mirror of Blender's built-in Face Orientation overlay
    face_orientation: BoolProperty(
        name="Face Orientation",
        default=False,
        update=update_face_orientation,
        description="Toggle Blender's built-in Face Orientation viewport overlay "
                    "(replaces the old flipped-normals counter — verify visually)",
    )

    # TOPOLOGY
    non_manifold:        BoolProperty(name="Non-manifold",            default=False, update=mc_object_datas_updater("non_manifold"),
                                      description="Edges with other than 2 adjacent faces (T-junctions, wire edges) — breaks booleans, cloth sims and export")
    boundary_edges:      BoolProperty(name="Boundary Edges",          default=False, update=mc_object_datas_updater("boundary_edges"),
                                      description="Open mesh borders (edges with exactly one adjacent face)")
    isolated_verts:      BoolProperty(name="Isolated Vertices",       default=False, update=mc_object_datas_updater("isolated_verts"),
                                      description="Vertices not connected to any edge")
    duplicate_verts:     BoolProperty(name="Duplicate Vertices",      default=False, update=mc_object_datas_updater("duplicate_verts"),
                                      description="Overlapping vertices within one connected shell (0.01 mm) — would merge on Merge by Distance. Coincident verts of DIFFERENT shells are intentional and not flagged")
    face_aspect_ratio:   BoolProperty(name="Face Aspect Ratio",       default=False, update=mc_object_datas_updater("face_aspect_ratio"),
                                      description="Quads with aspect ratio exceeding threshold (default 6:1) — causes stretching artifacts under subdivision")
    triangles:           BoolProperty(name="Triangles",               default=False, update=mc_object_datas_updater("triangles"),
                                      description="Triangular faces — midpoly workflow tolerates them; critical in deform zones and under subdivision")
    ngons:               BoolProperty(name="Ngons",                   default=False, update=mc_object_datas_updater("ngons"),
                                      description="Faces with 5+ edges — unpredictable renderer triangulation, normal artifacts on hard surfaces")
    poles:               BoolProperty(name="Poles",                   default=False, update=mc_object_datas_updater("poles"),
                                      description="Interior vertices with non-standard edge count (3, 5, >5) — affects subdivision and skinning, often intentional")
    zero_area:           BoolProperty(name="Zero-area faces",         default=False, update=mc_object_datas_updater("zero_area"),
                                      description="Degenerate faces with near-zero area — NaN normals, broken UVs. Caused by boolean, knife, merge")
    z_fighting:          BoolProperty(name="Z-Fighting",              default=False, update=mc_object_datas_updater("z_fighting"),
                                      description="Coplanar face overlap within the mesh and between tracked objects")
    lamina:              BoolProperty(name="Lamina",                  default=False, update=mc_object_datas_updater("lamina"),
                                      description="Zero-thickness faces folded onto themselves (contour reuses an edge or vertex) — break booleans, subdivision and export")
    zero_length_edges:   BoolProperty(name="Zero Length Edges",       default=False, update=mc_object_datas_updater("zero_length_edges"),
                                      description="Edges of near-zero length (below 1e-8) — degenerate geometry from merges and booleans")
    starlike:            BoolProperty(name="Starlike",                default=False, update=mc_object_datas_updater("starlike"),
                                      description="Faces whose outline self-intersects when projected onto the face plane (non-starlike) — unpredictable triangulation and shading")
    sharp_edges_not_hard: BoolProperty(name="Sharp Edges Not Hard",  default=False, update=mc_object_datas_updater("sharp_edges_not_hard"),
                                      description="Edges with a dihedral angle of 30° or more that are NOT marked sharp — smooth shading across a sharp corner causes shading artifacts")

    # TRANSFORMS
    non_applied_transform: BoolProperty(name="Non-applied rotation", default=False, update=mc_object_datas_updater("non_applied_transform"),
                                      description="Non-zero object rotation — changes normal directions on export, breaks physics and bone orientation")
    scale:                 BoolProperty(name="Scale (not 1.0)",      default=False, update=mc_object_datas_updater("scale"),
                                      description="Scale other than 1.0 on any axis — distorts simulations, skeleton deformation and texel density")
    origin_at_zero:        BoolProperty(name="Origin not at zero",   default=False, update=mc_object_datas_updater("origin_at_zero"),
                                        description="Object pivot point is not at world origin (0, 0, 0)")
    modifier_stack:        BoolProperty(name="Modifier Stack",       default=False, update=mc_object_datas_updater("modifier_stack"),
                                        description="Unapplied modifiers present on object (pipeline non-whitelisted)")
    uncentered_pivots:     BoolProperty(name="Uncentered Pivots",    default=False, update=mc_object_datas_updater("uncentered_pivots"),
                                        description="Pivot is further than 5% of the bbox diagonal from the bbox center — rotates around a wrong point, breaks rigging and mirroring")
    parent_geometry:       BoolProperty(name="Parent Geometry",      default=False, update=mc_object_datas_updater("parent_geometry"),
                                        description="Object parented under another mesh object — breaks export hierarchies")

    # SYMMETRY
    symmetry_x: BoolProperty(name="Symmetry X", default=False, update=mc_object_datas_updater("symmetry_x"),
                             description="Vertices without a mirror pair across the X axis (KD-tree)")
    symmetry_y: BoolProperty(name="Symmetry Y", default=False, update=mc_object_datas_updater("symmetry_y"),
                             description="Vertices without a mirror pair across the Y axis (KD-tree)")
    symmetry_z: BoolProperty(name="Symmetry Z", default=False, update=mc_object_datas_updater("symmetry_z"),
                             description="Vertices without a mirror pair across the Z axis (KD-tree)")

    # UV
    uv_single_set:    BoolProperty(name="Single UV Set",        default=False, update=mc_object_datas_updater("uv_single_set"),
                                   description="Mesh must have exactly one UV map")
    uv_overlap:       BoolProperty(name="UV Overlap",           default=False, update=mc_object_datas_updater("uv_overlap"),
                                   description="Overlapping UV islands — identical texels for different polygons, impossible to bake unique textures")
    uv_micro_shell:   BoolProperty(name="UV Micro-shells",      default=False, update=mc_object_datas_updater("uv_micro_shell"),
                                   description="UV islands too small for texturing (below area threshold) — waste atlas space, blurry texels")
    uv_texel_density: BoolProperty(name="Texel Density",        default=False, update=mc_object_datas_updater("uv_texel_density"),
                                   description="Texel density in px/cm shown as metric; becomes a control only when a target TD is set")
    uv_stretch:       BoolProperty(name="UV Stretch",           default=False, update=mc_object_datas_updater("uv_stretch"),
                                   description="Faces where the UV-space angle deviates from the 3D angle — texture distortion")
    uv_padding:       BoolProperty(name="UV Padding",           default=False, update=mc_object_datas_updater("uv_padding"),
                                   description="UV shells closer than the padding threshold — bleeding during mip-mapping")
    uv_udim_bounds:   BoolProperty(name="UDIM Bounds",          default=False, update=mc_object_datas_updater("uv_udim_bounds"),
                                   description="UV islands crossing UDIM tile boundaries — cannot assign a correct UDIM texture")
    uv_material_udim: BoolProperty(name="Uv Material Udim",         default=False, update=mc_object_datas_updater("uv_material_udim"),
                                   description="Each UDIM tile must contain shells from one material only (регламент: 1 UDIM = 1 material group)")
    missing_uvs:      BoolProperty(name="Missing UVs",          default=False, update=mc_object_datas_updater("missing_uvs"),
                                   description="Faces without UV mapping (no UV layer, or all loops at 0,0) — unpacked geometry, broken texel lookups in bake")

    # NAMING
    obj_naming:    BoolProperty(name="Object Name",   default=False, update=update_obj_naming,
                                description="Object names against naming policy: default names, .001 numbering, case, prefix/suffix rules")
    col_naming:    BoolProperty(name="Group Name",    default=False, update=mc_object_datas_updater("col_naming"),
                                description="Collection names against naming policy")
    mesh_data_naming: BoolProperty(name="Mesh Data Name", default=False, update=mc_object_datas_updater("mesh_data_naming"),
                                description="Mesh data block must not keep Blender auto-names ('Mesh.101') — rename to <object>_mesh. Suffix configurable in Preferences")
    mat_numbering: BoolProperty(name="Mat Numbering", default=False, update=mc_object_datas_updater("mat_numbering"),
                                description="Material names must not contain Blender auto-numbering (.001, .002 ...)")
    duplicated_names: BoolProperty(name="Duplicated Names", default=False, update=mc_object_datas_updater("duplicated_names"),
                                description="Exact object name used by more than one object in the scene (linked-library collisions) — breaks export and pipeline collection")
    trailing_numbers: BoolProperty(name="Trailing Numbers", default=False, update=mc_object_datas_updater("trailing_numbers"),
                                description="Object name ends with digits (Cube.001-style leftovers) — rename with a proper suffix")

    # Inline naming policy fields — combined with prefs at validation time
    obj_required_prefix: StringProperty(name="Prefix", default="",
                                        description="Required object name prefix (e.g. 'sm_')")
    obj_required_suffix: StringProperty(name="Suffix", default="",
                                        description="Required object name suffix (e.g. '_geo')")
    col_required_prefix: StringProperty(name="Prefix", default="",
                                        description="Required group name prefix (e.g. 'grp_')")
    col_required_suffix: StringProperty(name="Suffix", default="",
                                        description="Required group name suffix (e.g. '_grp')")
    mesh_required_suffix: StringProperty(name="Mesh Suffix", default="_mesh",
                                        description="Required mesh data block suffix (e.g. '_mesh'). Used by the Mesh Data Name check and its Fix button")

    # TD scope toggle — controls UV Space / Density summary in UV panel
    uv_td_scope_active: BoolProperty(
        name="Active Object Only",
        default=False,
        description="Show UV Space and Density for the active object only (off = all validated objects)",
    )

    # MATERIALS
    mat_suffix:       BoolProperty(name="Material Suffix (_mat)", default=False, update=mc_object_datas_updater("mat_suffix"),
                                   description="Material names must end with the _mat suffix")
    mat_assignment:   BoolProperty(name="Material Assignment",    default=False, update=mc_object_datas_updater("mat_assignment"),
                                   description="Empty material slots (slot exists, no material) — black geometry in render")
    missing_textures: BoolProperty(name="Missing Textures",       default=False, update=mc_object_datas_updater("missing_textures"),
                                   description="Detect missing texture files referenced in material node trees")

    # SCENE-LEVEL check (not per-object — drawn at top of panel)
    scene_units: BoolProperty(
        name="Scene Units",
        default=False,
        description="Scene must use METRIC / METERS with scale_length = 1.0",
    )

    # Category collapsed state — False = collapsed by default for compact startup
    cat_topology_open:   BoolProperty(name="Topology",   default=False)
    cat_transforms_open: BoolProperty(name="Transforms", default=False)
    cat_symmetry_open:   BoolProperty(name="Symmetry",   default=False)
    cat_uv_open:         BoolProperty(name="UV",         default=False)
    cat_naming_open:     BoolProperty(name="Naming",     default=False)
    cat_materials_open:  BoolProperty(name="Materials",  default=False)

    # Object list section — collapsed by default to keep the panel clean
    obj_list_open: BoolProperty(
        name="Object List",
        default=False,
        description="Show / hide the per-object details list",
    )
    uv_obj_list_open: BoolProperty(
        name="UV Object List",
        default=False,
        description="Show / hide the per-object UV results list in the UV Editor",
    )

    # UDIM Padding Map — collapse toggle in UV panel
    uv_padding_stats_open: BoolProperty(
        name="UDIM Padding Map",
        default=True,
        description="Expand / collapse the per-UDIM padding statistics block",
    )

    # Object list filter
    obj_filter_text: StringProperty(
        name="Search",
        default="",
        description="Filter objects by name",
    )
    obj_filter_errors_only: BoolProperty(
        name="Issues Only",
        default=False,
        description="Show only objects that have at least one active issue",
    )
    uv_rename_target: EnumProperty(
        name="Rename To",
        items=_uv_rename_items,
        description="Target UV map name (DCC conventions + names detected on validated objects)",
    )
    uv_rename_all_scene: BoolProperty(
        name="All Scene Objects",
        default=False,
        description="Rename UV maps on ALL mesh objects in the scene, not only validated ones",
    )

    # Health-strip swatch colors — written by _compute_asset_summary (ui.py),
    # drawn as color cells in the score block. Hover a cell: category + legend.
    # Colors live as RNA props because panels have no other sanctioned way
    # to show real colors.
    hs_topology: FloatVectorProperty(name="Topology", subtype='COLOR', size=4,
                                       min=0.0, max=1.0, default=(0.25, 0.8, 0.35, 1.0),
                                       description="Topology: green = clean, yellow = warnings, red = blockers")
    hs_transforms: FloatVectorProperty(name="Transforms", subtype='COLOR', size=4,
                                       min=0.0, max=1.0, default=(0.25, 0.8, 0.35, 1.0),
                                       description="Transforms: green = clean, yellow = warnings, red = blockers")
    hs_symmetry: FloatVectorProperty(name="Symmetry", subtype='COLOR', size=4,
                                       min=0.0, max=1.0, default=(0.25, 0.8, 0.35, 1.0),
                                       description="Symmetry: green = clean, yellow = warnings, red = blockers")
    hs_uv: FloatVectorProperty(name="UV", subtype='COLOR', size=4,
                                       min=0.0, max=1.0, default=(0.25, 0.8, 0.35, 1.0),
                                       description="UV: green = clean, yellow = warnings, red = blockers")
    hs_naming: FloatVectorProperty(name="Naming", subtype='COLOR', size=4,
                                       min=0.0, max=1.0, default=(0.25, 0.8, 0.35, 1.0),
                                       description="Naming: green = clean, yellow = warnings, red = blockers")
    hs_materials: FloatVectorProperty(name="Materials", subtype='COLOR', size=4,
                                       min=0.0, max=1.0, default=(0.25, 0.8, 0.35, 1.0),
                                       description="Materials: green = clean, yellow = warnings, red = blockers")
    hs_cleanup: FloatVectorProperty(name="Cleanup", subtype='COLOR', size=4,
                                       min=0.0, max=1.0, default=(0.25, 0.8, 0.35, 1.0),
                                       description="Cleanup: green = clean, yellow = warnings, red = blockers")

    # Progressive validation progress (0..1), updated by the validation timer
    validation_progress: FloatProperty(
        name="Validation Progress",
        min=0.0, max=1.0, default=0.0,
    )
    obj_filter_check: EnumProperty(
        name="Check Filter",
        items=_check_filter_items,
        description="Show only objects with issues from the selected check",
    )
    obj_sort_worst: BoolProperty(
        name="Worst First",
        default=False,
        description="Sort the object list by total issue count — worst objects on top",
    )

    # Material → UDIM highlight selection (UV panel)
    mat_udim_selected: StringProperty(
        name="Selected Material",
        default="",
        description="Material currently highlighted in the UV editor (click to toggle)",
    )

    # CLEANUP
    unused_data: BoolProperty(
        name="Unused Data",
        default=False,
        update=mc_object_datas_updater("unused_data"),
        description="Empty vertex groups and leftover custom mesh attributes",
    )

    # Category collapse — Cleanup
    cat_cleanup_open: BoolProperty(name="Cleanup", default=True)

    # Hierarchy block — section collapse toggle
    hierarchy_block_open: BoolProperty(
        name="Hierarchy",
        default=False,
        description="Expand / collapse the Hierarchy validator block",
    )
    # Hierarchy block — flat list of problem objects instead of full tree
    hierarchy_issues_only: BoolProperty(
        name="Issues Only",
        default=False,
        description="Show only objects with hierarchy findings (off = full tree per asset root)",
    )

    # Naming Audit block — section collapse toggle
    naming_audit_open: BoolProperty(
        name="Naming Audit",
        default=False,
        description="Expand / collapse the Naming Audit block",
    )

    # Ignore List section toggle
    ignore_list_open: BoolProperty(
        name="Ignore List",
        default=False,
        description="Show / hide ignored checks across all tracked objects",
    )

    checker_options = tuple(item for sublist in CHECK_CATEGORIES.values() for item in sublist)

    def draw_options(self, layout, severity_filter=None):
        """Draw the check grid.

        severity_filter – if given, only show checks whose CHECK_SEVERITY level
        is in the set.  E.g. {'BLOCKER', 'WARNING'} for Coordinator Mode.
        Categories where all checks are filtered out are hidden entirely.
        """
        from .manager import MeshCheck
        from .ui import CHECK_SEVERITY  # lazy import to avoid circular
        addon_name = __name__.rsplit(".", 1)[0]
        try:
            addon_prefs = bpy.context.preferences.addons[addon_name].preferences
        except Exception:
            addon_prefs = None

        for cat_name, checks in CHECK_CATEGORIES.items():
            # Apply severity filter — skip categories where nothing passes
            if severity_filter:
                visible_checks = [c for c in checks
                                  if CHECK_SEVERITY.get(c, 'INFO') in severity_filter]
                if not visible_checks:
                    continue
            else:
                visible_checks = list(checks)

            open_prop = f"cat_{cat_name.lower()}_open"
            is_open   = getattr(self, open_prop, True)

            box = layout.box()

            # ── Collapsible header ─────────────────────────────────────────
            # The spacer label after the name is what pushes the Fix button
            # and the on/off checkbox to the right edge (labels expand to
            # fill the row).
            header = box.row(align=True)
            header.prop(
                self, open_prop,
                text="",
                icon="TRIA_DOWN" if is_open else "TRIA_RIGHT",
                emboss=False,
            )
            header.label(
                text=pretty_name(cat_name),
                icon=_CAT_ICONS.get(cat_name, "DOT"),
            )
            header.label(text="")

            # Fix button — only when at least one fixable check in the category has issues
            if MeshCheck.objects:
                cat_has_fix = any(
                    _FIX_OPERATORS.get(c)
                    and getattr(self, c, False)
                    and any(
                        mc_obj._checks.get(c) and mc_obj._checks[c].count > 0
                        for mc_obj in MeshCheck.objects.values()
                    )
                    for c in visible_checks
                )
                if cat_has_fix:
                    fix_op = header.operator(
                        "asset_checker.fix_category",
                        text="Fix",
                        icon="TOOL_SETTINGS",
                    )
                    fix_op.category = cat_name

            any_on = any(getattr(self, c, False) for c in visible_checks if hasattr(self, c))
            op = header.operator(
                "mesh_check.toggle_category",
                text="",
                icon="CHECKBOX_HLT" if any_on else "CHECKBOX_DEHLT",
                emboss=False,
            )
            op.category = cat_name

            # Hierarchy follows Naming even when the category is collapsed
            if not is_open:
                if cat_name == "NAMING":
                    hier_box = layout.box()
                    try:
                        from .ui import draw_hierarchy_block
                        draw_hierarchy_block(hier_box, self)
                    except Exception as _he:
                        alog(f"[AssetChecker] hierarchy block draw error: {_he}")
                continue

            # ── Check grid ─────────────────────────────────────────────────
            row = box.row(align=True)
            col_1 = row.column()
            col_2 = row.column()

            for i, check in enumerate(visible_checks):
                col = col_1 if i % 2 == 0 else col_2
                r = col.row(align=True)
                icon = "CHECKBOX_HLT" if getattr(self, check, False) else "CHECKBOX_DEHLT"
                label = _CHECK_LABELS.get(check, pretty_name(check))
                r.prop(self, check, icon=icon, emboss=False, text=label)

                if addon_prefs and hasattr(addon_prefs, f"{check}_color"):
                    c = r.row()
                    c.scale_x = 0.15
                    c.scale_y = 0.8
                    c.alignment = "RIGHT"
                    c.prop(addon_prefs, f"{check}_color", text="")

            # ── Inline UV actions: map names + rename (PROKLADKA conventions) ─
            if cat_name == "UV" and MeshCheck.objects:
                from collections import Counter
                _unames = Counter()
                for _o in MeshCheck.objects:
                    try:
                        for _l in _o.data.uv_layers:
                            _unames[_l.name] += 1
                    except Exception:
                        continue
                if _unames:
                    box.separator(factor=0.3)
                    box.label(
                        text="UV Names: " + "  ·  ".join(
                            f"{n} ×{c}" for n, c in _unames.most_common()),
                        icon="UV_DATA",
                    )
                    _rn = box.row(align=True)
                    _rn.prop(self, "uv_rename_target", text="")
                    _rn.operator("asset_checker.uv_rename", text="Rename")
                    box.prop(self, "uv_rename_all_scene", text="All Scene Objects",
                             icon="OUTLINER_OB_MESH")

            # ── Inline CLEANUP actions ─────────────────────────────────────
            if cat_name == "CLEANUP":
                box.separator(factor=0.3)
                col = box.column(align=True)
                col.operator(
                    "asset_checker.fix_unused_data",
                    text="Remove Empty Vertex Groups",
                    icon="GROUP_VERTEX",
                )
                col.operator(
                    "object.material_slot_remove_unused",
                    text="Remove Unused Material Slots",
                    icon="MATERIAL",
                )
                col.separator(factor=0.5)
                op = col.operator(
                    "outliner.orphans_purge",
                    text="Purge Orphan Data-Blocks",
                    icon="ORPHAN_DATA",
                )
                op.do_local_ids = True
                op.do_linked_ids = False
                op.do_recursive  = True

            # ── Inline naming policy fields ────────────────────────────────
            if cat_name == "NAMING":
                box.separator(factor=0.5)
                split = box.row(align=False)

                obj_col = split.column(align=True)
                obj_col.label(text="Objects:", icon="OBJECT_DATA")
                obj_col.prop(self, "obj_required_prefix", text="Prefix")
                obj_col.prop(self, "obj_required_suffix", text="Suffix")

                grp_col = split.column(align=True)
                grp_col.label(text="Groups:", icon="OUTLINER_COLLECTION")
                grp_col.prop(self, "col_required_prefix", text="Prefix")
                grp_col.prop(self, "col_required_suffix", text="Suffix")

                mesh_col = split.column(align=True)
                mesh_col.label(text="Mesh:", icon="MESH_DATA")
                mesh_col.label(text="")   # align with Prefix rows — mesh has no prefix rule
                mesh_col.prop(self, "mesh_required_suffix", text="Suffix")

                box.operator(
                    "asset_checker.check_naming",
                    text="Check Naming",
                    icon="VIEWZOOM",
                )

                # ── Naming Audit sub-section ────────────────────────────────
                box.separator(factor=0.3)
                try:
                    from .ui import draw_naming_audit_block
                    draw_naming_audit_block(box, self)
                except Exception as _ne:
                    alog(f"[AssetChecker] naming audit block draw error: {_ne}")

            # ── Hierarchy validator — standalone block right after Naming ──────
            if cat_name == "NAMING":
                hier_box = layout.box()
                try:
                    from .ui import draw_hierarchy_block
                    draw_hierarchy_block(hier_box, self)
                except Exception as _he:
                    alog(f"[AssetChecker] hierarchy block draw error: {_he}")

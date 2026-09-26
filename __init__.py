# -*- coding:utf-8 -*-
# Metadata is defined in blender_manifest.toml (Blender 4.2+ extension standard).

import bpy
import json
from bpy.props import BoolProperty, PointerProperty

if "bpy" in locals():
    import importlib
    from . import core, naming, preferences, properties, ui, manager, update_checker
    importlib.reload(core)
    importlib.reload(naming)
    importlib.reload(preferences)
    importlib.reload(properties)
    importlib.reload(ui)
    importlib.reload(manager)
    importlib.reload(update_checker)
else:
    from . import core, naming, preferences, properties, ui, manager, update_checker

classes = (
    # NamingEntry must precede MeshCheckPreferences (CollectionProperty type dependency)
    preferences.NamingEntry,
    # StukachPresetItem must precede MeshCheckPreferences (CollectionProperty type dependency)
    preferences.StukachPresetItem,
    # Object naming policy operators
    preferences.ASSET_CHECKER_OT_naming_add_prefix,
    preferences.ASSET_CHECKER_OT_naming_remove_prefix,
    preferences.ASSET_CHECKER_OT_naming_add_suffix,
    preferences.ASSET_CHECKER_OT_naming_remove_suffix,
    # Collection naming policy operators
    preferences.ASSET_CHECKER_OT_col_naming_add_prefix,
    preferences.ASSET_CHECKER_OT_col_naming_remove_prefix,
    preferences.ASSET_CHECKER_OT_col_naming_add_suffix,
    preferences.ASSET_CHECKER_OT_col_naming_remove_suffix,
    preferences.ASSET_CHECKER_OT_mesh_naming_add_suffix,
    preferences.ASSET_CHECKER_OT_mesh_naming_remove_suffix,
    preferences.ASSET_CHECKER_OT_hierarchy_layer_add,
    preferences.ASSET_CHECKER_OT_hierarchy_layer_remove,
    preferences.MeshCheckPreferences,
    preferences.ASSET_CHECKER_OT_profile_apply,
    properties.MESH_CHECK_OT_toggle_category,
    properties.ASSET_CHECKER_OT_select_check_elements,
    properties.ASSET_CHECKER_OT_set_td_target,
    properties.ASSET_CHECKER_OT_check_naming,
    properties.ASSET_CHECKER_OT_highlight_mat_udim,
    properties.ASSET_CHECKER_OT_collapse_objects,
    properties.ASSET_CHECKER_OT_fix_transforms,
    properties.ASSET_CHECKER_OT_fix_scale,
    properties.ASSET_CHECKER_OT_fix_origin,
    properties.ASSET_CHECKER_OT_fix_modifier_stack,
    properties.ASSET_CHECKER_OT_fix_merge_by_distance,
    properties.ASSET_CHECKER_OT_fix_zero_area,
    properties.ASSET_CHECKER_OT_fix_ngons,
    properties.ASSET_CHECKER_OT_fix_lamina,
    properties.ASSET_CHECKER_OT_fix_sharp_edges,
    properties.ASSET_CHECKER_OT_fix_mat_numbering,
    properties.ASSET_CHECKER_OT_fix_uv_single_set,
    properties.ASSET_CHECKER_OT_fix_naming,
    properties.ASSET_CHECKER_OT_fix_unused_data,
    properties.ASSET_CHECKER_OT_fix_mesh_data_naming,
    properties.ASSET_CHECKER_OT_copy_debug_info,
    properties.ASSET_CHECKER_OT_fix_mat_suffix,
    properties.ASSET_CHECKER_OT_fix_category,
    properties.ASSET_CHECKER_OT_export_report,
    properties.ASSET_CHECKER_OT_preflight_export,
    properties.ASSET_CHECKER_OT_save_checkpoint,
    properties.ASSET_CHECKER_OT_clear_checkpoint,
    properties.ASSET_CHECKER_OT_load_checkpoint,
    properties.ASSET_CHECKER_OT_toggle_ignore,
    properties.ASSET_CHECKER_OT_clear_ignore_object,
    properties.ASSET_CHECKER_OT_clear_all_ignores,
    properties.ASSET_CHECKER_OT_validate_scene,
    properties.ASSET_CHECKER_OT_validate_collection,
    properties.ASSET_CHECKER_OT_clear_validation,
    properties.ASSET_CHECKER_MT_presets,
    properties.ASSET_CHECKER_MT_preset_export,
    properties.ASSET_CHECKER_OT_preset_add,
    properties.ASSET_CHECKER_OT_preset_remove,
    properties.ASSET_CHECKER_OT_preset_export,
    properties.ASSET_CHECKER_OT_preset_import,
    properties.ASSET_CHECKER_OT_next_issue,
    properties.ASSET_CHECKER_OT_copy_summary,
    properties.ASSET_CHECKER_OT_uv_rename,
    properties.MeshCheckProperties,
    ui.ASSET_CHECKER_PT_Panel,
    ui.ASSET_CHECKER_PT_UV_Panel,
    naming.ASSET_CHECKER_OT_select_object,
    naming.ASSET_CHECKER_OT_run_naming_audit,
    naming.ASSET_CHECKER_OT_clear_naming_audit,
    naming.ASSET_CHECKER_OT_scan_hierarchy,
    naming.ASSET_CHECKER_OT_clear_hierarchy,
    naming.ASSET_CHECKER_OT_hierarchy_toggle_root,
    naming.ASSET_CHECKER_OT_hierarchy_toggle_rule,
    naming.ASSET_CHECKER_OT_hierarchy_ignore_toggle,
    naming.ASSET_CHECKER_OT_hierarchy_clear_ignores,
    naming.ASSET_CHECKER_OT_hierarchy_fix_grp_suffix,
    naming.ASSET_CHECKER_OT_hierarchy_fix_renumber,
    naming.ASSET_CHECKER_OT_hierarchy_fix_adopt,
    naming.ASSET_CHECKER_OT_hierarchy_fix_create_root,
    naming.ASSET_CHECKER_OT_hierarchy_create_skeleton,
)


def register():
    for cls in classes:
        try:
            if hasattr(bpy.types, cls.__name__):
                bpy.utils.unregister_class(getattr(bpy.types, cls.__name__))
            bpy.utils.register_class(cls)
        except Exception as e:
            print(f"[AssetChecker] Warning: {e}")

    update_checker.register()

    # Next Issue hotkey (respects the Preferences toggle)
    try:
        properties._register_hotkey()
    except Exception as e:
        print(f"[AssetChecker] hotkey register: {e}")

    # Viewport HUD
    try:
        manager.ViewportHUD.register()
    except Exception as e:
        print(f"[AssetChecker] HUD register: {e}")

    bpy.types.WindowManager.mesh_check_props = PointerProperty(
        type=properties.MeshCheckProperties)

    bpy.types.Object.mesh_check_statistics = BoolProperty(
        name="Toggle Visibility",
        default=False)

    # Seed the mesh-data suffix list with the pipeline default on first run
    try:
        prefs = bpy.context.preferences.addons.get(__name__)
        if prefs is None:
            prefs = bpy.context.preferences.addons.get(__name__.rsplit(".", 1)[0])
        if prefs is not None and not len(prefs.preferences.mesh_naming_suffixes):
            prefs.preferences.mesh_naming_suffixes.add().value = "_mesh"
    except Exception as e:
        print(f"[AssetChecker] mesh suffix seed: {e}")

    from .manager import register_state_handlers
    register_state_handlers()

    # Migrate legacy pref-collection presets (<= 1.4.1) to native preset files
    try:
        import os
        from .properties import _preset_dir
        prefs = bpy.context.preferences.addons.get(__name__)
        if prefs is None:
            prefs = bpy.context.preferences.addons.get(__name__.rsplit(".", 1)[0])
        if prefs is not None:
            pref = prefs.preferences
            for item in list(pref.presets):
                try:
                    flags = json.loads(item.checks_json)
                    lines = ["import bpy",
                             "mc = bpy.context.window_manager.mesh_check_props"]
                    for key, val in flags.items():
                        lines.append(f"mc.{key} = {val!r}")
                    dst = os.path.join(_preset_dir(), f"{item.name}.py")
                    with open(dst, "w", encoding="utf-8") as fh:
                        fh.write("\n".join(lines) + "\n")
                except Exception:
                    pass
            while len(pref.presets):
                pref.presets.remove(0)
    except Exception:
        pass


def unregister():
    try:
        manager.ViewportHUD.unregister()
    except Exception as e:
        print(f"[AssetChecker] HUD unregister: {e}")

    try:
        properties._unregister_hotkey()
    except Exception as e:
        print(f"[AssetChecker] hotkey unregister: {e}")

    try:
        from .manager import unregister_state_handlers
        unregister_state_handlers()
    except Exception as e:
        print(f"[AssetChecker] unregister_state_handlers: {e}")

    try:
        update_checker.unregister()
    except Exception as e:
        print(f"[AssetChecker] unregister update_checker: {e}")

    try:
        from .manager import MeshCheck, MeshCheckGPU, UVCheckGPU
    except Exception as e:
        print(f"[AssetChecker] unregister: manager unavailable ({e})")
        for cls in reversed(classes):
            try:
                bpy.utils.unregister_class(cls)
            except Exception:
                pass
        return

    if hasattr(bpy.app.handlers, 'depsgraph_update_post'):
        if MeshCheck.callback in bpy.app.handlers.depsgraph_update_post:
            try:
                bpy.app.handlers.depsgraph_update_post.remove(MeshCheck.callback)
            except Exception:
                pass

    if MeshCheckGPU._handler:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(MeshCheckGPU._handler, 'WINDOW')
            MeshCheckGPU._handler = None
        except Exception:
            pass

    if UVCheckGPU._handler:
        try:
            bpy.types.SpaceImageEditor.draw_handler_remove(UVCheckGPU._handler, 'WINDOW')
            UVCheckGPU._handler = None
        except Exception:
            pass

    try:
        from .naming import NamingMarker, NamingAudit
        NamingMarker.remove()
        NamingAudit.clear()
    except Exception:
        pass

    for mc in list(MeshCheck.objects.values()):
        try:
            mc._drop_cached_bm()
        except Exception:
            pass
    MeshCheck.objects.clear()

    try:
        del bpy.types.Object.mesh_check_statistics
    except Exception:
        pass
    try:
        del bpy.types.WindowManager.mesh_check_props
    except Exception:
        pass

    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass


if __name__ == "__main__":
    register()

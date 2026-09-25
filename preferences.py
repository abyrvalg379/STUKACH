# -*- coding:utf-8 -*-
import bpy
from bpy.types import AddonPreferences, PropertyGroup
from bpy.props import (FloatVectorProperty, FloatProperty, StringProperty,
                       CollectionProperty, IntProperty, EnumProperty,
                       BoolProperty)


# ── Naming policy entry (one prefix or suffix) ────────────────────────────────

class NamingEntry(PropertyGroup):
    """Single configurable naming prefix or suffix."""
    value: StringProperty(name="", default="")


# ── Naming policy operators ───────────────────────────────────────────────────

class ASSET_CHECKER_OT_naming_add_prefix(bpy.types.Operator):
    """Add a required object name prefix"""
    bl_idname = "asset_checker.naming_add_prefix"
    bl_label = "Add Prefix"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        prefs.naming_prefixes.add()
        return {'FINISHED'}


class ASSET_CHECKER_OT_naming_remove_prefix(bpy.types.Operator):
    """Remove the selected required prefix"""
    bl_idname = "asset_checker.naming_remove_prefix"
    bl_label = "Remove Prefix"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        if 0 <= self.index < len(prefs.naming_prefixes):
            prefs.naming_prefixes.remove(self.index)
        return {'FINISHED'}


class ASSET_CHECKER_OT_naming_add_suffix(bpy.types.Operator):
    """Add a required object name suffix"""
    bl_idname = "asset_checker.naming_add_suffix"
    bl_label = "Add Suffix"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        prefs.naming_suffixes.add()
        return {'FINISHED'}


class ASSET_CHECKER_OT_naming_remove_suffix(bpy.types.Operator):
    """Remove the selected required suffix"""
    bl_idname = "asset_checker.naming_remove_suffix"
    bl_label = "Remove Suffix"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        if 0 <= self.index < len(prefs.naming_suffixes):
            prefs.naming_suffixes.remove(self.index)
        return {'FINISHED'}


class ASSET_CHECKER_OT_col_naming_add_prefix(bpy.types.Operator):
    """Add a required collection name prefix"""
    bl_idname = "asset_checker.col_naming_add_prefix"
    bl_label = "Add Prefix"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        prefs.col_naming_prefixes.add()
        return {'FINISHED'}


class ASSET_CHECKER_OT_col_naming_remove_prefix(bpy.types.Operator):
    """Remove the selected required collection prefix"""
    bl_idname = "asset_checker.col_naming_remove_prefix"
    bl_label = "Remove Prefix"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        if 0 <= self.index < len(prefs.col_naming_prefixes):
            prefs.col_naming_prefixes.remove(self.index)
        return {'FINISHED'}


class ASSET_CHECKER_OT_col_naming_add_suffix(bpy.types.Operator):
    """Add a required collection name suffix"""
    bl_idname = "asset_checker.col_naming_add_suffix"
    bl_label = "Add Suffix"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        prefs.col_naming_suffixes.add()
        return {'FINISHED'}


class ASSET_CHECKER_OT_col_naming_remove_suffix(bpy.types.Operator):
    """Remove the selected required collection suffix"""
    bl_idname = "asset_checker.col_naming_remove_suffix"
    bl_label = "Remove Suffix"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        if 0 <= self.index < len(prefs.col_naming_suffixes):
            prefs.col_naming_suffixes.remove(self.index)
        return {'FINISHED'}


class ASSET_CHECKER_OT_mesh_naming_add_suffix(bpy.types.Operator):
    """Add a required mesh datablock suffix"""
    bl_idname = "asset_checker.mesh_naming_add_suffix"
    bl_label = "Add Suffix"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        prefs.mesh_naming_suffixes.add()
        return {'FINISHED'}


class ASSET_CHECKER_OT_mesh_naming_remove_suffix(bpy.types.Operator):
    """Remove the selected required mesh datablock suffix"""
    bl_idname = "asset_checker.mesh_naming_remove_suffix"
    bl_label = "Remove Suffix"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        if 0 <= self.index < len(prefs.mesh_naming_suffixes):
            prefs.mesh_naming_suffixes.remove(self.index)
        return {'FINISHED'}


class ASSET_CHECKER_OT_hierarchy_layer_add(bpy.types.Operator):
    """Add a functional layer name to the Hierarchy whitelist"""
    bl_idname = "asset_checker.hierarchy_layer_add"
    bl_label = "Add Layer"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        prefs.hierarchy_layer_names.add()
        return {'FINISHED'}


class ASSET_CHECKER_OT_hierarchy_layer_remove(bpy.types.Operator):
    """Remove the selected functional layer from the Hierarchy whitelist"""
    bl_idname = "asset_checker.hierarchy_layer_remove"
    bl_label = "Remove Layer"
    bl_options = {'REGISTER', 'UNDO'}

    index: IntProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        if 0 <= self.index < len(prefs.hierarchy_layer_names):
            prefs.hierarchy_layer_names.remove(self.index)
        return {'FINISHED'}


def _uv_padding_settings_update(self, context):
    """Re-run cross-object padding check when any threshold setting changes.
    Called automatically by Blender when uv_padding_shell_px / tile_px /
    texture_size is edited in the N-panel or Preferences."""
    try:
        from .manager import MeshCheck
        MeshCheck._run_global_uv_padding()
        scr = getattr(context, 'screen', None)
        if scr:
            for area in scr.areas:
                if area.type in ('VIEW_3D', 'IMAGE_EDITOR'):
                    area.tag_redraw()
    except Exception:
        pass


class StukachPresetItem(PropertyGroup):
    """Named check-set preset — stored with preferences (per Blender install)."""
    name:        StringProperty(name="Preset Name")
    checks_json: StringProperty(name="Checks JSON",
                                description="JSON dict {check_key: enabled}")


# Hotkeys
def _reload_next_issue_hotkey(self, context):
    from .properties import _register_hotkey
    _register_hotkey()


class ASSET_CHECKER_OT_profile_apply(bpy.types.Operator):
    """Apply a checker category profile in one click"""
    bl_idname = "asset_checker.profile_apply"
    bl_label = "Apply Profile"
    bl_options = {'REGISTER'}

    profile: StringProperty()

    def execute(self, context):
        prefs = context.preferences.addons[__name__.rsplit(".", 1)[0]].preferences
        values = {
            # everything on
            "ALL": {},
            # modeler: topology + transforms only
            "MODELER": {"enable_uv": False, "enable_symmetry": False,
                        "enable_naming": False, "enable_materials": False,
                        "enable_cleanup": False},
        }.get(self.profile)
        if values is None:
            return {'CANCELLED'}
        for attr in ("enable_topology", "enable_transforms", "enable_symmetry",
                     "enable_uv", "enable_naming", "enable_materials",
                     "enable_cleanup"):
            setattr(prefs, attr, attr not in values)
        self.report({'INFO'}, f"Profile applied: {self.profile.title()}")
        return {'FINISHED'}


class MeshCheckPreferences(AddonPreferences):
    bl_idname = __name__.rsplit(".", 1)[0]

    # Check presets (v1.4.1) — named sets of enabled checks
    presets:       CollectionProperty(type=StukachPresetItem)
    preset_active: StringProperty(name="Active Preset", default="")

    # Update checker — state of the last manual check
    update_auto_check: BoolProperty(
        name="Check for updates daily", default=True,
        description="Silently compare the installed version with the latest "
                    "GitHub release once a day (one anonymous request)")

    # Hotkeys
    use_next_issue_hotkey: BoolProperty(
        name="Next Issue hotkey (Shift+N)", default=True,
        description="Cycle through problem objects with Shift+N in the 3D "
                    "viewport (Object Mode, only while validation is active). "
                    "Turn off if it conflicts with another addon — the binding "
                    "can also be changed natively in Preferences > Keymap "
                    "(search for 'Next Issue')",
        update=_reload_next_issue_hotkey)
    show_viewport_hud: BoolProperty(
        name="Viewport HUD", default=True,
        description="Show the validation status and the focused finding info "
                    "in the corner of the 3D viewport")
    advance_after_fix: BoolProperty(
        name="Auto-advance after fix", default=True,
        description="After a successful fix, jump to the next object with issues")
    update_checking: BoolProperty(name="Checking", default=False)
    update_result:  StringProperty(name="Update Check Result", default="")
    update_url:     StringProperty(name="Latest Release URL", default="")

    edges_width:   FloatProperty(name="Edges Width",  default=2.0,  min=1.0, max=10.0, subtype="PIXEL")
    faces_offset:  FloatProperty(name="Faces Offset", default=0.03, min=0.0, max=5.0,  precision=3)
    edges_alpha:   FloatProperty(name="Edges Alpha",  default=1.0,  min=0.0, max=1.0,  precision=3)
    faces_alpha:   FloatProperty(name="Faces Alpha",  default=0.4,  min=0.0, max=1.0,  precision=3)
    point_size:    FloatProperty(name="Vertex Size",  default=10.0, min=0.1, max=20.0, subtype="PIXEL")
    points_offset: FloatProperty(name="Points Offset",default=0.03, min=0.0, max=5.0,  precision=3)
    overlay_xray:  BoolProperty(name="X-Ray Overlay", default=True,
                                description="Draw marks through the mesh: faces and points stay visible behind walls. "
                                            "Turn off to make solid walls hide marks on far-side geometry")

    # TOPOLOGY
    non_manifold_color:         FloatVectorProperty(name="Non manifold",         default=(0.02, 1.0,  0.02), min=0.0, max=1.0, size=3, subtype="COLOR")
    boundary_edges_color:       FloatVectorProperty(name="Boundary edges",       default=(1.0,  0.5,  0.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    isolated_verts_color:       FloatVectorProperty(name="Isolated vertices",    default=(1.0,  1.0,  0.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    duplicate_verts_color:      FloatVectorProperty(name="Duplicate vertices",   default=(1.0,  0.6,  0.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    triangles_color:            FloatVectorProperty(name="Triangles",            default=(0.7,  0.7,  0.02), min=0.0, max=1.0, size=3, subtype="COLOR")
    ngons_color:                FloatVectorProperty(name="Ngons",                default=(0.7,  0.02, 0.02), min=0.0, max=1.0, size=3, subtype="COLOR")
    zero_area_color:            FloatVectorProperty(name="Zero-area",            default=(1.0,  0.0,  1.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    z_fighting_color:           FloatVectorProperty(name="Z-Fighting",           default=(1.0,  0.0,  0.0),  min=0.0, max=1.0, size=3, subtype="COLOR")

    # POLES
    poles_color:           FloatVectorProperty(name="Poles",           default=(0.25, 0.4,  1.0),  min=0.0, max=1.0, size=3, subtype="COLOR")

    # TRANSFORMS
    non_applied_transform_color: FloatVectorProperty(name="Rotation issue",    default=(1.0, 0.0, 0.0), min=0.0, max=1.0, size=3, subtype="COLOR")
    scale_color:                 FloatVectorProperty(name="Scale issue",        default=(1.0, 0.4, 0.0), min=0.0, max=1.0, size=3, subtype="COLOR")
    origin_at_zero_color:        FloatVectorProperty(name="Origin not at zero", default=(1.0, 0.8, 0.0), min=0.0, max=1.0, size=3, subtype="COLOR")
    modifier_stack_color:        FloatVectorProperty(name="Modifier stack",     default=(0.6, 0.0, 1.0), min=0.0, max=1.0, size=3, subtype="COLOR")
    face_aspect_ratio_threshold: FloatProperty(
        name="Aspect Ratio Threshold",
        description="Quads with ratio longer_side/shorter_side above this value are flagged",
        default=6.0, min=1.5, max=50.0, precision=1,
    )
    face_aspect_ratio_color:     FloatVectorProperty(name="Face Aspect Ratio",  default=(1.0, 0.85, 0.0), min=0.0, max=1.0, size=3, subtype="COLOR")

# SYMMETRY
    symmetry_x_color: FloatVectorProperty(name="Symmetry X", default=(1.0,  0.15, 0.15), min=0.0, max=1.0, size=3, subtype="COLOR")
    symmetry_y_color: FloatVectorProperty(name="Symmetry Y", default=(0.15, 1.0,  0.15), min=0.0, max=1.0, size=3, subtype="COLOR")
    symmetry_z_color: FloatVectorProperty(name="Symmetry Z", default=(0.15, 0.4,  1.0),  min=0.0, max=1.0, size=3, subtype="COLOR")

    # UV
    uv_single_set_color:    FloatVectorProperty(name="UV Single Set",   default=(0.0, 0.5, 1.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    uv_overlap_color:       FloatVectorProperty(name="UV Overlap",      default=(1.0, 0.2, 0.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    uv_micro_shell_color:   FloatVectorProperty(name="UV Micro-shell",  default=(1.0, 0.0, 0.8),  min=0.0, max=1.0, size=3, subtype="COLOR")
    uv_texel_density_color: FloatVectorProperty(name="Texel Density",   default=(0.3, 0.9, 0.5),  min=0.0, max=1.0, size=3, subtype="COLOR")
    uv_stretch_color:       FloatVectorProperty(name="UV Stretch",      default=(1.0, 0.5, 0.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    uv_padding_color:       FloatVectorProperty(name="UV Padding",      default=(1.0, 0.6, 0.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    uv_udim_bounds_color:   FloatVectorProperty(name="UDIM Bounds",     default=(0.7, 0.2, 1.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    uv_material_udim_color: FloatVectorProperty(name="Uv Material Udim",   default=(1.0, 0.2, 0.6),  min=0.0, max=1.0, size=3, subtype="COLOR")

    # NAMING colors
    obj_naming_color:  FloatVectorProperty(name="Naming issue",  default=(1.0, 0.5, 0.0), min=0.0, max=1.0, size=3, subtype="COLOR")
    col_naming_color:  FloatVectorProperty(name="Col naming",    default=(0.5, 0.5, 0.5), min=0.0, max=1.0, size=3, subtype="COLOR")
    mat_numbering_color: FloatVectorProperty(name="Mat numbering", default=(1.0, 0.4, 0.1), min=0.0, max=1.0, size=3, subtype="COLOR")

    # Validator identity — used in reports and the Copy Summary signature
    validator_name: StringProperty(
        name="Validator Name",
        default="",
        description="Name written into validation reports (empty = system login)",
    )

    # Coordinator workstation flags
    start_in_coordinator: BoolProperty(
        name="Start in Coordinator Mode",
        default=False,
        description="Open STUKACH in Coordinator Mode on addon load and after "
                    "every file load — for curator/lead workstations",
    )
    coordinator_lock: BoolProperty(
        name="Coordinator Lock",
        default=False,
        description="In Coordinator Mode hide fix actions (category Fix, "
                    "hierarchy fixes, UV rename, cleanup tools) — coordinator "
                    "reviews and reports, artist fixes",
    )

    # Preferences tab pages — the full settings sheet is far too tall as one scroll
    prefs_section: EnumProperty(
        name="Section",
        items=(
            ('OVERLAY', "Overlay", "Viewport overlay style: faces, edges, points"),
            ('UV', "UV", "UV thresholds: texel density, padding, stretch, aspect ratio, count thresholds"),
            ('NAMING', "Naming", "Naming policy: prefixes, suffixes, hierarchy whitelist"),
            ('CHECKS', "Checks", "Check behavior thresholds"),
            ('COLORS', "Colors", "Per-check overlay colors"),
        ),
        default='OVERLAY',
        options={'HIDDEN'},
    )

    # NAMING POLICY — object prefixes / suffixes
    naming_prefixes: CollectionProperty(type=NamingEntry, name="Object Required Prefixes")
    naming_suffixes: CollectionProperty(type=NamingEntry, name="Object Required Suffixes")
    # NAMING POLICY — collection prefixes / suffixes
    col_naming_prefixes: CollectionProperty(type=NamingEntry, name="Collection Required Prefixes")
    col_naming_suffixes: CollectionProperty(type=NamingEntry, name="Collection Required Suffixes")
    # NAMING POLICY — mesh datablock suffixes (data names like 'body_mesh')
    mesh_naming_suffixes: CollectionProperty(type=NamingEntry, name="Mesh Data Required Suffixes")

    # HIERARCHY VALIDATOR — functional layer whitelist, group suffix
    # (findings affect Asset Status only in Coordinator Mode — acceptance gate)
    hierarchy_grp_suffix: StringProperty(
        name="Group Suffix",
        default="_grp",
        description="Required suffix for group empties in the Hierarchy validator (empty = '_grp')",
    )
    hierarchy_layer_names: CollectionProperty(type=NamingEntry, name="Functional Layer Whitelist")

    # CHECKS — behavior thresholds
    sharp_angle_deg: FloatProperty(
        name="Angle threshold", default=60.0, min=5.0, max=179.0, precision=1,
        description="Hard Edges: flag smooth-shaded edges whose dihedral angle "
                    "exceeds this many degrees. Lower = stricter (30 is the "
                    "classic default, 60 suits smooth/curved surfaces)")
    sharp_bevel_width: FloatProperty(
        name="Chamfer width", default=0.5, min=0.05, max=10.0, precision=2,
        subtype='PERCENTAGE',
        description="Hard Edges: a smooth steep edge hugging a strip thinner "
                    "than this % of the object's size is a chamfer and is not "
                    "flagged (the shading artifact is invisible on a strip that thin)",
    )

    # Per-category switches: a disabled category is hidden in the panel and
    # never executed (RUN, Live, overlays, reports).  Default = all on.
    enable_topology:   BoolProperty(name="Topology",   default=True,
                                    description="Show and run the TOPOLOGY checks")
    enable_transforms: BoolProperty(name="Transforms", default=True,
                                    description="Show and run the TRANSFORMS checks")
    enable_symmetry:   BoolProperty(name="Symmetry",   default=True,
                                    description="Show and run the SYMMETRY checks")
    enable_uv:         BoolProperty(name="UV",         default=True,
                                    description="Show and run the UV checks")
    enable_naming:     BoolProperty(name="Naming",     default=True,
                                    description="Show and run the NAMING checks")
    enable_materials:  BoolProperty(name="Materials",  default=True,
                                    description="Show and run the MATERIALS checks")
    enable_cleanup:    BoolProperty(name="Cleanup",    default=True,
                                    description="Show and run the CLEANUP checks")

    # UV PADDING settings
    uv_padding_texture_size: EnumProperty(
        name="Padding Texture Size",
        description="Reference texture size for UV padding threshold calculation. "
                    "Must match the texture size used during UV packing (e.g. UVPackmaster Texture Size)",
        items=(('0', '512 px',  ''), ('1', '1024 px', ''),
               ('2', '2048 px', ''), ('3', '4096 px', '')),
        default='3',  # 4096 — UVPackmaster default
        update=_uv_padding_settings_update,
    )
    uv_padding_shell_px: IntProperty(
        name="Shell Padding",
        description="Minimum required padding between UV islands in pixels "
                    "(scaled to UV space using the Padding Texture Size setting)",
        default=16, min=1, max=256,
        update=_uv_padding_settings_update,
    )
    uv_padding_tile_px: IntProperty(
        name="Tile Border Padding",
        description="Minimum required padding from UV island edges to UDIM tile borders "
                    "in pixels (scaled to UV space using the Padding Texture Size setting)",
        default=8, min=1, max=128,
        update=_uv_padding_settings_update,
    )

    # UV STRETCH settings
    uv_stretch_threshold: FloatProperty(
        name="Stretch Threshold",
        description="Maximum allowed angle deviation between 3D and UV space (radians). "
                    "Lower = more strict. Default 0.5 rad ≈ 28°",
        default=0.5, min=0.05, max=3.14, precision=2,
    )

    # TEXEL DENSITY settings
    uv_td_texture_size: EnumProperty(
        name="Texture Size",
        description="Reference texture size for texel density calculation",
        items=(('0', '512 px',  ''), ('1', '1024 px', ''),
               ('2', '2048 px', ''), ('3', '4096 px', '')),
        default='3',
    )
    uv_td_target: FloatProperty(
        name="Target TD",
        description="Target texel density in px/cm (0 = informational only, no flagging)",
        default=0.0, min=0.0, max=500.0, precision=2,
    )
    uv_td_tolerance: FloatProperty(
        name="Tolerance %",
        description="Allowed deviation from target TD in percent (e.g. 20 = ±20%)",
        default=20.0, min=1.0, max=100.0, precision=1,
    )

    # MATERIALS
    mat_suffix_color:        FloatVectorProperty(name="Mat suffix",        default=(0.5, 0.5, 0.5), min=0.0, max=1.0, size=3, subtype="COLOR")
    mat_assignment_color:    FloatVectorProperty(name="Mat assign",        default=(0.5, 0.5, 0.5), min=0.0, max=1.0, size=3, subtype="COLOR")
    missing_textures_color:  FloatVectorProperty(name="Missing textures",  default=(1.0, 0.2, 0.2), min=0.0, max=1.0, size=3, subtype="COLOR")

    # CLEANUP
    unused_data_color: FloatVectorProperty(name="Unused Data", default=(0.6, 0.4, 0.1), min=0.0, max=1.0, size=3, subtype="COLOR")

    # MAYA v1.1.0 PARITY
    lamina_color:              FloatVectorProperty(name="Lamina",              default=(1.0, 0.1, 0.7),  min=0.0, max=1.0, size=3, subtype="COLOR")
    zero_length_edges_color:   FloatVectorProperty(name="Zero Length Edges",   default=(1.0, 0.25, 0.25), min=0.0, max=1.0, size=3, subtype="COLOR")
    starlike_color:            FloatVectorProperty(name="Starlike",            default=(0.1, 0.9, 0.9),  min=0.0, max=1.0, size=3, subtype="COLOR")
    sharp_edges_not_hard_color: FloatVectorProperty(name="Sharp Edges Not Hard", default=(1.0, 0.55, 0.1), min=0.0, max=1.0, size=3, subtype="COLOR")
    missing_uvs_color:         FloatVectorProperty(name="Missing UVs",         default=(0.95, 0.85, 0.1), min=0.0, max=1.0, size=3, subtype="COLOR")
    duplicated_names_color:    FloatVectorProperty(name="Duplicated Names",    default=(1.0, 0.2, 0.2),  min=0.0, max=1.0, size=3, subtype="COLOR")
    trailing_numbers_color:    FloatVectorProperty(name="Trailing Numbers",    default=(0.9, 0.6, 0.2),  min=0.0, max=1.0, size=3, subtype="COLOR")
    uncentered_pivots_color:   FloatVectorProperty(name="Uncentered Pivots",   default=(0.8, 0.5, 1.0),  min=0.0, max=1.0, size=3, subtype="COLOR")
    parent_geometry_color:     FloatVectorProperty(name="Parent Geometry",     default=(0.65, 0.85, 0.2), min=0.0, max=1.0, size=3, subtype="COLOR")

    # CHECK THRESHOLDS — count ≤ threshold → yellow dot; count > threshold → red dot
    # Only the three checks that make sense to tune are exposed here.
    threshold_triangles: IntProperty(
        name="Triangles",
        description="Counts up to this value show a yellow dot; above — red.\n"
                    "Set to 0 to flag any triangle as red immediately",
        default=50, min=0, max=10_000,
    )
    threshold_ngons: IntProperty(
        name="Ngons",
        description="Counts up to this value show a yellow dot; above — red.\n"
                    "Set to 0 to flag any ngon as red immediately",
        default=10, min=0, max=10_000,
    )
    threshold_poles: IntProperty(
        name="Poles",
        description="Counts up to this value show a yellow dot; above — red.\n"
                    "Set to 0 to flag any pole as red immediately",
        default=20, min=0, max=10_000,
    )

    def draw(self, context):
        layout = self.layout

        # Interface — always visible; the flags people actually need to find
        box = layout.box()
        box.label(text="Interface", icon="WINDOW")
        box.prop(self, "start_in_coordinator")
        box.prop(self, "coordinator_lock")
        vrow = box.row(align=True)
        vrow.prop(self, "validator_name", text="Validator", icon="USER")
        box.prop(self, "use_next_issue_hotkey")
        box.prop(self, "show_viewport_hud")
        box.prop(self, "advance_after_fix")

        # Updates
        box = layout.box()
        box.label(text="Updates", icon="WORLD")
        box.prop(self, "update_auto_check")
        row = box.row(align=True)
        row.operator("asset_checker.check_updates",
                     text="Checking..." if self.update_checking else "Check for updates",
                     icon="FILE_REFRESH")
        if self.update_result:
            from . import update_checker
            stale_update = (self.update_result.startswith("Update available")
                            and not update_checker.result_is_valid())
            if self.update_result.startswith("Update available") and not stale_update:
                box.row(align=True).operator("asset_checker.open_releases",
                                             text=self.update_result,
                                             icon="URL")
            else:
                hint = box.row()
                hint.enabled = False
                if stale_update:
                    hint.label(text=f"Up to date ({self.update_result.rsplit(':', 1)[1].strip()})",
                               icon="INFO")
                else:
                    hint.label(text=self.update_result, icon="INFO")

        # Section tabs — the full sheet as one scroll was far too tall
        row = layout.row(align=True)
        row.prop(self, "prefs_section", expand=True)

        if self.prefs_section == 'OVERLAY':
            self._draw_section_overlay(layout)
        elif self.prefs_section == 'UV':
            self._draw_section_uv(layout)
        elif self.prefs_section == 'NAMING':
            self._draw_section_naming(layout)
        elif self.prefs_section == 'CHECKS':
            self._draw_section_checks(layout)
        elif self.prefs_section == 'COLORS':
            self._draw_section_colors(layout)

    def _draw_section_checks(self, layout):
        box = layout.box()
        box.label(text="Hard Edges (Sharp Edges Not Hard)", icon="EDGESEL")
        box.prop(self, "sharp_angle_deg")
        box.prop(self, "sharp_bevel_width")
        hint = box.row()
        hint.enabled = False
        hint.label(text="Edges hugging thinner strips are treated as chamfers", icon="INFO")

        box = layout.box()
        box.label(text="Categories", icon="OUTLINER_COLLECTION")
        prow = box.row(align=True)
        prow.operator("asset_checker.profile_apply", text="All", icon="CHECKBOX_HLT").profile = "ALL"
        prow.operator("asset_checker.profile_apply", text="Modeler", icon="MOD_BUILD").profile = "MODELER"
        col = box.column(align=True)
        for attr in ("enable_topology", "enable_transforms", "enable_symmetry",
                     "enable_uv", "enable_naming", "enable_materials", "enable_cleanup"):
            col.prop(self, attr, toggle=True)
        hint = box.row()
        hint.enabled = False
        hint.label(text="Disabled: hidden in the panel, never runs, not in reports", icon="INFO")

    def _draw_section_overlay(self, layout):
        box = layout.box()
        box.label(text="Faces / Edges", icon="FACESEL")
        box.prop(self, "overlay_xray")
        box.prop(self, "edges_width")
        box.prop(self, "faces_offset")
        box.prop(self, "edges_alpha")
        box.prop(self, "faces_alpha")

        box = layout.box()
        box.label(text="Points", icon="VERTEXSEL")
        box.prop(self, "point_size")
        box.prop(self, "points_offset")

    def _draw_section_uv(self, layout):
        box = layout.box()
        box.label(text="Texel Density", icon="UV")
        row = box.row(align=True)
        row.label(text="Texture Size:")
        row.prop(self, "uv_td_texture_size", text="")
        row = box.row(align=True)
        row.label(text="Target TD (px/cm):")
        row.prop(self, "uv_td_target", text="")
        row = box.row(align=True)
        row.label(text="Tolerance:")
        row.prop(self, "uv_td_tolerance", text="")
        hint = box.row()
        hint.enabled = False
        hint.label(text="Target TD = 0 \u2192 display only, no error flagging", icon="INFO")

        box = layout.box()
        box.label(text="UV Padding", icon="UV_FACESEL")
        row = box.row(align=True)
        row.label(text="Shell padding (px):")
        row.prop(self, "uv_padding_shell_px", text="")
        row = box.row(align=True)
        row.label(text="Tile border (px):")
        row.prop(self, "uv_padding_tile_px", text="")
        hint = box.row()
        hint.enabled = False
        hint.label(text="Pixel thresholds scale with Texture Size setting", icon="INFO")

        box = layout.box()
        box.label(text="UV Stretch", icon="UV_DATA")
        row = box.row(align=True)
        row.label(text="Threshold (rad):")
        row.prop(self, "uv_stretch_threshold", text="")
        hint = box.row()
        hint.enabled = False
        hint.label(text="Angle diff > threshold \u2192 face flagged as stretched", icon="INFO")

        box = layout.box()
        box.label(text="Face Aspect Ratio", icon="MESH_GRID")
        row = box.row(align=True)
        row.label(text="Threshold (ratio):")
        row.prop(self, "face_aspect_ratio_threshold", text="")
        hint = box.row()
        hint.enabled = False
        hint.label(text="Quads above this ratio are flagged (default 6:1)", icon="INFO")

        box = layout.box()
        box.label(text="Check Thresholds", icon="SETTINGS")
        hint = box.row()
        hint.enabled = False
        hint.label(text="Count \u2264 threshold \u2192 yellow  \u00b7  above \u2192 red  \u00b7  0 = always red",
                   icon="INFO")
        col = box.column(align=True)
        for attr, label in (
            ("threshold_triangles", "Triangles"),
            ("threshold_ngons",     "Ngons"),
            ("threshold_poles",     "Poles"),
        ):
            row = col.row(align=True)
            row.label(text=label + ":")
            row.prop(self, attr, text="")

    def _draw_section_naming(self, layout):
        box = layout.box()
        box.label(text="Naming Policy", icon="FILE_TEXT")

        def _draw_policy_domain(parent, domain_label, entries_prefix, entries_suffix,
                                op_add_pre, op_rm_pre, op_add_suf, op_rm_suf):
            sub = parent.box()
            sub.label(text=domain_label, icon="DOT")
            split = sub.split(factor=0.5)

            c = split.column(align=True)
            c.label(text="Prefixes:")
            for i, entry in enumerate(entries_prefix):
                row = c.row(align=True)
                row.prop(entry, "value", text="")
                op = row.operator(op_rm_pre, text="", icon="X", emboss=False)
                op.index = i
            c.operator(op_add_pre, text="Add", icon="ADD")

            c = split.column(align=True)
            c.label(text="Suffixes:")
            for i, entry in enumerate(entries_suffix):
                row = c.row(align=True)
                row.prop(entry, "value", text="")
                op = row.operator(op_rm_suf, text="", icon="X", emboss=False)
                op.index = i
            c.operator(op_add_suf, text="Add", icon="ADD")

        _draw_policy_domain(
            box, "Objects",
            self.naming_prefixes,    self.naming_suffixes,
            "asset_checker.naming_add_prefix",     "asset_checker.naming_remove_prefix",
            "asset_checker.naming_add_suffix",     "asset_checker.naming_remove_suffix",
        )
        _draw_policy_domain(
            box, "Collections",
            self.col_naming_prefixes, self.col_naming_suffixes,
            "asset_checker.col_naming_add_prefix",  "asset_checker.col_naming_remove_prefix",
            "asset_checker.col_naming_add_suffix",  "asset_checker.col_naming_remove_suffix",
        )

        # Mesh data — suffix only (checked by mesh_data_naming)
        box_m = box.box()
        box_m.label(text="Mesh Data (data block suffix)")
        op_add = "asset_checker.mesh_naming_add_suffix"
        op_rm = "asset_checker.mesh_naming_remove_suffix"
        for i, entry in enumerate(self.mesh_naming_suffixes):
            r = box_m.row(align=True)
            r.prop(entry, "value", text="")
            op = r.operator(op_rm, text="", icon="X", emboss=False)
            op.index = i
        box_m.operator(op_add, text="Add", icon="ADD")

        # Hierarchy validator — layers whitelist + group suffix
        box_h = box.box()
        box_h.label(text="Hierarchy", icon="EMPTY_AXIS")
        row = box_h.row(align=True)
        row.label(text="Group suffix:")
        row.prop(self, "hierarchy_grp_suffix", text="")
        hint = box_h.row()
        hint.enabled = False
        hint.label(text="Findings affect Asset Status in Coordinator Mode", icon="INFO")
        col = box_h.column(align=True)
        col.label(text="Functional layer whitelist:")
        for i, entry in enumerate(self.hierarchy_layer_names):
            r = col.row(align=True)
            r.prop(entry, "value", text="")
            op = r.operator("asset_checker.hierarchy_layer_remove", text="", icon="X", emboss=False)
            op.index = i
        col.operator("asset_checker.hierarchy_layer_add", text="Add Layer", icon="ADD")
        hint = box_h.row()
        hint.enabled = False
        hint.label(text="Adds to the 24 built-in layers (static, geo, ...)", icon="INFO")

        hint = box.row()
        hint.enabled = False
        hint.label(text="Empty list = no requirement enforced", icon="INFO")

    def _draw_section_colors(self, layout):
        box = layout.box()
        box.label(text="Pipeline check colors", icon="MODIFIER")
        # a ROW holding two columns — sibling columns inside a box stack
        # vertically, side-by-side needs the row wrapper
        pair = box.row(align=True)
        left = pair.column(align=True)
        right = pair.column(align=True)
        colors = (
            "triangles_color", "ngons_color", "non_manifold_color", "boundary_edges_color",
            "isolated_verts_color", "duplicate_verts_color", "poles_color", "zero_area_color",
            "z_fighting_color",
            "non_applied_transform_color", "scale_color", "origin_at_zero_color",
            "modifier_stack_color",
            "face_aspect_ratio_color",
            "symmetry_x_color", "symmetry_y_color", "symmetry_z_color",
            "uv_single_set_color",
            "uv_overlap_color", "uv_micro_shell_color",
            "uv_texel_density_color", "uv_stretch_color", "uv_padding_color",
            "uv_udim_bounds_color", "uv_material_udim_color",
            "obj_naming_color", "col_naming_color", "mat_numbering_color",
            "mat_suffix_color", "mat_assignment_color", "missing_textures_color",
            "unused_data_color",
            "lamina_color", "zero_length_edges_color", "starlike_color",
            "sharp_edges_not_hard_color", "missing_uvs_color",
            "duplicated_names_color", "trailing_numbers_color",
            "uncentered_pivots_color", "parent_geometry_color",
        )
        for i, attr in enumerate(colors):
            col = left if i % 2 == 0 else right
            prop_def = self.bl_rna.properties.get(attr)
            label = prop_def.name if prop_def else attr
            row = col.row(align=True)
            split = row.split(factor=0.55)
            split.label(text=label + ":")
            split.prop(self, attr, text="")

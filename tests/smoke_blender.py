# -*- coding:utf-8 -*-
"""STUKACH headless smoke test - runs INSIDE Blender (-b).

Builds a synthetic "garden of defects" scene (one object per defect class),
runs all checkers, applies every fix operator, re-validates and asserts.
Also probes: checker/severity registry sync, hierarchy validator rules,
report export (JSON/CSV/HTML), Next Issue poll from Edit Mode, dead-object
purge, NaN-UV UDIM map. The per-check "no exceptions" gate is the stukach.log
scan at the end.

Prerequisite: the stukach extension is installed into a user resources dir
pointed to by BLENDER_USER_RESOURCES (see tests/run_smoke.py).

Exit code: 0 = all steps passed, 1 = at least one step failed.
Never returns through the normal interpreter teardown: Blender -b can hang
on exit on some setups (local Windows grable), os._exit is safe everywhere.
"""

import bmesh
import bpy
import importlib
import math
import os
import sys
import tempfile
import traceback

MOD = "bl_ext.user_default.stukach"

RESULTS = []


def step(name, fn):
    try:
        info = fn() or ""
        RESULTS.append((name, True, info))
        print(f"[SMOKE] PASS {name} {info}")
    except Exception as e:
        RESULTS.append((name, False, str(e)))
        print(f"[SMOKE] FAIL {name}: {e}")
        traceback.print_exc()


def expect(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ── Enable the extension ─────────────────────────────────────────────────────
import addon_utils

enable_info = addon_utils.enable(MOD, default_set=True, persistent=True)
if MOD not in sys.modules:
    # addon_utils.enable returns (mod, ) or None on failure depending on version
    raise SystemExit(f"cannot enable {MOD}: {enable_info!r}")

manager = importlib.import_module(MOD + ".manager")
core = importlib.import_module(MOD + ".core")
props_mod = importlib.import_module(MOD + ".properties")
ui = importlib.import_module(MOD + ".ui")
naming = importlib.import_module(MOD + ".naming")

MeshCheck = manager.MeshCheck
MeshCheckObject = manager.MeshCheckObject

prefs = bpy.context.preferences.addons[MOD].preferences
mc = bpy.context.window_manager.mesh_check_props

# ── Scene helpers ────────────────────────────────────────────────────────────


def bmesh_obj(name, build_fn):
    """Create a linked mesh object named <name> (mesh data <name>_mesh)."""
    me = bpy.data.meshes.new(name + "_mesh")
    bm = bmesh.new()
    build_fn(bm)
    bm.to_mesh(me)
    bm.free()
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def cube_bm(bm, size=1.0, loc=(0, 0, 0)):
    bmesh.ops.create_cube(bm, size=size)
    bmesh.ops.translate(bm, verts=bm.verts[:], vec=loc)


def add_mat(ob, name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    ob.data.materials.append(m)


def ensure_uv(ob, name="UVMap"):
    return ob.data.uv_layers.new(name=name)


def counts(check_name):
    """check_name count per tracked object name."""
    out = {}
    for obj, mco in MeshCheck.objects.items():
        try:
            out[obj.name] = mco._checks[check_name].count
        except ReferenceError:
            continue
    return out


def max_count(check_name):
    return max(counts(check_name).values(), default=0)


def flush_validation():
    """Run the progressive-validation worker synchronously (timers don't tick
    while our script runs)."""
    guard = 0
    while MeshCheck._validation_queue and guard < 100000:
        MeshCheck._validation_flush()
        guard += 1
    expect(not MeshCheck._validation_queue, "validation queue not drained")


def revalidate():
    """Full re-validation: drop stale bmesh caches, rebuild MeshCheckObjects."""
    for mco in list(MeshCheck.objects.values()):
        mco._drop_cached_bm()
    MeshCheck.objects.clear()
    bpy.ops.asset_checker.validate_scene("EXEC_DEFAULT")
    flush_validation()


# ── Garden of defects ────────────────────────────────────────────────────────
# One object per defect class, each with a known expected diagnosis.


def make_garden():
    # ngons: a pentagon face (5+ verts)
    def _ngon(bm):
        pts = [(math.cos(2 * math.pi * i / 5) * 0.7,
                math.sin(2 * math.pi * i / 5) * 0.7, 0) for i in range(5)]
        bm.faces.new([bm.verts.new(p) for p in pts])

    ob = bmesh_obj("ngon_cube_geo", _ngon)
    add_mat(ob, "steel_ngon_mat")

    # zero_area: fully collinear quad (distinct verts, zero surface)
    def _zero_area(bm):
        for x in range(4):
            bm.verts.new((float(x), 0, 0))
        bm.verts.ensure_lookup_table()
        bm.faces.new(tuple(bm.verts))

    ob = bmesh_obj("zero_area_quad_geo", _zero_area)
    add_mat(ob, "steel_zeroarea_mat")

    # duplicate_verts: two triangles joined by a bridge edge into ONE shell,
    # with a coincident corner pair (a0/b0) that merge-by-distance must weld
    def _dup_verts(bm):
        a0 = bm.verts.new((10, 0, 0))
        a1 = bm.verts.new((11, 0, 0))
        a2 = bm.verts.new((10, 1, 0))
        b0 = bm.verts.new((10, 0, 0))  # coincident with a0
        b1 = bm.verts.new((11, 0, 0))  # coincident with a1
        b2 = bm.verts.new((11, 1, 0))
        bm.faces.new((a0, a1, a2))
        bm.faces.new((b0, b1, b2))
        bm.edges.new((a2, b2))  # bridge -> single connected shell

    ob = bmesh_obj("dup_verts_shell_geo", _dup_verts)
    add_mat(ob, "steel_dupverts_mat")

    # isolated vert: clean cube + one detached vertex
    def _iso(bm):
        cube_bm(bm, 1.0, (20, 0, 0))
        bm.verts.new((20, 5, 5))

    ob = bmesh_obj("iso_vert_cube_geo", _iso)
    add_mat(ob, "steel_iso_mat")

    # lamina: face whose contour repeats a vertex (zero-thickness fold).
    # bmesh refuses to build it, so go through from_pydata - that is also how
    # real-world lamina faces appear (imports / scripts).
    def _lamina():
        me = bpy.data.meshes.new("lamina_face_geo_mesh")
        me.from_pydata([(30, 0, 0), (31, 0, 0), (30, 1, 0)], [], [(0, 1, 2, 1)])
        me.update()
        ob = bpy.data.objects.new("lamina_face_geo", me)
        bpy.context.scene.collection.objects.link(ob)
        return ob

    ob = _lamina()
    add_mat(ob, "steel_lamina_mat")

    # zero-length edge: two coincident verts joined by an edge
    def _zero_len(bm):
        v0 = bm.verts.new((40, 0, 0))
        v1 = bm.verts.new((40, 0, 0))
        bm.edges.new((v0, v1))

    ob = bmesh_obj("zero_len_edge_geo", _zero_len)
    add_mat(ob, "steel_zerolen_mat")

    # starlike: strongly concave (dart) quad - the vertex-average centroid
    # must fall OUTSIDE the kernel, so the reflex vertex nearly touches the
    # opposite edge
    def _starlike(bm):
        pts = [(50, 0, 0), (52, 0, 0), (50.1, 0.05, 0), (50, 2, 0)]
        verts = [bm.verts.new(p) for p in pts]
        bm.faces.new(verts)

    ob = bmesh_obj("starlike_dart_geo", _starlike)
    add_mat(ob, "steel_starlike_mat")

    # non-applied transform + non-unit scale (transform-key driven checks)
    ob = bmesh_obj("unapplied_geo", lambda bm: cube_bm(bm, 1.0, (60, 0, 0)))
    ob.rotation_euler = (0.3, 0.0, 0.5)
    ob.scale = (1.5, 1.0, 1.0)
    add_mat(ob, "steel_unapplied_mat")

    # missing UVs: cube without a UV layer
    ob = bmesh_obj("no_uv_cube_geo", lambda bm: cube_bm(bm, 1.0, (70, 0, 0)))
    add_mat(ob, "steel_nouv_mat")

    # modifier stack: unapplied Subsurf
    ob = bmesh_obj("subsurf_geo", lambda bm: cube_bm(bm, 1.0, (80, 0, 0)))
    ob.modifiers.new("Subdiv", "SUBSURF")
    add_mat(ob, "steel_subsurf_mat")

    # sharp_edges_not_hard guard: smooth shading + sharp flags + custom
    # normals -> the check must SKIP (custom-normal driven shading), not flag
    def _sharp_custom(bm):
        cube_bm(bm, 1.0, (90, 0, 0))
        bm.edges.ensure_lookup_table()
        for e in bm.edges[:2]:
            e.smooth = False

    ob = bmesh_obj("sharp_custom_geo", _sharp_custom)
    me = ob.data
    me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    me.update()
    normals = [(0.0, 0.0, 1.0)] * len(me.vertices)
    me.normals_split_custom_set_from_vertices(normals)
    expect(me.has_custom_normals, "custom normals did not stick - guard probe invalid")
    add_mat(ob, "steel_sharp_mat")

    # unused data: empty vertex group + leftover custom attribute
    ob = bmesh_obj("unused_data_geo", lambda bm: cube_bm(bm, 1.0, (100, 0, 0)))
    ob.vertex_groups.new(name="empty_vg")
    ob.data.attributes.new("leftover_attr", "FLOAT", "POINT")
    add_mat(ob, "steel_unused_mat")

    # trailing numbers (.001/.002 leftovers).  DuplicatedNames itself is a
    # linked-library check - inside one .blend names are unique by design,
    # so it cannot fire here and is asserted clean in st_clean_probes.
    ob = bmesh_obj("prop_box.001", lambda bm: cube_bm(bm, 1.0, (110, 0, 0)))
    add_mat(ob, "steel_prop_mat")
    ob = bmesh_obj("prop_box.002", lambda bm: cube_bm(bm, 1.0, (112, 0, 0)))
    add_mat(ob, "steel_prop2_mat")

    # NaN UVs: UDIM map must survive non-finite UVs (tb3 gun01 regression)
    def _nan_uv():
        ob = bmesh_obj("nan_uv_cube_geo", lambda bm: cube_bm(bm, 1.0, (120, 0, 0)))
        add_mat(ob, "steel_nanuv_mat")
        ensure_uv(ob)
        uvs = ob.data.uv_layers[0].data
        nan = float("nan")
        for i, d in enumerate(uvs):
            if i < 4:  # first face only
                d.uv = (nan, nan)
        return ob

    nan_obj = _nan_uv()

    # UV overlap: every loop pinned to the same UV corner
    def _overlap():
        ob = bmesh_obj("uv_overlap_geo", lambda bm: cube_bm(bm, 1.0, (130, 0, 0)))
        add_mat(ob, "steel_overlap_mat")
        ensure_uv(ob)
        for d in ob.data.uv_layers[0].data:
            d.uv = (0.1, 0.1)
        return ob

    _overlap()

    # inter-object z-fighting pair: two planes that truly cross through
    # their centers (BVHTree.overlap needs a real intersection, and the
    # checker filters pairs whose face centroids are farther than 0.1 mm -
    # so the tilt is tiny and pivots at the plane center)
    def _plane(bm):
        v0 = bm.verts.new((-1, -1, 0))
        v1 = bm.verts.new((1, -1, 0))
        v2 = bm.verts.new((1, 1, 0))
        v3 = bm.verts.new((-1, 1, 0))
        bm.faces.new((v0, v1, v2, v3))

    ob = bmesh_obj("zf_bottom_geo", _plane)
    add_mat(ob, "steel_zf_a_mat")
    ob.location = (141, 1, 0)
    ob = bmesh_obj("zf_top_geo", _plane)
    add_mat(ob, "steel_zf_b_mat")
    ob.location = (141, 1, 0)
    ob.rotation_euler.x = math.radians(0.003)

    # hierarchy fixture:
    #   asset_root (EMPTY, missing _grp suffix)
    #     wheels_grp (functional layer) -> brakes_grp (part group)
    #       brakes_01_geo / door_front_geo (parent_mismatch: base is "brakes")
    #   orphan_part_geo (loose mesh), base_1_geo (bad numbering EMPTY)
    #   hull_geo (mesh) -> body_geo (mesh under mesh)
    def empty(name):
        e = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(e)
        return e

    root = empty("asset_root")
    wheels = empty("wheels_grp")
    wheels.parent = root
    brakes = empty("brakes_grp")
    brakes.parent = wheels
    bw = bmesh_obj("brakes_01_geo", lambda bm: cube_bm(bm, 0.5, (150, 0, 0)))
    add_mat(bw, "steel_wheel_mat")
    bw.parent = brakes
    bd = bmesh_obj("door_front_geo", lambda bm: cube_bm(bm, 0.5, (152, 0, 0)))
    add_mat(bd, "steel_wheel2_mat")
    bd.parent = brakes
    orph = bmesh_obj("orphan_part_geo", lambda bm: cube_bm(bm, 0.5, (160, 0, 0)))
    add_mat(orph, "steel_orphan_mat")
    bad_num = empty("base_1_geo")
    hull = bmesh_obj("hull_geo", lambda bm: cube_bm(bm, 0.5, (170, 0, 0)))
    add_mat(hull, "steel_hull_mat")
    body = bmesh_obj("body_geo", lambda bm: cube_bm(bm, 0.4, (170, 0, 0.6)))
    add_mat(body, "steel_body_mat")
    body.parent = hull

    bpy.context.view_layer.update()  # fresh matrix_world for transform keys
    return nan_obj


# ── Steps ────────────────────────────────────────────────────────────────────


def st_clean_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for block in (bpy.data.meshes, bpy.data.materials):
        for x in list(block):
            if x.users == 0:
                block.remove(x)
    expect(len(bpy.data.objects) == 0, "scene not clean")


def st_enable_checks():
    for cat in ("topology", "transforms", "symmetry", "uv", "naming",
                "materials", "cleanup"):
        expect(hasattr(prefs, "enable_" + cat), f"prefs missing enable_{cat}")
        setattr(prefs, "enable_" + cat, True)
    for key in manager._AC_CHECK_PROPS:
        expect(hasattr(mc, key), f"mesh_check_props missing '{key}'")
        setattr(mc, key, True)
    return f"{len(manager._AC_CHECK_PROPS)} checks enabled"


def st_registry_sync():
    expect(len(core.CHECK_TYPES) == 42,
           f"CHECK_TYPES has {len(core.CHECK_TYPES)} entries, expected 42")
    expect(set(ui.CHECK_SEVERITY) == set(core.CHECK_TYPES),
           "CHECK_SEVERITY out of sync with CHECK_TYPES")
    expect(set(props_mod._CATEGORY_OF) >= set(core.CHECK_TYPES),
           "checks without a category in CHECK_CATEGORIES")
    _probe = bmesh_obj("registry_probe_geo", lambda bm: cube_bm(bm, 0.5, (0, 50, 0)))
    add_mat(_probe, "steel_probe_mat")
    MeshCheck.objects.clear()
    mco = MeshCheckObject(_probe)
    expect(set(mco._checks) == set(core.CHECK_TYPES),
           "MeshCheckObject did not instantiate every checker")
    mco._drop_cached_bm()
    MeshCheck.objects.clear()
    bpy.data.objects.remove(_probe, do_unlink=True)
    return "42 checks, severity map and categories in sync"


def st_validate():
    garden_names = [o.name for o in bpy.data.objects if o.type == "MESH"]
    bpy.ops.asset_checker.validate_scene("EXEC_DEFAULT")
    flush_validation()
    tracked = len(MeshCheck.objects)
    expect(tracked == len(garden_names),
           f"tracked {tracked}, expected {len(garden_names)}")
    return f"{tracked} objects tracked"


def _expect_flag(name, minimum=1):
    expect(max_count(name) >= minimum,
           f"{name} not flagged (expected >= {minimum}, got counts {counts(name)})")


def st_defects_flagged():
    for name in ("ngons", "zero_area", "duplicate_verts", "isolated_verts",
                 "lamina", "zero_length_edges", "starlike",
                 "non_applied_transform", "scale", "modifier_stack",
                 "missing_uvs", "unused_data", "trailing_numbers",
                 "uv_overlap", "uv_single_set"):
        _expect_flag(name)
    return "15 defect classes flagged"


def st_clean_probes():
    """False-positive probes: healthy aspects must stay at zero."""
    for name in ("mat_assignment", "missing_textures", "duplicated_names",
                 "uv_udim_bounds", "sharp_edges_not_hard"):
        expect(max_count(name) == 0,
               f"{name} false positive: {counts(name)}")
    return "no false positives on clean probes"


def st_nan_uv():
    ob = bpy.data.objects["nan_uv_cube_geo"]
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    try:
        m = core.build_material_udim_map(ob, bm)
        info = f"map={ {k: len(v) for k, v in m.items()} }"
    finally:
        bm.free()
    return info


def st_zfighting_inter():
    MeshCheck._run_inter_object_z_fighting()
    a = counts("z_fighting")
    total = sum(a.values())
    expect(total >= 1, f"inter-object z-fighting not flagged: {a}")
    return f"pair flagged ({a.get('zf_bottom_geo', 0)}+{a.get('zf_top_geo', 0)})"


def st_hierarchy():
    result = naming.HierarchyValidator.scan_scene(prefs=prefs)
    MeshCheck.hierarchy_result = result
    rules = {i.rule for i in result.issues}
    wanted = {"missing_grp_suffix", "orphan_mesh", "blender_numbering",
              "mesh_under_mesh", "parent_mismatch"}
    missing = wanted - rules
    expect(not missing, f"hierarchy rules not detected: {missing} (got {sorted(rules)})")
    expect(result.objects_scanned >= 10,
           f"hierarchy scanned only {result.objects_scanned} objects")
    eff = naming.hierarchy_effective_issues(result)
    expect(len(eff) >= len(wanted), "hierarchy_effective_issues empty")
    return f"{len(result.issues)} issues, rules {sorted(wanted)}"


def st_next_issue_edit_mode():
    ob = bpy.data.objects["ngon_cube_geo"]
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set("EXEC_DEFAULT", mode="EDIT")
    try:
        op = props_mod.ASSET_CHECKER_OT_next_issue
        expect(op.poll(bpy.context),
               "Next Issue poll failed from Edit Mode (poll regression)")
        res = bpy.ops.asset_checker.next_issue("EXEC_DEFAULT")
        expect(res == {"FINISHED"}, f"Next Issue returned {res}")
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set("EXEC_DEFAULT", mode="OBJECT")
    return "poll + cycle from Edit Mode OK"


def st_fix_wave():
    """Run the full fix set, re-validate, then run it again - a fix can
    surface a new finding (merge-by-distance leaves an isolated vert), the
    panel workflow repeats Fix until the object is clean."""
    all_cancelled = []
    for rnd in (1, 2):
        applied, cancelled = [], []
        for key, op_id in props_mod._FIX_OPERATORS.items():
            mod, ident = op_id.split(".")
            fn = getattr(getattr(bpy.ops, mod), ident)
            try:
                res = fn("EXEC_DEFAULT")
            except Exception as e:
                raise AssertionError(f"{op_id} raised: {e}")
            (applied if res == {"FINISHED"} else cancelled).append(key)
        all_cancelled = cancelled
        revalidate()
    return f"2 rounds done, round-2 idle ops: {len(all_cancelled)} ({all_cancelled})"


def st_defects_fixed():
    for name in ("ngons", "zero_area", "duplicate_verts", "isolated_verts",
                 "lamina", "zero_length_edges", "non_applied_transform",
                 "scale", "modifier_stack", "unused_data"):
        expect(max_count(name) == 0, f"{name} still flagged after fix: {counts(name)}")
    for name in ("mat_assignment", "missing_textures",
                 "uv_udim_bounds", "sharp_edges_not_hard"):
        expect(max_count(name) == 0, f"{name} false positive after fixes: {counts(name)}")
    return "all fixable defects resolved, clean probes still clean"


def st_reports():
    import json as _json
    op = props_mod.ASSET_CHECKER_OT_export_report
    report = op._build_report(bpy.context)
    expect(isinstance(report, dict) and report, "empty report dict")
    out = tempfile.gettempdir()
    op._write_json(report, p_json := os.path.join(out, "smoke_report.json"))
    op._write_csv(report, os.path.join(out, "smoke_report.csv"))
    op._write_html(report, os.path.join(out, "smoke_report.html"))
    with open(p_json, encoding="utf-8") as fh:
        parsed = _json.load(fh)
    expect(len(_json.dumps(parsed)) > 50, "JSON report suspiciously small")
    for p in (os.path.join(out, "smoke_report.csv"),
              os.path.join(out, "smoke_report.html")):
        expect(os.path.getsize(p) > 0, f"{p} empty")
    return "JSON/CSV/HTML written"


def st_dead_object_purge():
    probe = bmesh_obj("doomed_geo", lambda bm: cube_bm(bm, 0.3, (0, -50, 0)))
    add_mat(probe, "steel_doomed_mat")
    MeshCheck.objects[probe] = MeshCheckObject(probe)
    bpy.data.objects.remove(probe, do_unlink=True)
    MeshCheck._purge_dead_objects()
    alive = set()
    for o in list(MeshCheck.objects):
        try:
            alive.add(o.name)
        except ReferenceError:
            continue
    expect("doomed_geo" not in alive, "dead object survived purge")
    revalidate()  # full pass with the dead reference gone
    return "purged without exception"


def st_log_hygiene():
    log = os.path.join(tempfile.gettempdir(), "stukach.log")
    if not os.path.exists(log):
        # alog creates the file on first write - no file means nothing at all
        # was logged, which is exactly what a clean run should produce
        return "nothing logged at all"
    bad = []
    with open(log, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if ("Error in " in line or "error:" in line.lower()
                    or "Traceback" in line or "flush error" in line):
                bad.append(line.rstrip())
    expect(not bad, f"addon logged exceptions:\n    " + "\n    ".join(bad[:10]))
    return "no exceptions in stukach.log"


def main():
    print("=" * 60)
    print("[SMOKE] STUKACH headless smoke test")
    print("=" * 60)

    step("clean_scene", st_clean_scene)
    step("enable_checks", st_enable_checks)
    step("registry_sync", st_registry_sync)

    make_garden()
    step("validate_scene", st_validate)
    step("defects_flagged", st_defects_flagged)
    step("clean_probes", st_clean_probes)
    step("nan_uv_udim_map", st_nan_uv)
    step("z_fighting_inter", st_zfighting_inter)
    step("hierarchy_scan", st_hierarchy)
    step("next_issue_edit_mode", st_next_issue_edit_mode)
    step("fix_wave", st_fix_wave)
    step("defects_fixed", st_defects_fixed)
    step("reports", st_reports)
    step("dead_object_purge", st_dead_object_purge)
    step("log_hygiene", st_log_hygiene)

    failed = [r for r in RESULTS if not r[1]]
    print("=" * 60)
    for name, ok, info in RESULTS:
        if not ok:
            print(f"[SMOKE] FAILED STEP: {name}: {info}")
    verdict = "PASS" if not failed else "FAIL"
    print(f"SMOKE_RESULT: {verdict} ({len(RESULTS) - len(failed)}/{len(RESULTS)} steps)")
    print("=" * 60)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0 if not failed else 1)


main()

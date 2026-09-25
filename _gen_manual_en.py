# -*- coding: utf-8 -*-
r"""STUKACH - User Guide (EN). Generator on the family template (_docstyle.py).
Run:  python _gen_manual_en.py    Output:  docs\STUKACH_Manual_EN.docx
"""

import json

import _docstyle as ds

OUT = r'D:\AI\ZCode\Project\STUKACH\work\docs\STUKACH_Manual_EN.docx'


def h1(doc, text):
    return ds.h1(doc, text)


def h2(doc, text):
    return ds.h2(doc, text)


def p(doc, text, bullet=False, italic=False, grey=False):
    return ds.p(doc, text, bullet=bullet, italic=italic, grey=grey)


def kv_note(doc, text):
    return ds.kv(doc, text)


def mono(doc, text):
    return ds.mono(doc, text)


def add_table(doc, rows, widths, sev_col=None):
    return ds.add_table(doc, rows, widths, sev_col=sev_col)


def _save(doc, out):
    ds.footer(doc.sections[1], 'STUKACH')
    ds.strip_tail(doc)
    doc.save(out)
    h1s = [t for t in ds.H1_REGISTRY if t.lower() not in ('table of contents', 'contents')]
    json.dump(h1s, open(out.replace('.docx', '.h1.json'), 'w', encoding='utf-8'),
              ensure_ascii=False)
    print('saved:', out)


doc = ds.new_doc('STUKACH', 'User Guide',
                 'BLENDER 5.2  -  V1.8.0  ·  MAYA 2025 - V1.3.0')

p(doc, 'STUKACH checks a scene for typical pipeline errors: topology, transforms, UVs, '
       'naming, materials and hierarchy structure. The artist sees the defects right in the '
       'viewport and fixes them before delivery, while the supervisor gets a formal verdict '
       'in one click. This document covers both versions: the main part describes the '
       'Blender version, section 11 covers Maya.')

kv_note(doc, 'Blender: github.com/abyrvalg379/STUKACH  ·  Maya: github.com/abyrvalg379/STUKACH_Maya')

h1(doc, 'Contents')
ds.toc_field(doc, 'Table of contents: open the document in Word/LibreOffice and refresh '
                  'the field (F9) to fill in page numbers.')

h1(doc, '1. About STUKACH')

h2(doc, '1.1 What STUKACH does')
p(doc, 'STUKACH is an asset quality checker embedded in a DCC panel. It replaces the '
       '"manual inspection" of an asset before delivery with formalized validation: a single '
       'run checks the scene objects against dozens of rules, highlights defects right on '
       'the viewport geometry, fixes typical problems with one button, and produces a report '
       'readable by both the artist and the supervisor.')
p(doc, 'Key features:', bullet=False)
for b in [
    '42 checks in 7 categories + scene units check (Blender); 43 checks + two scene checks (Maya);',
    'asset hierarchy validator - 13 structure rules (roots, layers, groups, branch naming);',
    'GPU overlays: defects are painted in color right on the geometry - faces, edges, vertices;',
    'Live mode: validation recalculates itself on edits, no re-RUN needed;',
    'one-button fixes: transforms, hierarchy, mesh data naming, garbage cleanup;',
    'Coordinator Mode: blockers and warnings only, a formal verdict;',
    'reports: clipboard copy, JSON/CSV/HTML, pre-flight before FBX/USD export;',
    'check set presets shared with the team as files.',
]:
    p(doc, b, bullet=True)

h2(doc, '1.2 Philosophy: three severity levels')
p(doc, 'Every STUKACH finding has a severity level. It is not a checkbox importance - the '
       'level directly defines the impact on the asset status and who makes the decision.')
add_table(doc, [
    ['Level', 'Meaning', 'Status impact'],
    ['BLOCKER', 'The asset cannot be delivered. The problem is guaranteed to break rendering, '
     'export, simulation or the downstream pipeline. Must be fixed before handoff.',
     'Drives the asset status to CRITICAL'],
    ['WARNING', 'A real problem, not always catastrophic. The artist must consciously decide - '
     'fix it or justify an exception.',
     'Drives the status to REVIEW'],
    ['INFO', 'Information for review. Not an error - it highlights spots requiring a conscious '
     'decision (triangles, poles, open edges).',
     'No status impact'],
], [3, 11.5, 4.5], sev_col=None)

h2(doc, '1.3 Two modes: Artist and Coordinator')
p(doc, 'The panel works in one of two modes. Artist Mode is the artist working mode: the '
       'full check set, viewport overlays and Fix buttons. Coordinator Mode is the acceptance '
       'mode: only BLOCKER and WARNING are shown, with the asset verdict and a Copy Report '
       'button. The Coordinator Lock switch (Preferences) additionally hides every Fix button '
       'in Coordinator Mode - the coordinator validates only. See section 10 for working in '
       'each mode.')

h2(doc, '1.4 Two versions')
add_table(doc, [
    ['', 'Blender version', 'Maya version'],
    ['Version', 'v1.8.0', 'v1.3.0'],
    ['Package', 'Blender 5.1+ extension (zip)', 'Maya 2025 Win x64 (python + C++ overlay plugin)'],
    ['Panel', 'View3D N-panel - STUKACH tab', 'Docked panel to the left of the Attribute Editor'],
    ['Checks', '42 + Scene Units', '43 + Scene Units + Empty Groups'],
    ['Hierarchy', '13-rule validator + fixes', 'Built with locators; validated in Blender'],
    ['Repository', 'github.com/abyrvalg379/STUKACH', 'github.com/abyrvalg379/STUKACH_Maya'],
], [3.2, 7.9, 7.9])
kv_note(doc, 'The Blender and Maya version numbers are independent. The Maya version covers '
             'validation at the modeling stage, the Blender version - at the finished asset '
             'acceptance stage.')

h1(doc, '2. Installation')

h2(doc, '2.1 Blender 5.1+')
for b in [
    'Download the zip of the latest release: github.com/abyrvalg379/STUKACH - Releases - the '
    'STUKACH.zip asset.',
    'Blender - Edit - Preferences - Get Extensions - the arrow menu in the top right corner - '
    'Install from Disk - pick the zip. Drag-and-drop installation works as well.',
    'Make sure the STUKACH extension is enabled (the checkbox).',
    'The panel appears in the 3D viewport N-panel (N key) - STUKACH tab.',
    'Updating: download the new zip and install it the same way, on top of the old version. '
    'Settings and presets survive.',
]:
    p(doc, b, bullet=True)
kv_note(doc, 'After the first launch it is recommended to open Preferences - Add-ons - '
             'STUKACH and press Save Preferences to pin the extension state.')

h2(doc, '2.2 Maya 2025 (Windows x64)')
for b in [
    'Download the kit of the latest release: github.com/abyrvalg379/STUKACH_Maya - Releases - '
    'STUKACH_Maya_vX.Y.Z.zip.',
    'Unpack it. Drag the install_stukach.py file with the mouse straight into the viewport of '
    'an open Maya - that is the stock drag-and-drop installer.',
    'The installer copies the package into Documents/maya/2025/scripts, the overlay plugin '
    'into Documents/maya/2025/plug-ins, and creates a STUKACH button on the shelf (Custom tab).',
    'Restart Maya (or load the plugin manually: Windows - Settings/Preferences - Plug-in '
    'Manager - stukachDrawOverride.mll).',
    'The panel opens with the STUKACH shelf button. By default it docks to the left of the '
    'Attribute Editor.',
]:
    p(doc, b, bullet=True)
kv_note(doc, 'Dependencies: numpy and scipy (installed into the Maya user site-packages). The '
             'binary overlay (stukachDrawOverride.mll) is built for Maya 2025 Windows x64 - on '
             'other OS/versions the panel works and the overlay falls back to display layers.')

h1(doc, '3. Quick start (Blender)')
p(doc, 'Five steps to the first asset report:')
for b in [
    'Open the N-panel (N) - the STUKACH tab - press RUN STUKACH. By default the selection is '
    'validated (Selected scope); press Scene for the whole scene.',
    'Wait for the progress (heavy scenes are validated in batches, the panel shows "Validating '
    'N/M"). The Objects list shows only objects with problems, worst on top.',
    'Click an object in the list - its per-check findings unfold. The Sel button selects the '
    'defective geometry and frames the camera; Show only highlights it in the viewport.',
    'Fix: some checks carry a Fix button (unapplied transforms, mesh data naming, garbage '
    'cleanup, hierarchy fixes). The rest is edited by hand - the overlay shows exactly where '
    'the defect is.',
    'Deliver: Copy Summary puts a report into the clipboard; in Coordinator Mode - Copy Report '
    'with the formal READY / REVIEW / BLOCKED verdict.',
]:
    p(doc, b, bullet=True)
kv_note(doc, 'You can now enable Live - validation recalculates itself on geometry, UV and '
             'transform edits.')

h1(doc, '4. Blender version interface')
p(doc, 'The N-panel runs top to bottom: run and modes - score and navigation - validation '
       'scope - checks - hierarchy - objects - status and export. Each block below.')

h2(doc, '4.1 Run and modes')
add_table(doc, [
    ['Element', 'What it does'],
    ['RUN STUKACH / STUKACH ACTIVE', 'Start and stop of validation. The first RUN validates '
     'the selection (Selected); widen the scope with the Scene / Collection buttons below.'],
    ['Coordinator Mode and Artist Mode', 'The coordinator/artist mode switch. In Coordinator '
     'Mode the INFO checks are hidden, the verdict and Copy Report appear. With Coordinator '
     'Lock on (see section 9) every Fix button is hidden.'],
    ['Live', 'Automatic revalidation on edits: topology, UVs, transforms, renames. New scene '
     'objects are picked up automatically; the hierarchy is rescanned on changes.'],
], [5.2, 13.8])

h2(doc, '4.2 Score and navigation')
add_table(doc, [
    ['Element', 'What it does'],
    ['Score block', 'The validation score and a health-strip - colored dots per category '
     '(green/yellow/red by count thresholds).'],
    ['Next Issue', 'Cyclic navigation over the defects: selects the next problem object, '
     'frames the camera, enables its worst check. Also walks objects found by the hierarchy '
     'validator alone.'],
    ['Copy Summary', 'A report into the clipboard. In Artist Mode - a compact summary, signed '
     'with the validator name (see section 9) and the date.'],
    ['Hints under the score', '"Validating N/M" - queue progress; "Scene changed - re-run" - '
     'the scene changed after the run; "Settings restored - press Run" - settings were '
     'restored from the scene, a new run is needed.'],
], [5.2, 13.8])

h2(doc, '4.3 Validation scope')
add_table(doc, [
    ['Button', 'Scope'],
    ['Scene', 'All mesh objects of the scene'],
    ['Collection', 'All mesh objects of the active collection (nested included)'],
    ['Clear', 'Reset the validation results'],
    ['(RUN)', 'The first run always takes Selected - the selection. It protects against an '
     'accidental run over the whole scene.'],
], [3.5, 15.5])

h2(doc, '4.4 The Pipeline Checks block')
p(doc, 'Checks are enabled here and the overlay look is configured. Categories collapse; '
       'every category has a master enable switch. Next to a check name - a colored swatch '
       '(the overlay color) and the finding counter after a run.')
add_table(doc, [
    ['Element', 'What it does'],
    ['Face Orientation | Scene Units', 'Face Orientation mirrors the stock Blender normal '
     'overlay (it replaces the old flipped/invalid normal counters removed from the checks). '
     'Scene Units is a separate scene-units check.'],
    ['X-Ray', 'The overlay transparency mode. On (default) - the markers draw through walls, '
     'everything is visible "x-ray style". Off - opaque mesh walls hide the markers on the '
     'far side. The stock viewport xray (Alt+Z) always forces see-through.'],
    ['Face Offset / Point Offset', 'The offset of face fills and point markers from the '
     'surface (the cure for overlay z-fighting).'],
    ['Presets', 'A native dropdown of named check sets + naming rules. Icons: + save, - '
     'delete, export to file, import from file (team sharing).'],
], [5.2, 13.8])

h2(doc, '4.5 The hierarchy block')
p(doc, 'Sits right after the NAMING category. The Scan button runs the scene structure check '
       'against pipeline conventions (see section 6): asset roots, functional layers, '
       'partitions, group suffixes. Findings are aggregated per rule - one row per rule with '
       'example objects, expanded by click. Issues only mode hides clean branches. In Live '
       'mode the scan reruns itself whenever the scene structure changes (the main scenario - '
       'accepting an asset after an FBX import).')

h2(doc, '4.6 The Objects list')
add_table(doc, [
    ['Element', 'What it does'],
    ['Search', 'An object name filter; the header counter shows "N / M".'],
    ['Issues', 'The "problem objects only" switch. On by default: clean objects are hidden, '
     'the header prints "All objects clean" when there are no defects.'],
    ['Object card', 'V/E/F/T - vertex, edge, face and triangle counters; finding rows per '
     'enabled check with counts.'],
    ['Sel', 'Selects the defective components in edit mode and frames the camera on them '
     '(viewFit).'],
    ['Show', 'Highlights the findings in the viewport without selecting.'],
    ['Fix', 'Fix buttons on checks that can repair themselves (see sections 8.4 and 6.4).'],
    ['Ign', 'Ignore the check on this object: the finding leaves the counters and statuses, '
     'the check is greyed out. The ignore list is the "Ignored Issues" block under Objects.'],
], [4.5, 14.5])

h2(doc, '4.7 Asset Status and export')
add_table(doc, [
    ['Element', 'What it does'],
    ['ASSET STATUS', 'READY (green) / REVIEW (yellow) / CRITICAL (red, with the English '
     'captions "production-ready", "needs more work", "publish blocked") - the combined '
     'verdict over every enabled check. In Coordinator Mode hierarchy findings escalate '
     'here too.'],
    ['Export: JSON / CSV / HTML', 'A full report into a file. The HTML carries a "Fix first" '
     'section - blockers by descending count with object names.'],
    ['Pre-flight FBX / USD', 'Pre-export validation: active BLOCKERs block the export with a '
     'report, WARNINGs pass with a warning.'],
    ['Checkpoint', 'Save / Load - a snapshot and restore of the validation state (enabled '
     'checks + results). Handy before experiments: Load brings the picture back, Run '
     'recomputes.'],
    ['Debug Info', 'The button at the very bottom: copies diagnostics into the clipboard - '
     'Blender/addon/OS versions, mode, active checks, the last 40 log lines. Attach it to '
     'bug reports.'],
], [5.2, 13.8])

h2(doc, '4.8 The Coordinator panel')
p(doc, 'With Coordinator Mode on, the panel shows the verdict plate (ASSET STATUS with a '
       'caption - "Blockers must be resolved before publish" / "Warnings require artist '
       'decision"), the Copy Report button, the Critical & Warning Checks block (BLOCKER and '
       'WARNING only) and the same Export/Pre-flight/Checkpoint. Back to the artist view - '
       'the Artist Mode button in the toolbar.')

h1(doc, '5. Checkers (Blender)')
p(doc, '42 checks in 7 categories + Scene Units. The set and severity match the v1.8.0 code; '
       'thresholds of some checks are configurable in Preferences (the UV tab, the Checks tab - '
       'the Hard Edges chamfer width). Update checking is described in section 9.1.')

h2(doc, '5.1 Scene Units (scene)')
add_table(doc, [
    ['Check', 'Severity', 'What it looks for', 'Why it matters'],
    ['Scene Units', 'BLOCKER', 'System is not Metric, Unit is not Meters, Scale is not 1.0',
     'Wrong units break texel density, physics, FBX export (the x100 scale) and any tool '
     'relying on real-world sizes'],
], [3.5, 2.5, 5.5, 7])

h2(doc, '5.2 TOPOLOGY (14)')
add_table(doc, [
    ['Check', 'Severity', 'What it looks for', 'Why it matters'],
    ['Non Manifold', 'BLOCKER', 'Edges with other than 2 adjacent faces (T-joints, edges '
     'without faces)', 'Breaks booleans, simulations, normal computation and any export '
     'requiring a closed volume'],
    ['Duplicate Verts', 'BLOCKER', 'Coincident vertices within one connected shell (a 0.01 mm '
     'threshold). Coincidences between different shells (bolts on armor) are intentional '
     'practice and are not flagged', 'They break normals and shading, break simulations. '
     'A product of booleans, knife and accidental Ctrl+D'],
    ['Zero Area', 'BLOCKER', 'Faces with an area close to zero', 'Degenerate faces produce NaN '
     'normals and break UVs. A side product of boolean and Merge'],
    ['Z-Fighting', 'BLOCKER', 'Coplanar faces overlapping each other', 'Flickering in renders '
     'and real-time. The classic artifact of duplicated geometry'],
    ['Lamina', 'BLOCKER', '"Laminar" faces - the face contour passes the same edges twice '
     '(e.g. after extruding and folding onto itself)', 'Zero thickness breaks boolean '
     'operations and export'],
    ['Zero Length Edges', 'BLOCKER', 'Zero-length edges (including sewn face contours)',
     'Degenerate geometry breaks subdivide and export'],
    ['Ngons', 'WARNING', 'Faces with 5+ edges', 'They triangulate unpredictably in the '
     'renderer; normal artifacts on hard surfaces'],
    ['Isolated Verts', 'WARNING', 'Vertices not connected to any edge', 'Garbage geometry: it '
     'pollutes vertex groups and UVs, invisible in renders'],
    ['Starlike', 'WARNING', 'Faces invisible from their own centroid: self-intersecting '
     'contours, concavity with the centroid outside, sewn zero-length edges', 'Such a face '
     'triangulates incorrectly - shading and bake artifacts'],
    ['Sharp Edges Not Hard', 'WARNING', 'Smooth-shaded edges (dihedral angle of 30 degrees or '
     'more) between substantial faces, not marked Sharp',
     'Smooth shading on a sharp corner produces a shading artifact. Skipped: custom-normal '
     'meshes, chamfer strips (threshold in Preferences - Checks), flat-shaded pairs'],
    ['Triangles', 'INFO', 'Triangular faces', 'A midpoly workflow allows triangulation - '
     'artist review. Critical only in deformation zones'],
    ['Boundary Edges', 'INFO', 'Open edges - exactly one adjacent face', 'They can be '
     'intentional (cutouts, hidden faces). Highlighted for review'],
    ['Face Aspect Ratio', 'INFO', 'Quads with an aspect ratio above the threshold (6:1 by '
     'default)', 'Stretched quads produce artifacts under subdivide and skinning'],
    ['Poles', 'INFO', 'Vertices with a non-standard edge count (3, 5, >5, 0)', 'Poles affect '
     'subdivide and skinning but are often intentional'],
], [3.4, 2.4, 6.1, 6.6], sev_col=1)

h2(doc, '5.3 TRANSFORMS (6)')
add_table(doc, [
    ['Check', 'Severity', 'What it looks for', 'Why it matters'],
    ['Non Applied Transform', 'BLOCKER', 'A non-zero object rotation', 'An unapplied rotation '
     'changes normal directions on export, breaks physics and bone orientation'],
    ['Scale', 'BLOCKER', 'Scale other than 1.0 on any axis (a 0.001 tolerance)',
     'A non-normalized scale distorts simulations, skeleton deformation and texel density'],
    ['Modifier Stack', 'WARNING', 'Unapplied modifiers (except Armature)', 'A stray Subdiv, '
     'Bevel or Mirror changes the final geometry on export'],
    ['Parent Geometry', 'WARNING', 'A mesh parented to another mesh', 'It breaks the asset '
     'hierarchy and scripted scene assembly attempts'],
    ['Origin At Zero', 'INFO', 'The object pivot is not at world zero', 'It can be '
     'intentional (a loop, a hinge). Highlighted for review'],
    ['Uncentered Pivots', 'INFO', 'The pivot is far from the center of its own bbox (>5% of '
     'the diagonal)', 'A convention check: buildings and locators have offset pivots - '
     'legitimate, the artist decides'],
], [3.8, 2.4, 5.6, 6.7], sev_col=1)

h2(doc, '5.4 SYMMETRY (3)')
add_table(doc, [
    ['Check', 'Severity', 'What it looks for', 'Why it matters'],
    ['Symmetry X / Y / Z', 'INFO', 'Vertices without a mirror pair on the axis (a KD-tree)',
     'Broken symmetry breaks mirror rigs and blend shapes. Enable consciously for symmetric '
     'objects - characters, vehicles'],
], [3.8, 2.4, 5.6, 6.7], sev_col=1)

h2(doc, '5.5 UV (9)')
add_table(doc, [
    ['Check', 'Severity', 'What it looks for', 'Why it matters'],
    ['UV Overlap', 'BLOCKER', 'Overlapping UV islands of different material groups',
     'Overlap = the same texels for different polygons: unique textures cannot be baked'],
    ['UV UDIM Bounds', 'BLOCKER', 'UV islands crossing a UDIM tile border', 'An island in two '
     'tiles = the right UDIM texture cannot be assigned'],
    ['Uv Material Udim', 'BLOCKER', 'Several material groups on one UDIM tile', 'It breaks '
     'the renderer UDIM addressing and texturing automation'],
    ['UV Single Set', 'WARNING', 'The UV set count is not exactly 1', 'Several sets are a '
     'sign of unfinished work or a pipeline conflict'],
    ['UV Micro Shell', 'WARNING', 'UV islands below the area threshold (about 6x6 px at 2048)',
     'Islands too small for texturing, wasting atlas space'],
    ['UV Stretch', 'WARNING', 'Faces where the UV angle differs strongly from the 3D angle',
     'Stretch = texture distortion: visible on patterns and the normal map'],
    ['UV Texel Density', 'INFO', 'TD deviation from the target value (px/cm)', 'With no '
     'Target TD set - it simply shows the real value'],
    ['UV Padding', 'INFO', 'The distance between shells below the threshold, or to the tile '
     'border below the threshold', 'Insufficient padding causes bleeding under mip-mapping; '
     'it can vary intentionally'],
    ['Missing UVs', 'WARNING', 'Faces without UV coordinates', 'A texture cannot be baked or '
     'stretched onto such faces'],
], [3.4, 2.4, 5.9, 6.8], sev_col=1)

h2(doc, '5.6 NAMING (6)')
p(doc, 'Naming rules are configured in Preferences - Naming (object/group prefixes and '
       'suffixes, mesh data; see section 9). The checks compare names against this policy.')
add_table(doc, [
    ['Check', 'Severity', 'What it looks for', 'Why it matters'],
    ['Object Name', 'WARNING', 'Default names (Cube, pCube1), .001 numbering, special '
     'characters, capital letters, prefix/suffix mismatches', 'Broken names break asset '
     'manager scripts and exact name matching'],
    ['Group Name', 'WARNING', 'The same rules for collections + the group prefix/suffix',
     'Broken naming breaks the hierarchy, LOD systems and shot assembly'],
    ['Mesh Data Name', 'WARNING', 'A mesh datablock name (Mesh.101) not matching the object '
     'name', 'Polluted datablocks surface in scripts and on linking'],
    ['Mat Numbering', 'WARNING', 'Material names with numbering (.001, .002)', 'A numbered '
     'material is a copy instead of the original; it breaks the material library'],
    ['Duplicated Names', 'BLOCKER', 'Matching object names in the scene', 'Name collisions '
     'break library linking and export - unlike Blender numbering this is a real conflict, '
     'not cosmetics'],
    ['Trailing Numbers', 'WARNING', 'Trailing numbers in names (bolt01, wheel2)', 'A '
     'convention check: proper partition numbering is strictly two digits after an '
     'underscore'],
], [3.2, 2.4, 6.2, 6.7], sev_col=1)

h2(doc, '5.7 MATERIALS (3)')
add_table(doc, [
    ['Check', 'Severity', 'What it looks for', 'Why it matters'],
    ['Mat Assignment', 'BLOCKER', 'Empty material slots', 'An object with an empty slot '
     'renders black/default - a defect in a production render'],
    ['Missing Textures', 'BLOCKER', 'Image Texture nodes with a missing file', 'A missing '
     'file = a pink/black render'],
    ['Mat Suffix', 'WARNING', 'Material names without the _mat suffix', 'A single suffix '
     'tells materials apart from meshes and groups in scripts'],
], [3.4, 2.4, 5.9, 6.8], sev_col=1)

h2(doc, '5.8 CLEANUP (1)')
add_table(doc, [
    ['Check', 'Severity', 'What it looks for', 'Why it matters'],
    ['Unused Data', 'WARNING', 'Empty vertex groups, unedited shape keys, junk custom '
     'attributes (stock Blender attributes are untouched; GN attributes are protected while '
     'the modifier is live)', 'Junk data bloats the file and confuses auto-riggers. The Fix '
     'removes the flagged items through a dialog'],
], [3.4, 2.4, 6.2, 6.5], sev_col=1)

h1(doc, '6. The hierarchy validator')

h2(doc, '6.1 Asset structure conventions')
p(doc, 'The asset hierarchy is assembled from group empties (Maya uses locators for this). '
       'The validator checks the structure against the conventions:')
for b in [
    'the asset root - a group empty with the _grp suffix (truck_a_grp, for example);',
    'inside - functional layers (geo, proxy, rig, wip etc.): the set is free, with a built-in '
    'whitelist of 24 common names, extendable in Preferences;',
    'partitions of repeated elements - strictly two-digit numbering after an underscore: '
    'bolt_01, bolt_02 (bolt_1 and bolt_002 are violations);',
    'every group with a group role carries the _grp suffix;',
    'names are lowercase, no .001, no forbidden characters, no default DCC names;',
    'lights and cameras are not part of the asset structure and are not validated; a static '
    'asset may be grouped right at the root.',
]:
    p(doc, b, bullet=True)

h2(doc, '6.2 Rules (13)')
add_table(doc, [
    ['Rule', 'Severity', 'What it catches'],
    ['Blender numbering (.001)', 'ERROR', 'Copies with .001 auto-numbering - a sign of '
     'duplication instead of renaming'],
    ['Missing group suffix', 'ERROR', 'A group with a group role missing the _grp suffix'],
    ['Forbidden characters', 'ERROR', 'Forbidden characters in node names'],
    ['Default DCC name', 'ERROR', 'Default package names (Cube, Empty, pCube1...)'],
    ['Empty group', 'ERROR', 'An empty with a group role and no children - an unfilled '
     'locator after import'],
    ['Uppercase in name', 'WARNING', 'Capital letters in the name'],
    ['Unknown functional layer', 'WARNING', 'A layer outside the whitelist (extended in '
     'Preferences)'],
    ['Orphan empty', 'WARNING', 'An empty unreachable from any asset root'],
    ['Orphan mesh', 'WARNING', 'A mesh unreachable from any asset root'],
    ['Name mismatch in group', 'WARNING', 'A node name not matching the <base> / <base>_NN '
     'pattern of its group'],
    ['Mesh under mesh', 'WARNING', 'A mesh parented to a mesh (a duplicate of the Parent '
     'Geometry check)'],
    ['No asset root', 'WARNING', 'No asset root in the scene'],
    ['Multiple asset roots', 'WARNING', 'Several roots - check that it is intentional'],
], [5.2, 2.8, 10.5], sev_col=1)

h2(doc, '6.3 Scanning')
for b in [
    'Scan - a manual scan start; the result is collapsible sections per asset root with '
    'their own ERROR/WARNING counters, plus "Not connected to any root" and scene-level '
    'finding sections.',
    'Issues only - show problem branches only.',
    'Live auto-scan: with Live enabled the scan reruns itself after structure changes (an '
    'FBX import, reparenting, renames). A "Stale" badge means the result is outdated - run '
    'Scan.',
    'An X on a finding - ignore the rule on that node; the "N ignored - clear" counter '
    'resets the ignores.',
]:
    p(doc, b, bullet=True)

h2(doc, '6.4 Fixes')
add_table(doc, [
    ['Fix', 'What it does'],
    ['Add _grp', 'Adds the _grp suffix to a group; name collisions are skipped with a report'],
    ['Renumber', 'Brings partition numbering to the two-digit base_01 grid (legal names are '
     'untouched; the rename is two-pass through temporary names - collision-free)'],
    ['Adopt Orphans', 'Connects orphaned nodes to a root: one root - automatically, several - '
     'with a dialog'],
    ['Create Root', 'Creates an asset root; an option to adopt the orphans right away'],
    ['Create Asset Skeleton', 'A static asset skeleton generator: the name comes from the '
     '.blend file, layers are picked from the whitelist with checkboxes. The asset is born '
     'legal, the validator accepts it'],
], [4.5, 14])
kv_note(doc, 'Every hierarchy fix rescans the structure right after applying.')

h2(doc, '6.5 The coordinator gate')
p(doc, 'In Artist Mode hierarchy findings do not affect the Asset Status - a WIP asset has '
       'the right to an unassembled structure. In Coordinator Mode hierarchy errors escalate '
       'the verdict: ERROR to CRITICAL, WARNING to REVIEW. The scan produces a verdict even '
       'for scenes without tracker-checked objects. The whitelist and suffix settings live '
       'in Preferences - Naming - Hierarchy.')

h1(doc, '7. Viewport overlays')
p(doc, 'Defects are painted over the geometry in the check color (the swatch in the check '
       'row, the palette in Preferences - Colors):')
add_table(doc, [
    ['Type', 'How it is drawn', 'Examples'],
    ['Faces', 'A semi-transparent face fill (Faces Alpha)', 'ngons, triangles, starlike, '
     'lamina, zero area, uv stretch, missing uvs'],
    ['Edges', 'Lines along edges (Edges Width / Edges Alpha); transform checks draw a heavy '
     'silhouette outline', 'non manifold, boundary edges, sharp edges, z-fighting, non '
     'applied transform, scale'],
    ['Points', 'Vertex/centroid markers (Vertex Size / Point Offset)', 'isolated verts, '
     'duplicate verts, poles, symmetry'],
], [2.8, 9.4, 6.8])
for b in [
    'X-Ray (a button in Pipeline Checks): off - the mesh walls occlude the far-side markers; '
    'on (default) - the markers show through everything. The stock viewport xray forces '
    'see-through.',
    'Face Offset / Point Offset - the marker offset from the surface, when the overlay '
    'flickers with the geometry.',
    'Sel in an object card selects the defect in edit mode; Show highlights without selecting.',
    'Face Orientation - the stock Blender normal overlay, invoked from the panel (blue/red = '
    'the normal direction).',
]:
    p(doc, b, bullet=True)

h1(doc, '8. Modes and tools')

h2(doc, '8.1 Live')
p(doc, 'Live watches the types of changes and recomputes only what was touched: topology '
     '(mesh edit, boolean, join), UV coordinates, transforms, object and mesh data renames. '
     'New scene objects join the validation automatically, the "Scene changed" badge '
     'reminds about scope extensions. The hierarchy is rescanned in Live too. For heavy '
     'scenes the revalidation runs in batches with progress on the panel.')

h2(doc, '8.2 Presets')
p(doc, 'A preset = a set of enabled checks + naming rules. Save with the + icon next to the '
     'dropdown, delete with -. Export/import as a file: a finished preset (say "midpoly" or '
     '"hero subdiv") can be handed to other users as a file. A preset is stored in the '
     'Blender preferences and survives addon updates.')

h2(doc, '8.3 Reports')
add_table(doc, [
    ['Format', 'Contents', 'Destination'],
    ['Copy Summary (artist)', 'A compact per-category summary + the validator signature and '
     'date', 'Clipboard'],
    ['Copy Report (coordinator)', 'The VALIDATION verdict: READY/REVIEW/BLOCKED + the '
     'BLOCKERS (fix first) and WARNINGS sections - the formal acceptance verdict',
     'Clipboard'],
    ['JSON / CSV / HTML', 'The full data: objects, checks, findings, hierarchy; the HTML '
     'carries the "Fix first" section', 'File'],
], [4.6, 10.4, 4])
kv_note(doc, 'The validator signature: Preferences - Interface - Validator (the OS login by '
             'default). It lands in every report and in Debug Info.')

h2(doc, '8.4 Fixes')
p(doc, 'Checks with automatic repair: Non Applied Transform, Scale (Apply Transform), '
       'Modifier Stack (Apply), Object/Group/Mesh Data Name (rename by policy), Mat '
       'Numbering, Unused Data (a cleanup dialog), the hierarchy fixes (section 6.4). The '
       'Fix button sits in the check row of an object card. In Coordinator Mode with '
       'Coordinator Lock every Fix is hidden - the coordinator looks but does not fix.')

h2(doc, '8.5 Checkpoint')
p(doc, 'Checkpoint Save pins the validation state into the scene (enabled checks + results), '
       'Checkpoint Load restores it. Useful before risky edits: save a checkpoint, '
       'experiment, load it back. A restore hint reminds you to press Run to recompute.')

h2(doc, '8.6 Pre-flight')
p(doc, 'Pre-flight FBX / USD is the gate before export: active BLOCKERs block the export '
     'with a report; WARNINGs only pass with a note. A broken asset never reaches the '
     'pipeline this way.')

h2(doc, '8.7 Logs and diagnostics')
for b in [
    'A session log is written to %TEMP%/stukach.log (about 256 KB rotation into .old).',
    'Debug Info into the clipboard: versions, mode, active checks, the log tail - paste it '
    'into a bug report.',
    'On a Blender crash the log is in %TEMP% - the first thing the author asks for.',
]:
    p(doc, b, bullet=True)

h1(doc, '9. Preferences')
p(doc, 'Preferences - Add-ons - STUKACH. Tabs: Interface, Overlay, UV, Naming, Checks, Colors.')
add_table(doc, [
    ['Tab', 'Settings'],
    ['Interface', 'Start in Coordinator Mode - the panel opens right in the acceptance mode; '
     'Coordinator Lock - hide every Fix button in Coordinator Mode (the coordinator validates '
     'only); Validator - the name in the report signatures.'],
    ['Overlay', 'X-Ray Overlay - marker transparency (section 7); Edges Width, Edges/Faces '
     'Alpha; Faces/Points Offset; Vertex Size.'],
    ['UV', 'Texel Density: texture size, target TD (px/cm), tolerance (Target = 0 shows the '
     'value only); UV Padding: shell and tile-border thresholds; stretch and aspect ratio '
     'thresholds.'],
    ['Naming', 'Objects and Groups: prefix/suffix lists (+/-); Mesh Data: the datablock '
     'suffix (_mesh by default); Hierarchy: the group suffix (_grp) and the functional '
     'whitelist (extends the 24 built-in layers).'],
    ['Checks', 'Hard Edges: the chamfer width threshold. An edge hugging a strip thinner than '
     'this percentage of the object size is a chamfer and is not flagged.'],
    ['Colors', 'The overlay color of every check, a two-column grid; applied to the viewport '
     'instantly.'],
], [3, 16])

h2(doc, '9.1 Updates')
p(doc, 'The Updates block: the Check for updates button compares the installed version with '
       'the latest GitHub release (one anonymous request, the UI never blocks).')
for b in [
    'The Check for updates daily toggle (on by default) - a silent auto-check once a day; '
    'when there is nothing new, nothing appears anywhere.',
    'When an update exists: the Update available: X.Y.Z line in the Preferences becomes a '
    'link to the release page, and a badge appears at the top of the STUKACH panel.',
    'Install the update the usual way: download the zip from the release page and install it '
    'via Install from Disk (section 2); the badge goes away afterwards.',
]:
    p(doc, b, bullet=True)

h1(doc, '10. How to use')

h2(doc, '10.1 For the artist')
for b in [
    'Load a ready check-set preset (Presets - import) or work with the default set; enable Live.',
    'RUN on the selection; widen to Scene/Collection to cover the whole scene.',
    'Work down the Objects list: Sel selects the defect and frames the camera, the overlay '
    'paints it in the check color, Live recomputes after edits automatically.',
    'BLOCKERs must be fixed (with the Fix button where possible), WARNINGs consciously '
    'accepted or fixed, INFOs at taste. Next Issue walks the remaining defects in a cycle.',
    'After an FBX import the new objects join Live by themselves and the hierarchy is '
    'rescanned automatically - put the structure in order with the section 6.4 fixes.',
    'Before delivery switch to Coordinator Mode and make sure the verdict is not BLOCKED; '
    'before experiments Checkpoint Save (section 8.5) is handy.',
]:
    p(doc, b, bullet=True)

h2(doc, '10.2 For the coordinator')
for b in [
    'Enable Coordinator Mode: the INFO checks hide, BLOCKER and WARNING remain.',
    'Run the validation over Scene (or the asset collection).',
    'Read the ASSET STATUS verdict: CRITICAL - there are blockers, REVIEW - there are '
    'warnings requiring a decision, READY - the asset is clean.',
    'Copy Report puts the formal verdict with the BLOCKERS (fix first) and WARNINGS sections '
    'into the clipboard.',
    'If you only validate, enable Coordinator Lock (Preferences - Interface): the Fix buttons '
    'hide; the Start in Coordinator Mode flag opens the panel right in that mode.',
]:
    p(doc, b, bullet=True)

h1(doc, '11. The Maya version')

h2(doc, '11.1 The panel')
p(doc, 'The STUKACH shelf button opens a panel with the same logic as in Blender: Run, the '
     'mode toolbar (Coordinator / Live / the "..." menu with coordinator flags), the score '
     'block, Next Issue, Copy Summary, Objects, ASSET STATUS, Delivery (Export / Pre-flight / '
     'Checkpoint), Debug Info. By default the panel docks to the left of the Attribute '
     'Editor; closing is the X, reopening is the shelf button (hot-reload built in).')

h2(doc, '11.2 Checks: 43 + two scene checks')
add_table(doc, [
    ['Category', 'Checks', 'Differences from Blender'],
    ['TOPOLOGY (14)', 'non manifold, boundary edges, isolated verts, duplicate verts, face '
     'aspect ratio, triangles, ngons, poles, zero area, z-fighting, hard edges, lamina, zero '
     'length edges, starlike', 'Hard Edges instead of Sharp Edges Not Hard: smooth edges '
     'with an angle of 30 degrees or more are flagged'],
    ['TRANSFORMS (6)', 'non applied transform, scale, construction history, origin at zero, '
     'uncentered pivots, parent geometry', 'Construction History (a binary check + node type '
     'parsing) instead of Modifier Stack'],
    ['SYMMETRY (3)', 'symmetry X / Y / Z', 'same as Blender'],
    ['UV (10)', 'single set, udim ready, udim bounds, material udim, overlap, micro shell, '
     'stretch, texel density, padding, missing uvs', 'There is UDIM Ready - the readiness of '
     'the UV set for UDIM tiles'],
    ['NAMING (6)', 'object name, group name, mat numbering, duplicated names, shape names, '
     'trailing numbers', 'Shape Names - the shape node name against the transform; no Mesh '
     'Data Name (that is a Blender concept)'],
    ['MATERIALS (3)', 'mat suffix, mat assignment, missing textures', 'same as Blender'],
    ['CLEANUP (1)', 'unused data (empty deformer sets, custom attributes)', 'same as Blender'],
    ['Scene', 'Scene Units + Empty Groups', 'Empty Groups - transforms without children: the '
     'classic empty groups left after rebuilds; removed manually only'],
], [3.2, 9.3, 6.5])

h2(doc, '11.3 Speed: the snapshot and progressive validation')
p(doc, 'Geometry is snapshotted in two OpenMaya iterator passes; 14 geometric checks run on '
     'a single traversal (no repeated scene queries). Validation runs as a queue of small '
     'batches - the Maya interface stays alive even on heavy scenes, with progress on the '
     'panel. Objects taking longer than a second are logged.')
kv_note(doc, 'Massive checks (hundreds of thousands of components) have a threshold: the '
             'report carries the honest count, while the overlay/selection uses an even '
             'sample of up to 5000 - the check row is marked "5000 sampled" and Sel is '
             'disabled.')

h2(doc, '11.4 The overlay')
p(doc, 'The colored defect highlight is drawn by a native Viewport 2.0 plugin '
     '(stukachDrawOverride): filled faces, edge lines, vertex markers, plus a wireframe box '
     'for transform checks. If the plugin is unavailable (another OS or Maya version), the '
     'overlay automatically falls back to display layers. The colors are configured with '
     'swatches on the panel.')

h2(doc, '11.5 Locator hierarchy')
for b in [
    'The asset structure is assembled in Maya with locator-groups following the section 6.1 '
    'conventions (_grp, base_01, lowercase names).',
    'After an FBX export/import the structure is checked by the hierarchy validator of the '
    'Blender version: groups made from locators arrive with the _grp suffix and pass the '
    'naming rules.',
    'There is no hierarchy validation in the Maya version - structural acceptance is done '
    'in Blender.',
]:
    p(doc, b, bullet=True)

h2(doc, '11.6 Maya version notes')
for b in [
    'Hard Edges stays silent in zones with custom normals (Weighted Normal and similar): '
    'Maya reads adjacent edges as hard - that is a package trait, not a checker bug.',
    'UV UDIM Bounds may flag clean objects with UVs on the tile border (uv = 1.0) - a known '
    'limitation, solved by a light seam shift.',
    'After STUKACH file updates always hot-reload with a second shelf button click - Maya '
    'does not re-read modules by itself.',
    'The log: %TEMP%/stukach_maya.log; Debug Info copies the diagnostics into the clipboard.',
    'Sel buttons on massive findings (>5000) are disabled - that is the freeze protection, '
    'the counter stays honest.',
]:
    p(doc, b, bullet=True)

h1(doc, '12. Troubleshooting')

kv_note(doc, 'Bug reports and wishes: github.com/abyrvalg379/STUKACH/issues (Blender), '
             'github.com/abyrvalg379/STUKACH_Maya/issues (Maya). Attach Debug Info and the '
             'reproduction scenario.')

add_table(doc, [
    ['Symptom', 'What it is and what to do'],
    ['"Settings restored - press Run to revalidate"', 'A stock STUKACH message: settings were '
     'restored from the scene on file load. Press Run - it is not a foreign addon and not an '
     'error.'],
    ['A "Scene changed" or Stale badge/hint', 'The scene changed after the run/scan. Re-run '
     'Run or Scan; in Live most of it is picked up automatically.'],
    ('An object does not appear in Objects', 'It is outside the validation scope: the first '
     'RUN takes Selected. Widen to Scene/Collection. A search filter or Issues-only is on - '
     'check the "N / M" header.'),
    ['The overlay shows through the mesh', 'That is the X-Ray button in Pipeline Checks '
     '(v1.7.5): turn it off and the walls will hide the far-side markers. An enabled Alt+Z '
     '(viewport xray) also forces the overlay to be transparent.'],
    ['Overlay markers flicker with the geometry', 'Raise Face/Point Offset in Pipeline Checks.'],
    ['A finding seems false', 'Check the check threshold in Preferences; ignore it precisely '
     '(Ign on the object, X on a hierarchy rule). If it is systematically false - attach '
     'Debug Info and write the author.'],
    ['The Fix button is unavailable / missing', 'The check has no auto-repair - it is edited '
     'by hand; or you are in Coordinator Mode with Coordinator Lock (the fixes are hidden on '
     'purpose).'],
    ('A big counter with Sel disabled ("5000 sampled")', 'The Maya freeze-protection '
     'threshold: the count is honest, selection/overlay work on a sample. Fix in areas.'),
    ['Maya: the panel did not appear after an update', 'Do a hot-reload with a second shelf '
     'button click; check the Plug-in Manager (stukachDrawOverride.mll). A Maya restart '
     'resolves the remaining cases.'],
    ['A Blender crash / hang', 'Do not close Blender until the log is taken: %TEMP%/'
     'stukach.log + the Debug Info button before the crash. Blender crash dumps (.crash) '
     'live in %TEMP%.'],
], [5.4, 13.6])

_save(doc, OUT)

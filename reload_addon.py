# Run this in Blender's Python console or via MCP to hot-reload STUKACH
import bpy, sys

MODULE = "bl_ext.user_default.stukach"

bpy.ops.preferences.addon_disable(module=MODULE)

to_del = [k for k in sys.modules if k == MODULE or k.startswith(MODULE + '.')]
for k in to_del:
    del sys.modules[k]

bpy.ops.preferences.addon_enable(module=MODULE)
print("[STUKACH] Reloaded OK")

"""Update checker — compare the installed version with the latest GitHub release.

Manual button in Preferences plus an optional silent daily auto-check
(Preferences toggle, default ON).  One anonymous GET to the public GitHub API
runs in a background thread, the result is polled back on the main thread via
bpy.app.timers.  No telemetry, no auto-install — on a newer release a badge
appears in the panel linking to the releases page.
"""

import json
import threading
import urllib.request
import webbrowser

import bpy

_REPO = "abyrvalg379/STUKACH"
_RELEASES_URL = f"https://github.com/{_REPO}/releases"
_API_URL = f"https://api.github.com/repos/{_REPO}/releases/latest"
_DAY = 24 * 3600

_busy = False


def _prefs():
    addon = bpy.context.preferences.addons.get(__name__.rsplit(".", 1)[0])
    return getattr(addon, "preferences", None) if addon else None


def _local_version_tuple():
    """Version from blender_manifest.toml (same source as the panel title)."""
    try:
        import sys
        from pathlib import Path
        try:
            import tomllib
        except ImportError:
            tomllib = None
        root = __name__.rsplit(".", 1)[0]
        base = Path(sys.modules[root].__file__).parent
        if tomllib is not None:
            with open(base / "blender_manifest.toml", "rb") as fh:
                ver = tomllib.load(fh).get("version", "0.0.0")
        else:
            ver = "0.0.0"
        return tuple(int(p) for p in str(ver).split(".")[:3])
    except Exception:
        return (0, 0, 0)


def _parse_tag(tag):
    parts = []
    for p in str(tag).strip().lstrip("vV").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def _stamp_path():
    import os
    import tempfile
    return os.path.join(tempfile.gettempdir(), "stukach_update_check.txt")


def _last_check_age():
    import time
    try:
        with open(_stamp_path()) as fh:
            return time.time() - float(fh.read().strip())
    except Exception:
        return None


def _write_stamp():
    import time
    try:
        with open(_stamp_path(), "w") as fh:
            fh.write(str(time.time()))
    except Exception:
        pass


def _fetch_latest():
    req = urllib.request.Request(_API_URL, headers={"User-Agent": "STUKACH-update-check"})
    with urllib.request.urlopen(req, timeout=6) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("tag_name", ""), data.get("html_url", _RELEASES_URL)


def start_check(silent=False):
    """Spawn the background request; results land in the preferences via timer.

    silent=True (the daily auto-check) never touches the button state or the
    result line — it only raises the panel badge when an update exists.
    """
    global _busy
    prefs = _prefs()
    if prefs is None or _busy:
        return
    _busy = True
    if not silent:
        prefs.update_checking = True
        prefs.update_result = "Checking..."
    box = {"done": False, "tag": "", "url": "", "error": ""}

    def worker():
        try:
            box["tag"], box["url"] = _fetch_latest()
        except Exception as e:
            box["error"] = str(e)
        box["done"] = True

    threading.Thread(target=worker, daemon=True).start()

    def poll():
        global _busy
        if not box["done"]:
            return 0.2
        _busy = False
        prefs = _prefs()
        if prefs is not None and not box["error"]:
            _write_stamp()
            if _parse_tag(box["tag"]) > _local_version_tuple():
                prefs.update_result = f"Update available: {box['tag']}"
                prefs.update_url = box["url"]
            elif not silent:
                prefs.update_result = f"Up to date ({box['tag']})"
                prefs.update_url = ""
        elif prefs is not None:
            if not silent:
                prefs.update_result = "Check failed (offline?)"
                prefs.update_url = ""
            print(f"[AssetChecker] update check failed: {box['error']}")
        return None  # unregister

    bpy.app.timers.register(poll, first_interval=0.2)


def _auto_tick():
    """Hourly lightweight re-arm: fires the silent check at most once a day."""
    prefs = _prefs()
    if prefs is not None and prefs.update_auto_check:
        age = _last_check_age()
        if age is None or age >= _DAY:
            start_check(silent=True)
    return 3600.0


def open_releases(context):
    prefs = _prefs()
    url = (getattr(prefs, "update_url", "") or "") if prefs else ""
    webbrowser.open(url or _RELEASES_URL)


class ASSET_CHECKER_OT_check_updates(bpy.types.Operator):
    bl_idname = "asset_checker.check_updates"
    bl_label = "Check for updates"
    bl_description = ("Compare the installed version with the latest GitHub "
                      "release (one anonymous request)")
    bl_options = {'REGISTER'}

    def execute(self, context):
        start_check()
        return {'FINISHED'}


class ASSET_CHECKER_OT_open_releases(bpy.types.Operator):
    bl_idname = "asset_checker.open_releases"
    bl_label = "Open Releases Page"
    bl_description = "Open the GitHub releases page in the browser"

    def execute(self, context):
        open_releases(context)
        return {'FINISHED'}


classes = (ASSET_CHECKER_OT_check_updates, ASSET_CHECKER_OT_open_releases)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if not bpy.app.timers.is_registered(_auto_tick):
        bpy.app.timers.register(_auto_tick, first_interval=10.0)


def unregister():
    if bpy.app.timers.is_registered(_auto_tick):
        bpy.app.timers.unregister(_auto_tick)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

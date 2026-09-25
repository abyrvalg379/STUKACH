# STUKACH — Roadmap

## Blender version

### Update checker (auto-update notifications)
- Daily background check of `api.github.com/repos/abyrvalg379/STUKACH/releases/latest`
  vs the local manifest version (threaded, non-blocking, silent on offline/proxy errors).
- Cached check timestamp — one request per 24h, zero telemetry.
- Panel header badge "Update: vX.Y.Z" + click opens the releases page.
- Preferences toggle "Check for updates" (default ON).
- No auto-install: show release link, user installs via Install from Disk.
- Candidate for the next feature release (v1.8.0).
- Reusable module (`owner/repo` parameter) — planned rollout to the other
  Blender products in the abyrvalg379 profile.

## Maya version

### Backlog (from v1.3.0)
- Migrate remaining legacy checks to the snapshot engine
- DCC-free `stukach_core` package (gate for the Houdini version)

## Cross-DCC
- Houdini version: after `stukach_core` (MVP on FBX, USD phase 2)
- 3ds Max: adapter after the core extraction (~2 sessions), cheap interim
  option — a "Max-inbound" preset in the Blender version

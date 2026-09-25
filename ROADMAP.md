# STUKACH — Roadmap

## In main since v1.8.0 (waiting for the next release)
Category switches in Preferences, category issue counters, Next Issue hotkey
(Shift+N, toggleable), stale-badge fix, crash fix (Live + Auto Merge modal
guard), Sel context fix, Hard Edges: angle threshold knob (default 60) +
bevel-aware + custom-normals skip, Blender 4.2+ support, manuals v1.8.0.
Release candidate: **v1.9.0**.

## v1.9.x — UX pass
- **HUD in the viewport**: validation status (`WARNING · 3B / 12W`) and, on
  focusing a finding (Sel / Next Issue), **what the finding is** — check name,
  count, object — because small defects are hard to see even with overlays.
- **Objects panel redesign**: current list is noisy (search + toggles +
  dropdown + Collapse All + V/E/F/T + 3-button rows in one stack). Redesign
  mockup first, approval by the author, then implementation.
- **Profiles in Preferences > Checks**: quick buttons ("All", "Modeler" =
  Topology + Transforms) driving the category switches in one click.
- **Auto-advance after Fix**: a successful fix jumps to the next issue
  (toggleable) — long fix lists become Fix / Fix / Fix.
- **Skip hidden objects** option for Scene scope (big assemblies).
- **Status-bar report** when RUN completes ("STUKACH: 5 issues in 38 objects").
- **Default preset**: one preset marked to auto-apply on new scenes.
- **Check search field**; "?" on a finding opens its manual section.

## v2.0 — STUKACH AI (local, Ollama)
Principles: validation stays deterministic; the AI explains, plans and
propagates — the human approves; everything local (localhost), zero telemetry;
every AI-assisted edit is previewable and one-shot undoable.

- **A. Advisor** — "Explain this finding" on every finding row: a structured
  prompt (check, severity, counts, metric, object stats) to a local model,
  the answer streams into a floating panel.  Read-only, no geometry access.
- **B. Chat with context** — "build a fix plan from this report", questions
  about rules, thresholds and the manual, grounded on the check registry.
- **C. Fix propagation — "do the same elsewhere"** (the flagship):
  1. the artist fixes one defect manually in Edit Mode;
  2. STUKACH captures the fix as a before/after BMesh diff (elements moved /
     merged / deleted / dissolved);
  3. similar findings are matched (same check + local topology similarity,
     LLM-assisted mapping between the fixed pattern and each candidate);
  4. the model produces a per-instance op plan; execution is deterministic
     bmesh ops with a preview list, per-instance accept/skip and one-shot
     undo.  AI plans, bmesh executes, the human approves.
- **Infra**: Ollama detection (localhost:11434, urllib — zero dependencies),
  model picker in Preferences, context builder over the check registry,
  streaming into the panel, graceful offline ("Ollama is not running").

## Maya
- Migrate the remaining legacy checks to the snapshot engine
- DCC-free `stukach_core` package (gate for the Houdini version)

## Cross-DCC
- Houdini version: after `stukach_core` (MVP on FBX, USD phase 2)
- 3ds Max: adapter after the core extraction; cheap interim — a "Max-inbound"
  preset in the Blender version

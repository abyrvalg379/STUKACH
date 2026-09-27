# STUKACH — Roadmap

> Политика версий до 2.0: небольшие частые релизы, фокус на удобстве и
> комфорте работы; попутно — поиск и фикс багов.  ИИ — отдельная большая
> тема, внедряем постепенно, когда созреет.

## v1.8.1 — готово в main, ждёт релиза
Category switches in Preferences, category issue counters, Next Issue hotkey
(Shift+N, toggleable), stale-badge fix, crash fix (Live + Auto Merge modal
guard), Sel context fix, Hard Edges: angle threshold knob (default 60) +
bevel-aware + custom-normals skip, Blender 4.2+ support, manuals v1.8.0.

## v1.8.2 — комфорт
- **HUD in the viewport**: validation status (`WARNING · 3B / 12W`) and, on
  focusing a finding (Sel / Next Issue), **what the finding is** — check name,
  count, object — because small defects are hard to see even with overlays.
- **Auto-advance after Fix**: a successful fix jumps to the next issue
  (toggleable) — long fix lists become Fix / Fix / Fix.
- **Status-bar report** when RUN completes ("STUKACH: 5 issues in 38 objects").
- **Profiles in Preferences > Checks**: quick buttons ("All", "Modeler" =
  Topology + Transforms) driving the category switches in one click.

## v1.9.x — панели и масштаб
- **Objects panel redesign**: the list is noisy (search + toggles + dropdown +
  Collapse All + V/E/F/T + 3-button rows in one stack).  Redesign mockup
  first, approval by the author, then implementation.
- **Skip hidden objects** option for Scene scope (big assemblies); measure
  performance on 100k+ object assemblies alongside (snapshot engine + dirty
  caching already cover the common case — this is about the extremes).
- **Default preset**: one preset marked as default.  Applied at the FIRST
  validation run in a new scene with a one-time dialog — never silently
  ("everything turned red after the update" is a release-notes generator).
- **Check search field**; "?" on a finding opens its manual section.
- **Checker reference generated from the registry**: markdown/docx tables
  from CHECK_SEVERITY / CHECK_CATEGORIES via the manual generator, built in
  CI — retires the hand-maintained pair reference (stale since v1.5.2).
- **Blender compatibility policy in README** (public): supported = 4.2 LTS +
  5.2, the CI matrix is the gate; Blender API breaking changes get a major
  bump.

## Inter-object Z-fighting — open semantic question
Exact duplicates and overlapping-face pairs are caught (KD-tree centroid
pass).  Strictly parallel planes with a small offset are NOT, and cannot be
without false positives: panel lines and decals are legitimately coplanar.
The fix is semantic, not algorithmic — pick one:
- **Decal whitelist**: skip pairs by material or name pattern (decal tag);
- **Tolerance knob**: user-configurable offset threshold, default off.
Either way, document the limitation honestly in the checker's help.

## v2.0 — STUKACH AI (локальный Ollama) — когда созреет
Principles: validation stays deterministic; the AI explains, plans and
propagates — the human approves; everything local (localhost), zero telemetry;
every AI-assisted edit is previewable and one-shot undoable.

- **A. Advisor** — "Explain this finding" on every finding row: a structured
  prompt (check, severity, counts, metric, object stats) to a local model,
  the answer streams into a floating panel.  Read-only, no geometry access.
- **B. Chat with context** — "build a fix plan from this report", questions
  about rules, thresholds and the manual, grounded on the check registry.
- **C. Fix propagation — "do the same elsewhere"**:
  1. the artist fixes one defect manually in Edit Mode;
  2. STUKACH captures the fix as a before/after BMesh diff (elements moved /
     merged / deleted / dissolved);
  3. similar findings are matched (same check + local topology similarity,
     LLM-assisted mapping between the fixed pattern and each candidate);
  4. the model produces a per-instance op plan; execution is deterministic
   bmesh ops with a preview list, per-instance accept/skip and one-shot
   undo.  AI plans, bmesh executes, the human approves.  Safety rails:
   a golden set of 20–30 real propagation cases as the regression gate, and
   a confidence threshold — below it the mapping is simply not offered
   (this separates "smart tool" from "roulette that occasionally wrecks
   a scene").
- **Infra**: Ollama detection (localhost:11434, urllib — zero dependencies),
  model picker in Preferences, context builder over the check registry,
  streaming into the panel, graceful offline ("Ollama is not running").

## Community
- **Enable GitHub Discussions** (or a feedback issue template): ~100 users
  and zero issues is not a quality signal — unhappy users uninstall silently.
  Without a feedback channel we don't know the real failure modes.

## Transferability criterion (bus factor = 1 today)
The project is ready to hand over when: the core lives as a separate package
independent of both DCC layers, checkers are data in a registry (not spread
across DCC code), manuals are generated from the registry, and both smoke
gates run without the author.  Two of these already hold; stukach_core +
registry is the path to the rest.

## Maya
- Migrate the remaining legacy checks to the snapshot engine
- DCC-free `stukach_core` package (gate for the Houdini version)
- No Maya CI is planned (Maya in CI is not cheap); the testing strategy is:
  snapshot engine tested as pure Python, the DCC layer stays thin.

## Cross-DCC
- Houdini version: after `stukach_core` (MVP on FBX, USD phase 2)
- 3ds Max: adapter after the core extraction; cheap interim — a "Max-inbound"
  preset in the Blender version

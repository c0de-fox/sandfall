# Sandfall — Consolidated Backlog

> **How to use:** this is a **re-ranking aid, not a commitment**. It aggregates
> the deferred items from every plan's Out-of-Scope section so the next "what
> next?" is a one-file read instead of an 8-plan re-survey. At each stopping
> point, **re-rank these against current context** (what just shipped, what the
> user is asking for, what's now cheap) rather than executing top-to-bottom.
> Each item cites its `source:` plan/reflection so you can pull the full
> rationale in one hop.

## In progress

- **`Grid.move` raw-array fast-swap** is currently being planned under
  `.agent/tasks/perf-grid-move/` (collapses the per-move `swap` from 12 Grid
  method calls to 1; ~2-3× on the busy/moving-scene per-cell rule cost; the
  deferred `can_displace` LUT in **Tier 1** below is its planned follow-on).
  `source: perf-grid-move/00` (this round); flagged in
  `performance-active-set/00` + `performance-dormant-cells/00` Out-of-Scope.

---

## Tier 1 — high value, feasible

- **More elements: acid** (dissolves materials), **oil** (flammable liquid,
  floats on water), **salt** (dissolves in water), **metal** (conducts/melts),
  **gunpowder** (explosive). The thermal system + the documented "Adding a new
  element" recipe make each rich and cheap.
  `source: sandfall/00` (acid/lava/oil/salt/electricity), `sandfall-temperature/00` (oil/acid/metal phase-change elements).
- **Save/load + stamps** — persist scenes; copy/paste regions. Pure UX, no sim
  change.
  `source: sandfall/00` (save/load, undo, scene presets), `sandfall-temperature/00` (save/load + stamps).
- **Line tool + eyedropper + element hotkeys (1-9).** Cheap UX completions to
  the brush/palette shipped under `brush-zoom-ui`.
  `source: brush-zoom-ui/00` (line tool / more brush shapes), `sandfall-temperature/00` (eyedropper).
- **(Perf) `can_displace` phase/density LUT** — the next busy-scene perf lever
  after `Grid.move`. `can_displace` does two `ELEMENTS` dict lookups per
  candidate neighbor; a lookup table indexed by `(src_id, target_id)` would cut
  it to one array read.
  `source: perf-grid-move/00` Out-of-Scope (the named follow-on to this round's swap fast-path).

## Tier 2 — strong value, bigger scope

- **Electricity / conductivity** — wires, sparks, machines. (Name clash to
  resolve: the existing `conductivity` is a *heat* conductivity, not electrical.)
  `source: sandfall-temperature/00` (Electricity / conductivity-as-current; Sandboxels / Powder Toy have it).
- **Cross-platform builds + CI** — Windows `.exe` and macOS `.app` via
  PyInstaller, plus a GitHub Actions matrix (`windows-latest`, `macos-latest`,
  `ubuntu-latest`) uploading `dist/sandfall*` per release tag. PyInstaller
  cannot cross-compile, so each platform builds on its own runner. Only the
  Linux binary is validated today.
  `source: project `AGENTS.md` (Future Work) + `README` + `sandfall/00` (Windows/macOS builds + CI explicitly deferred).
- **Ambient thermostat / Newton's-law-of-cooling drift** toward `AMBIENT_TEMP`
  — the closed, insulated thermal system slowly accumulates heat over a long
  session (fire re-asserts burn-temp every step); this is the documented
  mitigation.
  `source: thermal-conservation-fix/00` Out-of-Scope + Decision Log #1 (user declined it for the fix; tracked for later).

## Tier 3 — polish

- **Glow / lighting from hot cells** — prettier than the flat `H` heat overlay.
  `source: sandfall-temperature/00` (Glow / lighting), `sandfall-temperature/04-reflection` (Suggestions).
- **Persistent viewport zoom + pan** — a real zoom factor applied to input
  mapping + pan state + minimap. (The follow-cursor magnifier in
  `brush-zoom-ui` was the deliberately lighter alternative.)
  `source: brush-zoom-ui/00` (Persistent viewport zoom + pan).
- **HEAT HUD indicator + cache heat-overlay RGB when paused.** Mirror the
  `PAUSED` glyph with a small `HEAT` marker; and short-circuit `render_heat` to
  reuse the last RGB when paused (matters only if the grid grows large).
  `source: sandfall-temperature/04-reflection` (Suggestions).
- **Rebindable hotkeys** — `Tab`/`Z`/`Space`/`N`/`H` are currently hardcoded.
  `source: brush-zoom-ui/00` (Rebindable hotkeys).

## Cleanup / hygiene

- **Remove the now-redundant `lava.py` steam-acceptance workaround** (commit
  `d65c4ab`; the STEAM-neighbor branch + docstring). Belt-and-suspenders since
  heat capacity: with WATER `cp=4` the adjacent water no longer pre-boils in
  one step, so the workaround is harmless but dead weight.
  `source: thermal-conservation-fix/00` Out-of-Scope + Decision Log #4.
- **`float32` temp storage** — eliminates the residual ~2.4% rounding drain
  that remains after round-to-nearest (`~10/410`). Not needed for correctness,
  but a clean future tidy; `int16` storage is kept for now.
  `source: thermal-conservation-fix/00` Decision Log #3 (round-to-nearest vs float32 trade-off) + its reflection.

## Also deferred (tracked for completeness — lower priority)

One-liners so this file genuinely covers every source Out-of-Scope section:

- **Sound, particles, screen shake, shaders.** `source: sandfall/00`.
- **Pressure / airflow simulation** (Powder Toy / Noita have it).
  `source: sandfall-temperature/00`.
- **Harmonic-mean face conductivity** (physically "correct" series-resistor
  form for insulator sandwiches). Revisit only if play shows insulators leaking
  too fast. `source: thermal-conservation-fix/00`.
- **Per-element conductivity tuning / flammability & phase-threshold retunes.**
  `source: thermal-conservation-fix/00`.
- **More brush shapes** (triangle, spray). Disk + Square shipped.
  `source: brush-zoom-ui/00`.
- **Brush-size/zoom numeric HUD readout** beyond the existing `r=`; **rich
  tooltip styling** (multi-line, icons, descriptions). `source: brush-zoom-ui/00`.
- **Throttling the particle-count HUD** (every N frames) or **incremental
  active-set tracking** (running count / dirty-cell set). The full-grid sum is
  ~0.04 ms — revisit only on much larger grids. `source: performance-active-set/00`, `performance-dormant-cells/00`.

## Rejected (do NOT plan)

- **Multithreading.** The GIL blocks real parallelism and the movement scan is
  intrinsically sequential (a cell's move depends on cells scanned before it in
  the same frame).
  `source: performance-active-set/00`, `performance-dormant-cells/00`.
- **GPU offloading.** The bottleneck is the sequential Python cellular-automaton
  scan, not rendering (~1 ms) or diffusion (~2.5 ms) — both already cheap and
  vectorized.
  `source: performance-active-set/00`, `performance-dormant-cells/00`.
- **A 2D single-pass `np.argwhere` active set.** Loses the per-row grouping
  needed for the per-row random scan direction — a behavior change, not an
  optimization. `source: performance-active-set/00`.

> **Note on already-shipped items** (kept out of the tiers above to avoid
> confusion): **per-element heat capacity** was deferred in
> `sandfall-temperature/00` but has since **shipped** under
> `thermal-conservation-fix/`; **Numba JIT** remains genuinely deferred (heavy
> dependency, restructures the rule registry) but is the single biggest latent
> perf lever (~10-50×) if the Python scan ever becomes the wall again.

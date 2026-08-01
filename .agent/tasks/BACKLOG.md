# Sandfall — Consolidated Backlog

> **How to use:** this is a **re-ranking aid, not a commitment**. It aggregates
> the deferred items from every plan's Out-of-Scope section so the next "what
> next?" is a one-file read instead of an 8-plan re-survey. At each stopping
> point, **re-rank these against current context** (what just shipped, what the
> user is asking for, what's now cheap) rather than executing top-to-bottom.
> Each item cites its `source:` plan/reflection so you can pull the full
> rationale in one hop.

## Recently shipped

(Everything that landed recently. Commit hashes for traceability.)

- **Thermal realism rework** (`7544f95`, `be7c194`) — ice reverted to a realistic
  non-source "frozen water" (melts at >0°C); **dry ice** (DRY_ICE=16, persistent
  solid cold source at -78°C) and **liquid nitrogen** (LN2=17, transient cold
  liquid at -196°C that boils off) added as the real cold sources.
- **Liquid through gas** (`752c253`) — liquids/powders now displace gases (water
  flows through steam walls, sand falls through steam). Complements gas buoyancy.
- **Gas buoyancy** (`a55ac54`) — steam and smoke rise through liquids.
- **Gunpowder + explosions** (`1b911f0`) — GUNPOWDER=15; detonates via thermal
  flashpoint (heat-triggered chain reactions); reusable `blast.explode` helper
  (heat burst + crater + scatter, destroys everything).
- **Acid/base neutralization steam-fix** (`05e3449`) — acid+base → hot STEAM
  (exothermic, condenses to water); ~1:1 (dilute cascade removed).
- **Acid + Base + Oil** (`177cf23`, `60eaf55`) — ACID=12/BASE=13 (consumed-on-
  dissolve; acid eats all but glass, base eats all but stone); OIL=14 (light
  flammable liquid, floats on water).
- **Float temps** (`c575ccb`) — `_temp` float32 (kills the int16 rounding stall).
- **Cross-platform builds + CI** (`d60654a`) — Windows/Linux/macOS binaries via
  GitHub Actions; first release v0.1.0 shipped (unsigned; signing deferred).
- **`Grid.move` + dormant cells + sparse scan** (`85f6a68`, `06b311d`, `03fc34d`)
  — performance: ~60 FPS with 28k settled particles.
- **Brush shapes + magnifier + tooltips + palette reorg** (`3c1a6b5`–`707e115`).

---

## Tier 1 — high value, feasible

- **More elements:** ~~**acid** (dissolves materials), **oil** (flammable
  liquid, floats on water)~~ *(done — acid/base pair in Phase 01, oil in
  Phase 02 of the new-elements plan)*, **salt** (dissolves in water), **metal**
  (conducts/melts), ~~**gunpowder** (explosive)~~ *(done — gunpowder + the
  reusable `blast.explode` helper shipped in the `gunpowder/` plan; thermal
  flashpoint trigger + heat burst crater/scatter, chain reactions for free)*.
  The thermal system + the documented "Adding a new element" recipe make each
  rich and cheap.
  `source: sandfall/00` (acid/lava/oil/salt/electricity), `sandfall-temperature/00` (oil/acid/metal phase-change elements).
- **Save/load + stamps** — persist scenes; copy/paste regions. Pure UX, no sim
  change.
  `source: sandfall/00` (save/load, undo, scene presets), `sandfall-temperature/00` (save/load + stamps).
- **Line tool + eyedropper + element hotkeys (1-9).** Cheap UX completions to
  the brush/palette shipped under `brush-zoom-ui`.
  `source: brush-zoom-ui/00` (line tool / more brush shapes), `sandfall-temperature/00` (eyedropper).
- **Plant growth review** — plant grows too slowly (`GROW_CHANCE=0.02` ≈ ~50
  steps per new cell on average when water-adjacent) and the water-proximity
  growth mechanic is not obvious/discoverable. Look at: (a) tuning
  `GROW_CHANCE` up; (b) making the water→growth interaction visible (a cue when
  plant is near water, or a tooltip/description noting it grows adjacent to
  water). `source:` user feedback.
- **Fire + water extinguish mechanic** — water currently shoves FIRE aside (no
  douse). Add a fire+water→steam/EMPTY reaction. Also unblocks fire rising
  through liquids (gas-buoyancy excluded fire for this reason).
  `source: liquid-through-gas/01-reflection` (fire-displacement edge), `gas-buoyancy/00`.
- **(Perf) `can_displace` phase/density LUT** — the next busy-scene perf lever
  after `Grid.move`. `can_displace` does two `ELEMENTS` dict lookups per
  candidate neighbor; a lookup table indexed by `(src_id, target_id)` would cut
  it to one array read.
  `source: perf-grid-move/00` Out-of-Scope (the named follow-on to this round's swap fast-path).

## Tier 2 — strong value, bigger scope

- **Electricity / conductivity** — wires, sparks, machines. (Name clash to
  resolve: the existing `conductivity` is a *heat* conductivity, not electrical.)
  `source: sandfall-temperature/00` (Electricity / conductivity-as-current; Sandboxels / Powder Toy have it).
- **Ambient thermostat / Newton's-law-of-cooling drift** toward `AMBIENT_TEMP`
  — the closed, insulated thermal system slowly accumulates heat over a long
  session (fire re-asserts burn-temp every step); this is the documented
  mitigation.
  `source: thermal-conservation-fix/00` Out-of-Scope + Decision Log #1 (user declined it for the fix; tracked for later).
- **More explosives** (TNT, bombs) — the `blast.explode` helper is reusable;
  `BLAST_RADIUS` is the knob. A fuse/detonator element (gunpowder is currently
  heat-triggered only) is the natural companion.
  `source: gunpowder/00` Out-of-Scope.
- **Concentration / mixing system for acid-base (Scope B chemistry layer).** A
  per-cell **concentration** field for ACID/BASE (0.0–1.0) that **diffuses/mixes
  like heat** (reuses the diffusion machinery), so "diluted acid" is a real,
  visible state instead of being indistinguishable from water. Built on that:
  **dissolution scaled by concentration** (weak/dilute acid dissolves slowly or
  not at all below a threshold — fixes "dilute acid dissolves nothing / looks
  like water"); **stoichiometric neutralization** (acid+base consume
  concentration ~1:1, exothermic proportional to the amount reacted, rather
  than consuming whole cells); and a **mixing heatmap** (`M` key, mirroring `H`)
  showing acid=red / base=blue intensity by concentration. This is the proper
  fix for the two user notes deferred from the acid/base neutralization fix; it
  is a thermal-scale chemistry layer (~3 phases: concentration field + diffusion,
  dissolution/neutralization rework, heatmap + UI). The interim **Scope A
  steam-fix** (acid+base → hot STEAM, breaking the dilute cascade to ~1:1)
  shipped first as a cheap behavior fix; this is the deliberate follow-on.
  `source: acid-base-neutralization/00` Out-of-Scope + Decision Log #2 (Scope A quick steam-fix approved; Scope B concentration system deferred here).

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
- **`float32` temp storage** — **SHIPPED** (`c575ccb`). Was deferred as a tidy;
  became necessary (int16 round-to-nearest stall broke ice-freezing-water). No
  longer pending.

## Also deferred (tracked for completeness — lower priority)

One-liners so this file genuinely covers every source Out-of-Scope section:

- **Cold-gas / cryogenic element** — for dry-ice sublimation and LN2 evaporation
  puffs (currently emit EMPTY/SMOKE). `source: thermal-realism/02-reflection`.
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

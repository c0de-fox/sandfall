# Sandfall Temperature / Heat Field — Master Plan

## Problem Statement

The v1 sandfall game (built under `.agent/tasks/sandfall/` and refined under
`.agent/tasks/sandfall-improvements/`) ships 7 interacting elements, a resizable
window, and a Linux single-binary build. Its single biggest missing mechanic is a
**thermal model**:

- Fire currently spreads by a **per-step probability** over flammable neighbors
  (`SPREAD_FACTOR = 0.3` multiplied by `target.flammability`, `fire.py:31` +
  `fire.py:59-72`). It does not heat anything; nothing has a temperature; phase
  changes (boil / freeze / melt) are impossible because the state to drive them
  does not exist.
- Research benchmark: ~11 of 13 notable falling-sand games (The Powder Toy,
  Noita, Sandboxels, *sand:box*, Atom Craft, etc.) have a real per-cell
  temperature field. Sandfall is the outlier.

This plan adds a per-cell **temperature field** with **heat diffusion** and
**phase changes**, and **replaces** the probabilistic fire spread with
temperature-driven combustion.

## Solution Summary

Four sequential phases, each a single atomic commit + reflection. The grid gains
a third parallel array (`_temp`, `int16`) that mirrors the consistency contract
the existing `_life` array already obeys; a single vectorized numpy diffusion
pass runs **before** the per-cell movement scan; fire becomes a heat source
rather than a spreader; four new elements (STEAM, ICE, LAVA, GLASS) exercise
boil/freeze/melt/condense transitions; and an `H` key renders a heat-map overlay
so the otherwise-invisible field is observable.

- **Phase 01 — Thermal data model (plumbing).** Add `_temp: int16` to `Grid` with
  `get_temp`/`set_temp` (clip to `[-200, 3000]`); extend `swap`, `fill_circle`,
  and `migrate_grid` to carry temp exactly as they carry life; extend the
  `Element` dataclass with thermal fields (`temp_spawn`, `flashpoint`,
  `conductivity`, and transition thresholds used in Phase 03); add `AMBIENT_TEMP`
  + diffusion tunables to `config.py`; create a new pure module
  `src/sandfall/thermal.py` with `diffuse_temps(temp, ids, cond_lut, rate)` and a
  conductivity-LUT builder; wire `Simulation.step` to run diffusion before the
  scan; update `paint_brush` to set spawn-temp (mirroring its life-seeding pass).
  No visible behavior change yet — pure plumbing.
- **Phase 02 — Thermal combustion.** Refactor `rules/fire.py`: fire sets /
  maintains its own burn-temp (~800) and emits heat to neighbors **via the
  diffusion pass**; **remove `SPREAD_FACTOR`** and the probabilistic
  neighbor-ignition loop (`fire.py:59-72`). Make `WOOD` and `PLANT` rules
  **reactive**: if `get_temp(x,y) > ELEMENTS[id].flashpoint` then become `FIRE`
  + seed life + set burn-temp (return `None`). Keep `SMOKE_CHANCE` smoke spawn
  and fire's rise behavior.
- **Phase 03 — Phase changes + 4 new elements.** Add `ElementId.STEAM`, `ICE`,
  `LAVA`, `GLASS` (8 → 12 members — a deliberate deviation from the v1 "no new
  members" note at `elements.py:10-14`; documented below). Add `ELEMENTS` entries
  with thermal fields + colors + rules (STEAM rises + condenses→WATER; ICE
  static + melts→WATER; LAVA liquid-like + cools→STONE + LAVA+WATER→
  STEAM+STONE; GLASS static, made by sand melting). Update `WATER`/`SAND` rules
  with boil/freeze/melt branches. Recompute the palette min-width math in
  `config.py` (12 swatches).
- **Phase 04 — Heat visualization + docs.** Add an `H` key toggle in `game.py`
  for a heat-overlay render mode; add pure `thermal_to_rgb(temp)` in
  `thermal.py` (blue→cyan→yellow→red, ambient-neutral) and a
  `Renderer.render_heat` path. Unit-test the gradient headlessly. Update
  `README.md` and `docs/ARCHITECTURE.md`.

## Phase List

| #  | Phase                                              | Cx | Depends On | Parallelizable With |
|----|----------------------------------------------------|----|------------|---------------------|
| 01 | Thermal data model (temp array + diffusion + plumbing) | M  | —          | —                   |
| 02 | Thermal combustion (fire = heat source; reactive ignition) | M  | 01         | —                   |
| 03 | Phase changes + 4 new elements (STEAM/ICE/LAVA/GLASS)  | L  | 02         | —                   |
| 04 | Heat visualization + docs (H overlay)              | M  | 03         | —                   |

## Dependency Map

```
01 (data model + diffusion) ──► 02 (combustion) ──► 03 (phase changes + elements) ──► 04 (viz + docs) ──► done
```

**All four are strictly sequential — DO NOT parallelize.** Reason: every phase
mutates the same shared core files (`grid.py`, `elements.py`, `simulation.py`,
`rules/_common.py`) and each builds directly on the previous phase's contract:

- **01 → 02**: Phase 02 depends on the `_temp` array, `get_temp`, the `Element`
  thermal fields (`flashpoint`, `burn_temp`), the conductivity LUT, and the
  diffusion pre-pass that Phase 01 introduces. Combustion cannot be written
  before the field it reads exists.
- **02 → 03**: Phase 03's transitions (water boils, sand melts, lava cools) are
  *temperature-driven rules*, and they coexist with fire's new heat-source
  behavior. Phase 02 must have already decoupled ignition from fire's scan (the
  reactive-rule contract relaxation) before more reactive rules are layered on.
  Phase 03 also removes the last `flammability`-based spread assumption.
- **03 → 04**: The heat overlay is the primary way to *see* the new field and
  the new phase changes in action; it makes little sense without the elements
  that exercise it. It is also the smallest phase and the natural place to write
  up the whole feature in docs.
- A phase may only START once its dependency has passed **all** verification
  gates (see each phase file).

## Decision Log

All decisions below are **user-approved** and must not be re-litigated. The
phrasing "user-approved" is taken from the prompt that authorized this plan.

1. **Temperature storage = a third parallel array on `Grid`: `_temp` (`int16`).**
   Mirrors the existing `_life` array consistency contract. `int16` (not
   `uint8`) because sand melts near 1700 and freezing needs sub-zero; clip band
   `[-200, 3000]`. Initialized everywhere to `AMBIENT_TEMP` (20), integer
   degrees-C-like units. *(Alternative considered: a `float32` field — rejected:
   the rest of the grid is integer (`uint8` ids/life); integer temp keeps the
   hot path branch-free and the LUT/diffusion trivially vectorized; the clip band
   fits `int16` with enormous headroom.)*
2. **Temp mirrors the `life` consistency contract exactly.** `swap` carries
   temp; `fill_circle` resets temp to `AMBIENT` (mirrors zeroing life,
   `grid.py:137-153`); `paint_brush` sets element-specific spawn-temp afterward
   (mirrors life-seeding, `brush.py:37-52`); `migrate_grid` copies the temp
   overlap (`grid.py:169-173`). One new array, the same three seams.
3. **Heat diffusion = a separate vectorized numpy pass run BEFORE the movement
   scan in `Simulation.step`.** Lives in a new pure module
   `src/sandfall/thermal.py` as `diffuse_temps(temp, ids, cond_lut, rate) ->
   new_temp`. Per-material conductivity via a conductivity LUT indexed by the id
   array (same LUT pattern as `renderer.build_color_lut`, `renderer.py:26-42`).
   This keeps the hot path cheap: the movement scan is unchanged and diffusion
   is one numpy op — directly mitigates perf risk #1 noted in
   `.agent/tasks/sandfall/00-overview.md:83`. *(Alternative considered: diffuse
   inside the per-cell scan — rejected: would be O(cells) Python again and would
   reintroduce the exact cost the v1 plan worried about.)*
4. **Combustion REPLACES the probabilistic fire spread.** Remove `SPREAD_FACTOR`
   (`fire.py:31`) and the probabilistic neighbor-ignition loop
   (`fire.py:59-72`). Fire only **emits/maintains heat**; a flammable cell
   ignites when its OWN temp exceeds its `flashpoint`. Ignition is the fuel's own
   rule (WOOD/PLANT check self-temp → become FIRE), which **decouples ignition
   from fire's scan**. User-approved wording: "Replace probabilistic spread".
   *(Alternative considered: keep probabilistic spread AND add heat — rejected:
   two ignition models fighting each other; the whole point is one physical
   cause.)*
5. **Four new elements added in Phase 03: STEAM, ICE, LAVA, GLASS.**
   `ElementId` grows 8 → 12 members. Transitions: WATER boils→STEAM / freezes→
   ICE; ICE melts→WATER; STEAM condenses→WATER; LAVA cools→STONE and
   LAVA+WATER→STEAM+STONE reaction; SAND melts→GLASS. Each new element needs a
   rule, a palette swatch, and a renderer LUT row. User-approved wording: "Water
   cycle + lava + glass".
6. **Heat visualization = an `H` key toggle (Phase 04).** Renders a heat-map
   overlay (blue→red by temp) instead of element colors, via a pure
   `thermal_to_rgb(temp)` helper. This is the primary way to SEE the new field;
   the mapping is unit-tested headlessly. *(Alternative considered: always-on
   tinted cells — rejected: hides the element art the player is interacting
   with; a toggle keeps the default look unchanged.)*
7. **The rule contract is formally relaxed for reactive rules.** A rule may
   transform its own cell in place and return `None` (the same exception
   `fire.py` already relies on for spread/smoke, acknowledged at `fire.py:14-19`).
   This is now the documented mechanism for temp-driven transitions (wood→fire,
   water→steam, sand→glass, lava→stone). See the Risks section for the
   re-dispatch caveat.

> **Deviation flagged for Phase 03.** The `ElementId` docstring at
> `elements.py:10-14` claims members are "defined in full" and that later phases
> "never add new enum members". Phase 03 deliberately breaks that v1 note by
> adding STEAM/ICE/LAVA/GLASS. The `docs/ARCHITECTURE.md` "Adding a new element"
> section (`ARCHITECTURE.md:262-285`) already anticipates this ("an intentional
> extension of that invariant — update the comment"); Phase 03 updates the
> comment and the docs to match the new reality.

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | M  | New array across 4 seams (Grid/swap/fill_circle/migrate) + new `Element` fields rippling through a frozen dataclass + a new pure module with numerically-careful diffusion + `Simulation.step` wiring + `paint_brush` spawn-temp. Foundational; no visible behavior to eyeball, so tests carry correctness. |
| 02    | M  | Behavior-changing refactor of the most complex existing rule (fire) + converting two static no-op rules (wood/plant) into reactive rules. Tuning burn-temp vs flashpoint so combustion actually chains. |
| 03    | L  | Largest surface area: 4 new enum members, 4 new ELEMENTS entries, 4 new rule files, edits to 2 existing rules (water/sand), a cross-element reaction (lava+water), palette min-width recompute, renderer LUT verification, and a new test file. |
| 04    | M  | New overlay render path + key handler + pure gradient helper + the doc write-up of the entire feature. Smallest code, but the docs must accurately describe Phases 01-03. |

## Risks & Unknowns

1. **Diffusion numerical stability.** Naive explicit diffusion overshoots and can
   oscillate. The chosen 4-neighborhood Laplacian update is stable only when
   `rate * max(conductivity) <= 0.25`; Phase 01 enforces this by construction
   (tunable defaults satisfy it) AND clips the result to the `int16` band
   `[-200, 3000]` inside `diffuse_temps`. Phase 01 unit-tests no-overshoot and
   equilibrium-reached explicitly. See the formula in the Phase 01 file.
2. **Performance of the diffusion pre-pass.** The movement scan is unchanged;
   diffusion is one vectorized numpy op over the `(H, W)` `int16` array. Should
   hold 60 FPS at the default 200×140 grid. **Measure at the Phase 01 gate** and
   record the actual per-frame cost in the Phase 01 reflection. If it regresses,
   the cheap fix is a conductivity-weighted sparse update or lowering the default
   `DIFFUSION_RATE` — both are config knobs introduced in Phase 01.
3. **Reactive-rule contract relaxation could let a transformed cell be
   re-dispatched later in the same scan.** This is the same caveat `fire.py`
   already documents (`fire.py:14-19`): a rule that transforms its own cell in
   place and returns `None` does not mark anything in the `moved` guard, so the
   new cell may be processed again this frame if the scan reaches it. With
   temp-driven transforms this is **bounded** (a transition consumes the
   condition — e.g. water at 110° becomes steam; the steam rule then runs but
   won't re-trigger a transition unless its temp crosses the *other* threshold)
   and usually desirable (chain reactions). Documented, not a bug.
4. **The `moved` guard only covers movement destinations, not in-place
   transforms.** Confirm in Phase 02 that transforms returning `None` need no
   guard update (they don't move anything, so there is no destination to guard).
   The guard's job — "don't move a cell twice" — is unaffected by a cell that
   transformed but did not move.
5. **`ElementId` enum growth (8 → 12) shifts every `int(ElementId.*)` LUT index.**
   `build_color_lut` sizes itself from `len(ElementId)` (`renderer.py:36`) and
   iterates `ELEMENTS` (`renderer.py:38-41`), so it auto-resizes. But any
   *hardcoded* index assumption in tests must be checked (the existing tests use
   `int(ElementId.*)` symbolic names, not magic numbers, so they should be safe —
   Phase 03 verifies). The conductivity LUT (Phase 01) uses the same
   `len(ElementId)` sizing, so it grows automatically too.
6. **Brush spawn-temp for FIRE/LAVA must set neighbors hot enough to ignite
   fuel.** Phase 02 tuning: the FIRE burn-temp (~800) and LAVA spawn-temp (~1500)
   must exceed WOOD's `flashpoint` (~300) / PLANT's (~250) after diffusion
   through one cell of air, so a painted fire next to wood actually ignites it.
   This is the acceptance criterion "combustion chains" in Phase 02.
7. **mypy strict on the new thermal module and the third array.** `_temp` must
   be typed `npt.NDArray[np.int16]`; `diffuse_temps` computes in `float64` then
   casts to `int16` — annotate the intermediate explicitly so mypy doesn't infer
   `float64` as the return. The new `Element` fields need defaults so every
   existing `ELEMENTS` entry still constructs without spelling them out.
8. **Line numbers in this plan are current as of the v1 + improvements source**
   (verified at planning time by reading every file cited). They WILL shift
   between phases. Implementers must re-read each file before editing rather
   than blind-applying line numbers.

## Documentation Updates (cross-phase)

Tracked here so nothing is forgotten; each phase file also lists its own:

- **`README.md`** — Features table (Phase 03: add STEAM/ICE/LAVA/GLASS rows and
  rewrite the Fire row to "emits heat; ignites fuel above its flashpoint");
  Controls table (Phase 04: add the `H` heat-overlay row); the "seven elements"
  intro line becomes "twelve elements with a temperature field".
- **`docs/ARCHITECTURE.md`** — New `thermal.py` module + the diffusion pre-pass
  in `Simulation.step`; the three-array `Grid` model (id + life + temp); the
  reactive-rule contract relaxation (formalize the `fire.py:14-19` exception as
  the temp-transition mechanism); the 4 new elements and the conductivity/flash
  point `Element` fields; the `thermal_to_rgb` heat-overlay render path (Phase
  04). Update the "Adding a new element" section's note about the enum-members
  comment (Phase 03).

## Foundation Reference

This plan builds on the completed v1 + improvements. For architecture context,
read:
- `.agent/tasks/sandfall/00-overview.md` — the original phase plan (the life-array
  consistency contract this plan mirrors; perf risk #1 this plan mitigates).
- `.agent/tasks/sandfall-improvements/00-overview.md` — the resizable-window /
  migrate-grid / palette-floor plan (the `migrate_grid` and `paint_brush` seams
  this plan extends).
- `src/sandfall/grid.py`, `src/sandfall/rules/_common.py`,
  `src/sandfall/rules/fire.py`, `src/sandfall/renderer.py` — the exact code each
  phase edits. Re-read before editing; line numbers shift between phases.

## Verification Philosophy (applies to ALL phases)

Every phase's `Verification Commands` block MUST include these six gates, and
ALL must exit zero before the next phase may begin:

```bash
uv run python -c "import sandfall"   # import / build smoke
uv run pytest                        # tests
uv run ruff check .                  # lint
uv run ruff format --check .         # format check
uv run mypy src                      # types (strict)
SANDFALL_FRAMES=60 uv run sandfall   # full SDL init->render->step->teardown
                                     # (headless fallback: SDL_VIDEODRIVER=dummy ...)
                                     # (real display: prefix DISPLAY=:1 in CI)
```

After each phase, the implementer MUST write `NN-<phase>-reflection.md` in this
directory capturing: what was difficult/unexpected, deviations from the plan +
why, what to pursue next, anything fun discovered (including the **measured
per-frame diffusion cost** at the Phase 01 gate — see Risk #2). Each phase is
ONE atomic git commit.

## Out of Scope (Future Work — DO NOT plan now)

- **Pressure / airflow simulation** (Powder Toy / Noita have it; deferred).
- **Electricity / conductivity-as-current** (Sandboxels / Powder Toy; deferred —
  note the name clash: this plan's `conductivity` is a *heat* conductivity, not
  electrical).
- **Per-element heat capacity** (the current model uses a single global diffusion
  `rate` + per-material `conductivity` scalar; full heat-capacity thermodynamics
  deferred).
- **Save/load + stamps, brush shapes, zoom, eyedropper** (independent UX work,
  separate plan).
- **Glow / lighting from hot cells** (prettier color-modulation viz beyond the
  `H` overlay).
- **More phase-change elements** (oil/acid/metal/etc.) — the 4 here prove the
  thermal mechanism; the pattern is now repeatable via the "Adding a new
  element" doc recipe.

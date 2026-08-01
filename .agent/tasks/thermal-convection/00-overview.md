# Sandfall Thermal Convection + Heatmap Enhancements — Master Plan

## Problem Statement

The thermal simulation currently transfers heat by **conduction only** — the
conservative face-flux diffusion pre-pass (`thermal.py:136-193`, shipped under
`thermal-conservation-fix/01`). That is correct but **incomplete**: in real
fluids, **convection is the dominant heat-transfer mechanism**. Hot fluid rises,
cold fluid sinks, and the resulting circulating currents equilibrate
temperature *far* faster than conduction alone. In sandfall today, a heat source
at the bottom of a water pool slowly warms the bottom layer and diffuses upward
over hundreds of steps (water's heat capacity `CP_WATER = 4.0` makes the
diffusion coefficient `rate*cond/cp ≈ 0.0175/step` — glacial). There are **no
currents, no circulation, no buoyancy within a phase**: hot water sits under cold
water and waits for conduction.

The user wants three things, all user-confirmed and not to be re-litigated:

1. **Convection** — temperature-driven buoyancy for **liquids AND gases** (a hot
   fluid cell rises through a cooler same-phase cell directly above it; the cool
   cell sinks). This IS the conduction improvement — convection makes fluids
   equilibrate fast enough to feel right; no separate conduction-rate change is
   needed.
2. **Temperature colorbar** — a vertical scale (blue→red with degree markers)
   shown in **H (heatmap) mode** so the heat colors are interpretable.
3. **Sparse flow arrows** — in H mode, small semi-transparent arrows every
   ~10×10 cell block showing the average fluid flow direction (like wind vectors
   on a weather map), so the convection currents are *visible*.

## Solution Summary

A **two-phase** change, each independently verifiable and committable:

- **Phase 01 — Convection (temperature-driven buoyancy).** Add ONE shared helper
  `maybe_convect(grid, x, y)` to `rules/_common.py` (the home of `can_displace`,
  `is_riseable`, `swap`). It checks: is this cell hotter than the same-phase
  (LIQUID or GAS) cell directly above it, by more than `CONVECTION_THRESHOLD`
  (10 °C)? If so, swap straight up (hot rises, cool sinks) and return `(x, y-1)`.
  Straight-up only; same-phase only; EMPTY above is left to the existing
  rise/fall. Each of the **6 liquid rules** (`water`, `oil`, `acid`, `base`,
  `lava`, `ln2`) and **3 gas rules** (`steam`, `smoke`, `fire`) calls
  `maybe_convect(grid, x, y)` AFTER its reactive checks (boil/freeze/condense/
  age/burn/neutralize/dissolve/solidify/re-assert/cling) and BEFORE its existing
  movement (fall/rise/spread/drift). If it returns a destination, the rule
  returns it (the cell convected this step; it does not also fall/rise).

  **Effect:** a heat source at the bottom of a water pool → bottom water heats →
  convects up (swaps with cooler water above) → cooler water sinks to the bottom
  → heats → rises → **circulation** → the whole pool equilibrates in tens of
  steps instead of hundreds. Same for gases (hot gas rises through cooler gas;
  fire at ~800 °C below cooler smoke/steam swaps up — a *new* gas-gas
  displacement path, verified against existing gas tests).

- **Phase 02 — Heatmap enhancements (colorbar + flow arrows).**
  - **`_flow` direction array on `Simulation`:** during the movement scan, when a
    rule returns a destination `(dx, dy)`, record the movement direction code
    (`1=up, 2=down, 3=left, 4=right`, vertical-preferred on diagonals) at the
    source cell `(x, y)`. Reset each step. Exposed via a `Simulation.flow`
    property. It is a per-step transient recorded as a byproduct of the existing
    scan (rules already return their destination) — one extra write per moved
    cell.
  - **Pure `flow_arrow_samples(flow, stride=10)` helper** in `renderer.py`:
    samples `_flow` at stride-cell block centers, sums the per-cell unit vectors
    per block, and returns arrow descriptors `(cx, cy, vx, vy)` for blocks whose
    net flow exceeds a threshold (still/mixed blocks produce no arrow).
    Numpy-only → unit-tested headlessly.
  - **Pure `build_colorbar_gradient(height)` helper** in `thermal.py`: reuses
    `thermal_to_rgb` on a 1-D temp ramp to produce the exact gradient column
    (hot at top → cold at bottom), so the colorbar is a perfect mirror of the
    heat-overlay colors. Numpy-only → unit-tested headlessly.
  - **`Game._draw_heat_overlays`** (new method, called from `_draw` when
    `self._heat_overlay`): draws the cached colorbar surface (rebuilt only on
    resize) on the right edge of the sim area with degree markers
    (`HEAT_VIZ_COLD`, `AMBIENT_TEMP`, 200, `HEAT_VIZ_HOT`), and draws the sparse
    semi-transparent (white, alpha 128) flow arrows on a cached SRCALPHA overlay
    surface. Both are UI overlays in H mode; neither affects the simulation.

## Phase List

| #  | Phase                                                | Cx | Depends On | Parallelizable With |
|----|------------------------------------------------------|----|------------|---------------------|
| 01 | Convection — `maybe_convect` + 9 rule integrations   | M  | —          | —                   |
| 02 | Heatmap enhancements — colorbar + flow arrows        | M  | 01         | —                   |

## Dependency Map

```
01 (convection) ──► 02 (colorbar + flow arrows) ──► done
```

**Strictly sequential.** Phase 02's flow arrows are *meaningful only once
convection exists* — without Phase 01 there is almost no intra-phase movement to
visualize (liquids in a static pool barely move; gases rise only into EMPTY).
Phase 01 is green first, then Phase 02 makes the resulting currents visible and
the heat colors legible. Phase 02's `_flow` tracking is a self-contained addition
to `Simulation.step` + renderer/game; it does not touch any rule.

## Decision Log

All decisions below are **user-approved** and must not be re-litigated. The
phrasing "user-confirmed" is taken from the prompt that authorized this plan.

1. **Convection for BOTH liquids AND gases (not just liquids).** User-confirmed
   scope. Hot water rises through cooler water; hot gas rises through cooler gas.
   *(Alternative considered: liquids only — rejected by the user.)* The gas case
   adds a NEW displacement path (fire through smoke/steam); Risks #3 covers it.
2. **Convection IS the conduction improvement — no separate conduction change.**
   User-confirmed. Convection makes fluids equilibrate fast enough to feel right;
   the conservative face-flux diffusion (`thermal.py:136-193`) and its
   `rate*max(cond)/min(cp) <= 0.25` bound are UNCHANGED. No `DIFFUSION_RATE`,
   harmonic-mean-conductivity, or `CP_*` tuning in this plan.
3. **Straight-up only (no diagonal convection).** A convecting cell swaps with
   the cell DIRECTLY above it. Diagonal convection would smear updrafts sideways;
   straight-up produces clean vertical circulation columns (updraft at the hot
   side, downdraft at the cool side). *(Alternative considered: 8-neighbor
   convection — rejected for cleaner currents; recorded Out of Scope.)*
4. **Same-phase only (LIQUID-LIQUID and GAS-GAS).** Cross-phase buoyancy is
   ALREADY handled: `is_riseable` lets a gas rise INTO a liquid
   (`_common.py:69-77`, gas/liquid buoyancy, shipped under `gas-buoyancy/`); and
   `can_displace` lets a denser phase sink through a lighter one
   (`_common.py:42-66`). Convection is the INTRA-phase movement — hot water
   rising WITHIN water. EMPTY above is explicitly skipped (EMPTY is handled by
   the existing fall/rise; treating it as convection would double-handle air).
5. **`CONVECTION_THRESHOLD = 10.0` as a module constant in `rules/_common.py`.**
   Minimum temperature difference (°C) to trigger a convective swap. Prevents
   jitter from tiny gradients (a 1-2 °C diffusion ripple should not flip cells
   every step). Tunable. Lives at the rule level (mirrors `LAVA_SOLIDIFY_TEMP`
   at `lava.py:43` and the `LN2_COLD_TARGET` at `ln2.py:46`), NOT as a new
   `Element` field and NOT in `config.py` — it is a single rule-level tunable,
   not a per-material property.
6. **`maybe_convect` as a shared helper in `_common.py`** (mirrors `can_displace`
   / `is_riseable` / `swap`). Centralizes the "may this cell convect up" test so
   the 9 rules share one definition and the test suite has one obvious seam.
   *(Alternative: inline the test in each rule — rejected for the same reason
   `can_displace` is shared.)*
7. **Integration: AFTER reactive checks, BEFORE movement; return the destination.**
   A cell that is about to boil/freeze/condense/age-out/ignite/neutralize/
   dissolve/solidify transforms in place and returns `None` FIRST (reactive-rule
   relaxation — a transforming cell does not also move). Only a cell that
   survived all reactive checks convects. If it convects, it returns the
   convect destination and does NOT also fall/rise/spread this step (one move
   per step, consistent with the existing rules). For `fire`, the convect call
   comes AFTER the cling-to-fuel guard (`fire.py:112-113`), so a fire clinging
   to fuel stays put (sustains heating) and only convects when it has no
   flammable neighbor in reach.
8. **`_flow` is a per-step transient on `Simulation`, NOT on `Grid`.** It records
   the movement direction of the LAST step for the renderer; it is not persistent
   simulation state, it is not carried by `swap`/`migrate_grid`, and it does not
   affect wake/dormancy. Built during `step()`, zeroed at the start of each
   `step()`, exposed via a `Simulation.flow` property. *(Rationale: `Grid` is the
   persistent element/temp/life/active store; a render-only transient does not
   belong there.)*
9. **Sparse flow arrows (one per ~10×10 block), semi-transparent, IN H mode.**
   User-confirmed. NOT a separate `F`-key flow-only overlay, and NOT per-cell
   dashes/streaklines. One arrow per `stride×stride` block (default stride 10),
   pointing in the block's dominant flow direction, drawn semi-transparent
   white (alpha 128) over the heat colors — like wind vectors on a weather map.
   *(Alternatives considered: per-cell dashes (too dense/noisy at 4 px/cell);
   a separate flow-only mode (rejected by the user — arrows overlay
   temperature).)*
10. **Colorbar in H mode, vertical, reusing `thermal_to_rgb`'s exact gradient.**
    User-confirmed. A `build_colorbar_gradient(height)` helper in `thermal.py`
    calls `thermal_to_rgb` on a 1-D temp ramp so the bar's colors are a perfect
    mirror of the cell coloring (no second gradient definition to drift). Degree
    markers at `HEAT_VIZ_COLD`, `AMBIENT_TEMP`, 200, `HEAT_VIZ_HOT` (the four
    anchors that bracket the interesting range).

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | M  | One shared helper + one module constant in `_common.py`, then a near-identical 4-line `maybe_convect` call inserted into **9 rules** (6 liquids + 3 gases) at a precise precedence point (after reactive checks, before movement) + a focused new test file. The convection is a NEW gas-gas displacement path (fire-through-smoke) that must not break existing gas tests; the pool-equilibration test must show a clear, deterministic improvement over conduction-only. The precedence placement in each rule is the careful part. |
| 02    | M  | A `_flow` array + direction recording in `Simulation.step`, two pure numpy helpers (`flow_arrow_samples`, `build_colorbar_gradient`), a new `Game._draw_heat_overlays` method (cached colorbar surface + cached SRCALPHA arrow overlay + degree-marker text), plus headless tests for the helpers and an SDL smoke for the visuals. Touches ≤3 subsystems (simulation, renderer/thermal, game). The arrow-direction averaging + threshold and the colorbar placement are the tunable unknowns. |

## Risks & Unknowns

1. **Scan-order effects on convective swaps (expected stable).** Convection
   swaps are processed bottom-to-top (the scan is y-descending,
   `simulation.py:136`). A hot cell at the bottom swaps up; the cooler cell now
   at the bottom heats next step and convects → circulation. The `moved` guard
   (`simulation.py:144-145,157`) marks the swap DESTINATION `(x, y-1)` so it is
   not re-dispatched when the scan reaches row `y-1` later; the source `(x,y)`
   is in a row already passed, so the swapped-down content is not reprocessed.
   `maybe_convect` does NOT itself check the destination's `moved` status — but
   neither do the existing `swap`-based moves (`water.py:66`, `smoke.py:39`), so
   it composes identically. One cell per step → no teleporting. **Verify** in the
   SDL smoke that a heated pool circulates without cells jumping multiple rows.
2. **Jitter from tiny gradients.** `CONVECTION_THRESHOLD = 10.0` prevents a 1-2 °C
   diffusion ripple from flipping cells every step. If playtesting shows
   flickering at an equilibrated interface, RAISE the threshold (it is the single
   tunable). Pin the final value in the Phase-01 reflection.
3. **Gas-gas convection is a NEW displacement path.** Fire (~800 °C, GAS) below
   cooler smoke/steam (GAS, lower temp) now swaps up. Today fire rises only into
   EMPTY (`fire.py:114-124`); smoke/steam rise via `is_riseable` (EMPTY or
   LIQUID, never GAS — `_common.py:77`). So fire-through-smoke and
   fire-through-steam are genuinely new. **Re-verify, do not assume:** run the
   full `tests/test_smoke.py`, `tests/test_fire.py`, `tests/test_gas_buoyancy.py`
   and `tests/test_phase.py` and record the outcome. Expected: they pass (the
   existing tests use specific EMPTY/liquid geometries; convection adds an
   additional movement option that should compose cleanly because it is gated on
   a >10 °C same-phase gradient those tests do not set up).
4. **Performance is negligible.** `maybe_convect` is one bounds check + one
   `get_temp` + one `get` + two `ELEMENTS[...]` dict lookups + one phase compare
   per liquid/gas cell per step (the reactive checks already ran, so the cell is
   definitely a liquid/gas). The `_flow` write is one `uint8` store per MOVED
   cell (a fraction of cells). Both are noise relative to the per-step diffusion
   pass and the numpy scan. No measurable frame-time impact expected.
5. **Flow-arrow visibility at 4 px/cell.** Arrows are sparse (one per ~10×10
   block ≈ one per ~40×40 screen px). They may be subtle at default zoom; the
   magnifier (`Z`) helps. Semi-transparent white (alpha 128) on the heat colors
   should read against blue/red but may wash out on near-neutral (ambient-gray)
   regions — acceptable, since neutral regions have little flow. If arrows are
   invisible, raise alpha to ~180 or add a thin dark outline (pin in the
   Phase-02 reflection).
6. **Existing 1×1 / tiny-grid tests are unaffected by convection.** On a 1×1 grid
   there is no cell above (`y-1 < 0` → `maybe_convect` returns `None`
   immediately). The phase-transition tests in `tests/test_phase.py` are
   therefore unchanged; the call is a no-op there.
7. **Colorbar overlays the rightmost sim columns.** The bar is ~20 px wide at the
   right edge of the scaled grid region. It covers a thin strip of the heat view;
   acceptable for a UI overlay (the bar IS the legend for those colors). If it is
   too intrusive, narrow to 16 px or move it just outside the grid into the
   `BG_COLOR` gutter when the window is wider than the grid — record the choice
   in the Phase-02 reflection.
8. **Line numbers in this plan are current as of the post-`thermal-realism`
   source** (verified at planning time by reading every file cited). The
   implementer MUST re-read each file before editing rather than blind-applying
   line numbers.

## Verification Philosophy (applies to both phases)

Each phase's `Verification Commands` block includes these gates, and ALL must
exit zero before the phase is considered done:

```bash
uv run pytest tests/test_phase.py tests/test_thermal.py tests/test_water.py -v
uv run python -c "import sandfall"
uv run pytest                                  # FULL suite -- regression guard
uv run ruff check .; uv run ruff format --check .; uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall            # SDL smoke (fallback SDL_VIDEODRIVER=dummy)
```

The headline proofs: **Phase 01** — a hot WATER cell below a cold WATER cell
swaps UP in one step (the literal buoyancy swap), and a heated water column's top
reaches a clearly-warm temp in tens of steps (impossible via conduction alone
through `CP_WATER=4.0` water). **Phase 02** — a cell that moved up is recorded as
`FLOW_UP` in `Simulation.flow`, `flow_arrow_samples` returns the dominant
direction for a uniform-flow block, and the SDL smoke shows the colorbar + arrows
in H mode.

After each phase, the implementer MUST write `0N-<phase>-reflection.md` in this
directory. Each phase is ONE atomic git commit. Do NOT write reflections during
planning — only after execution.

## Out of Scope (Future Work — DO NOT implement now)

- **Diagonal convection.** Straight-up only for now (Decision #3). Diagonal
  convection (8-neighbor) would smear updrafts; revisit only if straight-up
  produces ugly one-cell-wide chimneys.
- **Convection for powders/solids.** Hot sand does not rise through cold sand —
  powders pile (friction) and solids are rigid. POWDER/SOLID phases are excluded
  by the `my_phase not in (Phase.LIQUID, Phase.GAS)` guard.
- **A separate flow-only overlay (F key).** Flow arrows are IN H mode (overlaid
  on temperature), not a separate mode (Decision #9).
- **Per-cell flow dashes or streaklines.** Sparse block-averaged arrows chosen
  instead (Decision #9).
- **Conduction rate tuning / harmonic-mean conductivity / `CP_*` re-tuning.**
  Convection covers the fluid-equilibration improvement (Decision #2). The
  diffusion kernel and its stability bound are UNCHANGED.
- **Ambient thermostat** (separate BACKLOG item). Not in scope here.

## Foundation Reference

This plan is the deliberate follow-on to the conservative-diffusion fix and the
gas-buoyancy work. For architecture context, read:

- `.agent/tasks/thermal-conservation-fix/01-conservative-diffusion.md` — the
  face-flux diffusion kernel (`thermal.py:136-193`) this plan builds ON (heat now
  moves correctly cell-to-cell; convection adds the bulk fluid movement on top).
- `.agent/tasks/gas-buoyancy/00-overview.md` — the `is_riseable` helper
  (`_common.py:69-77`) for CROSS-phase gas-through-liquid buoyancy. Convection is
  the INTRA-phase complement (same-phase hot-rises-through-cool).
- `.agent/tasks/thermal-realism/00-overview.md` — the cold-source / phase-
  transition model and the rule-precedence / dormant-wake discipline this plan
  follows (reactive checks first; movement last; one move per step).
- `src/sandfall/rules/_common.py` (`can_displace`, `is_riseable`, `swap`,
  `seed_*_life` — where `maybe_convect` goes), the 9 rule files, `simulation.py`
  (scan loop + wake conditions), `thermal.py` (`thermal_to_rgb`), `renderer.py`
  (`render_heat`), `game.py` (`_draw`, `_heat_overlay`), `config.py`
  (`HEAT_VIZ_COLD`/`HEAT_VIZ_HOT`), `elements.py` (`Phase` enum). **Re-read
  before editing; line numbers shift.**

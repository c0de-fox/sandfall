# Phase 01 Reflection — Convection (temperature-driven buoyancy)

## What was done

Added **temperature-driven intra-phase buoyancy (convection)** to the thermal
model. A shared `maybe_convect(grid, x, y) -> tuple[int, int] | None` helper in
`rules/_common.py` checks whether this cell is hotter than the same-phase cell
directly above it by more than `CONVECTION_THRESHOLD = 10.0` °C; if so it swaps
straight up (hot rises, cooler sinks) and returns `(x, y - 1)`. Integrated into
all **9 fluid rules** (6 liquids: water, oil, acid, base, lava, ln2; 3 gases:
steam, smoke, fire) — called AFTER reactive checks (boil/freeze/condense/age/
burn/neutralize/dissolve/solidify/re-assert/cling) and BEFORE the existing
movement (fall/rise/spread/drift). If it returns a destination the rule returns
it (one move per step). For `fire` the call is AFTER the cling-to-fuel guard so
a fire clinging to fuel stays put. Straight-up only; same-phase only; EMPTY
above is skipped; powders/solids are excluded by the `Phase.LIQUID/GAS` guard.

## The deviation from the plan spec — a liquid density guard (Option B)

The plan's `maybe_convect` (verbatim) is **same-phase, pure-temperature**. The
plan's Risk #3 flagged only the **gas-gas** displacement path as new/risky. In
execution it turned out the **liquid-liquid** variant breaks an existing test in
a way the plan did not anticipate:

- `tests/test_phase.py::test_ln2_floats_on_water` (1×4: LN2 on top of WATER).
  LN2 re-asserts -196 °C; the water below is ~20 °C. Both are `Phase.LIQUID`,
  ΔT ≈ 216 °C ≫ threshold → the plan's pure-temp `maybe_convect` swaps warm
  water UP through cold LN2, **inverting the density stratification**: LN2
  (density 0.8) sinks to the bottom under water/ice instead of floating. The
  test asserts LN2 ends ABOVE the water column → fails (`assert 3 < 2`).

This is correct convection *as the plan literally specified it*, but it is
physically wrong for this material pair: cold LN2 (0.808 g/cc) is lighter than
warm water (~0.998 g/cc) regardless of the temperature difference, so it should
float. The same conflict would in principle affect any hot-denser-liquid-below-
cold-lighter-liquid pair (e.g. hot water under cold oil); the suite only catches
LN2/water because lava reacts with water before convection runs and there is no
oil temperature-gradient test.

**Resolution (user-approved Option B):** added a 3-line **density guard for
liquids only** after the same-phase check, before the temperature check
(`_common.py:196-201`):

```python
if my_phase == Phase.LIQUID:
    if ELEMENTS[ElementId(my_id)].density > ELEMENTS[ElementId(above_id)].density:
        return None
```

- Strict `>` (not `>=`) so **same-density pairs still convect** — water↔water
  (density 1.0 == 1.0, the headline case), lava↔lava, etc.
- A **denser** liquid does not buoy up through a lighter one even when hotter
  (density stratification dominates in liquids): hot water stays put under cold
  LN2 / cold oil; lava stays down under water (though they react first anyway).
- **Gases are exempt** (the guard is gated on `my_phase == Phase.LIQUID`): gas
  densities are all negligible and close together, so temperature is the
  dominant buoyancy driver — e.g. hot FIRE (~800 °C, density 0.1) still rises
  through cooler SMOKE (0.05) / STEAM (0.04), the new gas-gas path the plan
  calls for.

Verified empirically: with the guard, **all 240 tests pass**; LN2 floats
correctly (`['EMPTY','EMPTY','LN2','ICE']`, LN2 above ICE); all 6 new
convection tests stay green (water↔water unaffected — equal density).

## The equilibration-test deviation (flagged, within plan latitude)

The plan's `test_convection_accelerates_pool_equilibration` asserted top >
80 °C after 60 steps with the bottom cell set to 1000 °C once. Two problems
with the literal form:

1. **Water at 1000 °C boils** (boil_point 100) — the water rule's reactive boil
   check fires *before* convection and converts the cell to STEAM at 120 °C
   (temp_spawn), so the "hot water cell" does not survive to convect. Measured
   top after 60 steps with the plan's exact setup: only **34 °C**.
2. Even with a continuous sub-boil heat source (bottom pinned to 99 °C each
   step, plan-permitted "pin a cell at a high temp"), the top reaches only
   **~62 °C** — not 80. Reason: once the column's local gradients drop below
   `CONVECTION_THRESHOLD`, convection stops firing and the slow diffusion
   pre-pass (rate·cond/cp ≈ 0.0175/step through cp=4 water) takes over, so the
   top asymptotes well below the 99 °C source.

**Resolution (within the plan's "don't go below ~50" latitude, flagged here):**
the test pins the bottom to **99 °C** each step (continuous sub-boil source →
pure water-water convection, no boiling) for 60 steps and asserts:
- `top_with_convection > 50` (measured **62.3 °C** — wide margin over 50), AND
- `top_conduction_only < AMBIENT_TEMP + 5` (measured **20.0 °C** — conduction
  alone leaves the top at ambient), AND
- `top_with_convection > top_conduction_only + 30` (62.3 vs 20.0 — the
  headline contrast: convection is the dominant fluid heat-transfer mechanism).

The conduction-only baseline is produced by monkeypatching
`sandfall.rules.water.maybe_convect` to a no-op (the column is all water, so
patching the one rule suffices) — the SAME isolation pattern the plan endorses
for "pin a cell at a high temp … or monkeypatch." This contrast (62 vs 20) is
stronger evidence than a bare absolute threshold.

## Final measured values (pinned)

| Quantity | Value |
|---|---|
| `CONVECTION_THRESHOLD` | **10.0** (unchanged — no retune needed) |
| Hot-water swap (1×3, bottom=99 °C, 1 step) | middle **97.6 °C** vs bottom **21.4 °C** (hot cell rose; both stay WATER) |
| Hot-gas swap (1×3 steam, bottom=500 °C, 1 step) | middle **470 °C** vs bottom **230 °C** (hot steam rose; all stay STEAM) |
| Pool equilibration (1×20, pin bottom=99 °C, 60 steps) | top **62.3 °C** with convection vs **20.0 °C** conduction-only |
| LN2-on-water float (1×4, 40 steps, with density guard) | `['EMPTY','EMPTY','LN2','ICE']` — LN2 floats above ICE ✓ |

Note on temp assertions: the Simulation runs ONE vectorized heat-diffusion
pre-pass BEFORE the movement scan, so every rule reads a freshly-diffused
temperature — the exact value a cell holds after a step is NOT the value the
test set. The convection tests therefore assert **inequalities** that prove the
swap direction (the hotter cell is now above the cooler one), not exact floats.

## Dormant-wake finding — NO `simulation.py` edit needed

Confirmed. The convective swap goes through the shared `swap` helper, so the
existing wake conditions cover it with zero changes to `simulation.py`:
- The returned destination `(x, y-1)` is marked `moved` (`simulation.py:157`),
  so the swapped-up cell is not re-dispatched when the scan reaches row `y-1`.
- `id_changed | moved` + dilation (condition 1) wakes the source/dest and their
  neighbors next frame — the sinking cooler cell is re-scanned, heats from the
  source, and convects in turn → **circulation** emerges for free.
- Thermal wake (condition 2) covers the diffusion ripple.
- The SDL smoke (60 frames, dummy driver) ran clean (exit 0, no traceback); no
  cell teleported >1 row per step (one swap per step by construction).

## Gas/fire/buoyancy/phase re-verification

Re-verified, **not pre-emptively changed** (per the plan's acceptance
criteria). With Option B applied, every one of these suites passes as-is — the
new gas-gas path (fire-through-smoke/steam) and the new liquid convection path
compose cleanly because they are gated on a >10 °C same-phase gradient those
tests do not set up, and the density guard preserves every existing liquid-
layering assertion:
- `tests/test_smoke.py` (3) — ✅
- `tests/test_fire.py` (8) — ✅
- `tests/test_gas_buoyancy.py` (11) — ✅ (including `test_steam_does_not_rise_
  through_solid_or_gas`, where equal-temp steam/smoke at 80 °C have ΔT = 0 →
  no convection; and `test_water_displaces_fire_edge`, where fire below water
  is a cross-phase pair → no convection)
- `tests/test_phase.py` (33, including `test_ln2_floats_on_water`) — ✅
- Full suite: **240 passed** (234 baseline + 6 new).

## Six-gate results (all green)

```
uv run pytest tests/test_convection.py tests/test_phase.py tests/test_smoke.py tests/test_fire.py tests/test_gas_buoyancy.py -v  → 55 passed
uv run python -c "import sandfall"                                                                            → exit 0
uv run pytest                                                                                                 → 240 passed
uv run ruff check .                                                                                           → All checks passed!
uv run ruff format --check .                                                                                  → 59 files already formatted
uv run mypy src                                                                                               → Success: no issues found in 32 source files
SANDFALL_FRAMES=60 SDL_VIDEODRIVER=dummy uv run sandfall                                                      → exit 0 (no traceback)
```

## Notes for Phase 02 (heatmap enhancements)

- The `_flow` direction recording (Phase 02) will pick up convection moves for
  free: every convective swap returns `(x, y-1)` = a pure-up move, so the flow
  arrows in H mode will visibly show the updraft columns convection creates
  (hot column arrows pointing up, the return downdraft pointing down). No extra
  plumbing beyond the planned `Simulation.flow` write on each returned dest.
- The density guard means liquid convection arrows will appear only in same-
  density regions (e.g. within a uniform water pool being heated from below);
  cross-liquid interfaces (water/oil, water/LN2) will show no convection arrows
  (density stratification holds there). This is the correct visualization.
- The equilibration-test pinning pattern (re-heat a cell each step + a
  monkeypatched no-convection baseline) is reusable for any future "X
  accelerates Y" contrast test.
- `CONVECTION_THRESHOLD = 10.0` held without retune. If playtesting shows
  flickering at an equilibrated interface, raise it (single tunable in
  `_common.py:147`). If it shows sluggish equilibration, lower it — but the
  ~62 °C asymptote in the 1×20 column is the diffusion handoff, not the
  threshold, so lowering the threshold alone won't push the top toward the
  source temp; that would need a diffusion tweak (explicitly out of scope per
  Decision #2).

## Anything difficult / unexpected

- The liquid-liquid density inversion (LN2/water) was the one genuine surprise.
  The plan's Risk analysis was thorough for gases but assumed same-phase liquid
  convection would "just work" — it does for same-density liquids (water/water,
  the intended case) but inverts stratification for liquids of very different
  densities. Option B's density guard is the minimal physically-correct fix and
  preserves every plan headline (water-water convection, gas-gas convection).
- The diffusion pre-pass running before the rule scan makes exact-temp
  assertions on post-step cells fragile — switched all convection tests to
  inequality assertions (which is actually a stronger statement: it proves the
  swap *direction*, not just that some temp landed somewhere).
- One atomic commit is appropriate for this phase (per the overview). **No git
  operations were performed** — changes are left unstaged per the task
  instructions; the commit is the human approval gate.

# Phase 01 Reflection: Revert ice to realistic + add dry ice

**Result: GREEN — all six gates exit zero.** Ice is back to a realistic
non-source; dry ice (`ElementId.DRY_ICE = 16`) is the persistent cold source at
−78 °C. No `simulation.py` edit was needed.

## Dormant-wake decision — NO edit (analysis confirmed)

`test_dry_ice_freezes_water` froze water **without** adding `DRY_ICE` to wake
condition 3 (`simulation.py:168-170`). The existing four wake conditions keep a
dry-ice freeze spreading, exactly as the plan's Decision #8 predicted. The
`thermal-float-ice` finding carries over verbatim under the new name/value.

Mechanism observed: dry ice re-asserts −78 each step (it self-wakes via its own
temp change as cold flows out → condition 2) → the whole-grid diffusion pre-pass
carries cold outward regardless of `active` → adjacent water cools (temp change
→ condition 2) → WATER rule freezes it to ICE (identity change → condition 1 +
dilate) → the cycle repeats through the growing ice shell.

**`simulation.py` is unchanged.** `DRY_ICE_COLD_TARGET = -78` ships as a module
constant in `rules/dry_ice.py`.

## Measured freeze spread (the integration-test evidence)

Seeded a 2×2 DRY_ICE block in a 12×12 water half-pool (`random.seed(0)`), ran a
real `Simulation`, counted ICE cells:

```
step  10: ice= 0  dry_ice=4
step  30: ice= 8  dry_ice=4
step  60: ice= 8  dry_ice=4
step 100: ice=10  dry_ice=4
step 150: ice=12  dry_ice=4
```

The freeze front advances by cold diffusing **through the growing ice shell**
from the persistent dry-ice source (only the 4 dry-ice cells re-assert cold; the
new ice does not). This is **slower** than the interim ice's 1→9-in-120 (where
every new ice cell re-asserted −50), as the plan's Risk #3 predicted — but it
DOES advance, and the integration test asserts only strict growth (`ice_after >
0`), not a rate. `DRY_ICE_COLD_TARGET = -78` (colder than the interim −50)
partially compensates. The cold target is a **knob**: colder → faster spread.

The slight plateau around step 30→60 (ice holds at 8) is the cold front
traversing the first ice shell layer before reaching fresh water — the
"diffusion through ice" cost the realistic model pays. Tuning note for a future
pass: if a faster spread is desired, lower `DRY_ICE_COLD_TARGET` or raise
`COND_DRY_ICE` (currently 0.20); both steepen the gradient through the shell.

## The deliberate behavior change — confirmed

- **Dry ice freezes water**: yes (`test_dry_ice_freezes_water`, 12 ICE cells
  from a 2×2 DRY_ICE seed over 150 steps).
- **Ice melts in ambient**: yes (`test_ice_melts_in_ambient` — ice at 20 °C →
  WATER on a 1×1 grid where diffusion is a no-op, so it reads exactly 20 >
  melt_point 0).
- **Ice no longer freezes water**: yes (`test_ice_does_not_freeze_water` — ICE
  at 0 °C next to WATER at 5 °C; the water cell stays WATER over 10 steps).

## Removing the `water → ice` sibling import — no issue

The `from .ice import ICE_COLD_TARGET` line in `water.py` and the `ICE_COLD_TARGET`
import in `tests/test_phase.py` were both deleted cleanly. The freeze branch in
`water.py` no longer writes the new ice's temp; the new ice keeps the water's
already-≤0 value (realistic). The one-way `water → ice` dependency that existed
only for the interim cold-seed is simply gone — no cycle, no stale reference,
ruff/mypy clean.

## SDL smoke

`SANDFALL_FRAMES=60 SDL_VIDEODRIVER=dummy uv run sandfall` → exit 0. Full
`SDL init → render → step → teardown` path runs clean with the new element.
(Headless environment: no manual paint observation. The auto-tested behavior
covers the visual claims — DRY_ICE resolves in the palette via `item_at`
(`test_palette_resolves_new_elements_and_fits_min_window`), and the
freeze/melt/sublimate behaviors are pinned in `test_phase.py`. The palette
auto-resized from `len(ElementId)` with **no** `renderer.py` / `ui.py` /
`game.py` edit, as the plan predicted.)

## An UNEXPECTED ripple — `test_acid_dissolves_ice` (deviation, documented)

The phase spec's "Changes Required" listed `test_ui.py` and `test_config.py` as
the only palette-width test updates. The full-suite run surfaced **two more
classes of ripple** that the spec did not enumerate:

1. **LUT-count tests** (`test_gunpowder.py::test_color_lut_has_16_rows`,
   `test_oil.py::test_color_lut_has_16_rows`,
   `test_renderer.py::test_build_color_lut_grew_with_new_elements`) hardcode the
   old element count (16) / LUT shape `(16, 3)`. These are the same enum-growth
   ripple the plan's overview Risk #6 anticipated for palette-width tests; they
   just live in different files. Fix: pure `16 → 17` literal bumps (+ added an
   explicit DRY_ICE index-16 color check to the renderer test, mirroring the
   OIL/GUNPOWDER checks). Renamed the two `*_16_rows` tests to `*_17_rows`.

2. **`test_acid_dissolves_ice` (behavior ripple, the interesting one).** This
   test set ICE at the default ambient temp (20 °C). Under the interim model
   ice re-asserted −50 so it stayed ice and the acid dissolved it. Under the
   **realistic** model that same ice now melts to WATER via diffusion/thermal
   branch **before** the acid acts — and worse, it became scan-order
   dependent: when ICE scanned first it melted to WATER, then the (denser)
   acid *displaced into* the water slot, leaving ACID at `(1,0)` instead of
   EMPTY (~50% fail rate). This is a **correct** consequence of the deliberate
   behavior change, not a bug. Fix (intent-preserving, not a weakening): hold
   the ICE cell at −10 °C so it stays below melt_point through one diffusion
   step and the acid's `DISSOLVE_CHANCE=1.0` dissolve path is what consumes it
   — exactly what the test names. The assertion (`both cells → EMPTY`) is
   unchanged; only the setup gained `g.set_temp(1, 0, -10)` and the docstring
   now explains the realistic-model interaction.

No test was weakened or skipped to force green. The acid fix isolates the
dissolve path the test targets; the LUT bumps track the enum growth.

## `docs/ARCHITECTURE.md` refreshed

- `ElementId` member list (`:248-258`): appended `DRY_ICE=16`, updated the
  "new members take 8..15" → "8..16".
- The `ICE.melt_point` note (`:277-285`): rewritten from "declared but NOT
  read ... persistent cold source ... melts ONLY via fire/lava contact" to
  "IS read by the realistic rule ... melts >0 ... DRY_ICE/LN2 are the cold
  sources".
- "Adding a new element" recipe (`:530-534`): the stale "ice's melt_point is
  currently unused by its rule" bullet → "ice's melt_point IS read by the
  realistic rule — ice melts to WATER above 0 °C".

## Six-gate results

| Gate | Command | Result |
|------|---------|--------|
| Phase-focused | `uv run pytest tests/test_phase.py tests/test_thermal.py -v` | ✅ 39 passed |
| Enum+registry | `uv run python -c "...DRY_ICE==16...in RULES..."` | ✅ OK |
| Full suite | `uv run pytest` | ✅ 230 passed (227 → 230, net +3) |
| Lint | `uv run ruff check .` | ✅ All checks passed |
| Format | `uv run ruff format --check .` | ✅ 57 files already formatted |
| Types | `uv run mypy src` | ✅ Success: no issues in 31 files |
| SDL smoke | `SANDFALL_FRAMES=60 SDL_VIDEODRIVER=dummy uv run sandfall` | ✅ exit 0 |

## Notes for Phase 02 (liquid nitrogen)

1. **Reuse the dormant-wake finding.** LN2 will be the second cold source and
   the same analysis applies: the whole-grid diffusion pre-pass + condition 2
   (thermal change) + condition 1 (identity change) should keep an LN2 freeze
   spreading **without** adding LN2 to condition 3. The Phase-01 gate
   (`test_dry_ice_freezes_water`) is now the precedent — write the parallel
   `test_ln2_freezes_water` and only touch `simulation.py` if it stalls.
2. **LN2 is TRANSIENT (carries `life`)**, unlike dry ice. That means a NEW
   `seed_nitrogen_life()` helper in `_common.py` (mirroring `seed_steam_life`)
   AND a new brush life-seeding branch in `brush.py` (mirroring the
   FIRE/SMOKE/STEAM branch). Dry ice needed neither (persistent, no life).
3. **The realistic-ice acid-test ripple is a warning for LN2.** Any existing
   test that places ICE (or WATER) next to a warm neighbor at ambient and
   assumes stability may now race the freeze/melt. Audit sibling tests when
   adding LN2's interactions. (The acid-dissolves-ice fix here is the
   template: hold the cold/thermal cell at an explicit temp that survives one
   diffusion step.)
4. **`MIN_WINDOW_W` will recompute again** 556 → 584 (20-item palette = 146
   cols) for the LN2 swatch, plus two more LUT rows and another `test_renderer`
   index check. The Phase-01 edit pattern is the recipe.
5. **Slower freeze through the shell is expected** — LN2's −196 will spread
   faster than dry ice's −78 (steeper gradient), but it boils off in a finite
   `life` window. The integration test should assert freezing happens *before*
   boil-off, and the `seed_nitrogen_life` range (`randint(30, 80)` per the
   plan) is the knob if it boils too fast.

## Did NOT commit

Per the hard constraint, no git operations were performed. All changes are left
unstaged for the human approval gate.

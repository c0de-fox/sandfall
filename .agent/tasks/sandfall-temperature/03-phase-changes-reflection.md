# Phase 03 Reflection — Phase changes + 4 new elements (STEAM / ICE / LAVA / GLASS)

## Summary

Added four new `ElementId` members (STEAM=8, ICE=9, LAVA=10, GLASS=11;
8 → 12) with `ELEMENTS` entries, colors, thermal thresholds, and rules;
wired the temperature-driven transitions (WATER boil→STEAM / freeze→ICE,
SAND melt→GLASS, ICE melt→WATER, STEAM condense→WATER, LAVA cool→STONE,
and the LAVA+WATER → STONE+STEAM reaction); extended the conductivity LUT
and the brush life-seeding to cover the new elements; bumped `MIN_WINDOW_W`
to 384 so the now-12-swatch palette fits at the minimum window size; and
added `tests/test_phase.py` plus focused assertions in the renderer/ui/
config suites. **No edits** to `fire.py`, `wood.py`, `plant.py`,
`thermal.py`'s diffusion math, `simulation.py`, or `grid.py` (all additive
registry/data/rule work on top of the Phase 02 baseline).

## Files changed

**New (5):**
- `src/sandfall/rules/steam.py` — gas, finite life, rises like smoke,
  condenses→WATER below `condense_point`.
- `src/sandfall/rules/ice.py` — static solid, melts→WATER above `melt_point`.
- `src/sandfall/rules/lava.py` — dense liquid (density 2.5), water-style
  movement; reacts with adjacent WATER → STONE+STEAM; else cools→STONE below
  `LAVA_SOLIDIFY_TEMP`; else flows.
- `src/sandfall/rules/glass.py` — static no-op solid (made by sand melting).
- `tests/test_phase.py` — 18 deterministic transition + brush-seeding tests.

**Modified (12):**
- `src/sandfall/elements.py` — docstring rewritten (v1 "never add members"
  note retired); 4 enum members; 4 `ELEMENTS` entries; `SAND.melt_point=1700`.
- `src/sandfall/config.py` — `COND_STEAM/ICE/LAVA/GLASS`; `MIN_WINDOW_W=384`.
- `src/sandfall/thermal.py` — `build_conductivity_lut` rows 8–11.
- `src/sandfall/rules/_common.py` — `seed_steam_life()` (range 80–160) + docstring.
- `src/sandfall/rules/water.py` — boil→STEAM / freeze→ICE branches at top.
- `src/sandfall/rules/sand.py` — melt→GLASS branch at top.
- `src/sandfall/rules/__init__.py` — register 4 rules; re-export `seed_steam_life`.
- `src/sandfall/brush.py` — STEAM life-seeding in `paint_brush`; `Callable` import.
- `tests/test_renderer.py`, `tests/test_ui.py`, `tests/test_config.py` —
  explicit (12,3)-LUT / 12-swatch / MIN_WINDOW_W assertions.
- `docs/ARCHITECTURE.md` — element-model member list + "Adding a new element" note.

Tests: **127 → 148 passed** (+21; none removed).

## Final transition-threshold values (pinned for Phase 04 docs)

| Transition | Threshold | Value | Where |
|---|---|---|---|
| WATER → STEAM (boil) | `boil_point` | 100 (Phase 01, unchanged) | `ELEMENTS` |
| WATER → ICE (freeze) | `freeze_point` | 0 (Phase 01, unchanged) | `ELEMENTS` |
| ICE → WATER (melt) | `melt_point` | 0 | `ELEMENTS` |
| STEAM → WATER (condense) | `condense_point` | 60 | `ELEMENTS` |
| SAND → GLASS (melt) | `melt_point` | 1700 | `ELEMENTS` |
| LAVA → STONE (solidify) | `LAVA_SOLIDIFY_TEMP` | 700 | rule constant, `lava.py` |
| LAVA + WATER → STONE + STEAM | (adjacency) | n/a | `lava.py` (fires before solidify) |

No Phase 01/02 values were changed. Stability invariant
`rate * max(cond) = 0.20 * 0.50 = 0.10 ≤ 0.25` still holds (max conductivity
is still FIRE's 0.50; LAVA at 0.45 is below it).

## STEAM got its OWN `seed_steam_life` (not smoke's helper)

Added `seed_steam_life()` → `random.randint(80, 160)` in `_common.py`,
re-exported from `rules/__init__.py`. Steam lingers longer than smoke
(wider window) so it drifts visibly before condensing. Both consumers go
through it: the lava+water reaction (which flashes water to steam) and the
painting path (`brush.paint_brush` now seeds STEAM life alongside FIRE/SMOKE).
ICE/GLASS need no life; LAVA needs no life. LAVA/ICE spawn-temp is handled
automatically by Phase 01's uniform `ELEMENTS[id].temp_spawn` seeding in
`paint_brush` (verified: painted LAVA is 1500, painted ICE is -5).

## Two spec bugs deliberately NOT copied (parallel to the flagged water one)

1. **Water freeze `or True`** (spec step 3a). The spec snippet literally
   read `if _WATER.freeze_point < 0 or True:` — the `or True` makes the
   branch always-true. Water's `freeze_point == 0` is a VALID active
   threshold (water freezes at/below 0°C). Wrote `if t <= _WATER.freeze_point:`
   per the prompt's explicit instruction (contract: "at or below freeze_point
   → ICE"). Confirmed NOT copied: `rg "or True" src/sandfall/rules/water.py`
   → no match.
2. **Ice melt `!= 0` guard** (spec step 5b, NOT pre-flagged by the prompt but
   the same class of bug). The spec snippet read
   `if _ICE.melt_point != 0 and grid.get_temp(...) > _ICE.melt_point:` — with
   `ICE.melt_point == 0` the `!= 0` guard is False, so ice would NEVER melt.
   Ice's `melt_point == 0` is a VALID active threshold (melts above 0°C).
   Wrote `if grid.get_temp(x, y) > _ICE.melt_point:` (no guard). Only ICE has
   a melt rule, so the threshold value is unambiguous; the wood/plant
   `flashpoint > 0` guard exists because their *default* 0 means "never",
   which is not the semantics for ice's melt_point.

Both transition checks (and sand's melt, lava's reaction/solidify) precede
movement and return `None`, so a transforming cell does not also move.

## The real surprise: lava+water reaction is preempted by the boil path

The prompt's pitfall #2 anticipated the water *falling away* from the lava.
The actual failure mode was different and more subtle: **at the realistic
LAVA spawn-temp (1500) the diffusion pre-pass heats the adjacent WATER above
its `boil_point` (100) in a single step**, so the WATER rule's boil branch
converts the water to STEAM *before* the LAVA rule's reaction branch runs
(whenever the randomized x-scan reaches water first) — yielding STEAM
without the STONE crust. Empirically (3×3 sealed box, 20 seeds): lava_temp
≥ 1200 → flaky ({STONE+STEAM, LAVA+STEAM}); lava_temp ≤ 1100 → deterministic
STONE+STEAM.

The fix is a **test-only** parameter: set the lava cell's temp to **1000**
(not the 1500 `temp_spawn`; `LAVA.temp_spawn` itself is unchanged). At 1000
the post-diffusion water temp is ~88 (below boil), so the water is still
WATER when LAVA scans and the reaction fires for BOTH scan directions. The
test loops `random.seed(i)` for i in range(20) and asserts STONE+STEAM +
in-range steam life each time — fully deterministic. This is NOT a weakened
test (it still asserts the full stone+steam reaction) and does not touch
`simulation.py`/`thermal.py`. **Flagged for Phase 04 docs / future tuning:**
in real gameplay, a freshly-painted 1500° lava next to water will sometimes
flash the water to steam without forming a stone crust (scan-order
dependent). That is arguably acceptable (both outcomes produce steam; the
stone is the variable part), but if reliable crust formation is desired,
the clean fix is to make the reaction fire on a STEAM neighbor too, or to
give the lava rule scan priority over water — both out of scope here.

No tuning was needed for sand→glass, water boil/freeze, ice melt, or steam
condense: those single-cell tests use `Grid(1, 1)`, where the diffusion
pre-pass is a true no-op (edge-padding replicates the lone cell on all four
sides → zero Laplacian), so the rule sees exactly the set temperature and
the spec's small margins (+20, −5, +5, …) all hold as written with zero
per-test arithmetic.

## Renderer / palette auto-resized with NO code edits

Confirmed the acceptance criterion: **no edit to `renderer.py` or `ui.py`
was needed.** `build_color_lut` sizes from `len(ElementId)` and iterates
`ELEMENTS`, so the 4 new colors appeared automatically at rows 8–11;
`palette_layout` iterates `ElementId`, so the 4 new swatches appeared
automatically. The only LUT edit was `thermal.build_conductivity_lut`
(rows 8–11) — but that builder assigns per-id rather than iterating a
registry, so extending it is the explicitly-spec'd additive change (not a
surprise). Pinned by `test_build_color_lut_grew_to_twelve_rows_with_new_elements`
(shape (12,3), rows 8–11 = new colors) and
`test_palette_resolves_phase03_elements_and_fits_min_window` (12 swatches,
new ones resolve via `swatch_at`, row fits in MIN_WINDOW_W).

## Enum-stability check

`[e.value for e in ElementId] == list(range(12))`; `int(SAND)==1`,
`int(PLANT)==7` — v1 indices unchanged, new members 8–11. `len(RULES)==11`
(EMPTY omitted, per the long-standing convention; meets the `>= 11` gate).

## Six gates — all green

| # | Gate | Result |
|---|------|--------|
| 1 | `uv run python -c "import sandfall"` | ✅ exit 0 |
| 2 | `uv run pytest` | ✅ 148 passed (127 → 148) |
| 3 | `uv run ruff check .` | ✅ All checks passed |
| 4 | `uv run ruff format --check .` | ✅ 47 files already formatted |
| 5 | `uv run mypy src` | ✅ no issues, 25 source files |
| 6 | `SANDFALL_FRAMES=60 uv run sandfall` | ✅ exit 0 (**real** SDL driver; no dummy fallback needed) |

Phase-focused suite (`test_phase test_renderer test_ui test_config`): 49 passed.
Enum+registry sanity (`len(ElementId)==12`, `SAND==1`, `PLANT==7`,
`len(RULES)>=11`): OK. Palette-fit sanity (`12*24+11*4+2*8 == 348 <= 384`): OK.

## Commit

**Not committed.** All changes left unstaged per instructions; the commit
decision is deferred to the user.

## Notes for Phase 04

- The heat overlay is the natural place to *see* the lava+water reaction
  and the boil/freeze/condense cycle. The 1000°-vs-1500° reaction caveat
  above is worth a sentence in the docs.
- `seed_steam_life` joins `seed_fire_life`/`seed_smoke_life` as the third
  canonical lifetime helper; the "Adding a new element" doc recipe already
  covers exposing a `seed_<name>_life` helper.
- All four new elements now have palette swatches and render correctly with
  no per-element renderer wiring — the LUT/palette-iterate pattern is the
  reason Phase 04 needs no element-specific render code either.

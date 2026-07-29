# Phase 03 Reflection — Minimal Element Set

## What was done

Implemented Phase 03 (Minimal Element Set). All 7 elements now interact:
sand sinks in water, water flows, fire ignites wood/plant and emits smoke
which rises and dissipates, plant grows near water, stone/wood stay put.

End state:

- `src/sandfall/grid.py` — EDITED: added a parallel `_life: NDArray[uint8]`
  array (same `(height, width)` shape) with `life` property (raw view),
  `get_life(x, y) -> int`, and `set_life(x, y, value)` (clips to uint8,
  silent on OOB). `set()` is unchanged (element-id only — see "life
  contract" below). `fill_circle()` now also zeroes life on painted cells
  so a brush overwriting a burning cell leaves no stale state.
- `src/sandfall/rules/_common.py` — NEW: shared `can_displace(src_id,
  target_id)` (EMPTY or strictly-lower-density LIQUID) and `swap(grid,
  x1,y1, x2,y2)` that swaps **both** element id and life. Every moving
  rule goes through this swap.
- `src/sandfall/rules/sand.py` — REFACTORED to drop its private
  `_can_displace`/`_swap` and use `_common`.
- `src/sandfall/rules/{water,stone,wood,fire,smoke,plant}.py` — NEW (6
  files). Stone/wood are explicit no-op rules (`return None`).
- `src/sandfall/rules/__init__.py` — registers all 7 elements.
- `src/sandfall/elements.py` — UNCHANGED. The Phase 02 placeholders
  already matched the phase-03 spec values exactly (water 1.0, stone 10.0,
  wood 8.0/flamm 0.25, fire 0.1, smoke 0.05, plant 8.0/flamm 0.4, colors
  per spec). No tuning needed.
- Tests: 46 total (was 21). New: `test_water.py` (4), `test_fire.py` (5),
  `test_smoke.py` (3), `test_plant.py` (3), `test_solids.py` (3),
  `test_package.py` (2 relocated), +7 life-array tests appended to
  `test_grid.py`. `test_simulation.py`'s `test_sand_sinks_through_water`
  was rewritten (see deviations).

## Verification gate results (all pass, exit 0)

| Gate | Result |
|------|--------|
| `uv run python -c "import sandfall; ... len(RULES)>=6"` | `gate1 ok 7 rules` |
| `uv run pytest` | `46 passed in 0.28s` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `25 files already formatted` |
| `uv run mypy src` | `Success: no issues found in 14 source files` |

## How the `life` array is wired (critical for Phase 04 rendering & Phase 06 packaging)

This is the cross-cutting data-structure addition. Read this if you touch
Grid or any rule.

**(a) Storage / access.** `Grid` owns a private `_life: NDArray[np.uint8]`
of shape `(height, width)`, allocated in `__init__` as zeros. Public API:
- `grid.life` → raw read-only-intent `(H, W) uint8` view (for renderers;
  Phase 04 may read it to tint fire/smoke by remaining life if desired,
  but must not mutate).
- `grid.get_life(x, y) -> int` (raises `IndexError` OOB, mirrors `get`).
- `grid.set_life(x, y, value)` (silent OOB, clips to 0..255, mirrors
  `set`'s "brushes don't raise" contract).

**(b) The common swap helper carries life on EVERY move.**
`rules/_common.py:swap()` reads both cells' element ids AND life, writes
both back swapped. Sand, water, fire, smoke all call only this helper to
move — so life is always consistent with the element id after any move.
Plant growth and fire-spread do NOT swap (they convert an EMPTY cell);
they use `grid.set()` + explicit `grid.set_life()`, which is correct
because the source cell's life is irrelevant in those paths.

**(c) Life contract — IMPORTANT for Phase 04 brushes.** `Grid.set()`
deliberately does NOT touch life (keeps it decoupled from element
semantics; the binding Phase 02 contract for `set` is preserved verbatim).
Consequences:
- When a rule creates FIRE/SMOKE, it MUST call `set_life` to seed the
  lifetime (fire spread, smoke spawn, and the rule itself on first
  existence all do this).
- When FIRE/SMOKE dies, the rule sets EMPTY and zeros life explicitly.
- **Phase 04 brush code**: when the user paints FIRE or SMOKE with a
  brush, the brush MUST also seed life (via `grid.set_life(...)`) or the
  painted fire will die on the first step (life defaults to 0). The
  existing `fill_circle` resets life to 0 — so a FIRE-painting brush in
  Phase 04 should call `fill_circle` then a parallel life-seeding pass
  (e.g. iterate the same disk and `set_life(x, y, random.randint(20,40))`
  for FIRE). Note this so it isn't a surprise.
- `fill_circle` zeroes life on every painted cell (defensive against
  stale life when overpainting a burning cell with another element).

**(d) Final rule signature is UNCHANGED.** Still
`update_*(grid: Grid, x: int, y: int) -> tuple[int, int] | None`. The
`life` array is accessed via the `grid` parameter (no signature change),
exactly as the phase file's "prefer attaching life as Grid.life to keep
Phase 02 code working" guidance recommended. `Simulation.step` was not
modified at all.

## Elements in `RULES` vs. skipped as static

All 7 non-EMPTY elements are registered (`len(RULES) == 7`):
- SAND, WATER, FIRE, SMOKE, PLANT — do real work.
- STONE, WOOD — registered as explicit no-op rules (`return None`).

**Deviation note on stone/wood:** the task setup-context said "prefer the
registry-skip approach (leave STONE/WOOD out of RULES)". But the phase
file's verification gate is `assert len(RULES) >= 6`, and the phase file's
own "Changes Required" lists `stone.py`/`wood.py` as NEW files and the
`__init__.py` section explicitly registers them. Skipping stone/wood would
yield 5 entries (SAND+WATER+FIRE+SMOKE+PLANT) and FAIL the `>= 6` gate.
Functionally a no-op rule and an absent entry are identical
(`Simulation.step` treats both as "cell doesn't move"); the explicit no-op
just makes intent visible and satisfies the gate. This reconciles the two
conflicting instructions in favor of the mandatory verification gate.

## Probabilistic tests — how they were made deterministic

The phase file sanctions seeding `random` and/or monkeypatching constants.
Both techniques are used:

- **`random.seed(0)`** at the top of every test via a `_seed()` helper
  (mirrors Phase 02's convention). This fixes the per-row x-scan direction
  and the diagonal-shuffle orders.
- **Bounded/eventual assertions**, never exact frame counts: e.g. "after
  200 steps, wood count decreased", "after 8 steps, at least one smoke
  cell is strictly above its start row", "smoke never appears below its
  start row (invariant checked every step)".
- **Monkeypatched probabilities** where the real low chance would be flaky
  even with a fixed seed:
  - `test_plant_grows_when_water_adjacent` and
    `test_plant_growth_does_not_consume_water` crank
    `plant_mod.GROW_CHANCE` to `1.0` (real value 0.02).
  - `test_fire_emits_smoke` cranks `fire_mod.SMOKE_CHANCE` to `1.0` (real
    0.05) — with seed 0 the real 5% over ~120 steps happened to never
    fire through the smoke-roll subsequence; cranking to 1.0 exercises
    the smoke-spawn path deterministically.

The fire-ignition tests (`test_fire_ignites_wood_neighbor`,
`test_fire_ignites_plant_neighbor`) use the REAL probabilities and rely on
seeded randomness + long roll counts (200/120 steps) — spread probability
is `min(1.0, flammability * 0.3)` = 0.075 (wood) / 0.12 (plant) per
neighbor per step, so ignition within the window is essentially certain.

## Tuning of constants

- `SPREAD_FACTOR = 0.3`, `SMOKE_CHANCE = 0.05` (fire) — exactly per phase
  file. Fire life `randint(20, 40)`, smoke life `randint(60, 120)` — per
  phase file.
- `GROW_CHANCE = 0.02` (plant) — per phase file.
- Smoke `_DRIFT_CHANCE = 0.25` (sideways drift when rising blocked) — not
  specified by phase file; chose 0.25 as a "sometimes" feel knob. Tunable.
- Water flow is one cell sideways per step (phase file's "v1: one cell
  sideways is fine"). Snappy enough at the grid sizes we'll use; if
  Phase 04/05 water looks sluggish, raise to a small N-cell spread.
- ELEMENTS values (colors/densities/flammability) — UNCHANGED from Phase
  02; all already matched the phase-03 spec exactly.

## Difficult / unexpected

1. **Name collision: `tests/test_smoke.py`.** The Phase 01 sanity test
   file (`test_package_imports`, `test_main_returns_zero`) occupied that
   name; the phase-03 file list also calls for `tests/test_smoke.py` for
   the element. I initially overwrote it with the element tests (caught
   via `git diff`). **Resolution:** relocated the two Phase 01 sanity
   tests to `tests/test_package.py` (clearer name anyway — "smoke test"
   is jargon), and kept `tests/test_smoke.py` for the element. Zero test
   coverage lost (still 46 passing). Future phase files: scan existing
   test filenames before declaring a "NEW" test file.
2. **The Phase 02 `test_sand_sinks_through_water` broke once water got a
   rule.** Its docstring literally said "Phase-03 liquid behavior is
   deferred" — that deferral is now over, so the test's premise (water
   inert) is stale. With water flowing sideways, sand no longer
   displaces it in a 3-wide grid (water flees before the scan reaches
   the sand). Rewrote the test to trap water in a **1-cell-wide column**
   (`Grid(width=1, height=4)`) where water cannot flee (down/diagonal/
   sideways all OOB), so the sand-displaces-water swap is the only
   available move and the test is deterministic. Same test name, same
   physical invariant, robust to water now having a rule. This is the
   only modification to an existing Phase 02 test; documented here and
   in the test's new docstring.
3. **mypy strict stayed painless.** `npt.NDArray[np.uint8]` for the new
   `_life` array, full annotations on all new rule fns and helpers, no
   `Any`. No new mypy tricks needed beyond what Phase 02 established.

## Deviations from the phase file

1. **Registered STONE/WOOD as no-op rules instead of skipping them.**
   Justified by the `len(RULES) >= 6` verification gate (see above).
2. **Did NOT introduce a shared `update_static` helper** for stone/wood
   (phase file sketched one). Two one-line `return None` functions are
   clearer than indirection through `_common.update_static`. Minor.
3. **Added a `_DRIFT_CHANCE = 0.25` knob to smoke** (sideways drift when
   rising is blocked). Phase file said "drift left/right ... with small
   chance" without a number; 0.25 is the chosen value.
4. **`fill_circle` now zeroes life** on painted cells (defensive). Phase
   file didn't specify; this prevents stale-life bugs when a brush
   overwrites a burning cell and keeps `life` consistent with the
   visible element.
5. **Relocated Phase 01 sanity tests** `tests/test_smoke.py` →
   `tests/test_package.py` to resolve the filename collision (see above).

## Performance observations (per-frame Python loop)

46 tests in 0.28s; the heaviest test steps a 5×5 grid 200 times. The
per-cell Python dispatch is still negligible at v1 grid sizes. The new
cost centers:
- Fire rule iterates the full 8-neighborhood every step (spread check) —
  ~8 `grid.get` calls per fire cell per frame.
- Smoke spawn + plant growth also iterate neighbors.
- All swaps do 4 `get` + 4 `set` + 4 `get_life` + 4 `set_life` = 16
  method calls. Method-call overhead is the dominant cost, not the numpy
  indexing (which is single-cell scalar).

For the planned Phase 04 grid (~200×150 = 30k cells, mostly EMPTY), the
`step()` early-outs EMPTY cells cheaply (`grid.get` + int compare). If
perf becomes an issue later, the seams to exploit are: (1) a dirty-cell
list (only iterate non-EMPTY cells — currently we scan every cell), (2)
vectorizing the EMPTY check, (3) inlining the swap into rules to cut
method-call overhead. None needed now; flagged for whoever profiles first.

## Suggestions for future work / agent improvements

- **Phase 04 (renderer)**: `Grid.life` is available as a parallel view —
  consider tinting FIRE/SMOKE by remaining life (e.g. fade fire from
  yellow→red as life drops) for a nice visual. The `(H, W) uint8` life
  array can be mapped to an alpha/brightness multiplier via surfarray.
  **Don't forget to seed life when painting FIRE/SMOKE with the brush**
  (see "life contract" above) or painted fire dies instantly.
- **Phase 05 (UI)**: the element palette will have 7 entries (sand,
  water, stone, wood, fire, smoke, plant). Colors come from
  `ELEMENTS[eid].color`. Brush radius via mousewheel per the overview.
- **Phase 06 (packaging)**: no new native deps this phase. `life` is
  plain numpy; nothing PyInstaller-specific to worry about.
- **Task-plan / agent prompt improvement**: when a phase declares test
  files as "NEW", it should first check they don't already exist. The
  `test_smoke.py` collision was foreseeable. Could be a checklist item
  in the implementer prompt: "before writing a NEW test file, glob the
  tests/ dir for name collisions."
- **Global AGENTS.md**: the "don't break existing tests" rule could
  clarify that *updating* a test whose documented premise becomes stale
  (e.g. "Phase 03 behavior is deferred") is legitimate when the phase
  that delivers that behavior lands — otherwise the implementer is
  stuck between "don't break" and "the test is now wrong."

## Fun discovered

- The 1-cell-wide column is a surprisingly clean test fixture for any
  "X displaces Y" invariant: it removes every escape direction except
  the one under test. Reusable for future liquid/liquid or gas/liquid
  displacement tests.
- Fire's emergent chain-reaction (ignited cell above the source gets
  re-scanned the same frame because the moved-guard only covers the one
  returned destination) actually looks *good* — fire climbs a wood
  pillar briskly without needing multi-cell-per-frame logic. A small
  accident of the single-return contract turning into a feature.
- `len(RULES) == 7` and every element has a defined behavior or explicit
  no-op — the registry is now exhaustive, which makes "what does element
  X do?" answerable by reading one dict.

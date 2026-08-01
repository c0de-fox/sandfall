# Phase 01 Reflection — Liquid/powder displaces gas

## What was done

One additive clause added to `can_displace` (`src/sandfall/rules/_common.py:64`)
so a **LIQUID or POWDER** source may move into a **GAS** target — the symmetric
complement of `is_riseable`. The final one-line `return` was restructured into a
two-clause `if … return True` block (lighter-LIQUID + gas) + `return False`.
The two docstrings in the same file were corrected (the `can_displace` docstring
no longer claims gases are not displacable; the module-docstring bullet now
mentions the gas clause and its complement-of-`is_riseable` framing). `Phase`
was already imported — no new import.

Tests (`tests/test_gas_buoyancy.py`): 3 new complement tests
(water-through-steam sideways, water-through-steam down, sand-through-steam),
1 optional fire-edge test, 1 repurposed drift test (water flanks → stone), and
a module-docstring paragraph noting the complement is tested here.

No rule file, `simulation.py`, `grid.py`, `config.py`, `elements.py`, or renderer
touched. No `is_riseable` change. The `src.phase in (LIQUID, POWDER)` guard
excludes gas-gas and solid sources by construction (locked by the existing
`test_steam_does_not_rise_through_solid_or_gas`, still green).

## Confirmation of the headline proofs

- **Water flows through a steam wall (sideways)** —
  `test_water_flows_through_steam_sideways` passes (seed 0, `_WARM = 80`):
  water enters the steam's old cell, steam shoved to the water's old cell. Held
  as written; no seed/temp tuning.
- **Water falls through steam (down)** — `test_water_falls_through_steam`
  passes. As the plan's trace predicted, the bottom→top scan visits the lower
  STEAM first, so it resolves via the **buoyancy path** (`is_riseable` — steam
  rises into the water above), producing the asserted water-below / steam-above
  state. Symmetric: both predicates agree on the swap.
- **Sand falls through steam** — `test_sand_falls_through_steam` passes. Steam
  visited first cannot rise into sand (`is_riseable(SAND)` is False — sand is
  POWDER), so it stays; the sand then sinks via `can_displace`. Proves the
  clause covers POWDER, not just LIQUID.

## Drift-test repurpose

`test_drift_does_not_go_sideways_through_liquid` (water flanks) was the **only**
existing test that collided with the fix: under the new clause its WATER flanks
shove the boxed STEAM sideways (the new correct liquid-through-gas behavior),
which would confound the drift-is-air-only assertion. Repurposed to
`test_drift_does_not_go_sideways_into_non_empty` with **STONE flanks** (drift
rejects any non-EMPTY cell identically, liquid or solid). The water-shoves-steam
coverage moved into the new complement tests. No other suite test relied on
gases being impassable — confirmed by the full-suite run (227 green).

## Buoyancy regression — preserved

All buoyancy tests stayed green **unchanged**:
`test_steam_rises_through_water`, `test_smoke_rises_through_water`,
`test_steam_rises_through_oil`, `test_steam_does_not_rise_through_solid_or_gas`,
and the multi-step `test_steam_rises_to_surface_of_water_pool` (200-step climb —
still surfaces). As the overview's trace argued, the bottom→top scan visits the
lower gas before the liquid above it each frame, so the gas rises via
`is_riseable` and the liquid-above never gets a chance to shove it — the outcome
is identical pre- and post-fix.

## Optional fire-edge test — included (not flaky)

The plan flagged `test_water_displaces_fire_edge` as fragile: FIRE.temp_spawn is
800C (≫ WATER.boil_point 100), so the heat-diffusion pre-pass could boil an
adjacent water cell before it moves. Verified **deterministic across seeds 0..7**
with `g.set_temp(1, 1, 20)` forcing the water cell cold — one diffusion step from
20C toward an 800C neighbor stays under the >100 boil threshold, so the water
survives to shove the fire. Included (not dropped) because the temp isolates
cleanly. **Documents the current behavior: water shoves FIRE aside rather than
dousing it — there is no fire+water extinguish mechanic yet.** A future
extinguish feature should change this test deliberately.

## Six (seven) verification gates — all exit zero

| # | Command | Result |
|---|---------|--------|
| 1 | `uv run pytest tests/test_gas_buoyancy.py tests/test_water.py tests/test_solids.py tests/test_simulation.py -v` | ✅ 31 passed |
| 2 | `uv run python -c "import sandfall"` (extended clause-wiring probe also OK) | ✅ exit 0 |
| 3 | `uv run pytest` (full suite) | ✅ 227 passed |
| 4 | `uv run ruff check .` | ✅ All checks passed |
| 5 | `uv run ruff format --check .` | ✅ 56 files already formatted (after one `ruff format .` pass to normalize comment spacing in the new tests) |
| 6 | `uv run mypy src` | ✅ no issues found in 30 source files |
| 7 | `SANDFALL_FRAMES=60 uv run sandfall` (+ `SDL_VIDEODRIVER=dummy` fallback) | ✅ exit 0 both ways |

## Test count

223 → **227** (+4: three complement tests + one optional fire-edge test; the
drift test was repurposed in place, not added).

## Notes / deviations

- **No git operations performed** per the user's instruction (the phase file's
  tail says to make one atomic commit — overridden by the explicit "Do NOT
  commit, stage, push, or amend. Leave changes unstaged."). Changes left
  unstaged. A pre-existing unrelated modification to
  `.agent/tasks/BACKLOG.md` (a plant-growth-review backlog note) was already in
  the working tree at HEAD `1927e68` and was **not** touched by this phase.
- The `ruff format` pass touched only comment-alignment whitespace inside the
  new test functions (e.g. `ElementId.SAND)   # …` → `ElementId.SAND)  # …`);
  no logic changed.

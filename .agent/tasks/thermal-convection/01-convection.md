# Phase 01: Convection — temperature-driven buoyancy for liquids AND gases

## Objective

Add ONE shared `maybe_convect(grid, x, y)` helper + a `CONVECTION_THRESHOLD`
constant to `rules/_common.py`, then insert a single `maybe_convect` call into
each of the **6 liquid rules** (`water`, `oil`, `acid`, `base`, `lava`, `ln2`)
and **3 gas rules** (`steam`, `smoke`, `fire`) at the precise precedence point
(AFTER all reactive checks, BEFORE the existing movement). A hot fluid cell
(>10 °C warmer than the same-phase cell directly above it) swaps straight up;
the rule returns the destination so the cell does not also fall/rise this step.
Add a focused `tests/test_convection.py` proving the swap, the pool-
equilibration speedup, the gas-gas case, and the negatives (powders/solids,
below-threshold, 1×1 no-op).

## Depends On

none — first phase.

## Can Parallelize With

none — Phase 02 depends on this (the flow arrows visualize the convection
currents Phase 01 creates).

## Recommended Agent

@implementer — one shared helper + one constant, then a near-identical 4-line
insertion into 9 rules at a precedence point that must be exact in each, plus a
new test file. The precedence placement and the new gas-gas displacement path are
the careful parts. Re-read every cited file before editing (line numbers below
are current at planning time and may have drifted). Read `00-overview.md` first.

## Changes Required

- `src/sandfall/rules/_common.py` — add `CONVECTION_THRESHOLD = 10.0` module
  constant + the `maybe_convect(grid, x, y) -> tuple[int, int] | None` helper
  (after `swap`, `_common.py:124-139`). `ELEMENTS`, `ElementId`, `Phase`, `Grid`
  are already imported (`_common.py:32-33`); no new import.
- `src/sandfall/rules/water.py` — add `maybe_convect` to the `._common` import
  (`water.py:32`); call it after the freeze block (`water.py:61-63`) and before
  the straight-down fall (`water.py:65`).
- `src/sandfall/rules/oil.py` — add `maybe_convect` to the `._common` import
  (`oil.py:27`); call it after the burn block (`oil.py:36-40`) and before the
  flow (`oil.py:42`).
- `src/sandfall/rules/acid.py` — add `maybe_convect` to the `._common` import
  (`acid.py:43-49`); call it after the dissolve block (`acid.py:120-137`) and
  before the flow (`acid.py:139`).
- `src/sandfall/rules/base.py` — add `maybe_convect` to the `._common` import
  (`base.py:44-50`); call it after the dissolve block (`base.py:112-129`) and
  before the flow (`base.py:131`).
- `src/sandfall/rules/lava.py` — add `maybe_convect` to the `._common` import
  (`lava.py:39`); call it after the solidify block (`lava.py:78-80`) and before
  the flow (`lava.py:82`).
- `src/sandfall/rules/ln2.py` — add `maybe_convect` to the `._common` import
  (`ln2.py:39`); call it after the re-assert-cold block (`ln2.py:61-62`) and
  before the flow (`ln2.py:64`).
- `src/sandfall/rules/steam.py` — add `maybe_convect` to the `._common` import
  (`steam.py:30`); call it after the age block (`steam.py:47-52`) and before the
  rise (`steam.py:54`).
- `src/sandfall/rules/smoke.py` — add `maybe_convect` to the `._common` import
  (`smoke.py:21`); call it after the age block (`smoke.py:30-35`) and before the
  rise (`smoke.py:37`).
- `src/sandfall/rules/fire.py` — add `maybe_convect` to the `._common` import
  (`fire.py:42`); call it AFTER the cling-to-fuel guard (`fire.py:112-113`) and
  before the rise (`fire.py:114`). (A clinging fire stays put; only a non-
  clinging fire convects.)
- `tests/test_convection.py` — NEW file with the focused tests below.

## Implementation Instructions

> Re-read each file before editing — line numbers below are current at planning
> time and may have drifted.

### 1. `src/sandfall/rules/_common.py` — the helper + constant

Append after `swap` (end of file, after `_common.py:139`). `swap` delegates to
`grid.move`, which carries element id + life + temp on every swap, so a
convecting cell keeps its heat and life as it rises (and the cooler cell keeps
its temp as it sinks) — identical to every other move.

```python
# Minimum temperature difference (degrees C) for a convective swap. Prevents
# jitter: a 1-2C diffusion ripple at a near-equilibrated interface must not flip
# cells every step. Tunable -- raise if playtesting shows flickering at an
# equilibrated boundary. Lives at the rule level (mirrors LAVA_SOLIDIFY_TEMP at
# lava.py:43 and LN2_COLD_TARGET at ln2.py:46); NOT a per-Element field.
CONVECTION_THRESHOLD = 10.0


def maybe_convect(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Temperature-driven buoyancy: if this cell is hotter than the same-phase
    cell directly above it (by > CONVECTION_THRESHOLD), swap straight up (hot
    rises; the cooler cell sinks). Returns ``(x, y - 1)`` if it swapped, else
    ``None``.

    Intra-phase convection ONLY: both cells must be the SAME phase and that
    phase must be LIQUID or GAS. Cross-phase buoyancy is already handled
    elsewhere -- :func:`is_riseable` lets a gas rise INTO a liquid
    (gas/liquid buoyancy), and :func:`can_displace` lets a denser phase sink
    through a lighter one. This helper is the INTRA-phase complement: hot water
    rising WITHIN water, hot gas rising WITHIN gas. EMPTY above is explicitly
    skipped (EMPTY is handled by the existing fall/rise; treating it as
    convection would double-handle air). Straight-up only (no diagonal
    convection) so updrafts form clean vertical columns.

    Called by every liquid/gas rule AFTER its reactive checks (a boiling/
    freezing/condensing/aging cell transforms in place and returns None before
    reaching here) and BEFORE its fall/rise/spread/drift. If this returns a
    destination, the rule returns it (the cell convected; it does not also
    fall/rise this step -- one move per step).
    """
    if y - 1 < 0:
        return None  # top row -- nothing above
    above_id = grid.get(x, y - 1)
    if above_id == ElementId.EMPTY:
        return None  # EMPTY above is handled by the existing rise/fall
    my_id = grid.get(x, y)
    my_phase = ELEMENTS[ElementId(my_id)].phase
    above_phase = ELEMENTS[ElementId(above_id)].phase
    # Same-phase LIQUID/LIQUID or GAS/GAS only. Powders (hot sand) and solids
    # never convect (they pile / are rigid). Different phases use is_riseable /
    # can_displace instead.
    if my_phase != above_phase or my_phase not in (Phase.LIQUID, Phase.GAS):
        return None
    if grid.get_temp(x, y) - grid.get_temp(x, y - 1) > CONVECTION_THRESHOLD:
        swap(grid, x, y, x, y - 1)
        return (x, y - 1)
    return None
```

Notes for the implementer:
- `grid.get` returns a plain `int` (`grid.py:159-168`); `ElementId(int)` and
  `int == ElementId.EMPTY` both work as written.
- `grid.get_temp` returns a `float` (`grid.py:220`); the `>` compare is exact
  float32-vs-float32. The 10 °C threshold is far above float32 noise.
- Do NOT add a `moved`-guard inside `maybe_convect`. The scan only calls the rule
  for cells not already moved (`simulation.py:144-145`), and the existing
  `swap`-based moves (`water.py:66`, `smoke.py:39`) likewise do not re-check the
  destination's `moved` status — convection composes identically (see
  `00-overview.md` Risks #1).

### 2. The 9 rule integrations (identical 4-line insertion each)

In EACH rule, after the imports add `maybe_convect` to the existing
`from ._common import (...)` block (alphabetical-ish, matching the existing
style), and insert this block at the precedence point named for each rule:

```python
    # Convection: a hot fluid cell rises through the cooler same-phase cell
    # above it (intra-phase buoyancy). Checked AFTER reactive transitions and
    # BEFORE gravity flow: a convecting cell swaps up this step instead of
    # falling/spreading (one move per step).
    convect = maybe_convect(grid, x, y)
    if convect is not None:
        return convect
```

The exact insertion points (re-read each file; the comment line above the first
move step is the anchor):

| Rule       | File:anchor (insert AFTER this, BEFORE the movement comment) |
|------------|--------------------------------------------------------------|
| water      | `water.py:63` (end of the `# Freeze -> ICE` block) → before `water.py:65` (`# Straight down.`) |
| oil        | `oil.py:40` (end of the `# 1. Burn` block) → before `oil.py:42` (`# 2. Flow like a light liquid`) |
| acid       | `acid.py:137` (end of the `# 3. Dissolve` block) → before `acid.py:139` (`# 4. Flow like a dense liquid`) |
| base       | `base.py:129` (end of the `# 3. Dissolve` block) → before `base.py:131` (`# 4. Flow like a dense liquid`) |
| lava       | `lava.py:80` (end of the `# 2. Cool -> STONE` block) → before `lava.py:82` (`# 3. Otherwise move like a dense liquid`) |
| ln2        | `ln2.py:62` (end of the `# 2. Re-assert cold` block) → before `ln2.py:64` (`# 3. Flow like a light liquid`) |
| steam      | `steam.py:52` (`grid.set_life(x, y, life)` of the age block) → before `steam.py:54` (`# 3. Rise`) |
| smoke      | `smoke.py:35` (`grid.set_life(x, y, life)` of the age block) → before `smoke.py:37` (`# 2. Rise`) |
| fire       | `fire.py:113` (`return None` of the cling guard) → before `fire.py:114` (`# Rise: straight up into EMPTY first`) |

**Why this precedence is correct:** every reactive branch that transforms the
own cell (boil → STEAM, freeze → ICE, condense → WATER, age-out → EMPTY, burn →
FIRE, neutralize → STEAM, dissolve → EMPTY, solidify → STONE) returns `None`
BEFORE the convect call, so a transforming cell convects nothing. Only a cell
that survived all reactive checks convects. For `fire` specifically, the convect
call sits AFTER `if _has_flammable_neighbor(...): return None` (`fire.py:112-
113`), so a fire clinging to fuel stays put (sustains heating of the fuel) and
only a free fire convects — matching the existing cling-vs-rise split.

### 3. `tests/test_convection.py` — NEW focused test file

Mirror the style of `tests/test_water.py` / `tests/test_gas_buoyancy.py`
(`random.seed(0)`, build a `Grid`, set cells + temps, `Simulation(grid)`,
`step()`, assert positions/temps). Import `CONVECTION_THRESHOLD` from
`sandfall.rules._common` for the threshold tests.

```python
"""Tests for temperature-driven convection (intra-phase buoyancy).

Hot fluid rises through cooler same-phase fluid; cold sinks. Covers liquids
(water pool), gases (steam column), the pool-equilibration speedup over
conduction-only, and the negatives (powders/solids, below-threshold, 1x1)."""

from __future__ import annotations

import random

import numpy as np

from sandfall.elements import AMBIENT_TEMP, ElementId
from sandfall.grid import Grid
from sandfall.rules._common import CONVECTION_THRESHOLD
from sandfall.simulation import Simulation


def _seed() -> None:
    random.seed(0)


def test_hot_water_rises_through_cold_water() -> None:
    """A hot WATER cell directly below a cold WATER cell swaps UP in one step."""
    _seed()
    grid = Grid(width=1, height=3)
    grid.set(0, 0, ElementId.WATER)   # top
    grid.set(0, 1, ElementId.WATER)   # middle (cold)
    grid.set(0, 2, ElementId.WATER)   # bottom (hot)
    grid.set_temp(0, 0, AMBIENT_TEMP)   # 20
    grid.set_temp(0, 1, AMBIENT_TEMP)   # 20
    grid.set_temp(0, 2, 200)            # hot
    sim = Simulation(grid)

    sim.step()

    # The hot cell (was at y=2) convected up to y=1; the cold middle cell sank
    # to y=2. Temps travel with the cells (swap carries temp).
    assert grid.get_temp(0, 1) == 200
    assert grid.get_temp(0, 2) == AMBIENT_TEMP


def test_hot_gas_rises_through_cold_gas() -> None:
    """A hot STEAM cell below cooler STEAM swaps UP (gas-gas convection)."""
    _seed()
    grid = Grid(width=1, height=3)
    for y in range(3):
        grid.set(0, y, ElementId.STEAM)
        grid.set_life(0, y, 200)   # long life so age does not expire it
    grid.set_temp(0, 0, 200)   # top -- warm enough to not condense (< condense 60)
    grid.set_temp(0, 1, 200)
    grid.set_temp(0, 2, 500)   # bottom -- hotter
    sim = Simulation(grid)

    sim.step()

    # Hot steam convected up: y=1 now holds the 500C cell, y=2 the 200C cell.
    # (All temps > condense_point 60 so no cell condensed to WATER.)
    assert grid.get(0, 1) == ElementId.STEAM
    assert grid.get(0, 2) == ElementId.STEAM
    assert grid.get_temp(0, 1) == 500
    assert grid.get_temp(0, 2) == 200


def test_convection_accelerates_pool_equilibration() -> None:
    """A heat source at the bottom of a water column warms the TOP far faster
    than conduction alone could (water cp=4.0 makes diffusion glacial).

    With convection the hot cell physically bubbles up one row per step, so the
    top warms within tens of steps; via pure conduction (coeff ~0.0175/step over
    20 cells) the top would still be ~ambient. We assert the convection outcome
    directly -- the top reaches a clearly-hot temp fast.
    """
    _seed()
    h = 20
    grid = Grid(width=1, height=h)
    for y in range(h):
        grid.set(0, y, ElementId.WATER)
        grid.set_temp(0, y, AMBIENT_TEMP)
    grid.set_temp(0, h - 1, 1000)   # heat the bottom cell
    sim = Simulation(grid)

    for _ in range(60):
        sim.step()

    top_temp = grid.get_temp(0, 0)
    # The hot cell convected up through the column (one row/step ~ 20 steps to
    # reach the top), then diffusion spread the heat. The top MUST be clearly
    # warm -- pure conduction through cp=4 water over 20 cells in 60 steps
    # leaves the top essentially at ambient (< 25C). Assert a wide margin.
    assert top_temp > 80, top_temp


def test_no_convection_for_powders() -> None:
    """Hot SAND below cold SAND does NOT convect (powders pile, not convect)."""
    _seed()
    grid = Grid(width=1, height=3)
    grid.set(0, 0, ElementId.SAND)   # top (cold)
    grid.set(0, 1, ElementId.SAND)   # middle (cold)
    grid.set(0, 2, ElementId.SAND)   # bottom (hot)
    grid.set_temp(0, 0, AMBIENT_TEMP)
    grid.set_temp(0, 1, AMBIENT_TEMP)
    grid.set_temp(0, 2, 500)
    sim = Simulation(grid)

    sim.step()

    # Powder: the hot cell stays put (no same-phase buoyancy). It may have fallen
    # logic is N/A (already at the floor); temps are unchanged in one step at the
    # cell positions because no swap occurred. The bottom cell is still hot.
    assert grid.get_temp(0, 2) == 500


def test_no_convection_below_threshold() -> None:
    """A temp difference < CONVECTION_THRESHOLD does not convect."""
    _seed()
    grid = Grid(width=1, height=2)
    grid.set(0, 0, ElementId.WATER)
    grid.set(0, 1, ElementId.WATER)
    grid.set_temp(0, 0, AMBIENT_TEMP)
    grid.set_temp(0, 1, AMBIENT_TEMP + CONVECTION_THRESHOLD - 1)  # just under
    sim = Simulation(grid)

    sim.step()

    # No swap: the bottom cell is still the (slightly) warmer one.
    assert grid.get_temp(0, 1) > grid.get_temp(0, 0)
    assert grid.get_temp(0, 1) == AMBIENT_TEMP + CONVECTION_THRESHOLD - 1


def test_convection_is_noop_on_single_cell() -> None:
    """A 1x1 grid has no cell above -> maybe_convect returns None (no crash)."""
    _seed()
    grid = Grid(width=1, height=1)
    grid.set(0, 0, ElementId.WATER)
    grid.set_temp(0, 0, 500)
    sim = Simulation(grid)

    sim.step()   # must not raise

    assert grid.get(0, 0) == ElementId.WATER
```

Notes for the implementer:
- The equilibration test (`test_convection_accelerates_pool_equilibration`) is
  the headline. If after 60 steps the top temp is NOT clearly warm, convection
  is not firing — debug before widening any threshold. The asserted `> 80` is a
  deliberately conservative floor (the hot cell reaches the top in ~20 steps
  and then has ~40 steps to diffuse); pin the actual measured value in the
  reflection. Do NOT loosen it below ~50 without flagging (that would mean
  convection is barely working).
- `test_hot_gas_rises_through_cold_gas` sets all temps above `condense_point`
  (60) so steam does not condense mid-test, and a long `life` so it does not
  expire (mirrors the `gas-buoyancy` test-isolation discipline).
- `test_no_convection_for_powders`: sand at the floor row does not move at all
  (no fall, no convection), so the bottom cell keeps its 500 °C. If sand were to
  somehow move, that would be a bug.

## Acceptance Criteria

- [ ] `rules/_common.py` defines `CONVECTION_THRESHOLD = 10.0` and
      `maybe_convect(grid, x, y) -> tuple[int, int] | None` that swaps straight
      up ONLY for same-phase LIQUID/LIQUID or GAS/GAS pairs where the lower cell
      is > `CONVECTION_THRESHOLD` warmer than the cell directly above, skips
      EMPTY-above and the top row, and leaves powders/solids/cross-phase pairs
      untouched.
- [ ] All **6 liquid rules** (`water`, `oil`, `acid`, `base`, `lava`, `ln2`) and
      all **3 gas rules** (`steam`, `smoke`, `fire`) call `maybe_convect(grid,
      x, y)` AFTER their reactive checks and BEFORE their movement, returning
      the convect destination when it fires (one move per step). For `fire` the
      call is AFTER the cling guard.
- [ ] `tests/test_convection.py::test_hot_water_rises_through_cold_water` passes
      — the hot WATER cell swaps UP into the cold cell above it in one step
      (temps travel with the swap). **(Headline liquid proof.)**
- [ ] `tests/test_convection.py::test_convection_accelerates_pool_equilibration`
      passes — a heated 1×20 water column's TOP is clearly warm (`> 80 °C`)
      after 60 steps (impossible via conduction alone through `CP_WATER=4.0`
      water). **(Headline equilibration proof.)**
- [ ] `tests/test_convection.py::test_hot_gas_rises_through_cold_gas` passes —
      hot STEAM convects up through cooler STEAM (the new gas-gas path).
- [ ] `tests/test_convection.py::test_no_convection_for_powders`,
      `test_no_convection_below_threshold`, and `test_convection_is_noop_on_
      single_cell` all pass.
- [ ] **Re-verified, not pre-emptively changed:** `tests/test_smoke.py`,
      `tests/test_fire.py`, `tests/test_gas_buoyancy.py`, and the full
      `tests/test_phase.py` / `tests/test_water.py` suites still pass (record
      the actual outcome in the reflection; re-tune ONLY if a test fails, and
      document the re-tune — the new gas-gas path is the risk, Risks #3).
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the new convection tests are the headline):
uv run pytest tests/test_convection.py -v

# Import smoke:
uv run python -c "import sandfall"

# Phase + thermal + water regression (the new gas-gas path must not break these):
uv run pytest tests/test_phase.py tests/test_thermal.py tests/test_water.py tests/test_smoke.py tests/test_fire.py tests/test_gas_buoyancy.py -v

# Full suite -- re-verifies the gas/fire/phase ripple tests:
uv run pytest

# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
# Heat a water pool from below (paint LAVA under a WATER pool), toggle H, watch
# convection currents equilibrate the pool; confirm no cells teleport (>1 row/step).
SANDFALL_FRAMES=60 uv run sandfall
```

All commands must exit zero. If a gas/fire/phase test fails because of the new
gas-gas convection path, re-tune the MINIMUM needed to make it pass (do not
widen thresholds gratuitously) and document the re-tune in the reflection.

## Documentation Updates

- `docs/ARCHITECTURE.md` — if it describes the heat-transfer model as
  "conduction only" or lists the movement rules, add a one-paragraph note that
  fluids (LIQUID + GAS) now convect (hot rises through cooler same-phase fluid,
  `CONVECTION_THRESHOLD`-gated) and that convection is the dominant fluid heat-
  transfer mechanism alongside the conservative diffusion pre-pass. If it does
  not describe heat transfer at that level, leave it. Note whichever you find in
  the reflection.
- The `_common.py` docstring + the `maybe_convect` docstring are the source of
  truth (updated as part of the code change above).

## Reflection & Commit

After implementation, write `01-convection-reflection.md` in this directory.
**Specifically include:**
- The re-verification outcome of the gas/fire/buoyancy/phase suites — did they
  pass as-is, or did the new gas-gas convection path break any (which, and what
  re-tune fixed it)?
- The measured top-temp in `test_convection_accelerates_pool_equilibration`
  after 60 steps (the headline number), and the final `CONVECTION_THRESHOLD`
  value if it was retuned.
- Whether the SDL smoke showed clean circulation (updraft/downdraft) without any
  cell teleporting >1 row per step (Risks #1).
- Anything difficult/unexpected, deviations from this plan + why, and anything
  fun discovered.

Then make ONE atomic git commit covering all changes in this phase.

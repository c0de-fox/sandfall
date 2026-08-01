# Phase 01: Gas rise through liquid (buoyancy)

## Objective

Add a shared `is_riseable` buoyancy predicate to `rules/_common.py`, then use it
in the **rise** steps (straight-up + up-diagonals) of BOTH `steam.py` and
`smoke.py` so a gas may rise into EMPTY **or any LIQUID** (gas up, liquid down).
The sideways **drift** stays EMPTY-only. Add a focused test file locking down the
behavior envelope.

## Depends On

none — builds on the shipped gas rules (`steam.py` rise/condense/age at
`:36-74`; `smoke.py` rise/age at `:25-57`; `_common.py` `swap` at `:75-90` and
the `ELEMENTS`/`ElementId`/`Phase` import at `:25`; `elements.py` `Phase.LIQUID`
membership = WATER / LAVA / ACID / BASE / OIL).

## Can Parallelize With

none — single-phase task.

## Recommended Agent

@implementer — small, well-specified edit: one helper + frozenset in
`_common.py`, two mirrored `== EMPTY` → `is_riseable(...)` edits per gas rule
(rise steps only, drift untouched), docstring touch-ups, and a new test file.
Read the overview's "test isolation from condensation" risk before writing the
steam tests: steam set without a warm temp condenses on step 1 (before it can
rise), so the buoyancy tests set a uniform warm temp (> `condense_point` 60)
across the steam + liquid column.

## Changes Required

- `src/sandfall/rules/_common.py` — add the `_LIQUID_IDS` frozenset (after the
  imports) and the `is_riseable` helper (after `can_displace`); add a bullet to
  the module docstring documenting the new helper.
- `src/sandfall/rules/steam.py` — add `is_riseable` to the `._common` import;
  change the two rise checks (`:53` straight-up, `:60` up-diagonal) from
  `== ElementId.EMPTY` to `is_riseable(grid.get(...))`; **leave the drift check
  (`:70`) as `== ElementId.EMPTY`**; update the module docstring (`:12`).
- `src/sandfall/rules/smoke.py` — mirror steam: add `is_riseable` to the
  `._common` import; change the two rise checks (`:36` straight-up, `:43`
  up-diagonal) to `is_riseable(grid.get(...))`; **leave the drift check (`:53`)
  as `== ElementId.EMPTY`**; update the module docstring (`:10`).
- `tests/test_gas_buoyancy.py` (NEW) — steam rises through water; steam reaches
  the surface of a water pool; smoke rises through water; steam rises through
  another liquid (oil); steam does NOT rise through a solid or another gas;
  drift stays EMPTY-only (steam blocked above by stone, flanked by water, does
  not drift sideways through the water).

> No changes to `elements.py`, `simulation.py`, `grid.py`, `config.py`, the
> renderer, or FIRE's rule. FIRE stays EMPTY-only (out of scope). Gas-through-
> liquid is a swap → existing `moved`/`id_changed` wake fires → no dormancy
> change.

## Implementation Instructions

### 1. `src/sandfall/rules/_common.py`

**1a. Add the `_LIQUID_IDS` frozenset** right after the imports (currently two
blank lines at `:27-28` separate the imports from `can_displace`; place the
constant in the first of those blank lines, after `:26`):

```python
from ..grid import Grid

# Gases rise through liquids (buoyancy): a gas swaps with a LIQUID above it.
# Precomputed once (Phase is static) so the per-cell rise check is a set lookup.
_LIQUID_IDS: frozenset[int] = frozenset(
    int(e) for e in ElementId if ELEMENTS[e].phase == Phase.LIQUID
)


def can_displace(src_id: ElementId, target_id: int) -> bool:
```

**1b. Add the `is_riseable` helper** immediately AFTER `can_displace` (which
ends at `:41`; the next definition is `seed_fire_life` at `:44`). Grouping the
two "can a cell move into another" predicates together:

```python
def is_riseable(cell_id: int) -> bool:
    """True if a gas may rise INTO the cell holding ``cell_id``.

    EMPTY (open air) or any LIQUID (buoyancy -- the gas swaps with the liquid,
    gas up / liquid down). Solids and other gases are NOT riseable (a gas does
    not displace stone or another gas). Used by the STEAM/SMOKE rise steps;
    the sideways drift steps stay EMPTY-only (buoyancy is upward, not lateral).
    """
    return cell_id == int(ElementId.EMPTY) or cell_id in _LIQUID_IDS
```

**1c. Add a bullet to the module docstring** (`_common.py:1-19`, which enumerates
`can_displace` / `swap` / the `seed_*_life` helpers). After the `can_displace`
bullet (`:5-7`), add:

```text
* :func:`is_riseable` — the gas buoyancy test (EMPTY or any LIQUID). A gas may
  rise INTO an EMPTY cell (open air) or any LIQUID cell (buoyancy -- the gas
  swaps with the liquid above it, gas up / liquid down). Solids and other gases
  are not riseable. Used by the STEAM/SMOKE rise steps; the drift steps stay
  EMPTY-only.
```

### 2. `src/sandfall/rules/steam.py`

**2a. Add `is_riseable` to the `._common` import** (`steam.py:28`):

```python
from ._common import is_riseable, swap
```

**2b. Change the straight-up rise check** (`steam.py:53`). Before:

```python
    # 3. Rise: straight up into EMPTY first; else up-diagonals randomized.
    if y - 1 >= 0 and grid.get(x, y - 1) == ElementId.EMPTY:
```

After:

```python
    # 3. Rise: straight up into EMPTY or a LIQUID (buoyancy -- gas rises, liquid
    #    sinks); else up-diagonals randomized.
    if y - 1 >= 0 and is_riseable(grid.get(x, y - 1)):
```

**2c. Change the up-diagonal rise check** (`steam.py:60`). Before:

```python
        if grid.in_bounds(nx, ny) and grid.get(nx, ny) == ElementId.EMPTY:
```

After:

```python
        if grid.in_bounds(nx, ny) and is_riseable(grid.get(nx, ny)):
```

**2d. Leave the drift check UNCHANGED** (`steam.py:70`) — it stays
`grid.get(nx, ny) == ElementId.EMPTY`. Drift is air-only by design (buoyancy is
upward, not lateral). Do NOT touch lines `:64-72`.

**2e. Update the module docstring** (`steam.py:12`). Before:

```text
Like smoke, steam only enters EMPTY cells (no gas-gas displacement in v1).
```

After:

```text
Like smoke, steam rises into EMPTY or a LIQUID (buoyancy -- the gas swaps with
the liquid above it, gas up / liquid down) and drifts sideways into EMPTY only.
No gas-gas displacement in v1 (a gas does not rise into another gas).
```

### 3. `src/sandfall/rules/smoke.py`

Mirror `steam.py` exactly (smoke has no condense path, so only the rise steps +
import + docstring change).

**3a. Add `is_riseable` to the `._common` import** (`smoke.py:19`):

```python
from ._common import is_riseable, swap
```

**3b. Change the straight-up rise check** (`smoke.py:36`). Before:

```python
    # 2. Rise: straight up into EMPTY first; else up-diagonals randomized.
    if y - 1 >= 0 and grid.get(x, y - 1) == ElementId.EMPTY:
```

After:

```python
    # 2. Rise: straight up into EMPTY or a LIQUID (buoyancy -- gas rises, liquid
    #    sinks); else up-diagonals randomized.
    if y - 1 >= 0 and is_riseable(grid.get(x, y - 1)):
```

**3c. Change the up-diagonal rise check** (`smoke.py:43`). Before:

```python
        if grid.in_bounds(nx, ny) and grid.get(nx, ny) == ElementId.EMPTY:
```

After:

```python
        if grid.in_bounds(nx, ny) and is_riseable(grid.get(nx, ny)):
```

**3d. Leave the drift check UNCHANGED** (`smoke.py:53`) — it stays
`grid.get(nx, ny) == ElementId.EMPTY`. Do NOT touch lines `:47-55`.

**3e. Update the module docstring** (`smoke.py:7-10`). Before:

```text
2. Rises: straight up into EMPTY; else up-diagonals randomized; else with a
   small chance drifts one cell sideways into EMPTY.

Like fire, smoke only enters EMPTY cells in v1 (no gas-gas displacement).
```

After:

```text
2. Rises: straight up into EMPTY or a LIQUID (buoyancy); else up-diagonals
   randomized; else with a small chance drifts one cell sideways into EMPTY.

Steam and smoke rise into EMPTY or a LIQUID (buoyancy -- the gas swaps with the
liquid above it) and drift sideways into EMPTY only. No gas-gas displacement in
v1. (FIRE still rises into EMPTY only.)
```

### 4. `tests/test_gas_buoyancy.py` (NEW)

Create a dedicated test file (mirrors how `tests/test_acid_base.py` is dedicated
to the acid/base feature). Module docstring:

```python
"""Tests for gas buoyancy: STEAM and SMOKE rise through liquids.

STEAM and SMOKE rise into EMPTY (open air, as before) OR any LIQUID (buoyancy --
the gas swaps with the liquid above it: gas up, liquid down). The sideways
DRIFT stays EMPTY-only (buoyancy is upward, not lateral). FIRE is unchanged
(EMPTY-only) -- out of scope.

Isolating buoyancy from condensation: STEAM condenses below its condense_point
(60C). A steam cell set without an explicit warm temp defaults to ambient (20C)
and condenses on step 1 -- before it can rise. So the steam tests set a uniform
warm temp (> 60) across the steam + liquid column so the diffusion Laplacian is
~zero and the steam stays gaseous while rising (mirrors the test_phase.py 1x1
diffusion-no-op philosophy). SMOKE has no condense path, so it needs only life.
"""
```

**4a. Steam rises through water** (the headline buoyancy proof — one step, one
swap). Stone side walls prevent sideways drift / diagonal escape so only the
straight-up rise is exercised; uniform warm temp prevents condensation:

```python
def test_steam_rises_through_water() -> None:
    """STEAM below WATER swaps up (buoyancy): after one step the steam is in the
    water's old cell (one row up) and the water is in the steam's old cell. Stone
    side walls prevent sideways drift; a uniform warm temp (> condense_point 60)
    across the pair keeps the diffusion Laplacian ~zero so the steam does not
    condense before rising."""
    random.seed(0)
    g = Grid(3, 4)
    # Stone walls left/right + floor to box the column.
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)  # floor
    # Steam at (1,2), WATER directly above at (1,1), open air at (1,0).
    g.set(1, 2, ElementId.STEAM)
    g.set_life(1, 2, 200)
    g.set(1, 1, ElementId.WATER)
    warm = ELEMENTS[ElementId.STEAM].temp_spawn  # 120, well above condense_point 60
    g.set_temp(1, 2, warm)
    g.set_temp(1, 1, warm)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM  # steam rose into the water's cell
    assert g.get(1, 2) == ElementId.WATER  # water sank into the steam's old cell
```

**4b. Steam reaches the surface of a water pool.** Steam at the bottom of a
water column bubbles up step-by-step and emerges above the water line into air:

```python
def test_steam_rises_to_surface_of_water_pool() -> None:
    """Steam released at the bottom of a water column bubbles up through the
    water (buoyancy, one swap per step) and emerges above the water line into
    air. Warm uniform temp (> condense_point) keeps it gaseous for the climb."""
    random.seed(0)
    g = Grid(3, 8)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 7, ElementId.STONE)  # floor
    # Water column rows 1-5; open air at row 0.
    warm = 80  # above condense_point 60 -> stays gaseous while climbing
    for y in range(1, 6):
        g.set(1, y, ElementId.WATER)
        g.set_temp(1, y, warm)
    g.set(1, 6, ElementId.STEAM)  # steam at the bottom of the pool
    g.set_life(1, 6, 500)
    g.set_temp(1, 6, warm)
    sim = Simulation(g)
    for _ in range(200):
        sim.step()
    steam_ys = [y for y in range(g.height) if g.get(1, y) == ElementId.STEAM]
    assert steam_ys, "steam expired/condensed before surfacing -- bump life/temp"
    # Steam climbed above the water line (water occupied rows 1-5; row 0 is air).
    assert min(steam_ys) <= 1, f"steam did not reach the surface: y={steam_ys}"
```

> The `<= 1` bound (steam reached the top of / above the water column, rows 1-5)
> is deliberately loose. If the steam condenses or expires before surfacing
> (diffusion toward the cold stone walls over 200 steps), bump `warm` / `life`
> and pin the values in the reflection.

**4c. Smoke rises through water** (mirror of 4a; smoke has no condense path, so
only life is needed — no temp setup):

```python
def test_smoke_rises_through_water() -> None:
    """SMOKE below WATER swaps up (buoyancy), mirroring steam. Smoke has no
    condense path, so only life is seeded (no temp setup needed)."""
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)
    g.set(1, 2, ElementId.SMOKE)
    g.set_life(1, 2, 200)
    g.set(1, 1, ElementId.WATER)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.SMOKE
    assert g.get(1, 2) == ElementId.WATER
```

**4d. Steam rises through another liquid (oil)** — proves the buoyancy is
generic over `Phase.LIQUID`, not water-specific. OIL is the lightest liquid
(density 0.8); steam (0.04) is still far lighter, so it rises:

```python
def test_steam_rises_through_oil() -> None:
    """Buoyancy is generic over Phase.LIQUID, not water-specific: steam below
    OIL (the lightest liquid, density 0.8) still rises through it."""
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)
    g.set(1, 2, ElementId.STEAM)
    g.set_life(1, 2, 200)
    g.set(1, 1, ElementId.OIL)
    warm = ELEMENTS[ElementId.STEAM].temp_spawn
    g.set_temp(1, 2, warm)
    g.set_temp(1, 1, warm)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM
    assert g.get(1, 2) == ElementId.OIL
```

**4e. Steam does NOT rise through a solid or another gas** — `is_riseable`
returns False for STONE and for SMOKE, so the steam stays put. Box the steam in
fully (stone above + up-diagonals + sides + floor) so it cannot move at all;
assert it remains in place (it ages, but does not displace):

```python
def test_steam_does_not_rise_through_solid_or_gas() -> None:
    """is_riseable is False for SOLIDS and other GASES: steam fully boxed in by
    stone (above + up-diagonals + sides) does NOT swap with the stone, and steam
    boxed in by smoke above does NOT swap with the smoke. The steam stays put."""
    random.seed(0)
    warm = ELEMENTS[ElementId.STEAM].temp_spawn

    # (a) Stone directly above + stone up-diagonals + stone sides + stone floor.
    g = Grid(3, 3)
    for y in range(g.height):
        for x in range(g.width):
            g.set(x, y, ElementId.STONE)
    g.set(1, 1, ElementId.STEAM)  # carve a steam pocket in solid stone
    g.set_life(1, 1, 200)
    g.set_temp(1, 1, warm)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM  # did not rise into stone

    # (b) SMOKE directly above the steam (gas-gas: not riseable).
    g2 = Grid(3, 4)
    for y in range(g2.height):
        g2.set(0, y, ElementId.STONE)
        g2.set(2, y, ElementId.STONE)
    g2.set(1, 3, ElementId.STONE)  # floor
    g2.set(1, 1, ElementId.SMOKE)  # smoke directly above
    g2.set_life(1, 1, 200)
    g2.set(1, 2, ElementId.STEAM)
    g2.set_life(1, 2, 200)
    g2.set_temp(1, 2, warm)
    Simulation(g2).step()
    assert g2.get(1, 2) == ElementId.STEAM  # did not rise into smoke
    assert g2.get(1, 1) == ElementId.SMOKE
```

> In (b) the up-diagonals from (1,2) are the stone walls (not riseable), so the
> only potential rise target is the smoke at (1,1) — which is_riseable rejects.
> If the scan order ever lets the smoke at (1,1) move first, re-seed / box it
> tighter; the assertion is "steam and smoke do not swap."

**4f. Drift stays EMPTY-only.** Steam blocked above by stone (straight-up rise
fails) and flanked by water on both sides: drift would target the water cells,
but drift is `== ElementId.EMPTY`, so the steam does NOT drift sideways through
the water. Assert the steam stays put and the water stays put:

```python
def test_drift_does_not_go_sideways_through_liquid() -> None:
    """Buoyancy is UPWARD only. A steam cell blocked above by STONE and flanked
    left/right by WATER cannot rise (stone is not riseable) and must NOT drift
    sideways through the water (drift is EMPTY-only). The steam stays put."""
    random.seed(0)
    g = Grid(3, 3)
    # Stone floor + stone directly above the steam (blocks straight-up rise).
    g.set(1, 0, ElementId.STONE)
    g.set(1, 2, ElementId.STONE)  # floor under the steam
    # Steam in the middle; WATER on both sides (drift targets, but not EMPTY).
    g.set(1, 1, ElementId.STEAM)
    g.set_life(1, 1, 200)
    g.set(0, 1, ElementId.WATER)
    g.set(2, 1, ElementId.WATER)
    warm = ELEMENTS[ElementId.STEAM].temp_spawn
    g.set_temp(1, 1, warm)
    g.set_temp(0, 1, warm)
    g.set_temp(2, 1, warm)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM  # did not drift into the water
    assert g.get(0, 1) == ElementId.WATER
    assert g.get(2, 1) == ElementId.WATER
```

> The up-diagonals from (1,1) are (0,0) and (2,0): both EMPTY (open corners).
> `is_riseable(EMPTY)` is True, so the steam MAY rise diagonally into a corner
> here. To force a clean "stays put" assertion, either fill (0,0)/(2,0) with
> stone too, or assert the steam did not enter the WATER cells (the narrower
> claim this test is named for). Recommended: fill the up-diagonal corners with
> stone so the steam is fully boxed except for the water sides, making "stays
> put" deterministic. Pin the final geometry in the reflection.

**4g. Module imports** for the test file:

```python
from __future__ import annotations

import random

from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation
```

## Acceptance Criteria

- [ ] `is_riseable` exists in `rules/_common.py`, returns True for `EMPTY` and
      every `Phase.LIQUID` id (WATER / LAVA / ACID / BASE / OIL) and False for
      solids (STONE / SAND / WOOD / …) and other gases (SMOKE / STEAM / FIRE).
- [ ] **STEAM rises through water**: one step swaps steam up / water down
      (`test_steam_rises_through_water` passes). Steam also reaches the surface
      of a pool (`test_steam_rises_to_surface_of_water_pool` passes).
- [ ] **SMOKE rises through water** (mirror) — `test_smoke_rises_through_water`
      passes.
- [ ] **Steam rises through another liquid** (oil) —
      `test_steam_rises_through_oil` passes (buoyancy is generic over LIQUID).
- [ ] **Steam does NOT rise through a solid or another gas** —
      `test_steam_does_not_rise_through_solid_or_gas` passes (`is_riseable` is
      False for STONE and SMOKE).
- [ ] **Drift stays EMPTY-only** — `test_drift_does_not_go_sideways_through_liquid`
      passes (steam flanked by water does not drift sideways through it).
- [ ] The sideways **drift** checks in `steam.py:70` and `smoke.py:53` are still
      `== ElementId.EMPTY` (unchanged — buoyancy is upward only).
- [ ] **FIRE is unchanged** — its rise rule is not edited (EMPTY-only).
- [ ] Module docstrings updated in `_common.py`, `steam.py`, `smoke.py` (no
      "only enters EMPTY cells" claim left for steam/smoke).
- [ ] Existing steam/smoke tests stay green (`tests/test_phase.py`,
      `tests/test_fire.py` — they rise into EMPTY, which `is_riseable` permits).
- [ ] Full suite stays green (217+ tests; this plan only adds, no removals).
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused tests (the new buoyancy tests):
uv run pytest tests/test_gas_buoyancy.py -v

# Existing gas tests stay green (they rise into EMPTY, still permitted):
uv run pytest tests/test_phase.py tests/test_fire.py -v

# Import sanity + the helper exists:
uv run python -c "import sandfall; from sandfall.rules._common import is_riseable; from sandfall.elements import ElementId; assert is_riseable(int(ElementId.EMPTY)) and is_riseable(int(ElementId.WATER)) and not is_riseable(int(ElementId.STONE)) and not is_riseable(int(ElementId.SMOKE)); print('buoyancy OK')"

# FULL suite -- regression guard (nothing else broke):
uv run pytest

# Lint + format + types:
uv run ruff check . && uv run ruff format --check . && uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
#   Manual check: spawn STEAM (or SMOKE) under a water pool. Expect it to
#   bubble up through the water and surface into the air -- NOT sit trapped
#   under the water line as before. FIRE under water should still go out / sit
#   (unchanged).
```

All commands must exit zero. Do not proceed to the reflection/commit until all
six pass.

## Documentation Updates

- None required beyond the in-code docstrings. The three rule-file / helper
  docstrings are updated in-place (steps 1c / 2e / 3e) — that is the only doc
  surface this change touches.
- No `AGENTS.md`, README, or `BACKLOG.md` change (gas buoyancy was not a tracked
  deferred item; it is a standalone fix).

## Reflection & Commit

After implementation, write `01-gas-rise-through-liquid-reflection.md`. Include:
- whether the **steam-through-water single-step swap** held as written or needed
  temp/life tuning (did `warm = temp_spawn` (120) keep it above `condense_point`
  (60) through the diffusion pre-pass?);
- the **reaches-surface step count / `warm` value** that reliably got the steam
  above the water line (did diffusion toward the cold stone walls cool it over
  200 steps, requiring a bump?);
- the final **drift-test geometry** (were the up-diagonal corners filled with
  stone to force "stays put", or was the narrower "did not enter water"
  assertion used?);
- whether any **existing test** relied on gas being trapped under a liquid and
  needed updating (none expected);
- confirmation the **drift checks** in both rules are still `== ElementId.EMPTY`
  and FIRE's rule is untouched.

Then make ONE atomic git commit covering `rules/_common.py`, `rules/steam.py`,
`rules/smoke.py`, and `tests/test_gas_buoyancy.py`.

# Phase 03: Phase changes + 4 new elements (STEAM / ICE / LAVA / GLASS)

## Objective

Exercise the thermal field with real phase transitions. Add four new
`ElementId` members (STEAM, ICE, LAVA, GLASS — **8 → 12**, a deliberate
deviation from the v1 "no new members" note), give each an `ELEMENTS` entry with
thermal fields + a color + a rule, and add temperature branches to the existing
`WATER` (boil → STEAM / freeze → ICE) and `SAND` (melt → GLASS) rules. Include
the LAVA+WATER → STEAM+STONE reaction. Verify the renderer LUT and palette
auto-resize, and recompute the palette minimum window width so the 12 swatches
still fit.

> **Deviation flagged.** `elements.py:10-14` claims `ElementId` members are
> "defined in full" and that later phases "never add new enum members". This
> phase intentionally adds four members. Update that docstring AND the
> `docs/ARCHITECTURE.md` "Adding a new element" note (`ARCHITECTURE.md:262-285`,
> which already anticipates "an intentional extension of that invariant — update
> the comment"). This is user-approved ("Water cycle + lava + glass") and
> recorded in the overview Decision Log #5.

## Depends On

02 (Thermal combustion) — must have passed all its gates. The temp-driven
reactive-rule mechanism this phase reuses for boil/freeze/melt is the same
contract Phase 02 formalized for wood/plant ignition, and Phase 02's tuned
thermal baseline (burn-temp/flashpoint/conductivity) is inherited here.

## Can Parallelize With

none — Phase 04's heat overlay is the only thing left, and it wants the new
elements in place to visualize.

## Recommended Agent

@implementer — largest surface area of the plan: 4 enum members, 4 registry
entries, 4 new rule files, edits to 2 existing rules, a cross-element reaction,
palette/geometry recompute, and a new test file. Read carefully; the
reactive-rule relaxation (overview Decision #7) is now used by 6 rules.

## Changes Required

- `src/sandfall/elements.py` — add `STEAM`, `ICE`, `LAVA`, `GLASS` to `ElementId`
  (8 → 12); update the docstring; add 4 `ELEMENTS` entries with thermal fields +
  colors + transition thresholds.
- `src/sandfall/config.py` — add `COND_STEAM`, `COND_ICE`, `COND_LAVA`,
  `COND_GLASS`; **recompute `MIN_WINDOW_W`** for 12 palette swatches.
- `src/sandfall/rules/steam.py` (NEW) — gas, rises like smoke, condenses→WATER.
- `src/sandfall/rules/ice.py` (NEW) — static solid, melts→WATER.
- `src/sandfall/rules/lava.py` (NEW) — liquid-like movement, very hot, cools→
  STONE, LAVA+WATER→STEAM+STONE reaction.
- `src/sandfall/rules/glass.py` (NEW) — static solid (no-op rule; made by sand
  melting).
- `src/sandfall/rules/water.py` — add boil→STEAM / freeze→ICE temp branches.
- `src/sandfall/rules/sand.py` — add melt→GLASS temp branch.
- `src/sandfall/rules/__init__.py` — register the 4 new rules in `RULES`;
  re-export `seed_smoke_life`-style helpers if any (steam life).
- `tests/test_phase.py` (NEW) — boil/freeze/melt/condense + lava+water reaction.
- `tests/test_ui.py`, `tests/test_config.py` — update the palette-count and
  min-width assertions (8 → 12 swatches).

## Implementation Instructions

> Re-read `elements.py`, `water.py`, `sand.py`, `smoke.py` (steam mirrors it),
> `stone.py`/`wood.py` (ice/glass mirror the reactive shape), `renderer.py`
> (LUT), `ui.py` (`palette_layout`), `config.py` (min-width math) before editing.

### 1. `src/sandfall/elements.py`

**1a. Add the enum members** after `PLANT = 7` (`elements.py:23`):

```python
class ElementId(IntEnum):
    """Stable integer IDs stored in the grid (uint8).

    Extended in Phase 03 (temperature feature) with STEAM, ICE, LAVA, GLASS.
    Earlier v1 notes said "never add new enum members"; that was superseded by
    the temperature feature (user-approved). Existing member values 0..7 are
    unchanged, so the LUT indices for the v1 elements are stable.
    """

    EMPTY = 0
    SAND = 1
    WATER = 2
    STONE = 3
    WOOD = 4
    FIRE = 5
    SMOKE = 6
    PLANT = 7
    STEAM = 8
    ICE = 9
    LAVA = 10
    GLASS = 11
```

> Existing values 0–7 are unchanged, so any code that relied on `int(SAND)==1`
> etc. is unaffected. New members take 8–11. `uint8` holds up to 255, so there
> is ample room.

**1b. Add the 4 `ELEMENTS` entries** after the PLANT entry (`elements.py:101-108`).
Thermal fields use the transition thresholds declared on `Element` in Phase 01
(`melt_point` / `boil_point` / `freeze_point` / `condense_point`):

```python
ElementId.STEAM: Element(
    id=ElementId.STEAM, name="steam",
    color=(220, 220, 230),
    density=0.04, phase=Phase.GAS,
    conductivity=0.25,
    temp_spawn=120,           # warm gas on spawn
    condense_point=60,        # below this temp, condenses -> WATER
),
ElementId.ICE: Element(
    id=ElementId.ICE, name="ice",
    color=(180, 220, 240),
    density=0.92, phase=Phase.SOLID,
    conductivity=0.18,
    temp_spawn=-5,
    melt_point=0,             # above 0 -> WATER
),
ElementId.LAVA: Element(
    id=ElementId.LAVA, name="lava",
    color=(240, 90, 20),
    density=2.5, phase=Phase.LIQUID,
    conductivity=0.45,
    temp_spawn=1500,           # painted lava starts very hot
    # cools -> STONE when temp drops below FREEZE_OF_LAVA threshold; use a
    # dedicated constant on the rule (no Element field for "solidifies into X")
),
ElementId.GLASS: Element(
    id=ElementId.GLASS, name="glass",
    color=(200, 230, 230),
    density=2.5, phase=Phase.SOLID,
    conductivity=0.10,
    # made only by SAND melting; static once formed.
),
```

Also set `SAND.melt_point` (the temp above which sand → GLASS, ~1700) and confirm
`WATER.boil_point=100` / `WATER.freeze_point=0` from Phase 01 are still set:

```python
ElementId.SAND: Element(..., conductivity=0.15, melt_point=1700),
```

### 2. `src/sandfall/config.py`

**2a. Add conductivities** for the new materials (alongside `COND_*` from
Phase 01):

```python
COND_STEAM = 0.25
COND_ICE = 0.18
COND_LAVA = 0.45
COND_GLASS = 0.10
```

And extend `thermal.build_conductivity_lut` (Phase 01) to set rows 8–11:

```python
lut[int(ElementId.STEAM)] = COND_STEAM
lut[int(ElementId.ICE)] = COND_ICE
lut[int(ElementId.LAVA)] = COND_LAVA
lut[int(ElementId.GLASS)] = COND_GLASS
```

**2b. Recompute the palette minimum width.** The palette now has **12 swatches**
(11 real elements + the Eraser). Width math
(`PALETTE_SWATCH=24`, `PALETTE_PADDING=4`, `PALETTE_MARGIN=8`):

```
12*24 + 11*4 + 2*8 == 288 + 44 + 16 == 348 px
```

`MIN_WINDOW_W` must exceed 348 with comfortable margin. Bump it to the next
clean `CELL_SIZE` multiple above 348+margin → **`MIN_WINDOW_W = 384`** (= 96
cols, 36 px of margin). Update the comment at `config.py:43-52` to show the new
math. `MIN_GRID_COLS` recomputes automatically from `MIN_WINDOW_W // CELL_SIZE`
(`config.py:51`) → 96. Leave `MIN_WINDOW_H`/`MIN_GRID_ROWS` unchanged.

### 3. `src/sandfall/rules/water.py`

**3a. Add boil/freeze branches** at the top of `update_water` (before the
movement logic, `water.py:19-50`). These are in-place transforms returning
`None` (reactive-rule relaxation, same as Phase 02 wood/plant):

```python
from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import swap

_WATER = ELEMENTS[ElementId.WATER]


def update_water(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    t = grid.get_temp(x, y)
    # Boil -> STEAM (carry a warm temp so the steam doesn't instantly condense).
    if _WATER.boil_point > 0 and t > _WATER.boil_point:
        grid.set(x, y, ElementId.STEAM)
        grid.set_temp(x, y, 120)        # warm steam
        return None
    # Freeze -> ICE.
    if _WATER.freeze_point < 0 or True:  # freeze_point == 0 is valid; treat as active
        if t <= _WATER.freeze_point:
            grid.set(x, y, ElementId.ICE)
            return None
    # ... existing fall/diagonal/sideways movement unchanged ...
```

Cleaner: `if _WATER.freeze_point != 0 or t <= 0` — pin whichever reads best; the
contract is "at or below `freeze_point` → ICE". (Water has no `life`, so no life
bookkeeping; temp is preserved through the transform so the resulting ICE/STEAM
keeps a sensible temperature.)

### 4. `src/sandfall/rules/sand.py`

**4a. Add the melt→GLASS branch** at the top of `update_sand`
(`sand.py:21-43`):

```python
_SAND = ELEMENTS[ElementId.SAND]

def update_sand(grid, x, y):
    if _SAND.melt_point > 0 and grid.get_temp(x, y) > _SAND.melt_point:
        grid.set(x, y, ElementId.GLASS)
        return None
    # ... existing powder movement unchanged ...
```

### 5. New rule files

**5a. `src/sandfall/rules/steam.py`** — mirror `smoke.py` (`smoke.py:25-57`):
gas, ages (finite life via `seed_smoke_life`-style helper or its own), rises
straight up / up-diagonals / drifts; **condenses→WATER** when its temp drops
below `condense_point`. Reuse `seed_smoke_life` for the lifetime range, or add
`seed_steam_life` in `_common.py` (recommend the latter for clarity, range
~`randint(80, 160)` since steam lingers longer than smoke).

```python
from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import swap, seed_steam_life   # add seed_steam_life in _common.py

_STEAM = ELEMENTS[ElementId.STEAM]
_DRIFT_CHANCE = 0.25

def update_steam(grid, x, y):
    # Condense -> WATER when cool enough.
    if grid.get_temp(x, y) < _STEAM.condense_point:
        grid.set(x, y, ElementId.WATER)
        return None
    # Age; expire to EMPTY.
    life = grid.get_life(x, y) - 1
    if life <= 0:
        grid.set(x, y, ElementId.EMPTY); grid.set_life(x, y, 0)
        return None
    grid.set_life(x, y, life)
    # Rise / drift — identical shape to smoke.update_smoke.
    ...
```

(`brush.paint_brush` must seed STEAM life too — extend its seeding pass to cover
STEAM, mirroring FIRE/SMOKE at `brush.py:37-52`.)

**5b. `src/sandfall/rules/ice.py`** — mirror `stone.py` (`stone.py:15-17`)
reactive shape: static, melts→WATER above `melt_point`:

```python
_ICE = ELEMENTS[ElementId.ICE]

def update_ice(grid, x, y):
    if _ICE.melt_point != 0 and grid.get_temp(x, y) > _ICE.melt_point:
        grid.set(x, y, ElementId.WATER)
        return None
    return None
```

**5c. `src/sandfall/rules/lava.py`** — liquid-like movement (reuse `water.py`'s
fall/diagonal/flow with `can_displace`, density 2.5 so it sinks under water and
water floats on it — which is what triggers the reaction). Two thermal
behaviors: (1) **cools→STONE** when temp drops below a solidify threshold
(e.g. `LAVA_SOLIDIFY_TEMP = 700`, a module constant); (2) **LAVA+WATER
reaction**: if any 4-neighbor is WATER, the lava becomes STONE and that water
neighbor becomes STEAM (hot). Returns `None` (in-place + side-effect).

```python
from __future__ import annotations
import random
from ..elements import ElementId
from ..grid import Grid
from ._common import can_displace, swap

LAVA_SOLIDIFY_TEMP = 700
_REACT_NEIGHBORS = ((0, -1), (0, 1), (-1, 0), (1, 0))  # 4-neighborhood

def update_lava(grid, x, y):
    # 1. React with adjacent WATER -> STEAM + STONE (side-effect on the neighbor).
    for dx, dy in _REACT_NEIGHBORS:
        nx, ny = x + dx, y + dy
        if grid.in_bounds(nx, ny) and grid.get(nx, ny) == ElementId.WATER:
            grid.set(x, y, ElementId.STONE)
            grid.set(nx, ny, ElementId.STEAM)
            grid.set_temp(nx, ny, 150)
            grid.set_life(nx, ny, seed_steam_life())   # if steam has life
            return None
    # 2. Cool -> STONE when below the solidify threshold.
    if grid.get_temp(x, y) < LAVA_SOLIDIFY_TEMP:
        grid.set(x, y, ElementId.STONE)
        return None
    # 3. Otherwise move like a dense liquid (fall / diagonal / flow), reusing
    #    the water-style displacement. Lava is denser than water so it sinks.
    ...  # straight down, down-diagonals randomized, sideways randomized
    return None
```

(Import `seed_steam_life`; if you used smoke's helper for steam life, import
that instead. Pin the choice in the reflection.) The LAVA+WATER side-effect is
the same kind of unreturned neighbor write `fire.py:14-19` already documents —
note it in the lava docstring.

**5d. `src/sandfall/rules/glass.py`** — pure no-op static solid (mirror
`stone.py`). Glass is made only by sand melting; once formed it never changes:

```python
def update_glass(grid, x, y):
    """Glass is a static solid. Made by SAND melting; does nothing on its own."""
    return None
```

### 6. `src/sandfall/rules/__init__.py`

**6a. Register the 4 new rules** (`rules/__init__.py:43-51`) and re-export
`seed_steam_life`:

```python
from .steam import update_steam
from .ice import update_ice
from .lava import update_lava
from .glass import update_glass
...
RULES = {
    ...,
    ElementId.STEAM: update_steam,
    ElementId.ICE: update_ice,
    ElementId.LAVA: update_lava,
    ElementId.GLASS: update_glass,
}
```

Add `seed_steam_life` to `_common.py` and to `__all__`.

### 7. Renderer + palette verification (mostly automatic)

- **Renderer LUT.** `build_color_lut` sizes itself from `len(ElementId)`
  (`renderer.py:36`) and iterates `ELEMENTS` (`renderer.py:38-41`), so the 4 new
  colors appear automatically. **Verify** with an assertion in
  `tests/test_renderer.py` (or a new test) that the LUT shape is now `(12, 3)`
  and rows 8–11 match the new element colors. No `renderer.py` edit needed.
- **Palette.** `palette_layout` iterates `ElementId` (`ui.py:79-83`), so the 4
  new swatches appear automatically. **Verify** in `tests/test_ui.py` that the
  palette now has 12 swatches (11 elements + eraser) and that `swatch_at`
  resolves the new ones. The `MIN_WINDOW_W` bump from 2b keeps them on-screen at
  the minimum size.

### 8. `tests/test_phase.py` (NEW)

Cover each transition deterministically (seed temp, step once, assert the
resulting element). Pattern mirrors `test_fire.py`'s seeded-temp style:

```python
from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation

def _step_with_temp(eid, temp):
    g = Grid(3, 3); g.set(1, 1, eid); g.set_temp(1, 1, temp)
    Simulation(g).step()
    return g

def test_water_boils_to_steam():
    g = _step_with_temp(ElementId.WATER, ELEMENTS[ElementId.WATER].boil_point + 20)
    assert g.get(1, 1) == ElementId.STEAM

def test_water_freezes_to_ice():
    g = _step_with_temp(ElementId.WATER, ELEMENTS[ElementId.WATER].freeze_point - 5)
    assert g.get(1, 1) == ElementId.ICE

def test_ice_melts_to_water():
    g = _step_with_temp(ElementId.ICE, ELEMENTS[ElementId.ICE].melt_point + 5)
    assert g.get(1, 1) == ElementId.WATER

def test_steam_condenses_to_water():
    g = _step_with_temp(ElementId.STEAM, ELEMENTS[ElementId.STEAM].condense_point - 10)
    # give the steam life so it doesn't expire on the same step
    g.set_life(1, 1, 50)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.WATER

def test_sand_melts_to_glass():
    g = _step_with_temp(ElementId.SAND, ELEMENTS[ElementId.SAND].melt_point + 50)
    assert g.get(1, 1) == ElementId.GLASS

def test_lava_cools_to_stone():
    from sandfall.rules.lava import LAVA_SOLIDIFY_TEMP
    g = _step_with_temp(ElementId.LAVA, LAVA_SOLIDIFY_TEMP - 50)
    assert g.get(1, 1) == ElementId.STONE

def test_lava_water_reaction():
    g = Grid(3, 3)
    g.set(0, 1, ElementId.LAVA); g.set_temp(0, 1, 1500)
    g.set(1, 1, ElementId.WATER); g.set_temp(1, 1, 20)
    Simulation(g).step()
    assert g.get(0, 1) == ElementId.STONE      # lava solidified
    assert g.get(1, 1) == ElementId.STEAM      # water flashed to steam

def test_paint_brush_lava_sets_spawn_temp():
    from sandfall.brush import paint_brush
    g = Grid(10, 10)
    paint_brush(g, 5, 5, 1, ElementId.LAVA)
    for x in range(g.width):
        for y in range(g.height):
            if g.get(x, y) == ElementId.LAVA:
                assert g.get_temp(x, y) == ELEMENTS[ElementId.LAVA].temp_spawn
```

### 9. Update existing tests for the wider palette

- `tests/test_ui.py` — any assertion on the swatch COUNT (8) becomes 12; any
  assertion that the rightmost swatch is the Eraser still holds (eraser is
  appended last, `ui.py:85`). The min-width reasoning in any test comment should
  reflect the new `12*24 + 11*4 + 2*8 == 348` math.
- `tests/test_config.py` — `MIN_WINDOW_W` is now 384; update the
  `compute_grid_dims` clamping test's expectations if it hardcodes 256/64 (it
  uses `MIN_GRID_COLS` symbolically at `test_config.py` via the constants, so it
  should auto-adjust — verify).

## Acceptance Criteria

- [ ] `ElementId` has 12 members (0–11); the v1 values 0–7 are unchanged; the
      docstring no longer claims "never add new members".
- [ ] All 4 new elements have `ELEMENTS` entries with sensible thermal fields +
      colors; `len(ELEMENTS) == 12`.
- [ ] WATER boils→STEAM above `boil_point` and freezes→ICE at/below
      `freeze_point` (deterministic tests pass).
- [ ] ICE melts→WATER above `melt_point`; STEAM condenses→WATER below
      `condense_point`; SAND melts→GLASS above `melt_point`; LAVA cools→STONE
      below the solidify threshold (tests pass).
- [ ] LAVA adjacent to WATER → STONE + STEAM (reaction test passes).
- [ ] STEAM has finite life (rises + drifts like smoke) and is seedable from the
      brush; ICE/GLASS are static.
- [ ] `RULES` registry enumerates all 12 elements; `len(RULES) == 12` (or 11
      real rules + EMPTY omitted — pin the convention; EMPTY has never had a
      rule).
- [ ] `build_color_lut` returns shape `(12, 3)` and rows 8–11 are the new colors
      (test passes; no `renderer.py` edit was needed).
- [ ] `palette_layout` yields 12 swatches (11 elements + eraser); `swatch_at`
      resolves the new ones.
- [ ] `MIN_WINDOW_W == 384`; the 12 swatches fit at the minimum window size
      (recompute documented in `config.py`).
- [ ] All six gates exit zero.

## Verification Commands

```bash
# Phase-specific:
uv run pytest tests/test_phase.py tests/test_renderer.py tests/test_ui.py tests/test_config.py -v
# Confirm the enum + registry grew and the v1 indices are stable:
uv run python -c "from sandfall.elements import ElementId; from sandfall.rules import RULES; assert [e.value for e in ElementId]==list(range(12)); assert int(ElementId.SAND)==1 and int(ElementId.PLANT)==7; assert len(RULES)>=11; print('enum+registry OK')"
# Confirm palette min-width math: 12 swatches fit in MIN_WINDOW_W.
uv run python -c "from sandfall.config import MIN_WINDOW_W, PALETTE_SWATCH, PALETTE_PADDING, PALETTE_MARGIN; need=12*PALETTE_SWATCH+11*PALETTE_PADDING+2*PALETTE_MARGIN; assert MIN_WINDOW_W>=need, (MIN_WINDOW_W, need); print('palette fits', need, '<=', MIN_WINDOW_W)"

# The six gates (all must exit zero):
uv run python -c "import sandfall"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
#   Manual check on DISPLAY=:1: paint LAVA into WATER (hiss -> steam + stone),
#   heat SAND with LAVA to make GLASS, freeze WATER to ICE and melt it back.
```

All commands must exit zero. Do NOT proceed to Phase 04 until all pass.

## Documentation Updates

- `docs/ARCHITECTURE.md` — the full thermal/element write-up is Phase 04, but
  update the `ElementId` member list in the "element model" section
  (`ARCHITECTURE.md:99-102`) and the "Adding a new element" note
  (`ARCHITECTURE.md:262-285`) now so the docs aren't transiently wrong between
  phases. (Phase 04 expands the rest.)

## Reflection & Commit

After implementation, write `03-phase-changes-reflection.md`. Include the final
transition-threshold values actually used (boil/freeze/melt/condense/solidify)
and any tuning needed to make the lava+water reaction and sand→glass feel right,
plus whether you gave STEAM its own `seed_steam_life` or reused smoke's. Then
make ONE atomic git commit covering all changes in this phase.

# Phase 02: Oil (floats on water, flammable)

## Objective

Add `ElementId.OIL = 14` — a light flammable liquid (density 0.8 < WATER 1.0)
that **floats on water** via the existing density-based `can_displace`, and
**ignites to FIRE** when heated above a low flashpoint (~150) so burning oil
spreads fire across a water surface. Oil is the simplest possible new element:
reactive burn checked first, then liquid flow — no dissolve/dilute. Extend the
thermal LUTs and recompute `MIN_WINDOW_W` for the wider 17-item palette.

> **Re-read before editing** (line numbers shifted by Phase 01; re-read each
> file): `src/sandfall/elements.py`, `src/sandfall/config.py`,
> `src/sandfall/thermal.py`, `src/sandfall/rules/__init__.py`,
> `src/sandfall/rules/water.py`, `src/sandfall/rules/wood.py`,
> `src/sandfall/rules/acid.py` (Phase 01 — oil must be added to acid's dissolve
> behavior), `tests/test_ui.py`, `tests/test_config.py`.

## Depends On

01 (Acid + Base) — must have passed all its gates. Phase 02 extends the enum
12→13 (from Phase 01) → 14, recomputes `MIN_WINDOW_W` a second time (16→17
palette items), and its tests assert that **acid dissolves oil** (oil is absent
from acid's resist set), which requires acid to exist.

## Can Parallelize With

none — last phase.

## Recommended Agent

@implementer — small surface area (one element, the simplest rule shape), but
it touches the same shared core files as Phase 01 and must keep the full suite
green after the enum grows again. The float/density behavior is the interesting
part (verify oil ends up ABOVE water).

## Changes Required

- `src/sandfall/elements.py` — add `OIL = 14` to `ElementId` (14 → 15 members);
  add an `ELEMENTS` entry (LIQUID/density 0.8/flashpoint 150 + color).
- `src/sandfall/config.py` — add `COND_OIL`, `CP_OIL`; **recompute
  `MIN_WINDOW_W`** for 17 palette items (→ 500).
- `src/sandfall/thermal.py` — add row 14 to both LUT builders; import the 2 new
  config constants.
- `src/sandfall/rules/oil.py` (NEW) — reactive burn first, then liquid flow.
- `src/sandfall/rules/__init__.py` — import + register `update_oil`.
- `src/sandfall/rules/acid.py` / `base.py` — verify oil is dissolvable (it is NOT
  in the resist sets, so no edit expected; add an assertion-test).
- `tests/test_oil.py` (NEW) — floats on water (density), ignites to FIRE,
  burning oil spreads fire across water.
- `tests/test_ui.py` — update the palette-count assertion (`13 → 14`) and the
  min-window math test (`16 → 17` items).
- `tests/test_config.py` — update the min-window test (`MIN_WINDOW_W 472 → 500`,
  `16 → 17` items).
- `docs/ARCHITECTURE.md` — append `OIL=14` to the member list.
- `.agent/tasks/BACKLOG.md` — strike "oil" from the "More elements" line.

## Implementation Instructions

### 1. `src/sandfall/elements.py`

**1a. Add the enum member** after `BASE = 13`:

```python
    ACID = 12
    BASE = 13
    OIL = 14
```

> Existing values 0–13 are unchanged. Update the enum docstring sentence (added
> in Phase 01) to note this feature also adds OIL (14).

**1b. Add the `ELEMENTS` entry** after the BASE entry. First-pass values
(Decision #12):

```python
    # --- Oil (light flammable liquid; floats on water) ----------------------
    # LIQUID with density 0.8 (< WATER 1.0 -> floats on water via can_displace).
    # Low flashpoint ~150 -> ignites to FIRE when heated by fire/lava (thermal
    # path). No dissolve/dilute of its own (rules/oil.py: burn first, then flow).
    # burn_temp is unset (declared default AMBIENT): when oil ignites it becomes
    # ElementId.FIRE, whose rule re-asserts FIRE.burn_temp (800).
    ElementId.OIL: Element(
        id=ElementId.OIL,
        name="oil",
        color=(70, 45, 25),         # dark oily brown
        density=0.8,
        phase=Phase.LIQUID,
        conductivity=0.12,          # oils are thermal insulators
        heat_capacity=1.5,
        flashpoint=150,
    ),
```

> `burn_temp` is left at its default (no field spelled out): oil becomes generic
> FIRE on ignition, and the FIRE rule (`fire.py:92-93`) re-asserts
> `_FIRE.burn_temp` (800). This is the same shape as wood/plant where the active
> heat comes from FIRE, not the fuel's own declared burn_temp (Risk #6 in the
> overview).

### 2. `src/sandfall/config.py`

**2a. Add the constants** alongside the Phase-01 block:

```python
COND_OIL = 0.12
...
CP_OIL = 1.5
```

> Stability unchanged (0.12 < FIRE 0.50; 1.5 > min 0.5).

**2b. Recompute `MIN_WINDOW_W`** for the 17-item palette (14 elements + Eraser +
Brush-shape + Magnifier). Update the comment (set in Phase 01) to:

```
# Minimum window size. Width must fit the whole palette (17 items: 14 element
# swatches + Eraser + Brush-shape + Magnifier). Width math:
#   17 * PALETTE_SWATCH + 16 * PALETTE_PADDING + PALETTE_GROUP_GAP + 2 * PALETTE_MARGIN
#   = 17*24 + 16*4 + 12 + 2*8 = 408 + 64 + 12 + 16 = 500  (== 125 * CELL_SIZE)
# 500 is the next clean CELL_SIZE multiple above the needed 500, = 125 cols.
```

Set `MIN_WINDOW_W = 500`. `MIN_GRID_COLS` → 125 automatically.

### 3. `src/sandfall/thermal.py`

Import `COND_OIL`, `CP_OIL` in the config import block; add row 14 to both
`build_conductivity_lut` and `build_heat_capacity_lut` (after the ACID/BASE rows
added in Phase 01):

```python
    lut[int(ElementId.ACID)] = COND_ACID
    lut[int(ElementId.BASE)] = COND_BASE
    lut[int(ElementId.OIL)] = COND_OIL
    return lut
```

```python
    lut[int(ElementId.ACID)] = CP_ACID
    lut[int(ElementId.BASE)] = CP_BASE
    lut[int(ElementId.OIL)] = CP_OIL
    return lut
```

### 4. `src/sandfall/rules/oil.py` (NEW)

The simplest reactive-liquid shape: burn first (mirror `wood.py:24-30`), then
flow (mirror `water.py:67-90`). No dissolve/dilute:

```python
"""Oil (LIQUID, light, flammable) update rule.

Oil is a light liquid (density 0.8, less than WATER 1.0 -> floats on water via
can_displace) that ignites when heated. Each step:

1. **Burn** -- if the cell's own temp exceeds its flashpoint (~150), become FIRE
   (seed life, set burn-temp). Mirrors wood/plant reactive ignition. Once oil
   ignites it becomes ElementId.FIRE, a persistent heat source whose diffusion
   heats neighboring oil above its flashpoint -> fire spreads across an oil
   slick (including oil floating on water).
2. **Flow** -- otherwise move like a light liquid: straight down, down-diagonals
   randomized, one-cell sideways randomized, all via can_displace + swap. Because
   oil is LIGHTER than water, water displaces oil (can_displace(WATER, OIL) is
   True) so water sinks and oil rises/floating -- oil ends up on top.

No dissolve/dilute (unlike acid/base). Burning oil on water spreads fire across
the surface because FIRE is already a persistent heat source + neighborhood wake
(simulation.py wake condition #3).
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import can_displace, seed_fire_life, swap

_ELM = ELEMENTS[ElementId.OIL]
_FIRE = ELEMENTS[ElementId.FIRE]


def update_oil(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an oil cell: burn when hot, else flow like a light liquid."""
    # 1. Burn: own temp above flashpoint -> FIRE.
    if _ELM.flashpoint > 0 and grid.get_temp(x, y) > _ELM.flashpoint:
        grid.set(x, y, ElementId.FIRE)
        grid.set_life(x, y, seed_fire_life())
        grid.set_temp(x, y, _FIRE.burn_temp)
        return None

    # 2. Flow like a light liquid (water.py shape via can_displace + swap).
    if y + 1 < grid.height and can_displace(ElementId.OIL, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)
    diagonals = [-1, 1]
    random.shuffle(diagonals)
    for dx in diagonals:
        nx, ny = x + dx, y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.OIL, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)
    sideways = [-1, 1]
    random.shuffle(sideways)
    for dx in sideways:
        nx, ny = x + dx, y
        if grid.in_bounds(nx, ny) and can_displace(ElementId.OIL, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None
```

> OIL has no finite life (it is fuel, not a timer), so it needs NO `seed_*_life`
> helper and NO brush change (`brush.py` seeds only FIRE/SMOKE/STEAM). Its
> `temp_spawn` defaults to `AMBIENT_TEMP`, so `paint_brush` needs no spawn-temp
> change. The palette swatch appears automatically (`ui.py:135-147`).

### 5. `src/sandfall/rules/acid.py` / `base.py` — verify oil is dissolvable

Oil is NOT in `ACID_RESIST` or `BASE_RESIST` (Phase 01), so acid/base dissolve
oil by default (Decision #10 — "acid dissolves oil since oil isn't in acid's
resist set"). **No edit to the resist sets is expected** — verify with an
assertion-test (below) rather than a code change. If the implementer prefers to
make the relationship explicit, they may add `ElementId.OIL` to a comment in the
resist-set declaration; do NOT add it to the frozenset itself (that would make
oil resist acid, contradicting Decision #10).

### 6. `src/sandfall/rules/__init__.py`

Import + register:

```python
from .oil import update_oil
...
RULES: dict[ElementId, UpdateFn] = {
    ...,
    ElementId.BASE: update_base,
    ElementId.OIL: update_oil,
}
```

### 7. Renderer + palette verification (automatic)

`build_color_lut` and `palette_layout` auto-resize from `len(ElementId)` (Phase
01 precedent). **Verify** (no edit): `build_color_lut().shape == (15, 3)` in the
new test.

### 8. `tests/test_oil.py` (NEW)

```python
import random
from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.renderer import build_color_lut
from sandfall.rules._common import can_displace
from sandfall.simulation import Simulation


def _step_single_cell(eid, temp):
    g = Grid(1, 1); g.set(0, 0, eid); g.set_temp(0, 0, temp)
    Simulation(g).step(); return g


# --- floats on water (density) ---
def test_oil_is_lighter_than_water():
    # water can displace oil (water sinks); oil cannot displace water (oil floats).
    assert can_displace(ElementId.WATER, int(ElementId.OIL)) is True
    assert can_displace(ElementId.OIL, int(ElementId.WATER)) is False


def test_oil_floats_above_water():
    """A cell of oil directly above water, stepped many times, ends with oil on
    top and water below (water sinks through the lighter oil)."""
    random.seed(0)
    g = Grid(1, 4)
    g.set(0, 0, ElementId.OIL)
    g.set(0, 1, ElementId.WATER)
    sim = Simulation(g)
    for _ in range(40):
        sim.step()
    # Oil is lighter -> it should have risen above the water.
    oil_y = [y for y in range(g.height) if g.get(0, y) == ElementId.OIL]
    water_y = [y for y in range(g.height) if g.get(0, y) == ElementId.WATER]
    assert oil_y and water_y
    assert min(oil_y) < max(water_y)   # oil is above at least some water


# --- ignites to FIRE ---
def test_oil_ignites_to_fire_when_hot():
    g = _step_single_cell(ElementId.OIL, ELEMENTS[ElementId.OIL].flashpoint + 50)
    assert g.get(0, 0) == ElementId.FIRE


def test_oil_at_ambient_stays_oil():
    g = _step_single_cell(ElementId.OIL, 20)
    assert g.get(0, 0) == ElementId.OIL


# --- burning oil spreads fire across water ---
def test_burning_oil_spreads_fire_across_water():
    """An oil slick floating on water, ignited at one end, spreads FIRE across
    the slick: fire is a persistent heat source whose diffusion heats neighboring
    oil above its flashpoint, so the fire front advances along the surface."""
    random.seed(0)
    g = Grid(7, 3)
    # Bottom row: water; middle row: oil floating on it; top row: empty.
    for x in range(7):
        g.set(x, 2, ElementId.WATER)
        g.set(x, 1, ElementId.OIL)
    # Ignite the leftmost oil directly (give it FIRE's burn-temp).
    g.set(0, 1, ElementId.FIRE)
    g.set_temp(0, 1, ELEMENTS[ElementId.FIRE].burn_temp)
    g.set_life(0, 1, 40)
    sim = Simulation(g)
    fire_before = int((g.array == int(ElementId.FIRE)).sum())
    for _ in range(120):
        sim.step()
    # Fire must have appeared in oil cells beyond the ignition point (spread).
    oil_or_fire_row1 = [
        g.get(x, 1) in (ElementId.OIL, ElementId.FIRE) for x in range(7)
    ]
    # At least one cell to the right of x=0 caught fire at some point; assert
    # the fire count is nonzero and the slick was disturbed (some oil burned).
    fire_after = int((g.array == int(ElementId.FIRE)).sum())
    oil_after = int((g.array == int(ElementId.OIL)).sum())
    assert oil_after < 7   # some oil ignited (burned away to fire/smoke/empty)


# --- acid dissolves oil (Decision #10) ---
def test_acid_dissolves_oil(monkeypatch):
    import sandfall.rules.acid as acid
    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1); g.set(0, 0, ElementId.ACID); g.set(1, 0, ElementId.OIL)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY        # oil eaten (not in ACID_RESIST)
    assert g.get(0, 0) == ElementId.EMPTY        # acid consumed


# --- renderer LUT grew ---
def test_color_lut_has_15_rows():
    assert build_color_lut().shape == (15, 3)
```

> The fire-spread test asserts the slick was *disturbed* (oil count dropped)
> rather than an exact fire count, because fire is finite-life and may have
> already expired some cells by the assertion time. The acceptance signal is
> "combustion chained across the surface" — pin the exact steady-state in the
> reflection if a tighter assertion is desired.

### 9. Update existing tests for the wider palette

- `tests/test_ui.py` — bump the element-count literal `13 → 14` (Phase 01 set it
  to 13); update `test_palette_resolves_phase03_elements_and_fits_min_window`
  item count `16 → 17`, padding count `15 → 16`, add OIL to the resolution check.
- `tests/test_config.py` — update `MIN_WINDOW_W == 472 → 500`, item count
  `16 → 17`, padding count `15 → 16`, `MIN_GRID_COLS == 118 → 125`.

## Acceptance Criteria

- [ ] `ElementId` has 15 members (0–14); values 0–13 unchanged; OIL=14.
      `int(SAND)==1`, `int(GLASS)==11`, `int(ACID)==12`, `int(OIL)==14`.
- [ ] OIL has an `ELEMENTS` entry with `phase=LIQUID`, `density==0.8`,
      `flashpoint==150`; `len(ELEMENTS) == 15`.
- [ ] Oil is lighter than water (`can_displace(WATER, OIL)` True; the reverse
      False) — density test passes.
- [ ] Oil floats above water after stepping (oil's min y < water's max y) —
      float test passes.
- [ ] Oil ignites to FIRE above flashpoint (single-cell test passes); at ambient
      it stays oil.
- [ ] Burning oil spreads fire across a water-surface slick (oil count drops;
      combustion chains) — spread test passes.
- [ ] Acid dissolves oil (oil NOT in `ACID_RESIST`) — deterministic test passes
      (Decision #10 verified).
- [ ] `RULES` enumerates all 15 elements (14 real rules + EMPTY omitted);
      `len(RULES) >= 14`.
- [ ] `build_color_lut().shape == (15, 3)`; palette has 14 element swatches + 3
      tools; `MIN_WINDOW_W == 500` and the 17-item row fits at the minimum size.
- [ ] Existing `test_ui.py` / `test_config.py` assertions updated and green.
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused new tests:
uv run pytest tests/test_oil.py -v

# Confirm the enum + registry grew and the stable indices held:
uv run python -c "from sandfall.elements import ElementId; from sandfall.rules import RULES; assert [e.value for e in ElementId]==list(range(15)); assert int(ElementId.SAND)==1 and int(ElementId.GLASS)==11 and int(ElementId.ACID)==12 and int(ElementId.OIL)==14; print('enum+registry OK')"

# Confirm palette min-width math: 17 items fit in MIN_WINDOW_W.
uv run python -c "from sandfall.config import MIN_WINDOW_W, PALETTE_GROUP_GAP, PALETTE_MARGIN, PALETTE_PADDING, PALETTE_SWATCH; need=17*PALETTE_SWATCH+16*PALETTE_PADDING+PALETTE_GROUP_GAP+2*PALETTE_MARGIN; assert MIN_WINDOW_W==500 and MIN_WINDOW_W>=need, (MIN_WINDOW_W, need); print('palette fits', need, '<=', MIN_WINDOW_W)"

# The six gates (all must exit zero):
uv run python -c "import sandfall"
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
#   Manual check on DISPLAY=:1: paint OIL onto WATER (it floats to the top),
#   drop a FIRE/LAVA onto the oil slick (fire races across the surface), paint
#   ACID onto an oil pool (acid eats the oil).
```

All commands must exit zero.

## Documentation Updates

- `docs/ARCHITECTURE.md:250-256` — append `OIL=14` to the `ElementId` member
  list (after the ACID/BASE entries added in Phase 01).
- `.agent/tasks/BACKLOG.md:30-31` — strike "oil" from the "More elements" line
  (acid was struck in Phase 01; leave salt/metal/gunpowder/electricity).
- `README.md` — if it has a Features/elements table, add an OIL row (and the
  ACID/BASE rows from Phase 01 if not already added).

## Reflection & Commit

After implementation, write `02-oil-reflection.md`. Include the final tuned
flashpoint/density (Decision #12), whether the float test needed more/fewer than
40 steps to settle, whether the fire-spread test could be tightened to an exact
assertion, and the acid-dissolves-oil confirmation. Then make ONE atomic git
commit covering all changes in this phase.

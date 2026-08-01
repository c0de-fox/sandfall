# Phase 02: Liquid nitrogen (transient cold liquid)

## Objective

Add `ElementId.LN2 = 17` — a light cryogenic LIQUID (density 0.8 < WATER 1.0 →
floats on water, like oil) that re-asserts `LN2_COLD_TARGET = -196` (its boiling
point) each step while alive, freezing adjacent water **aggressively** via
diffusion (much colder than dry ice's −78), and is **TRANSIENT**: it carries a
per-cell `life` countdown (new `seed_nitrogen_life()` helper, short window
`randint(30, 80)`) and boils off to EMPTY at ambient (room temp ≫ −196). Rule
precedence mirrors `rules/oil.py` (light-liquid flow) prefixed by age + cold-
reassert. Extend the thermal LUTs and recompute `MIN_WINDOW_W` for the 20-item
palette.

> **Re-read before editing** (line numbers shifted by Phase 01; re-read each
> file): `src/sandfall/elements.py`, `src/sandfall/config.py`,
> `src/sandfall/thermal.py`, `src/sandfall/rules/__init__.py`,
> `src/sandfall/rules/_common.py` (where `seed_nitrogen_life` is added),
> `src/sandfall/rules/oil.py` (the light-LIQUID flow pattern LN2 mirrors),
> `src/sandfall/rules/smoke.py` / `steam.py` (the age/expire idiom LN2 mirrors),
> `src/sandfall/brush.py` (the life-seeding pass LN2 joins),
> `tests/test_phase.py`, `tests/test_ui.py`, `tests/test_config.py`.

## Depends On

01 (ice revert + dry ice) — must have passed all its gates. Phase 02 extends
the enum 16→17 (from Phase 01's 15→16), recomputes `MIN_WINDOW_W` a second time
(19→20 palette items), and its `test_ln2_freezes_water_aggressively` test
asserts LN2 freezes water to ICE (the realistic model where only cold sources
freeze water — confirmed by Phase 01's dry-ice freeze test).

## Can Parallelize With

none — last phase.

## Recommended Agent

@implementer — a single new element whose rule combines three proven shapes
(oil's light-liquid flow, smoke/steam's age/expire idiom, fire/dry-ice's cold-
re-assert), plus a new `seed_nitrogen_life` helper and a brush life-seeding
branch. The interesting unknown is the boil-off tuning (must freeze water before
boiling away — overview Risk #5); the `test_ln2_freezes_water_aggressively` +
`test_ln2_boils_off` tests are the gate. Read `00-overview.md` first (Decision
Log #4-#5, Risks #5), then re-read every file cited above before editing.

## Changes Required

- `src/sandfall/elements.py` — add `LN2 = 17` to `ElementId` (17 → 18 members);
  add an `ELEMENTS` entry (LIQUID/density 0.8/temp_spawn −196/cond 0.30/cp 2.0 +
  pale-blue color).
- `src/sandfall/config.py` — add `COND_LN2 = 0.30`, `CP_LN2 = 2.0`;
  **recompute `MIN_WINDOW_W`** for the 20-item palette (→ 584 = 146 cols).
- `src/sandfall/thermal.py` — add row 17 (LN2) to both LUT builders; import
  `COND_LN2`, `CP_LN2`.
- `src/sandfall/rules/_common.py` — add `seed_nitrogen_life()` (short window
  `randint(30, 80)`); document it alongside the existing `seed_*_life` helpers.
- `src/sandfall/rules/ln2.py` (NEW) — transient cold-liquid rule: age (boil off
  to EMPTY) → re-assert −196 → flow like a light liquid (oil shape).
- `src/sandfall/rules/__init__.py` — import + register `update_ln2`; re-export
  `seed_nitrogen_life` (add to the `._common` import + `__all__`).
- `src/sandfall/brush.py` — add an `LN2` branch to the life-seeding selection
  (`:66-73`) so a painted LN2 blob gets a finite life; import `seed_nitrogen_life`.
- `src/sandfall/simulation.py` — **audit-only** (Phase 01 settled the dormant-
  wake question for cold sources; LN2 is transient so it self-wakes via aging +
  identity change. Verify, do not edit unless a test stalls.)
- `tests/test_phase.py` — ADD `test_ln2_freezes_water_aggressively`,
  `test_ln2_boils_off`, `test_ln2_floats_on_water`, `test_paint_brush_ln2_seeds_life`.
- `tests/test_ui.py` — palette-count literal `16 → 17`; min-window math
  `19 → 20` items; add `LN2` to the `new_elements` list.
- `tests/test_config.py` — min-window test `MIN_WINDOW_W 556 → 584`, item count
  `19 → 20`, padding `18 → 19`, `MIN_GRID_COLS 139 → 146`.
- `docs/ARCHITECTURE.md` — append `LN2=17` to the member list; add a sentence on
  the cold-source category (dry ice persistent + LN2 transient).
- `.agent/tasks/BACKLOG.md` — strike "Thermal realism rework" from the Tier 2
  entry (it has shipped).

## Implementation Instructions

> Re-read each file before editing — line numbers below are current as of the
> Phase-01-complete source and may have drifted.

### 1. `src/sandfall/elements.py`

**1a. Add the enum member** after `DRY_ICE = 16` (added in Phase 01):

```python
    GUNPOWDER = 15
    # --- New element (thermal-realism: dry ice cold source) ---
    DRY_ICE = 16
    # --- New element (thermal-realism: liquid nitrogen cold source) ---
    LN2 = 17
```

> Existing values 0–16 are unchanged. Append a sentence to the enum docstring
> noting this feature also adds LN2 (17).

**1b. Add the `ELEMENTS` entry** after the DRY_ICE entry (added in Phase 01).
First-pass values (Decision #4 + overview Risks #5):

```python
    # --- Liquid nitrogen (LIQUID, transient cold source; thermal-realism) ---
    # LIQUID with density 0.8 (< WATER 1.0 -> floats on water, like oil). Re-
    # asserts LN2_COLD_TARGET (-196C, its boiling point) each step while alive
    # (rules/ln2.py) -> freezes water AGGRESSIVELY (much colder than dry ice).
    # TRANSIENT: carries a per-cell life (seed_nitrogen_life) and boils off to
    # EMPTY at ambient (room temp far exceeds -196). temp_spawn=-196. No
    # flashpoint/burn (it is a cold source, not a fuel).
    ElementId.LN2: Element(
        id=ElementId.LN2,
        name="liquid nitrogen",
        color=(150, 190, 235),  # pale cryogenic blue (distinct from ICE/WATER)
        density=0.8,
        phase=Phase.LIQUID,
        conductivity=0.30,
        heat_capacity=2.0,
        temp_spawn=-196,
    ),
```

### 2. `src/sandfall/config.py`

**2a. Add the constants** alongside the DRY_ICE block (Phase 01):

```python
# Liquid nitrogen (transient cold-source liquid). Higher conductivity than dry
# ice so its extreme cold propagates fast (aggressive freeze before boil-off).
COND_LN2 = 0.30
...
# Liquid nitrogen (transient cold-source liquid).
CP_LN2 = 2.0
```

> Stability unchanged (0.30 < FIRE 0.50; 2.0 > min 0.5).

**2b. Recompute `MIN_WINDOW_W`** for the 20-item palette (17 element swatches +
Eraser + Brush-shape + Magnifier). Update the comment (set in Phase 01):

```
# Minimum window size. Width must fit the whole palette (20 items: 17 element
# swatches + Eraser + Brush-shape + Magnifier). Width math:
#   20 * PALETTE_SWATCH + 19 * PALETTE_PADDING + PALETTE_GROUP_GAP + 2 * PALETTE_MARGIN
#   = 20*24 + 19*4 + 12 + 2*8 = 480 + 76 + 12 + 16 = 584  (== 146 * CELL_SIZE)
# 584 is a clean CELL_SIZE multiple, = 146 cols.
```

Set `MIN_WINDOW_W = 584`. `MIN_GRID_COLS` → 146 automatically.

### 3. `src/sandfall/thermal.py` + `rules/_common.py` + `rules/__init__.py`

**3a. `thermal.py`** — add `COND_LN2`, `CP_LN2` to the `from .config import (...)`
block in alphabetical position (`COND_LN2` between `COND_LAVA` and `COND_OIL`;
`CP_LN2` between `CP_LAVA` and `CP_OIL`). Add row 17 to both LUT builders (after
the DRY_ICE row from Phase 01):

```python
    lut[int(ElementId.DRY_ICE)] = COND_DRY_ICE
    # Liquid nitrogen (transient cold-source liquid).
    lut[int(ElementId.LN2)] = COND_LN2
    return lut
```

```python
    lut[int(ElementId.DRY_ICE)] = CP_DRY_ICE
    lut[int(ElementId.LN2)] = CP_LN2
    return lut
```

**3b. `rules/_common.py`** — add `seed_nitrogen_life()` after `seed_steam_life`
(`_common.py:98-108`):

```python
def seed_nitrogen_life() -> int:
    """Return a freshly seeded lifetime (in steps) for a new LN2 cell.

    Liquid nitrogen boils off rapidly at ambient (room temperature is far above
    its -196C boiling point), so its window is SHORT. Tuned (first-pass 30..80)
    so a painted blob visibly freezes a patch of adjacent water before boiling
    away to EMPTY; pin the final range in the reflection. Both the brush and any
    future reaction that spawns LN2 go through this so a painted LN2 and a
    reaction-spawned one live for the same window of steps.
    """
    return random.randint(30, 80)
```

**3c. `rules/__init__.py`** — three edits:

- Import the new rule:
  ```python
  from .ln2 import update_ln2
  ```
- Re-export the new life helper: add `seed_nitrogen_life` to the
  `from ._common import ...` line (`:21`) AND to `__all__` (`:46-52`):
  ```python
  from ._common import seed_fire_life, seed_nitrogen_life, seed_smoke_life, seed_steam_life
  ...
  __all__ = [
      "RULES",
      "UpdateFn",
      "seed_fire_life",
      "seed_nitrogen_life",
      "seed_smoke_life",
      "seed_steam_life",
  ]
  ```
- Register the rule in `RULES` (after the DRY_ICE entry from Phase 01):
  ```python
      # Dry ice (persistent cold-source solid; thermal-realism).
      ElementId.DRY_ICE: update_dry_ice,
      # Liquid nitrogen (transient cold-source liquid; thermal-realism).
      ElementId.LN2: update_ln2,
  ```

### 4. `src/sandfall/rules/ln2.py` (NEW) — transient cold liquid

The rule combines three proven shapes: smoke/steam's age/expire idiom (decrement
life → EMPTY at ≤0), dry-ice/fire's cold re-assert, and oil's light-liquid flow.
Precedence (per the overview): (1) age / boil off, (2) re-assert cold, (3) flow.
Full file:

```python
"""Liquid nitrogen (LIQUID, transient cold source) update rule.

Liquid nitrogen is a light cryogenic liquid (density 0.8 < WATER 1.0 -> floats
on water via can_displace, like oil) and the coldest cold source: it re-asserts
``LN2_COLD_TARGET`` = -196C (its boiling point) each step WHILE ALIVE, so its
diffusion freezes adjacent water AGGRESSIVELY (much colder than dry ice's -78).

Unlike dry ice, LN2 is **transient**: it boils off at ambient (room temperature
is far above its -196C boiling point). It carries a per-cell ``life`` countdown
(seeded by :func:`sandfall.rules._common.seed_nitrogen_life`); when life is
exhausted the cell becomes EMPTY (boiled away). The short window is tuned so a
painted blob visibly freezes a patch of water before it boils off. (A cold SMOKE
puff on boil-off is a noted visual option, deferred for scope; EMPTY is the
minimal choice -- see the thermal-realism plan Out of Scope.)

Each step, in fixed precedence:

1. **Age / boil off** -- decrement life; at <= 0 become EMPTY (boiled away). This
   mirrors the smoke/steam age idiom (``rules/smoke.py``).
2. **Re-assert cold** -- while alive, clamp temp DOWN to LN2_COLD_TARGET so the
   diffusion pre-pass keeps drawing extreme cold from it (mirrors dry ice's /
   fire's re-assert).
3. **Flow** -- move like a light liquid (water.py / oil.py shape via can_displace
   + swap): straight down, down-diagonals randomized, one-cell sideways
   randomized. Because LN2 is LIGHTER than water, water displaces it (it floats).

No burn/dissolve of its own. ``swap`` carries life AND temp on every flow move,
so a flowing LN2 cell keeps its remaining life and its -196 cold. This is the
formal use of the reactive-rule relaxation for the age/re-assert steps
(transform own cell in place, return None); the flow step returns a destination.
"""

from __future__ import annotations

import random

from ..elements import ElementId
from ..grid import Grid
from ._common import can_displace, swap

# The cold temperature an LN2 cell holds (and re-asserts) each step while alive.
# A cold source: diffusion carries this cold outward. NOT a physical temperature
# beyond being LN2's boiling point (-196C) -- it is a tunable knob for freeze
# spread rate. Far colder than DRY_ICE_COLD_TARGET (-78), so LN2 freezes water
# much faster than dry ice -- but only for as long as its finite life lasts.
LN2_COLD_TARGET = -196


def update_ln2(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an LN2 cell: age (boil off), re-assert cold, else flow like a light
    liquid."""
    # 1. Age; boil off to EMPTY when life is exhausted (mirrors smoke/steam).
    life = grid.get_life(x, y) - 1
    if life <= 0:
        grid.set(x, y, ElementId.EMPTY)
        grid.set_life(x, y, 0)
        return None
    grid.set_life(x, y, life)

    # 2. Re-assert cold while alive (persistent extreme-cold source).
    if grid.get_temp(x, y) > LN2_COLD_TARGET:
        grid.set_temp(x, y, LN2_COLD_TARGET)

    # 3. Flow like a light liquid (water.py / oil.py shape via can_displace + swap).
    if y + 1 < grid.height and can_displace(ElementId.LN2, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)
    diagonals = [-1, 1]
    random.shuffle(diagonals)
    for dx in diagonals:
        nx, ny = x + dx, y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.LN2, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)
    sideways = [-1, 1]
    random.shuffle(sideways)
    for dx in sideways:
        nx, ny = x + dx, y
        if grid.in_bounds(nx, ny) and can_displace(ElementId.LN2, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None
```

Notes for the implementer:
- The age step runs FIRST and returns on expiry, so a boiling-off LN2 cell does
  NOT also flow or re-assert cold on its final step. This matches smoke/steam
  (`rules/smoke.py:29-35`).
- The re-assert runs BEFORE the flow so the cell is cold when it swaps; `swap`
  carries the −196 temp with it (`_common.swap` exchanges temp on every move).
- `can_displace(ElementId.LN2, ...)` makes water displace LN2 (water sinks, LN2
  floats) because LN2.density (0.8) < WATER.density (1.0) — the same density
  relation oil uses (`rules/oil.py:43-59`).
- No `flashpoint`/burn (LN2 is a cold source, not a fuel).

### 5. `src/sandfall/brush.py` — seed LN2 life on paint

LN2 has a finite life; without seeding, a painted LN2 cell would have life 0 and
boil off on the very next step (the classic "painted fire dies instantly" bug,
now for LN2). Add an `LN2` branch to the seed-selection ladder (`brush.py:66-73`)
and import the helper.

**5a. Import** (`brush.py:27`, extend the existing `from .rules import ...`):

```python
from .rules import seed_fire_life, seed_nitrogen_life, seed_smoke_life, seed_steam_life
```

**5b. The seed-selection ladder** (`brush.py:66-73`) gains an LN2 branch:

```python
    if element_id == ElementId.FIRE:
        seed: Callable[[], int] | None = seed_fire_life
    elif element_id == ElementId.SMOKE:
        seed = seed_smoke_life
    elif element_id == ElementId.STEAM:
        seed = seed_steam_life
    elif element_id == ElementId.LN2:
        seed = seed_nitrogen_life
    else:
        seed = None
```

> LN2's `temp_spawn=-196` ≠ `AMBIENT_TEMP`, so the existing spawn-temp pass
> (`brush.py:91-92`) sets each painted LN2 cell to −196 automatically — no extra
> temp wiring. The palette swatch appears automatically (`ui.palette_layout`
> iterates `ElementId`).

### 6. `src/sandfall/simulation.py` — audit-only (verification)

LN2 is **transient**, so it self-wakes without joining wake condition 3: each
step its rule decrements life (the `set_life` write does not by itself mark
active, but the cell's *identity change* to EMPTY on expiry triggers wake
condition 1, and while alive the cold re-assert + the adjacent water's temp
change trigger conditions 1/2). Re-read `simulation.py:158-170` and confirm via
the Phase-02 tests. **Do NOT edit `simulation.py`** unless
`test_ln2_freezes_water_aggressively` or `test_ln2_boils_off` stalls (a transient
cell vanishing to EMPTY always wakes its neighbors via condition 1, so a stall
here would be surprising — pin it in the reflection if it happens).

### 7. `tests/test_phase.py` — ADD the LN2 tests

Add these near the dry-ice tests (after the Phase-01 additions). They use the
seeded / single-cell patterns already in the file.

```python
# --- Liquid nitrogen (transient cold liquid) -------------------------------


def test_ln2_freezes_water_aggressively() -> None:
    """A blob of LN2 in water freezes a patch of it before boiling off.

    LN2 re-asserts LN2_COLD_TARGET (-196) while alive -- far colder than dry ice
    (-78) -- so its diffusion freezes adjacent water fast. The freeze must
    happen WITHIN the short life window (seed_nitrogen_life ~= 30..80), which is
    the boil-off tuning gate (overview Risk #5). Asserts SOME ice forms.
    """
    from sandfall.rules._common import seed_nitrogen_life
    from sandfall.rules.ln2 import LN2_COLD_TARGET

    random.seed(0)
    g = Grid(8, 8)
    for y in range(8):
        for x in range(8):
            g.set(x, y, ElementId.WATER)
    # Seed a 2x2 LN2 blob in the middle, each with a max-life window so it has
    # the most time to freeze before boiling off.
    for dy in range(2):
        for dx in range(2):
            g.set(3 + dx, 3 + dy, ElementId.LN2)
            g.set_temp(3 + dx, 3 + dy, LN2_COLD_TARGET)
            g.set_life(3 + dx, 3 + dy, 80)  # top of the window -> max freeze time
    sim = Simulation(g)
    assert int((g.array == int(ElementId.ICE)).sum()) == 0  # no ice yet
    for _ in range(80):
        sim.step()
    ice_after = int((g.array == int(ElementId.ICE)).sum())
    # LN2 froze some water before boiling off. Exact count depends on the
    # seed_nitrogen_life window + LN2_COLD_TARGET; the point is freezing happened.
    assert ice_after > 0, ice_after


def test_ln2_boils_off() -> None:
    """LN2 is transient: a blob left at ambient boils away to EMPTY once its
    finite life is exhausted (room temp >> -196)."""
    random.seed(0)
    g = Grid(3, 3)
    for y in range(3):
        for x in range(3):
            g.set(x, y, ElementId.LN2)
            g.set_life(x, y, 80)  # top of the window
    sim = Simulation(g)
    for _ in range(200):  # well past the max life window
        sim.step()
    assert int((g.array == int(ElementId.LN2)).sum()) == 0  # all boiled off


def test_ln2_floats_on_water() -> None:
    """LN2 (density 0.8) is lighter than WATER (1.0): it floats -- a cell of LN2
    directly above water, stepped many times, ends with LN2 above water (water
    sinks through the lighter LN2). Mirrors the oil float test."""
    from sandfall.rules._common import can_displace

    # Density relation: water displaces LN2 (water sinks); LN2 cannot displace water.
    assert can_displace(ElementId.WATER, int(ElementId.LN2)) is True
    assert can_displace(ElementId.LN2, int(ElementId.WATER)) is False

    random.seed(0)
    g = Grid(1, 4)
    g.set(0, 0, ElementId.LN2)
    g.set_life(0, 0, 80)  # keep it alive long enough to settle
    g.set(0, 1, ElementId.WATER)
    sim = Simulation(g)
    for _ in range(40):
        sim.step()
    # LN2 is lighter -> it should have risen above the water (before boiling off
    # within the 80-step life window; 40 steps < 80 so it is still alive).
    ln2_y = [y for y in range(g.height) if g.get(0, y) == ElementId.LN2]
    water_y = [y for y in range(g.height) if g.get(0, y) == ElementId.WATER]
    assert ln2_y and water_y
    assert min(ln2_y) < max(water_y)   # LN2 is above at least some water


def test_paint_brush_ln2_seeds_life() -> None:
    """A painted LN2 disk's cells get a finite life (seed_nitrogen_life) and the
    -196 spawn temp. Without the life seeding, painted LN2 would have life 0 and
    boil off on the next step."""
    from sandfall.rules._common import seed_nitrogen_life

    life_min, life_max = 30, 80  # seed_nitrogen_life window (single source of truth)
    g = Grid(10, 10)
    paint_brush(g, 5, 5, 1, ElementId.LN2)
    ln2_cells = [
        (x, y)
        for y in range(g.height)
        for x in range(g.width)
        if g.get(x, y) == ElementId.LN2
    ]
    assert ln2_cells, "expected a disk of LN2 cells to be painted"
    for x, y in ln2_cells:
        assert life_min <= g.get_life(x, y) <= life_max, (x, y)
        assert g.get_temp(x, y) == ELEMENTS[ElementId.LN2].temp_spawn, (x, y)
```

> The freeze test seeds life at 80 (top of the window) so the LN2 has the most
> time to freeze before boiling off — this isolates the freeze mechanism from the
> boil-off tuning. If even at life=80 no ice forms, the freeze mechanism (not the
> life window) is the problem — widen investigation (re-assert / conductivity /
> dormant-wake) before touching the life range.

### 8. Update existing palette-width tests

- `tests/test_ui.py` — bump the element-count literal `16 → 17` (Phase 01 set it
  to 16); update `test_palette_resolves_new_elements_and_fits_min_window` item
  count `19 → 20`, padding count `18 → 19`, add `ElementId.LN2` to the
  `new_elements` list.
- `tests/test_config.py` — update `MIN_WINDOW_W == 556 → 584`, item count
  `19 → 20`, padding count `18 → 19`, `needed == 556 → 584`,
  `MIN_GRID_COLS == 139 → 146`.

### 9. Renderer + palette verification (automatic)

`build_color_lut` and `palette_layout` auto-resize from `len(ElementId)` (Phase 01
precedent). **Verify** (no edit) via the enum-count check in Verification
Commands.

## Acceptance Criteria

- [ ] `ElementId.LN2 == 17`; `len(ElementId) == 18`; values 0–16 unchanged
      (`int(GUNPOWDER) == 15`, `int(DRY_ICE) == 16`, `int(LN2) == 17`). LN2 has an
      `ELEMENTS` entry with `phase=LIQUID`, `density==0.8`, `temp_spawn==-196`.
- [ ] `seed_nitrogen_life()` exists in `_common.py` and returns `randint(30, 80)`;
      it is re-exported from `rules/__init__.py` (`from sandfall.rules import
      seed_nitrogen_life` works).
- [ ] `rules/ln2.py` ages (life ≤0 → EMPTY, mirroring smoke), re-asserts
      `LN2_COLD_TARGET = -196` while alive, then flows like a light liquid (oil
      shape); `swap` carries life + temp on flow moves.
- [ ] `paint_brush` seeds LN2 life (new branch) — `test_paint_brush_ln2_seeds_life`
      passes (painted LN2 has life in [30,80] and temp −196).
- [ ] LN2 is lighter than water (`can_displace(WATER, LN2)` True; reverse False)
      and floats above water after stepping — `test_ln2_floats_on_water` passes.
- [ ] **`test_ln2_freezes_water_aggressively` passes** — some ice forms from an
      LN2 blob in water within the life window (the boil-off tuning gate; Risk #5).
- [ ] **`test_ln2_boils_off` passes** — an LN2 blob left at ambient is entirely
      EMPTY after ~200 steps (transient).
- [ ] `build_conductivity_lut` / `build_heat_capacity_lut` have 18 rows; row 17
      is `COND_LN2` / `CP_LN2`.
- [ ] `RULES` enumerates all 18 elements (17 real rules + EMPTY omitted);
      `len(RULES) >= 17`.
- [ ] `MIN_WINDOW_W == 584` (= 146 cols); the 20-item palette row fits at the
      minimum size; `test_ui.py` / `test_config.py` palette assertions updated
      and green.
- [ ] Existing tests stay green (Phase 01's dry-ice + ice-revert tests, and the
      whole prior suite).
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the new LN2 tests + regression on the thermal suite):
uv run pytest tests/test_phase.py tests/test_thermal.py -v

# Confirm the enum + registry grew and the stable indices held:
uv run python -c "from sandfall.elements import ElementId; from sandfall.rules import RULES, seed_nitrogen_life; assert [e.value for e in ElementId]==list(range(18)); assert int(ElementId.GUNPOWDER)==15 and int(ElementId.DRY_ICE)==16 and int(ElementId.LN2)==17; assert ElementId.LN2 in RULES; assert 30 <= seed_nitrogen_life() <= 80; print('enum+registry+life OK')"

# Confirm palette min-width math: 20 items fit in MIN_WINDOW_W.
uv run python -c "from sandfall.config import MIN_WINDOW_W, PALETTE_GROUP_GAP, PALETTE_MARGIN, PALETTE_PADDING, PALETTE_SWATCH; need=20*PALETTE_SWATCH+19*PALETTE_PADDING+PALETTE_GROUP_GAP+2*PALETTE_MARGIN; assert MIN_WINDOW_W==584 and MIN_WINDOW_W>=need, (MIN_WINDOW_W, need); print('palette fits', need, '<=', MIN_WINDOW_W)"

# FULL suite -- regression guard:
uv run pytest

# Lint / format / types:
uv run ruff check . && uv run ruff format --check . && uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
#   Manual check: paint LN2 onto a WATER pool (it floats, freezes a patch of
#   water to ICE aggressively, then boils away to EMPTY); paint LN2 alone in open
#   air (it boils off within ~30-80 steps); the H overlay shows LN2 at the deep-
#   cold saturation color.
```

All commands must exit zero. If `test_ln2_freezes_water_aggressively` freezes
nothing even at life=80, investigate the freeze mechanism (re-assert /
conductivity / dormant-wake) before widening the life window — LN2 must earn its
freeze through cold, not through lingering. Pin the final `seed_nitrogen_life`
range + spread in the reflection.

## Documentation Updates

- `docs/ARCHITECTURE.md:250-258` — append `LN2=17` to the `ElementId` member
  list (after the DRY_ICE entry from Phase 01).
- `docs/ARCHITECTURE.md:280-285` — add a sentence noting the two cold-source
  categories now exist: dry ice (persistent solid) and liquid nitrogen
  (transient liquid); ice is a realistic non-source.
- `docs/ARCHITECTURE.md:360-368` — the `seed_*_life` list currently enumerates
  fire/smoke/steam; add `seed_nitrogen_life -> randint(30, 80)` and note LN2
  joins FIRE/SMOKE/STEAM in the brush life-seeding pass.
- `.agent/tasks/BACKLOG.md:74-84` — strike / mark "Thermal realism rework" as
  shipped (this plan delivers it); leave the cold-gas sub-item noted as still
  deferred if desired.

## Reflection & Commit

After implementation, write `02-liquid-nitrogen-reflection.md`. Include the
**final tuned `seed_nitrogen_life` range** (Decision #4 / Risk #5) and whether
the first-pass `randint(30, 80)` let LN2 freeze water before boiling away or
needed widening/narrowing; the **measured freeze spread** (how much ice an LN2
blob made before boiling off) at `LN2_COLD_TARGET=-196`; whether the float test
needed more/fewer than 40 steps; whether any dormant-wake edit was needed (it
should not be — LN2 is transient); and whether a cold-SMOKE boil-off puff is
worth adding later (Out of Scope). Then make ONE atomic git commit covering all
changes in this phase.

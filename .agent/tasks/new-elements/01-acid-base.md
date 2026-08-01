# Phase 01: Acid + Base (the dissolving pair)

## Objective

Add two new dense, reactive liquids — `ElementId.ACID = 12` and
`ElementId.BASE = 13` — that **dissolve** neighboring materials (consumed-on-
dissolve, Powder Toy model), **neutralize** each other into water, **dilute**
probabilistically in water, and **burn** (flashpoint → FIRE) when heated. Acid
resists glass; base resists stone (a deliberate mirror). Extend the thermal LUTs
and recompute `MIN_WINDOW_W` for the wider 16-item palette. Existing v1 +
temperature elements (0–11) are unchanged.

> **Re-read before editing** (line numbers below are current as of the
> post-`thermal-float-ice` source and WILL shift): `src/sandfall/elements.py`,
> `src/sandfall/config.py`, `src/sandfall/thermal.py`, `src/sandfall/rules/
> __init__.py`, `src/sandfall/rules/water.py`, `src/sandfall/rules/lava.py`,
> `src/sandfall/rules/wood.py`, `src/sandfall/rules/_common.py`,
> `src/sandfall/simulation.py`, `tests/test_phase.py`, `tests/test_ui.py`,
> `tests/test_config.py`, and `docs/ARCHITECTURE.md:509-544`.

## Depends On

none — builds on the completed temperature + dormant-cell features (the reactive-
rule contract, the `flashpoint` ignition path, density-based `can_displace`, the
thermal LUT builders, and the dormant wake conditions are all in place).

## Can Parallelize With

none — Phase 02 (oil) depends on this phase's enum growth and its tests assert
acid-dissolves-oil.

## Recommended Agent

@implementer — largest surface area of the plan: 2 enum members, 2 ELEMENTS
entries, 2 new rule files each with a 5-step precedence + resist sets + module
constants, a cross-rule neutralization (side-effect write), the thermal LUT
rows, a `MIN_WINDOW_W` recompute, existing-test updates, and a new test file
covering 7+ behaviors. Read carefully; the precedence order (Decision #9) and
the idempotent neutralization (Decision #5) are the correctness cruxes.

## Changes Required

- `src/sandfall/elements.py` — add `ACID = 12`, `BASE = 13` to `ElementId`
  (12 → 14 members); add 2 `ELEMENTS` entries with LIQUID/density/thermal fields
  + colors.
- `src/sandfall/config.py` — add `COND_ACID`, `COND_BASE`, `CP_ACID`, `CP_BASE`;
  **recompute `MIN_WINDOW_W`** for 16 palette items (→ 472).
- `src/sandfall/thermal.py` — add rows 12–13 to `build_conductivity_lut` and
  `build_heat_capacity_lut`; import the 4 new config constants.
- `src/sandfall/rules/acid.py` (NEW) — 5-step precedence rule + module constants
  + acid resist frozenset.
- `src/sandfall/rules/base.py` (NEW) — mirror of `acid.py` with the base resist
  frozenset.
- `src/sandfall/rules/__init__.py` — import + register the 2 new rules in
  `RULES`.
- `tests/test_acid_base.py` (NEW) — dissolve (per material) / glass survives /
  neutralize / dilute / burn / consumed / smoke, + dormant-wall integration.
- `tests/test_ui.py` — update the palette-count assertion (`11 → 13`) and the
  min-window math test (`14 → 16` items).
- `tests/test_config.py` — update the min-window test (`MIN_WINDOW_W 416 → 472`,
  `14 → 16` items).
- `docs/ARCHITECTURE.md` — extend the `ElementId` member list + the "Adding a new
  element" recipe (dissolve-resist obligation note).
- `.agent/tasks/BACKLOG.md` — strike "acid" from the "More elements" line.

## Implementation Instructions

### 1. `src/sandfall/elements.py`

**1a. Add the enum members** after `GLASS = 11` (`elements.py:46`):

```python
    GLASS = 11
    # --- New elements (acid/base pair) ---
    ACID = 12
    BASE = 13
```

> Existing values 0–11 are unchanged, so every LUT index is stable. The enum
> docstring (`elements.py:22-33`) says members were "Extended in Phase 03 ...
> 8..11"; append a sentence noting this feature extends to ACID/BASE (12..13),
> same "supported operation" status as `ARCHITECTURE.md:513-518` already grants.

**1b. Add the 2 `ELEMENTS` entries** after the GLASS entry (`elements.py:229-238`).
Use these first-pass values (Decision #12 — tune in the reflection):

```python
    # --- Acid + Base (dense reactive liquids; consumed-on-dissolve) ---------
    # Both are LIQUID (density 1.2, denser than WATER 1.0 -> sink through water).
    # flashpoint ~200 -> burn to FIRE when heated by lava/fire (thermal path);
    # burn_temp ~600 documents the fuel character (active heat comes from the
    # FIRE rule, same as WOOD/PLANT). The dissolve/neutralize/dilute logic lives
    # entirely in rules/acid.py + rules/base.py (no Element fields for it).
    ElementId.ACID: Element(
        id=ElementId.ACID,
        name="acid",
        color=(110, 220, 70),       # bright acid green
        density=1.2,
        phase=Phase.LIQUID,
        conductivity=0.30,
        heat_capacity=2.0,
        flashpoint=200,
        burn_temp=600,
    ),
    ElementId.BASE: Element(
        id=ElementId.BASE,
        name="base",
        color=(180, 90, 200),       # violet (alkali)
        density=1.2,
        phase=Phase.LIQUID,
        conductivity=0.30,
        heat_capacity=2.0,
        flashpoint=200,
        burn_temp=600,
    ),
```

### 2. `src/sandfall/config.py`

**2a. Add the conductivity + heat-capacity constants** alongside the Phase-03
block (`config.py:123-127` for `COND_*`, `config.py:142-146` for `CP_*`):

```python
# New reactive liquids (acid/base pair).
COND_ACID = 0.30
COND_BASE = 0.30
...
CP_ACID = 2.0
CP_BASE = 2.0
```

> Stability check (`config.py:104-107`): the new conductivities (0.30) are below
> FIRE (0.50) and the new heat-capacities (2.0) are above the min (0.5), so
> `0.20 * 0.50 / 0.5 == 0.20 <= 0.25` is unchanged. No tunable bump needed.

**2b. Recompute `MIN_WINDOW_W`** for the 16-item palette (13 elements + Eraser +
Brush-shape + Magnifier). Update the comment at `config.py:71-79` to show the new
math:

```
# Minimum window size. Width must fit the whole palette (16 items: 13 element
# swatches + Eraser + Brush-shape + Magnifier). Width math:
#   16 * PALETTE_SWATCH + 15 * PALETTE_PADDING + PALETTE_GROUP_GAP + 2 * PALETTE_MARGIN
#   = 16*24 + 15*4 + 12 + 2*8 = 384 + 60 + 12 + 16 = 472  (== 118 * CELL_SIZE)
# 472 is the next clean CELL_SIZE multiple above the needed 472, = 118 cols.
```

Set `MIN_WINDOW_W = 472` (`config.py:80`). `MIN_GRID_COLS` recomputes
automatically (`config.py:82`) → 118. Leave `MIN_WINDOW_H`/`MIN_GRID_ROWS`
unchanged.

### 3. `src/sandfall/thermal.py`

**3a.** Import the 4 new constants in the `from .config import (...)` block
(`thermal.py:17-47`): add `COND_ACID`, `COND_BASE`, `CP_ACID`, `CP_BASE`.

**3b.** Extend `build_conductivity_lut` (`thermal.py:51-74`) with rows 12–13
(after the GLASS row, `thermal.py:73`):

```python
    lut[int(ElementId.GLASS)] = COND_GLASS
    # New reactive liquids.
    lut[int(ElementId.ACID)] = COND_ACID
    lut[int(ElementId.BASE)] = COND_BASE
    return lut
```

**3c.** Mirror in `build_heat_capacity_lut` (`thermal.py:77-99`, after
`thermal.py:98`):

```python
    lut[int(ElementId.GLASS)] = CP_GLASS
    lut[int(ElementId.ACID)] = CP_ACID
    lut[int(ElementId.BASE)] = CP_BASE
    return lut
```

> Both LUTs size from `len(ElementId)` (`thermal.py:60`, `thermal.py:85`), so
> they grow 12 → 14 rows automatically; the explicit row writes fill the new
> slots (otherwise they'd default to 0.0, which for cp would divide-by-zero in
> diffusion — `thermal.py:157`).

### 4. `src/sandfall/rules/acid.py` (NEW)

Mirror `lava.py`'s structure (reactive neighbor side-effect + module constant +
liquid flow). Module-level constants + resist set at top, then the 5-step
precedence function. Full skeleton:

```python
"""Acid (LIQUID, dense, consumed-on-dissolve) update rule.

Acid is a dense liquid (density 1.2, denser than WATER 1.0 -> sinks through
water) that DISSOLVES adjacent materials (Powder Toy's consumed-on-dissolve
model). Each step, in fixed precedence:

1. **Burn** -- if the cell's own temp exceeds its flashpoint, become FIRE (seed
   life, set burn-temp). Mirrors wood/plant reactive ignition.
2. **Neutralize** -- if any orthogonal neighbor is BASE, BOTH this cell and
   that neighbor become WATER (a side-effect write on the neighbor, like the
   LAVA+WATER reaction). Idempotent: setting WATER on already-WATER is harmless,
   so the randomized scan order does not matter.
3. **Dilute** -- if any orthogonal neighbor is WATER, with per-step chance
   DILUTE_CHANCE become WATER itself. If it does NOT dilute, fall through to
   dissolve/flow (so acid still sinks through water).
4. **Dissolve** -- with per-step chance DISSOLVE_CHANCE, eat ONE adjacent
   dissolvable neighbor: the target becomes EMPTY (or, with chance
   DISSOLVE_SMOKE_CHANCE, SMOKE seeded via seed_smoke_life for visual feedback),
   and the acid cell itself becomes EMPTY (consumed). Acid dissolves everything
   EXCEPT the ACID_RESIST set (glass resists acid -> glass containers hold it).
5. **Flow** -- otherwise move like a dense liquid (water.py shape: straight
   down, down-diagonals randomized, one-cell sideways randomized) via
   can_displace + swap.

Because dissolve consumes the acid cell (id-changed) every time it fires, the
dormant-cell wake condition (id_changed | moved, dilated) keeps the front
alive without ACID joining the FIRE/LAVA persistent-source wake. See the master
plan Risks #1.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import can_displace, seed_fire_life, seed_smoke_life, swap

# Tunables (first-pass values; pin final tuned values in the reflection).
DISSOLVE_CHANCE = 0.5        # per-step chance to eat one dissolvable neighbor
DILUTE_CHANCE = 0.08         # per-step chance to dilute into adjacent water
DISSOLVE_SMOKE_CHANCE = 0.10 # chance a dissolved target emits SMOKE (else EMPTY)

# Acid does NOT dissolve these (glass resists acid; the rest are the special
# non-dissolve cases). A neighbor is dissolvable iff grid.get != EMPTY and not
# in this set. EMPTY is included so the single `not in` test suffices.
ACID_RESIST: frozenset[int] = frozenset(
    int(e)
    for e in (
        ElementId.EMPTY, ElementId.GLASS,
        ElementId.ACID, ElementId.BASE,
        ElementId.WATER, ElementId.LAVA, ElementId.FIRE,
        ElementId.SMOKE, ElementId.STEAM,
    )
)

_ELM = ELEMENTS[ElementId.ACID]
_FIRE = ELEMENTS[ElementId.FIRE]

# Orthogonal 4-neighborhood (matches lava.py / fire.py / the diffusion pass).
_NEIGHBORS_4: tuple[tuple[int, int], ...] = ((0, -1), (0, 1), (-1, 0), (1, 0))


def update_acid(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an acid cell: burn, else neutralize, else dilute, else dissolve,
    else flow like a dense liquid."""
    # 1. Burn: own temp above flashpoint -> FIRE.
    if _ELM.flashpoint > 0 and grid.get_temp(x, y) > _ELM.flashpoint:
        grid.set(x, y, ElementId.FIRE)
        grid.set_life(x, y, seed_fire_life())
        grid.set_temp(x, y, _FIRE.burn_temp)
        return None

    # Scan the 4-neighborhood once for the reactive checks.
    for dx, dy in _NEIGHBORS_4:
        nx, ny = x + dx, y + dy
        if not grid.in_bounds(nx, ny):
            continue
        nb = grid.get(nx, ny)

        # 2. Neutralize: acid adjacent to BASE -> BOTH become WATER (side-effect
        #    write on the neighbor, idempotent across scan orders).
        if nb == ElementId.BASE:
            grid.set(x, y, ElementId.WATER)
            grid.set(nx, ny, ElementId.WATER)
            return None

        # 3. Dilute: acid adjacent to WATER -> probabilistically become WATER.
        #    (If it does not dilute, keep scanning; the dissolve/flow steps
        #    still run so it sinks through water.)
        if nb == ElementId.WATER and random.random() < DILUTE_CHANCE:
            grid.set(x, y, ElementId.WATER)
            return None

    # 4. Dissolve: with DISSOLVE_CHANCE, eat ONE dissolvable neighbor (consumed).
    if random.random() < DISSOLVE_CHANCE:
        targets = [
            (x + dx, y + dy)
            for dx, dy in _NEIGHBORS_4
            if grid.in_bounds(x + dx, y + dy)
            and grid.get(x + dx, y + dy) not in ACID_RESIST
        ]
        if targets:
            tx, ty = random.choice(targets)
            if random.random() < DISSOLVE_SMOKE_CHANCE:
                grid.set(tx, ty, ElementId.SMOKE)
                grid.set_life(tx, ty, seed_smoke_life())
            else:
                grid.set(tx, ty, ElementId.EMPTY)
            # Acid itself is consumed.
            grid.set(x, y, ElementId.EMPTY)
            return None

    # 5. Flow like a dense liquid (water.py shape via can_displace + swap).
    if y + 1 < grid.height and can_displace(ElementId.ACID, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)
    diagonals = [-1, 1]
    random.shuffle(diagonals)
    for dx in diagonals:
        nx, ny = x + dx, y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.ACID, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)
    sideways = [-1, 1]
    random.shuffle(sideways)
    for dx in sideways:
        nx, ny = x + dx, y
        if grid.in_bounds(nx, ny) and can_displace(ElementId.ACID, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None
```

> **Note on the dilute/dissolve scan.** The neutralize+ dilute loop reads the
> neighborhood once; dilute fires on the FIRST water neighbor it finds (a cell
> with one water neighbor dilutes the same as one with four — only one acid cell
> is consumed either way). This matches "dilute once per step". If you prefer to
> collect all water neighbors first, that is equivalent for the consumed-once
> contract — pin the choice in the reflection.

### 5. `src/sandfall/rules/base.py` (NEW)

Identical to `acid.py` with two substitutions:
- The `BASE_RESIST` frozenset swaps `GLASS` for `STONE` (base resists stone;
  base dissolves glass):

  ```python
  BASE_RESIST: frozenset[int] = frozenset(
      int(e)
      for e in (
          ElementId.EMPTY, ElementId.STONE,
          ElementId.ACID, ElementId.BASE,
          ElementId.WATER, ElementId.LAVA, ElementId.FIRE,
          ElementId.SMOKE, ElementId.STEAM,
      )
  )
  ```
- The neutralize check looks for `ElementId.ACID` (instead of BASE): `if nb ==
  ElementId.ACID: grid.set(x,y,WATER); grid.set(nx,ny,WATER); return None`.
- Module constants `DISSOLVE_CHANCE` / `DILUTE_CHANCE` / `DISSOLVE_SMOKE_CHANCE`
  are declared on `base.py` too (mirror `LAVA_SOLIDIFY_TEMP` per Decision "each
  rule file"); use the same first-pass values. `_ELM = ELEMENTS[ElementId.BASE]`.
- The flow step passes `ElementId.BASE` to `can_displace`.

Everything else (precedence, docstring structure, the flow shape) is byte-for-
byte the same as `acid.py`. The idempotent neutralization (both rules set BOTH
cells to WATER) is what makes the scan order irrelevant (Decision #5).

### 6. `src/sandfall/rules/__init__.py`

**6a.** Import the two new rules (`rules/__init__.py:22-32`):

```python
from .acid import update_acid
from .base import update_base
```

**6b.** Register them in `RULES` (`rules/__init__.py:50-63`):

```python
RULES: dict[ElementId, UpdateFn] = {
    ...,
    ElementId.GLASS: update_glass,
    # New reactive liquids.
    ElementId.ACID: update_acid,
    ElementId.BASE: update_base,
}
```

> ACID/BASE have no finite life (they are consumed, not expired), so they need
> NO `seed_*_life` helper and NO brush life-seeding change (`brush.py:66-73` only
> seeds FIRE/SMOKE/STEAM). Their `temp_spawn` defaults to `AMBIENT_TEMP`, so
> `paint_brush` needs no spawn-temp change either. The palette swatches appear
> automatically (`ui.palette_layout` iterates `ElementId`, `ui.py:135-147`).

### 7. Renderer + palette verification (automatic — verify, do not edit)

- **Renderer LUT.** `build_color_lut` sizes from `len(ElementId)`
  (`renderer.py:37`) and iterates `ELEMENTS` (`renderer.py:39-42`), so the 2 new
  colors appear automatically. **Verify** (no edit) via a LUT-shape assertion in
  the new test file: `build_color_lut().shape == (14, 3)`.
- **Palette.** `palette_layout` iterates `ElementId` (`ui.py:135-147`), so the 2
  new swatches appear automatically. The `MIN_WINDOW_W` bump from 2b keeps them
  on-screen at the minimum size.

### 8. `tests/test_acid_base.py` (NEW)

Deterministic tests using the seeded / single-cell / monkeypatch patterns from
`tests/test_phase.py:41-52`. Monkeypatch the module constants for probabilistic
behaviors (they are module globals read at call time, like `fire.py:96`
`SMOKE_CHANCE`):

```python
import random
from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.renderer import build_color_lut
from sandfall.simulation import Simulation
from sandfall.rules._common import can_displace


def _step_single_cell(eid, temp):
    g = Grid(1, 1); g.set(0, 0, eid); g.set_temp(0, 0, temp)
    Simulation(g).step(); return g


# --- dissolve (monkeypatch DISSOLVE_CHANCE=1.0, DISSOLVE_SMOKE_CHANCE=0.0) ---
def test_acid_dissolves_sand(monkeypatch):
    import sandfall.rules.acid as acid
    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1); g.set(0, 0, ElementId.ACID); g.set(1, 0, ElementId.SAND)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY        # sand eaten
    assert g.get(0, 0) == ElementId.EMPTY        # acid consumed

# ... repeat for STONE, WOOD, PLANT, ICE (all in acid's dissolvable set).
# And the glass-survives case:
def test_acid_does_not_dissolve_glass(monkeypatch):
    import sandfall.rules.acid as acid
    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    g = Grid(2, 1); g.set(0, 0, ElementId.ACID); g.set(1, 0, ElementId.GLASS)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.GLASS        # glass survives

# base mirror: base dissolves glass, NOT stone
def test_base_dissolves_glass(monkeypatch):
    import sandfall.rules.base as base
    monkeypatch.setattr(base, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(base, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1); g.set(0, 0, ElementId.BASE); g.set(1, 0, ElementId.GLASS)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY
    assert g.get(0, 0) == ElementId.EMPTY

def test_base_does_not_dissolve_stone(monkeypatch):
    import sandfall.rules.base as base
    monkeypatch.setattr(base, "DISSOLVE_CHANCE", 1.0)
    g = Grid(2, 1); g.set(0, 0, ElementId.BASE); g.set(1, 0, ElementId.STONE)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.STONE


# --- neutralize (deterministic across scan orders) ---
def test_acid_base_neutralize_both_become_water():
    for i in range(20):
        random.seed(i)
        g = Grid(2, 1); g.set(0, 0, ElementId.ACID); g.set(1, 0, ElementId.BASE)
        Simulation(g).step()
        assert g.get(0, 0) == ElementId.WATER, f"seed={i}"
        assert g.get(1, 0) == ElementId.WATER, f"seed={i}"


# --- dilute (monkeypatch DILUTE_CHANCE=1.0) ---
def test_acid_dilutes_into_water(monkeypatch):
    import sandfall.rules.acid as acid
    monkeypatch.setattr(acid, "DILUTE_CHANCE", 1.0)
    g = Grid(2, 1); g.set(0, 0, ElementId.ACID); g.set(1, 0, ElementId.WATER)
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.WATER


# --- burn (flashpoint -> FIRE; single cell, diffusion no-op on 1x1) ---
def test_acid_ignites_to_fire_when_hot():
    g = _step_single_cell(ElementId.ACID, ELEMENTS[ElementId.ACID].flashpoint + 50)
    assert g.get(0, 0) == ElementId.FIRE


# --- smoke on dissolve (monkeypatch DISSOLVE_SMOKE_CHANCE=1.0) ---
def test_dissolve_emits_smoke(monkeypatch):
    import sandfall.rules.acid as acid
    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 1.0)
    g = Grid(2, 1); g.set(0, 0, ElementId.ACID); g.set(1, 0, ElementId.SAND)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.SMOKE        # sand -> smoke
    assert g.get(0, 0) == ElementId.EMPTY        # acid consumed


# --- density (acid sinks through water) ---
def test_acid_is_denser_than_water():
    assert can_displace(ElementId.ACID, int(ElementId.WATER)) is True
    assert can_displace(ElementId.WATER, int(ElementId.ACID)) is False


# --- dormant interaction: acid eats through a wall (Risks #1) ---
def test_acid_eats_through_sand_wall():
    """A column of acid dropped onto a sand wall dissolves through it over many
    steps. Guards the dormant-wake sufficiency finding (consumed-on-dissolve
    keeps the front alive without ACID joining the FIRE/LAVA wake)."""
    random.seed(0)
    g = Grid(3, 8)
    # A 4-row sand wall at the bottom.
    for y in range(4, 8):
        for x in range(3):
            g.set(x, y, ElementId.SAND)
    # A column of acid above it.
    for y in range(4):
        g.set(1, y, ElementId.ACID)
    sim = Simulation(g)
    sand_before = int((g.array == int(ElementId.SAND)).sum())
    for _ in range(200):
        sim.step()
    sand_after = int((g.array == int(ElementId.SAND)).sum())
    assert sand_after < sand_before, (sand_before, sand_after)


# --- renderer LUT grew ---
def test_color_lut_has_14_rows():
    assert build_color_lut().shape == (14, 3)
```

> The dissolve/neutralize/dilute tests use `Grid(2, 1)` so the two cells are
> orthogonally adjacent (acid's 4-neighborhood sees the neighbor). On such a tiny
> grid, set both cells before constructing `Simulation` so the `__init__`
> bootstrap (`simulation.py:100`) seeds both as active. The `random.seed` loop on
> neutralize verifies both scan orders (Risk #3).

### 9. Update existing tests for the wider palette

- `tests/test_ui.py:35` — `test_palette_layout_has_11_elements_then_3_tools`
  hardcodes `len(elements) == len(ElementId) - 1 == 11`. Update the literal `11`
  → `13` (the test name + the `== len(ElementId) - 1` half auto-adjust). Rename
  the test to reflect 13 elements if the name reads wrong.
- `tests/test_ui.py:198-238` —
  `test_palette_resolves_phase03_elements_and_fits_min_window` hardcodes the
  `14 * PALETTE_SWATCH + 13 * PALETTE_PADDING + ...` math and asserts it fits
  `MIN_WINDOW_W`. Update the item count `14 → 16` and the padding count `13 →
  15`, and add ACID/BASE to the `new_elements` resolution check. The
  `last.x + last.w + PALETTE_MARGIN <= MIN_WINDOW_W` assertion must still hold.
- `tests/test_config.py:93-122` —
  `test_min_window_width_fits_full_palette_with_group_gap` hardcodes
  `MIN_WINDOW_W == 416` and the 14-item math. Update to `MIN_WINDOW_W == 472`,
  item count `14 → 16`, padding count `13 → 15`, and `MIN_GRID_COLS == 118`.

## Acceptance Criteria

- [ ] `ElementId` has 14 members (0–13); values 0–11 are unchanged
      (`int(SAND)==1`, `int(GLASS)==11`); ACID=12, BASE=13.
- [ ] Both have `ELEMENTS` entries with `phase=LIQUID`, `density==1.2`,
      `flashpoint==200`, `burn_temp==600`, sensible `conductivity`/`heat_capacity`
      + colors; `len(ELEMENTS) == 14`.
- [ ] Acid dissolves SAND/STONE/WOOD/PLANT/ICE (target→EMPTY, acid→EMPTY
      consumed) but NOT GLASS (glass survives) — deterministic tests pass.
- [ ] Base dissolves GLASS (and the other materials) but NOT STONE — tests pass.
- [ ] Acid adjacent to BASE → BOTH become WATER, for any seed / scan order (the
      20-seed neutralize test passes).
- [ ] Acid adjacent to WATER dilutes to WATER at `DILUTE_CHANCE==1.0` (deterministic
      test passes); acid ignites to FIRE above flashpoint (single-cell test passes);
      dissolve emits SMOKE at `DISSOLVE_SMOKE_CHANCE==1.0` (test passes).
- [ ] Acid is denser than water (`can_displace(ACID, WATER)` True, the reverse
      False) — density test passes.
- [ ] **Dormant interaction**: a column of acid eats through a sand wall over
      many steps (sand count strictly decreases) — integration test passes
      (Risks #1 verified; no `simulation.py` wake-condition edit was needed).
- [ ] `RULES` registry enumerates all 14 elements (13 real rules + EMPTY
      omitted); `len(RULES) >= 13`.
- [ ] `build_color_lut().shape == (14, 3)`; palette has 13 element swatches + 3
      tools; `MIN_WINDOW_W == 472` and the 16-item row fits at the minimum size.
- [ ] Existing `test_ui.py` / `test_config.py` palette-count + min-width
      assertions updated and green.
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused new tests:
uv run pytest tests/test_acid_base.py -v

# Confirm the enum + registry grew and the stable indices held:
uv run python -c "from sandfall.elements import ElementId; from sandfall.rules import RULES; assert [e.value for e in ElementId]==list(range(14)); assert int(ElementId.SAND)==1 and int(ElementId.GLASS)==11 and int(ElementId.ACID)==12 and int(ElementId.BASE)==13; print('enum+registry OK')"

# Confirm palette min-width math: 16 items fit in MIN_WINDOW_W.
uv run python -c "from sandfall.config import MIN_WINDOW_W, PALETTE_GROUP_GAP, PALETTE_MARGIN, PALETTE_PADDING, PALETTE_SWATCH; need=16*PALETTE_SWATCH+15*PALETTE_PADDING+PALETTE_GROUP_GAP+2*PALETTE_MARGIN; assert MIN_WINDOW_W==472 and MIN_WINDOW_W>=need, (MIN_WINDOW_W, need); print('palette fits', need, '<=', MIN_WINDOW_W)"

# The six gates (all must exit zero):
uv run python -c "import sandfall"
uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
#   Manual check on DISPLAY=:1: paint ACID onto a SAND wall (it eats through),
#   paint ACID next to BASE (both -> water), drop ACID through WATER (sinks +
#   slowly dilutes), heat ACID with LAVA (ignites to FIRE), hold ACID in a
#   GLASS cup (survives).
```

All commands must exit zero. Do NOT proceed to Phase 02 until all pass.

## Documentation Updates

- `docs/ARCHITECTURE.md:250-256` — append `ACID=12, BASE=13` to the `ElementId`
  member list.
- `docs/ARCHITECTURE.md:509-544` — extend the "Adding a new element" recipe with
  a note on the **dissolve-resist obligation**: when adding a future element,
  decide per-element whether acid/base dissolves it and add it to (or omit it
  from) the `ACID_RESIST` / `BASE_RESIST` frozensets in `rules/acid.py` /
  `rules/base.py`.
- `.agent/tasks/BACKLOG.md:30-31` — strike "acid" from the "More elements" line
  (leave salt/metal/gunpowder/electricity).

## Reflection & Commit

After implementation, write `01-acid-base-reflection.md`. Include the **final
tuned values** for `DISSOLVE_CHANCE` / `DILUTE_CHANCE` / `DISSOLVE_SMOKE_CHANCE`
/ flashpoint / density (Decision #12), the **dormant-interaction finding**
(did the wall-eat test pass without a wake-condition edit? — Risk #1), whether
the dilute step scans the whole neighborhood or fires on the first water
neighbor, and whether ignition used `_FIRE.burn_temp` or the element's own
(Risk #6). Then make ONE atomic git commit covering all changes in this phase.

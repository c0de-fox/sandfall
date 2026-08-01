# Phase 01: Revert ice to realistic + add dry ice

## Objective

Land two coupled changes as one atomic unit so there is never a window with no
way to freeze water: (a) **revert `update_ice` to a realistic non-source
"frozen water"** — restore the thermal melt (`> melt_point → WATER`), delete the
`ICE_COLD_TARGET` re-assert, stop seeding new ice cold in the water freeze
branch, set `ICE.temp_spawn = 0`; and (b) **add `ElementId.DRY_ICE = 16`**, a
SOLID persistent cold source that re-asserts `DRY_ICE_COLD_TARGET = -78` (the
exact mechanism being retired from ice, just colder and named realistically),
freezing adjacent water via diffusion and sublimating only via direct fire/lava
contact. Extend the thermal LUTs and recompute `MIN_WINDOW_W` for the 19-item
palette.

> **Re-read before editing** (line numbers below are current as of the
> gunpowder-complete source and WILL shift): `src/sandfall/rules/ice.py`,
> `src/sandfall/rules/water.py`, `src/sandfall/rules/_common.py` (the
> `seed_smoke_life` helper dry ice imports), `src/sandfall/elements.py`,
> `src/sandfall/config.py`, `src/sandfall/thermal.py`,
> `src/sandfall/rules/__init__.py`, `src/sandfall/simulation.py:158-170`
> (wake conditions — audit only), `tests/test_phase.py`, `tests/test_ui.py`,
> `tests/test_config.py`, and `docs/ARCHITECTURE.md:250-285,511-553`.

## Depends On

none — builds on the completed temperature feature (float temps, the
conservative diffusion, the reactive-rule contract, the interim persistent-
cold-source ice whose mechanism dry ice inherits).

## Can Parallelize With

none — Phase 02 (liquid nitrogen) depends on this phase's enum growth
(15→16) and its tests assert LN2 floats on water (needs the LIQUID pattern
confirmed alongside dry ice). The ice revert is inside THIS phase so it lands
with dry ice.

## Recommended Agent

@implementer — a focused rule rewrite (ice revert), a new sibling rule file
(`dry_ice.py`, lifting the interim-ice shape), the enum/ELEMENTS/LUT/config/
registry growth, two test reworks + two new tests, and a dormant-wake
*verification* (the unknown is whether the existing wake conditions keep a
dry-ice freeze spreading without adding DRY_ICE to condition 3 — the
`test_dry_ice_freezes_water` integration test is the gate). Read `00-overview.md`
first (Decision Log #2-#9, Risks #1-#4), then re-read every file cited above
before editing.

## Changes Required

- `src/sandfall/rules/ice.py` — **full rewrite**: delete `ICE_COLD_TARGET` and
  the re-assert; restore the thermal melt (`get_temp > melt_point → WATER`); keep
  the direct fire/lava contact melt (LAVA→STEAM, FIRE→WATER); rewrite the module
  docstring (interim cold source → realistic frozen water).
- `src/sandfall/rules/water.py` — freeze branch (`:62-65`) stops seeding the new
  ice cold: drop the `grid.set_temp(x, y, ICE_COLD_TARGET)` write (`:64`) and the
  `from .ice import ICE_COLD_TARGET` import (`:33`); the new ice keeps the
  water's already-≤0 temp.
- `src/sandfall/elements.py` — `ICE.temp_spawn`: −5 → **0** (`:238`); add
  `DRY_ICE = 16` to `ElementId` (after `GUNPOWDER = 15`, `:71`); add an
  `ELEMENTS` entry for DRY_ICE (SOLID, density 1.0, cond 0.20, cp 2.0,
  `temp_spawn=-78`, pale color).
- `src/sandfall/config.py` — add `COND_DRY_ICE = 0.20`, `CP_DRY_ICE = 2.0`;
  **recompute `MIN_WINDOW_W`** for the 19-item palette (→ 556 = 139 cols).
- `src/sandfall/thermal.py` — add row 16 (DRY_ICE) to both LUT builders; import
  `COND_DRY_ICE`, `CP_DRY_ICE`.
- `src/sandfall/rules/dry_ice.py` (NEW) — persistent-cold-source rule mirroring
  the *current* `ice.py` (re-assert `DRY_ICE_COLD_TARGET = -78`; sublimate via
  direct fire/lava contact: FIRE→EMPTY, LAVA→SMOKE).
- `src/sandfall/rules/__init__.py` — import + register `update_dry_ice`.
- `src/sandfall/simulation.py` — **audit-only unless the integration test fails**
  (see step 7). Verify the dormant-wake conditions (`:158-170`) keep a dry-ice
  freeze spreading WITHOUT adding DRY_ICE. Only if `test_dry_ice_freezes_water`
  stalls: add `| (data == int(ElementId.DRY_ICE))` to the condition-3 dilate
  (`:168-170`).
- `tests/test_phase.py` — REMOVE the `ICE_COLD_TARGET` import (`:31`); rework
  `test_water_freezes_to_ice` (`:66-80`) temp assertion; rework
  `test_ice_freeze_spreads_through_water` (`:83-116`) → `test_dry_ice_freezes_water`
  (seed DRY_ICE, not ICE); FLIP `test_ice_at_ambient_stays_ice` (`:158-167`) →
  `test_ice_melts_in_ambient`; ADD `test_ice_does_not_freeze_water`;
  `test_paint_brush_ice_sets_cold_spawn_temp` docstring (`:316`) −5 → 0; ADD
  `test_dry_ice_persists_in_ambient` + `test_dry_ice_melts_via_fire_contact`.
- `tests/test_ui.py` — palette-count literal `15 → 16` (`:41`); min-window math
  `18 → 19` items (`:242-248`); add `DRY_ICE` to the `new_elements` list (`:217-226`).
- `tests/test_config.py` — min-window test `MIN_WINDOW_W 528 → 556`, item count
  `18 → 19`, padding `17 → 18`, `MIN_GRID_COLS 132 → 139` (`:93-124`).
- `docs/ARCHITECTURE.md` — append `DRY_ICE=16` to the member list; refresh the
  ice bullet (now a realistic non-source) and the `ICE.melt_point` note.

## Implementation Instructions

> Re-read each file before editing — line numbers below are current at the
> gunpowder-complete source and may have drifted. The `ice.py` revert and the
> new `dry_ice.py` + `water.py` freeze-branch edit must land together (the
> `ICE_COLD_TARGET` name disappears from `ice.py`, so `water.py`'s import of it
> and the test import must be removed in the same commit or imports break).

### 1. `src/sandfall/rules/ice.py` — full rewrite (realistic non-source)

Replace the entire current file (`ice.py:1-83`). The reverted rule restores the
thermal melt, keeps the fire/lava contact melt, drops `ICE_COLD_TARGET`
entirely. Exact replacement:

```python
"""Ice (SOLID, frozen water) update rule.

Ice is **realistic frozen water**: it melts to WATER when its own temperature
exceeds its ``melt_point`` (0C) -- so a lone ice block in 20C ambient melts,
and ice warming at the edge of a freeze patch reverts to water. Ice does NOT
freeze water on its own (it sits at ~0C and cannot pull 20C water below 0);
freezing water now requires a colder-than-freezing cold source whose diffusion
cools adjacent water to/below 0C, at which point the WATER rule freezes it. See
``rules/dry_ice.py`` (persistent, -78C) and ``rules/ln2.py`` (transient, -196C).

Ice is still destroyed quickly by direct fire/lava contact (the real-world way):
a FIRE neighbor -> WATER; a LAVA neighbor -> STEAM (the lava reaction flashes
the melt to steam). This is checked FIRST so a hot contact destroys the ice
before the ambient-melt branch runs.

This reverts the interim persistent-cold-source model (re-asserting an
``ICE_COLD_TARGET`` and disabling ambient melt) that shipped so ice could freeze
water before real cold-source elements existed; dry ice now fills that role. See
the ``thermal-realism`` plan and BACKLOG ("Thermal realism rework").

This is the formal use of the reactive-rule contract relaxation (transform own
cell in place, return None); the cell does not MOVE so the simulation's
moved-this-frame guard is unaffected.
"""

from __future__ import annotations

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import seed_steam_life

_ICE = ELEMENTS[ElementId.ICE]
_STEAM = ELEMENTS[ElementId.STEAM]

# Orthogonal neighborhood for the fire/lava melt check (matches the
# 4-neighborhood the diffusion pre-pass and lava.py use).
_MELT_NEIGHBORS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (0, 1),
    (-1, 0),
    (1, 0),
)


def update_ice(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an ice cell: melt via direct fire/lava contact, else melt in place
    when warmer than melt_point (realistic ambient melt).

    1. **Melt via direct fire/lava contact.** A FIRE neighbor -> become WATER; a
       LAVA neighbor -> become STEAM (the lava reaction flashes the melt to
       steam). Checked FIRST so a hot contact destroys the ice immediately.
    2. **Thermal melt.** Otherwise, if the cell's own temp exceeds its
       melt_point (0C), become WATER -- a lone ice block in ambient melts. (The
       melt_point is now USED, unlike under the interim cold-source model where
       it was declared-but-unread.)
    """
    # 1. Direct fire/lava contact melts the ice (dramatic reactions first).
    for dx, dy in _MELT_NEIGHBORS:
        nx, ny = x + dx, y + dy
        if not grid.in_bounds(nx, ny):
            continue
        neighbor = grid.get(nx, ny)
        if neighbor == ElementId.LAVA:
            grid.set(x, y, ElementId.STEAM)
            grid.set_temp(x, y, _STEAM.temp_spawn)  # warm gas on melt-by-lava
            grid.set_life(x, y, seed_steam_life())
            return None
        if neighbor == ElementId.FIRE:
            grid.set(x, y, ElementId.WATER)
            return None

    # 2. Thermal melt: warmer than melt_point -> WATER (realistic ambient melt).
    if grid.get_temp(x, y) > _ICE.melt_point:
        grid.set(x, y, ElementId.WATER)
        return None

    return None
```

Notes for the implementer:
- The old `ICE_COLD_TARGET = -50` module constant and its re-assert block are
  GONE. `_ICE = ELEMENTS[ElementId.ICE]` is restored (the rule now reads
  `_ICE.melt_point`); the interim version had dropped this binding.
- `seed_steam_life` stays imported from `._common` (the LAVA-contact branch still
  seeds steam life, exactly as before).
- LAVA is checked before FIRE (more dramatic reaction wins when both are
  adjacent) — same order as the interim rule; document in the reflection if
  flipped.

### 2. `src/sandfall/rules/water.py` — stop seeding new ice cold

The freeze branch (`water.py:59-65`) currently writes `ICE_COLD_TARGET` onto the
new ice so the (interim) freeze front advances. Under the realistic model the
new ice simply keeps the water's already-≤0 temp — no special seeding. Two edits:

**2a. Remove the import** (`water.py:33`): delete the line
`from .ice import ICE_COLD_TARGET`. (The remaining `from ._common import ...` at
`:32` is unchanged.) This removes the one-way `water → ice` sibling dependency
that existed only for the interim cold-seed.

**2b. The freeze branch** (`water.py:59-65`) becomes (drop the `set_temp` line
and its now-stale comment):

```python
    # Freeze -> ICE (at or below freeze_point; freeze_point == 0 is valid).
    # The new ice keeps the water's already-<=0 temp (realistic: no cold-source
    # seeding). It melts again once it warms above melt_point via diffusion.
    if t <= _WATER.freeze_point:
        grid.set(x, y, ElementId.ICE)
        return None
```

Also refresh the freeze bullet in the module docstring (`water.py:15-17`) — drop
the "seeded at ICE_COLD_TARGET so the freeze front advances" phrasing; note the
new ice keeps the water's temp and a cold source (dry ice / LN2) drives the
freeze.

### 3. `src/sandfall/rules/dry_ice.py` (NEW) — persistent cold source at -78

This is the *current* interim `ice.py` shape lifted verbatim, with three
substitutions: `DRY_ICE_COLD_TARGET = -78` (not −50); re-assert reads
`DRY_ICE_COLD_TARGET`; the fire/lava sublimation outputs change to FIRE→EMPTY /
LAVA→SMOKE (dry ice has no liquid phase). Full file:

```python
"""Dry ice (SOLID, persistent cold source) update rule.

Dry ice is the **persistent cold source** that ice used to be (interim): each
step it re-asserts its cold target temperature (``DRY_ICE_COLD_TARGET`` = -78C,
the sublimation point of CO2), exactly as a living fire cell re-asserts its
burn_temp (``rules/fire.py``). The Simulation's vectorized diffusion pre-pass
carries that cold outward; adjacent water cools to/below its freeze_point and
the WATER rule freezes it to ICE. Because dry ice is much colder than ice (-78
vs ~0), cold propagates THROUGH the resulting ice shell (ice conducts heat) to
reach ever-farther water, so the freeze front advances while the dry ice
persists. This is the realistic Powder Toy / Sandboxels cold source.

Dry ice sublimates ONLY via direct fire/lava contact (NOT ambient -- it
re-asserts cold): a FIRE neighbor -> EMPTY (gentle sublimation); a LAVA neighbor
-> SMOKE (intense heat -> a visible CO2 vapor puff, seeded with smoke life). It
persists indefinitely in ambient.

This is the formal use of the reactive-rule contract relaxation (transform own
cell in place, return None); the cell does not MOVE so the simulation's
moved-this-frame guard is unaffected.
"""

from __future__ import annotations

from ..elements import ElementId
from ..grid import Grid
from ._common import seed_smoke_life

# The cold temperature a dry-ice cell holds (and re-asserts) each step. A cold
# source: diffusion carries this cold outward, but cannot warm the dry ice above
# this value while the rule keeps re-asserting it. NOT a physical temperature --
# it is a tunable knob for freeze spread rate (colder -> faster spread). -78 is
# CO2's sublimation point; colder than the interim ICE_COLD_TARGET (-50), so it
# freezes water faster than interim ice did. Mirrors the LAVA_SOLIDIFY_TEMP
# pattern in rules/lava.py.
DRY_ICE_COLD_TARGET = -78

# Orthogonal neighborhood for the fire/lava sublimation check (matches the
# 4-neighborhood the diffusion pre-pass and lava.py use).
_SUBLIMATE_NEIGHBORS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (0, 1),
    (-1, 0),
    (1, 0),
)


def update_dry_ice(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step a dry-ice cell: sublimate via direct fire/lava contact, else
    re-assert cold.

    1. **Sublimate via direct fire/lava contact.** A FIRE neighbor -> EMPTY
       (gentle sublimation); a LAVA neighbor -> SMOKE (intense heat flashes it
       to a vapor puff). Checked FIRST so a hot contact destroys the dry ice
       before it can re-assert cold. (Dry ice does NOT sublimate from ambient --
       it re-asserts cold each step.)
    2. **Re-assert the cold target.** While still dry ice, clamp the cell's temp
       DOWN to DRY_ICE_COLD_TARGET each step so it remains a persistent cold
       source the diffusion pre-pass draws from (mirrors fire's burn-temp
       re-assert and the retired interim-ice behavior).
    """
    # 1. Direct fire/lava contact sublimates the dry ice.
    for dx, dy in _SUBLIMATE_NEIGHBORS:
        nx, ny = x + dx, y + dy
        if not grid.in_bounds(nx, ny):
            continue
        neighbor = grid.get(nx, ny)
        if neighbor == ElementId.LAVA:
            grid.set(x, y, ElementId.SMOKE)
            grid.set_life(x, y, seed_smoke_life())
            return None
        if neighbor == ElementId.FIRE:
            grid.set(x, y, ElementId.EMPTY)
            return None

    # 2. Re-assert cold: a living dry-ice cell is a persistent cold source.
    if grid.get_temp(x, y) > DRY_ICE_COLD_TARGET:
        grid.set_temp(x, y, DRY_ICE_COLD_TARGET)

    return None
```

Notes for the implementer:
- LAVA→SMOKE (dramatic) is checked before FIRE→EMPTY (gentle), mirroring interim
  ice's LAVA-before-FIRE priority.
- `seed_smoke_life` is imported from `._common` (already exported there; sibling
  module, no cycle). No `_DRY_ICE = ELEMENTS[...]` binding is needed — the rule
  reads no `Element` field (the cold target is the module constant, and the
  sublimation outputs are hard-coded EMPTY/SMOKE).

### 4. `src/sandfall/elements.py`

**4a. `ICE.temp_spawn`: −5 → 0** (`elements.py:238`). Frozen water is ~0°C;
water freezing keeps its temp (~0°C), so painted/spawned ice should match.
Update the inline comment too:

```python
        temp_spawn=0,  # painted ice starts at ~0C (frozen water; melts >0)
        melt_point=0,  # above 0 -> WATER (0 is a VALID active threshold for ice)
```

**4b. Add the enum member** after `GUNPOWDER = 15` (`elements.py:71`):

```python
    GUNPOWDER = 15
    # --- New element (thermal-realism: dry ice cold source) ---
    DRY_ICE = 16
```

> Existing values 0–15 are unchanged, so every LUT index is stable. Append a
> sentence to the enum docstring noting this feature extends to DRY_ICE (16),
> same supported-operation status as the prior extensions.

**4c. Add the `ELEMENTS` entry** after the GUNPOWDER entry (`elements.py:319-328`).
First-pass values (Decision #3 + overview Risks #3):

```python
    # --- Dry ice (SOLID, persistent cold source; thermal-realism) -----------
    # SOLID at density ~1.0 (does not flow; sits where painted). Re-asserts
    # DRY_ICE_COLD_TARGET (-78C, CO2 sublimation point) each step in its rule
    # (rules/dry_ice.py), so it is the cold source that freezes water (the role
    # ice used to play in the interim model, but colder and named realistically).
    # temp_spawn=-78 (painted dry ice starts at its cold target). Persists in
    # ambient; sublimates only via direct fire/lava contact (EMPTY/SMOKE). No
    # flashpoint/burn (it is a cold source, not a fuel).
    ElementId.DRY_ICE: Element(
        id=ElementId.DRY_ICE,
        name="dry ice",
        color=(225, 230, 235),  # pale off-white (distinct from ICE 180,220,240)
        density=1.0,
        phase=Phase.SOLID,
        conductivity=0.20,
        heat_capacity=2.0,
        temp_spawn=-78,
    ),
```

### 5. `src/sandfall/config.py`

**5a. Add the constants** alongside the existing material blocks (COND near
`:135-136`, CP near `:163-164`):

```python
# Dry ice (persistent cold-source solid). Mid conductivity (cold propagates
# through it to adjacent water); cp like ice (2.0).
COND_DRY_ICE = 0.20
...
# Dry ice (persistent cold-source solid).
CP_DRY_ICE = 2.0
```

> Stability unchanged (`config.py:104-107`): 0.20 < FIRE 0.50; 2.0 > min 0.5 →
> `0.20 * 0.50 / 0.5 == 0.20 <= 0.25` holds.

**5b. Recompute `MIN_WINDOW_W`** for the 19-item palette (16 element swatches +
Eraser + Brush-shape + Magnifier). Update the comment at `config.py:71-79`:

```
# Minimum window size. Width must fit the whole palette (19 items: 16 element
# swatches + Eraser + Brush-shape + Magnifier). Width math:
#   19 * PALETTE_SWATCH + 18 * PALETTE_PADDING + PALETTE_GROUP_GAP + 2 * PALETTE_MARGIN
#   = 19*24 + 18*4 + 12 + 2*8 = 456 + 72 + 12 + 16 = 556  (== 139 * CELL_SIZE)
# 556 is a clean CELL_SIZE multiple, = 139 cols.
```

Set `MIN_WINDOW_W = 556` (`config.py:80`). `MIN_GRID_COLS` recomputes
automatically (`config.py:82`) → 139.

### 6. `src/sandfall/thermal.py` + `rules/__init__.py`

**6a. `thermal.py`** — add `COND_DRY_ICE`, `CP_DRY_ICE` to the
`from .config import (...)` block (`:17-55`) in alphabetical position (the
project uses ruff/isort, which enforces ordering: `COND_DRY_ICE` between
`COND_BASE` and `COND_EMPTY`; `CP_DRY_ICE` between `CP_BASE` and `CP_EMPTY`).
Add row 16 to both LUT builders (after the GUNPOWDER row, `thermal.py:88` /
`:120`):

```python
    lut[int(ElementId.GUNPOWDER)] = COND_GUNPOWDER
    # Dry ice (persistent cold-source solid).
    lut[int(ElementId.DRY_ICE)] = COND_DRY_ICE
    return lut
```

```python
    lut[int(ElementId.GUNPOWDER)] = CP_GUNPOWDER
    lut[int(ElementId.DRY_ICE)] = CP_DRY_ICE
    return lut
```

> Both LUTs size from `len(ElementId)` (`thermal.py:68`, `:100`), so they grow
> 16 → 17 rows automatically; the explicit row write fills the new slot
> (otherwise it defaults to 0.0, which for cp would divide-by-zero in diffusion).

**6b. `rules/__init__.py`** — import + register (`:22-36` imports, `:54-74`
RULES):

```python
from .dry_ice import update_dry_ice
```

```python
    # Gunpowder (explosive powder).
    ElementId.GUNPOWDER: update_gunpowder,
    # Dry ice (persistent cold-source solid; thermal-realism).
    ElementId.DRY_ICE: update_dry_ice,
```

> DRY_ICE has no finite life (it is a persistent source, not a timer), so it
> needs NO `seed_*_life` helper and NO brush life-seeding change. Its
> `temp_spawn=-78` ≠ `AMBIENT_TEMP`, so `paint_brush`'s existing spawn-temp pass
> (`brush.py:91-92`) handles it automatically — no brush edit. The palette
> swatch appears automatically (`ui.palette_layout` iterates `ElementId`).

### 7. `src/sandfall/simulation.py` — audit-only (verification gate)

**Do NOT edit `simulation.py` yet.** Re-read `simulation.py:158-170` (the four
wake conditions) and reason (Decision #8):

- The diffusion pre-pass (`:116`) runs WHOLE-GRID regardless of `active`, so cold
  from a dormant dry-ice cell still propagates into adjacent water/ice.
- That water cools (temp changes) → condition 2 (`:163`, `grid._temp !=
  temp_before`) wakes it → scanned → freeze-check → freezes to ICE.
- The freshly-frozen cell changed identity → condition 1 (`:158-159`, `id_changed`
  + dilate) wakes it + its neighbors (incl. the dry-ice cell).
- The dry-ice cell warms slightly as cold flows out (temp changes) → condition 2
  wakes it → `update_dry_ice` re-asserts `DRY_ICE_COLD_TARGET`.

So the analysis says the existing wake conditions **should** keep a dry-ice
freeze spreading **without** adding DRY_ICE to condition 3 (`:168-170`). This is
the same case interim ice was, and the `thermal-float-ice` finding (no wake edit
needed) should carry over. **Verify with the integration test in step 8c BEFORE
deciding.** Only if `test_dry_ice_freezes_water` shows NO freezing (ice count
stays 0 over ~150 steps): add DRY_ICE to condition 3:

```python
        active_next |= _dilate(
            (data == int(ElementId.FIRE))
            | (data == int(ElementId.LAVA))
            | (data == int(ElementId.DRY_ICE))
        )
```

…updating the comment to explain DRY_ICE is a persistent cold source. **Pin the
decision and its evidence in the reflection.** Default expectation: NO edit.

### 8. `tests/test_phase.py`

**8a. Remove the `ICE_COLD_TARGET` import** (`test_phase.py:31`). It is being
deleted from `ice.py`; leaving the import breaks collection. (The reworked tests
below import `DRY_ICE_COLD_TARGET` from `sandfall.rules.dry_ice` instead, locally
where needed.)

**8b. `test_water_freezes_to_ice`** (`test_phase.py:66-80`) — the freeze branch
no longer seeds the new ice cold; the new ice keeps the water's temp. The test
sets the water to `freeze_point - 5` (−5), so the new ice holds −5. Replace the
assertion at `:80` and refresh the docstring tail (`:74-77`):

```python
    g = _step_single_cell(ElementId.WATER, ELEMENTS[ElementId.WATER].freeze_point - 5)
    assert g.get(0, 0) == ElementId.ICE
    # The new ice keeps the water's already-<=0 temp (realistic: no cold-source
    # seeding). It was set to freeze_point-5, so it stays at freeze_point-5.
    assert g.get_temp(0, 0) == ELEMENTS[ElementId.WATER].freeze_point - 5
```

**8c. Rework `test_ice_freeze_spreads_through_water`** (`:83-116`) →
**`test_dry_ice_freezes_water`** — the headline Phase-01 integration test AND
the dormant-wake gate (step 7). Seed a DRY_ICE block (not ICE) in water, step a
real `Simulation`, assert ice count grows from 0 (dry ice freezes water via
diffusion). Replace the whole function:

```python
def test_dry_ice_freezes_water() -> None:
    """A block of DRY_ICE in water freezes its surroundings (dry ice is the cold
    source; the freeze spreads via diffusion).

    The headline Phase-01 test: dry ice re-asserts DRY_ICE_COLD_TARGET (-78)
    each step, so cold propagates via diffusion into adjacent water, the water
    cools below freeze_point, and the WATER rule freezes it to ICE. Because the
    newly-formed ice is NOT itself a cold source (realistic), the freeze front
    advances by cold diffusing THROUGH the growing ice shell from the dry-ice
    source -- slower than the interim 1->9-in-120 spread, but it DOES spread.

    It also pins the dormant-wake sufficiency finding: a real ``Simulation``
    rebuilds its active set each step, so if ANY ice forms here the existing
    wake conditions keep the front alive without needing DRY_ICE in the wake
    condition. If this test freezes NOTHING, add DRY_ICE to condition 3
    (simulation.py:168-170) per the plan's step 7.
    """
    from sandfall.rules.dry_ice import DRY_ICE_COLD_TARGET

    random.seed(0)
    g = Grid(12, 12)
    # Fill the bottom half with water.
    for y in range(6, 12):
        for x in range(12):
            g.set(x, y, ElementId.WATER)
    # Seed a small dry-ice block in the middle of the water.
    for dy in range(2):
        for dx in range(2):
            g.set(5 + dx, 7 + dy, ElementId.DRY_ICE)
            g.set_temp(5 + dx, 7 + dy, DRY_ICE_COLD_TARGET)
    sim = Simulation(g)
    assert int((g.array == int(ElementId.ICE)).sum()) == 0  # no ice yet
    for _ in range(150):
        sim.step()
    ice_after = int((g.array == int(ElementId.ICE)).sum())
    # The dry ice froze some water (strictly more than zero). The exact count
    # depends on DRY_ICE_COLD_TARGET tuning; the point is freezing happened at
    # all. If ice_after == 0, the dormant-wake sufficiency is falsified -- apply
    # the step-7 simulation.py edit and re-run.
    assert ice_after > 0, ice_after
```

**8d. FLIP `test_ice_at_ambient_stays_ice`** (`:158-167`) →
**`test_ice_melts_in_ambient`** — the deliberate behavior change. Ice at 20°C
now MELTS (realistic non-source). On a 1×1 grid diffusion is a no-op so the ice
reads exactly 20 → `> melt_point(0)` → WATER:

```python
def test_ice_melts_in_ambient() -> None:
    """Ice at ambient MELTS to WATER (realistic non-source: temp > melt_point).

    This is the deliberate Phase-01 behavior change that retires the interim
    persistent-cold-source model: ice no longer re-asserts cold, so a lone ice
    block in 20C ambient warms above its melt_point and melts. (Dry ice / LN2 are
    now the cold sources that freeze water.)
    """
    g = _step_single_cell(ElementId.ICE, 20)
    assert g.get(0, 0) == ElementId.WATER
```

**8e. ADD `test_ice_does_not_freeze_water`** — ice no longer freezes water. Ice
(next to water at a mild temp) does NOT convert the water to ice. Put this near
the other ice tests (after `test_ice_melts_in_ambient`):

```python
def test_ice_does_not_freeze_water() -> None:
    """Ice adjacent to ambient water does NOT freeze it (ice is a non-source).

    Ice sits at ~0C and cannot pull 20C water below its freeze_point; only a
    colder-than-freezing cold source (dry ice / LN2) can. The water cell stays
    WATER (and the ice, warming via diffusion, eventually melts).
    """
    random.seed(0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ICE)
    g.set_temp(0, 0, 0)  # ice at its melt_point (stays ice: >0 is false)
    g.set(1, 0, ElementId.WATER)
    g.set_temp(1, 0, 5)  # mild water, well above freeze_point
    for _ in range(10):
        Simulation(g).step()
    # The water cell never froze -- ice is not a cold source.
    assert g.get(1, 0) == ElementId.WATER
```

**8f. `test_paint_brush_ice_sets_cold_spawn_temp`** (`:315-327`) — only the
docstring changes (`:316`): `"-5"` → `"0"`. The assertion
`g.get_temp(...) == ELEMENTS[ElementId.ICE].temp_spawn` already reads the field,
so it auto-adjusts to the new `temp_spawn=0`.

```python
def test_paint_brush_ice_sets_cold_spawn_temp() -> None:
    """A painted ICE disk's cells hold ICE's cold spawn temp (0)."""
```

**8g. ADD `test_dry_ice_persists_in_ambient`** — dry ice re-asserts cold and
does NOT sublimate at ambient (it is the persistent source):

```python
def test_dry_ice_persists_in_ambient() -> None:
    """Dry ice at ambient does NOT sublimate (it re-asserts cold; only fire/lava
    destroy it). The deliberate persistent-cold-source behavior, now under the
    dry-ice name instead of ice."""
    from sandfall.rules.dry_ice import DRY_ICE_COLD_TARGET

    g = _step_single_cell(ElementId.DRY_ICE, 20)
    assert g.get(0, 0) == ElementId.DRY_ICE
    # It re-asserted its cold target (the persistent-cold-source behavior).
    assert g.get_temp(0, 0) == DRY_ICE_COLD_TARGET
```

**8h. ADD `test_dry_ice_melts_via_fire_contact`** — dry ice + FIRE neighbor →
EMPTY (sublimation):

```python
def test_dry_ice_sublimates_via_fire_contact() -> None:
    """Dry ice sublimates to EMPTY when an orthogonal neighbor is FIRE."""
    g = Grid(3, 1)
    g.set(0, 0, ElementId.DRY_ICE)
    g.set(1, 0, ElementId.FIRE)
    g.set_life(1, 0, 50)  # keep fire alive through the step
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.EMPTY
```

> `test_ice_melts_to_water_via_fire_contact` (`:128-141`) and
> `test_ice_melts_to_steam_via_lava_contact` (`:144-155`) are UNCHANGED — the
> reverted ice rule keeps that exact fire/lava-contact melt shape, so both still
> pass as written.

### 9. Update existing palette-width tests

- `tests/test_ui.py:35,41` — `test_palette_layout_has_15_elements_then_3_tools`
  hardcodes `len(elements) == len(ElementId) - 1 == 15`. Update the literal `15
  → 16` (the `== len(ElementId) - 1` half auto-adjusts). Rename the test to
  reflect 16 elements if the name reads wrong.
- `tests/test_ui.py:198-248` — `test_palette_resolves_new_elements_and_fits_min_window`
  hardcodes the `18 * PALETTE_SWATCH + 17 * PALETTE_PADDING + ...` math and the
  18-item count in its docstring. Update item count `18 → 19`, padding count
  `17 → 18`, add `ElementId.DRY_ICE` to the `new_elements` list (`:217-226`).
  The `last.x + last.w + PALETTE_MARGIN <= MIN_WINDOW_W` assertion must still
  hold (it will, since `MIN_WINDOW_W` was bumped to match).
- `tests/test_config.py:93-124` —
  `test_min_window_width_fits_full_palette_with_group_gap` hardcodes
  `MIN_WINDOW_W == 528` (`:114`), the 18-item `needed` math (`:115-120`),
  `needed == 528` (`:121`), and `MIN_GRID_COLS == 132` (`:124`). Update to
  `MIN_WINDOW_W == 556`, item count `18 → 19`, padding `17 → 18`, `needed == 556`,
  `MIN_GRID_COLS == 139`.

### 10. Renderer + palette verification (automatic — verify, do not edit)

`build_color_lut` (`renderer.py`) and `palette_layout` (`ui.py`) both auto-resize
from `len(ElementId)` (precedent: acid/base/oil/gunpowder all appeared with no
wiring). **Verify** (no edit) via the enum-count check in Verification Commands.

## Acceptance Criteria

- [ ] `rules/ice.py` defines NO `ICE_COLD_TARGET`; `update_ice` melts to WATER
      when `get_temp > melt_point` (thermal melt restored), and via direct
      fire/lava contact (LAVA→STEAM, FIRE→WATER) checked first; the module
      docstring describes the realistic non-source model and points at dry ice /
      LN2 as the cold sources.
- [ ] `rules/water.py` freeze branch no longer writes the new ice's temp; the
      `from .ice import ICE_COLD_TARGET` import is GONE (no sibling-rule
      dependency on ice remains).
- [ ] `rules/dry_ice.py` defines `DRY_ICE_COLD_TARGET = -78`; `update_dry_ice`
      re-asserts it when the cell is warmer, and sublimates via direct fire/lava
      contact (FIRE→EMPTY, LAVA→SMOKE); it does NOT sublimate in ambient.
- [ ] `ElementId.DRY_ICE == 16`; `len(ElementId) == 17`; values 0–15 unchanged
      (`int(GUNPOWDER) == 15`). DRY_ICE has an `ELEMENTS` entry with
      `phase=SOLID`, `temp_spawn==-78`, sensible cond/cp + color.
- [ ] **`test_dry_ice_freezes_water` passes** — ice count strictly grows from 0
      over ~150 steps in a real `Simulation` (the headline; the realistic model
      must still freeze water via a cold source). If it froze nothing,
      `simulation.py` condition-3 was extended with `| (data == DRY_ICE)` and the
      decision + evidence are in the reflection; otherwise `simulation.py` is
      unchanged (recorded).
- [ ] `test_ice_melts_in_ambient` passes (ice at 20°C → WATER);
      `test_ice_does_not_freeze_water` passes (water stays WATER next to ice);
      `test_dry_ice_persists_in_ambient` + `test_dry_ice_sublimates_via_fire_contact`
      pass.
- [ ] `test_water_freezes_to_ice` asserts the new ice keeps the water's temp
      (`freeze_point - 5`); `test_paint_brush_ice_sets_cold_spawn_temp` docstring
      reads "0".
- [ ] `ICE.temp_spawn == 0`; `ICE.melt_point` is still declared and now USED by
      the rule.
- [ ] `build_conductivity_lut` / `build_heat_capacity_lut` have 17 rows; row 16
      is `COND_DRY_ICE` / `CP_DRY_ICE`.
- [ ] `MIN_WINDOW_W == 556` (= 139 cols); the 19-item palette row fits at the
      minimum size; `test_ui.py` / `test_config.py` palette assertions updated
      and green.
- [ ] `RULES` enumerates all 17 elements (16 real rules + EMPTY omitted);
      `len(RULES) >= 16`.
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the reworked ice tests + the dry-ice freeze-spread gate):
uv run pytest tests/test_phase.py tests/test_thermal.py -v

# Confirm the enum + registry grew and the stable indices held:
uv run python -c "from sandfall.elements import ElementId; from sandfall.rules import RULES; assert [e.value for e in ElementId]==list(range(17)); assert int(ElementId.SAND)==1 and int(ElementId.GUNPOWDER)==15 and int(ElementId.DRY_ICE)==16; assert ElementId.DRY_ICE in RULES; print('enum+registry OK')"

# Confirm palette min-width math: 19 items fit in MIN_WINDOW_W.
uv run python -c "from sandfall.config import MIN_WINDOW_W, PALETTE_GROUP_GAP, PALETTE_MARGIN, PALETTE_PADDING, PALETTE_SWATCH; need=19*PALETTE_SWATCH+18*PALETTE_PADDING+PALETTE_GROUP_GAP+2*PALETTE_MARGIN; assert MIN_WINDOW_W==556 and MIN_WINDOW_W>=need, (MIN_WINDOW_W, need); print('palette fits', need, '<=', MIN_WINDOW_W)"

# FULL suite -- regression guard:
uv run pytest

# Lint / format / types:
uv run ruff check . && uv run ruff format --check . && uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
#   Manual check: paint DRY_ICE into a WATER pool (ice forms around it and the
#   freeze spreads while the dry ice persists); paint ICE alone in open air at
#   ambient (it melts to WATER); touch ICE with FIRE (->WATER) and LAVA (->STEAM);
#   touch DRY_ICE with FIRE (->EMPTY) and LAVA (->SMOKE); the H overlay shows
#   dry ice at deep-cold and ice near 0.
```

All commands must exit zero. If `test_dry_ice_freezes_water` freezes nothing
(ice count stays 0), apply the step-7 `simulation.py` dormant-wake extension and
re-run before concluding the phase is done. Do NOT weaken the freeze assertion
to pass — dry ice freezing water is the whole point of Phase 01.

## Documentation Updates

- `docs/ARCHITECTURE.md:250-258` — append `DRY_ICE=16` to the `ElementId`
  member list.
- `docs/ARCHITECTURE.md:280-285` — the `ICE.melt_point` note currently says ice
  is a persistent cold source that re-asserts `ICE_COLD_TARGET` and melts only
  via fire/lava contact. REFRESH it: ice is now a realistic non-source that
  melts at `> melt_point` (the field is now USED), and dry ice / LN2 are the cold
  sources.
- `docs/ARCHITECTURE.md:530-534` — the "Adding a new element" recipe's ice
  bullet (ICE.melt_point unused by the rule) is now stale; update it to say
  ice's melt_point IS used by the realistic rule.

## Reflection & Commit

After implementation, write `01-ice-revert-dry-ice-reflection.md` in this
directory. **Specifically include:**
- The **dormant-wake decision and its evidence**: did `test_dry_ice_freezes_water`
  freeze water WITHOUT adding DRY_ICE to condition 3 (confirming the analysis), or
  did it freeze nothing and require the `| (data == DRY_ICE)` extension? Quote the
  `ice_after` count from the integration test (the actual spread number).
- The `DRY_ICE_COLD_TARGET` value shipped (`-78`) and the measured freeze-spread
  shape (how many cells of ice over how many steps) — note it as a knob and
  compare to the interim ice's 1→9-in-120.
- Whether removing the `water → ice` sibling import introduced any issue (it
  should not — the dependency is simply gone).
- The measured behavior in the SDL smoke: does dry ice visibly grow an ice shell
  in water? does a lone ice block melt in ambient? does the `H` overlay show dry
  ice cold and ice near 0?
- Which `docs/ARCHITECTURE.md` sections were refreshed (the ice bullet + the
  melt_point note).
- Anything difficult/unexpected, deviations from this plan + why, and anything
  fun discovered.

Then make ONE atomic git commit covering all changes in this phase.

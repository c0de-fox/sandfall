# Phase 01: Gunpowder + the reusable `blast.explode` helper

## Objective

Add `ElementId.GUNPOWDER = 15` — a dark POWDER (density ~1.5, like sand) that
**flows like sand when left alone** and **detonates (heat burst + crater +
scatter) when heated** above its `flashpoint` (~200) — plus a reusable
`src/sandfall/rules/blast.py::explode` helper that future explosives (TNT, etc.)
call. Fire, lava, or another blast's heat sets gunpowder off → chain reactions
for free. Extend the thermal LUTs and recompute `MIN_WINDOW_W` for the wider
18-item palette. Existing values 0–14 are unchanged; v1+ behavior is untouched.

> **Re-read before editing** (line numbers below are current as of the post-
> `new-elements/oil` source and WILL shift): `src/sandfall/elements.py`,
> `src/sandfall/config.py`, `src/sandfall/thermal.py`,
> `src/sandfall/rules/__init__.py`, `src/sandfall/rules/sand.py`,
> `src/sandfall/rules/wood.py`, `src/sandfall/rules/lava.py`,
> `src/sandfall/rules/_common.py`, `src/sandfall/simulation.py`,
> `tests/test_phase.py`, `tests/test_acid_base.py`, `tests/test_ui.py`,
> `tests/test_config.py`, and `docs/ARCHITECTURE.md:248-257` + `:510-545`.

## Depends On

none — builds on the completed temperature + dormant-cell + acid/base/oil
features (the reactive-rule contract, the `flashpoint` ignition path, the
`LAVA_SOLIDIFY_TEMP` module-constant pattern, the reactive side-effect write,
the thermal LUT builders, the auto-resizing renderer/palette, and the dormant
wake conditions are all in place).

## Can Parallelize With

none — single phase; it mutates the shared core files every element pass touches.

## Recommended Agent

@implementer — mid-size surface area: 1 enum member, 1 `ELEMENTS` entry, 1
genuinely new module (`blast.py` — the circular-radius heat/crater/scatter
helper with outer-ring-first ordering; the only non-recipe code), 1 small rule
file (`gunpowder.py`: detonate-or-flow), the thermal LUT row, the
`MIN_WINDOW_W` recompute, the existing palette-count/min-width test updates, and
a new test file. Read `rules/lava.py` (module-constant + side-effect-write
pattern), `rules/wood.py` (flashpoint trigger), and `rules/sand.py` (the powder
flow shape) carefully. The blast ring-ordering (Risk #3) and the heat-vs-melt
tension (Risk #4) are the correctness cruxes.

## Changes Required

- `src/sandfall/elements.py` — add `GUNPOWDER = 15` to `ElementId` (15 → 16
  members); add an `ELEMENTS` entry (POWDER/density 1.5/flashpoint 200 + color).
- `src/sandfall/config.py` — add `COND_GUNPOWDER`, `CP_GUNPOWDER`; **recompute
  `MIN_WINDOW_W`** for the 18-item palette (→ 528).
- `src/sandfall/thermal.py` — add row 15 to `build_conductivity_lut` and
  `build_heat_capacity_lut`; import the 2 new config constants.
- `src/sandfall/rules/blast.py` (NEW) — the reusable `explode(grid, x, y, ...)`
  helper: heat burst + crater + scatter over a circular radius, outer-ring-first.
  Module-level tunables mirroring `LAVA_SOLIDIFY_TEMP`.
- `src/sandfall/rules/gunpowder.py` (NEW) — detonate (thermal trigger → call
  `explode`, then cell → FIRE) checked first, then flow like a powder (sand.py
  shape).
- `src/sandfall/rules/__init__.py` — import + register `update_gunpowder` in
  `RULES`.
- `tests/test_gunpowder.py` (NEW) — detonates-when-heated / chain-reaction /
  destroys-everything-in-crater / heat-burst-ignites-wood-and-boils-water /
  scatter / stable-at-ambient + renderer-LUT-grew.
- `tests/test_ui.py` — update the palette-count assertion (`14 → 15`) and the
  min-window math test (`17 → 18` items).
- `tests/test_config.py` — update the min-window test (`MIN_WINDOW_W 500 → 528`,
  `17 → 18` items, `MIN_GRID_COLS 125 → 132`).
- `docs/ARCHITECTURE.md` — append `GUNPOWDER=15` to the member list.
- `.agent/tasks/BACKLOG.md` — strike "gunpowder" from the "More elements" line.

## Implementation Instructions

### 1. `src/sandfall/elements.py`

**1a. Add the enum member** after `OIL = 14` (`elements.py:62`):

```python
    OIL = 14
    # --- New element (gunpowder) ---
    GUNPOWDER = 15
```

> Existing values 0–14 are unchanged, so every LUT index is stable. Append a
> sentence to the enum docstring (`elements.py:22-44`) noting this feature adds
> GUNPOWDER (15) — same "supported operation" status as the prior extensions.

**1b. Add the `ELEMENTS` entry** after the OIL entry (`elements.py:291-301`).
First-pass values (Decision #11 — tune in the reflection):

```python
    # --- Gunpowder (explosive powder; detonates when heated) -----------------
    # POWDER with density 1.5 (like SAND -> piles and falls like sand when not
    # ignited). flashpoint ~200 -> DETONATES (heat burst + crater + scatter via
    # rules/blast.py) when its own temp exceeds the flashpoint. Fire, lava, or
    # ANOTHER explosion's heat burst sets it off -> chain reactions. burn_temp is
    # left at its default (AMBIENT_TEMP): on detonation the cell becomes
    # ElementId.FIRE, whose rule re-asserts _FIRE.burn_temp (800) -- the same
    # shape as wood/plant/oil where the active heat comes from FIRE, not the
    # fuel's own declared burn_temp (overview Risk #6 / Decision #3).
    ElementId.GUNPOWDER: Element(
        id=ElementId.GUNPOWDER,
        name="gunpowder",
        color=(60, 60, 68),          # dark gray/black (distinct from SMOKE 90 & STONE 120)
        density=1.5,
        phase=Phase.POWDER,
        conductivity=0.15,           # a powder, like sand
        heat_capacity=1.5,
        flashpoint=200,
    ),
```

### 2. `src/sandfall/config.py`

**2a. Add the constants** alongside the existing blocks (`config.py:128-134` for
`COND_*`, `config.py:154-160` for `CP_*`):

```python
# Gunpowder (explosive powder). A powder like sand: low conductivity, mid cp.
COND_GUNPOWDER = 0.15
...
# Gunpowder (explosive powder). Same thermal mass as sand (1.5).
CP_GUNPOWDER = 1.5
```

> Stability check (`config.py:104-107`): 0.15 < FIRE 0.50; 1.5 > min 0.5, so
> `0.20 * 0.50 / 0.5 == 0.20 <= 0.25` is unchanged (Risk #6).

**2b. Recompute `MIN_WINDOW_W`** for the 18-item palette (15 elements + Eraser +
Brush-shape + Magnifier). Update the comment at `config.py:71-79`:

```
# Minimum window size. Width must fit the whole palette (18 items: 15 element
# swatches + Eraser + Brush-shape + Magnifier). Width math:
#   18 * PALETTE_SWATCH + 17 * PALETTE_PADDING + PALETTE_GROUP_GAP + 2 * PALETTE_MARGIN
#   = 18*24 + 17*4 + 12 + 2*8 = 432 + 68 + 12 + 16 = 528  (== 132 * CELL_SIZE)
# 528 is the next clean CELL_SIZE multiple above the needed 528, = 132 cols.
```

Set `MIN_WINDOW_W = 528` (`config.py:80`). `MIN_GRID_COLS` recomputes
automatically (`config.py:82`) → 132. Leave `MIN_WINDOW_H`/`MIN_GRID_ROWS`
unchanged.

### 3. `src/sandfall/thermal.py`

**3a.** Import the 2 new constants in the `from .config import (...)` block
(`thermal.py:17-53`): add `COND_GUNPOWDER`, `CP_GUNPOWDER` (keep the block
alphabetical-ish as it is now).

**3b.** Extend `build_conductivity_lut` (`thermal.py:57-85`) with row 15 (after
the OIL row, `thermal.py:83-84`):

```python
    # Oil (row 14).
    lut[int(ElementId.OIL)] = COND_OIL
    # Gunpowder (row 15).
    lut[int(ElementId.GUNPOWDER)] = COND_GUNPOWDER
    return lut
```

**3c.** Mirror in `build_heat_capacity_lut` (`thermal.py:88-115`, after
`thermal.py:113-114`):

```python
    # Oil (row 14).
    lut[int(ElementId.OIL)] = CP_OIL
    # Gunpowder (row 15).
    lut[int(ElementId.GUNPOWDER)] = CP_GUNPOWDER
    return lut
```

> Both LUTs size from `len(ElementId)` (`thermal.py:66`, `thermal.py:96`), so
> they grow 15 → 16 rows automatically; the explicit row write fills the new
> slot (otherwise it defaults to 0.0, which for cp would divide-by-zero in
> diffusion — `thermal.py:173`).

### 4. `src/sandfall/rules/blast.py` (NEW)

The reusable blast helper. Module-level tunables at top (mirror
`LAVA_SOLIDIFY_TEMP` at `lava.py:43`), then `explode`. The geometry is a circular
radius processed **outer ring first** (so scatter pushes into already-processed
cells, reducing double-move — Risk #3). Recommended skeleton (the implementer
may refine; keep the contract — heat everything / spare GUNPOWDER / crater the
inner / scatter loose outward):

```python
"""Reusable explosion helper (heat burst + crater + scatter).

``explode(grid, x, y, ...)`` models a blast as three effects applied over a
circular radius (``dx*dx+dy*dy <= radius*radius``), processed outer ring first:

1. **Heat burst** (distance falloff) -- raises the temp of every non-empty cell
   in the radius. This is what CHAINS gunpowder (other gunpowder heated past its
   flashpoint detonates on its own scan / next frame), ignites flammables
   (wood/plant/oil -> FIRE via their own flashpoint rules), and boils water
   (-> STEAM) -- all through the existing thermal thresholds, no new transition
   code.
2. **Crater** (inner radius) -- destroys everything (user choice: no blast-
   resistant material). The very core (d <= 1) becomes FIRE (the fireball, hot,
   seeded life) with CORE_FIRE_CHANCE; the rest of the crater -> EMPTY (or SMOKE
   with CRATER_SMOKE_CHANCE for visual). EXCEPTION: GUNPOWDER in the radius is
   NOT destroyed here -- it is only HEATED (step 1), so it chains via its own
   rule (destroying it would break the chain).
3. **Scatter** (outer radius) -- loose materials (POWDER/LIQUID phase) are
   pushed one cell OUTWARD (away from the blast center) with SCATTER_CHANCE if
   the outward target is EMPTY, for the "stuff goes flying" feel.

All writes are side-effect writes (direct grid.set / set_temp, like lava.py's
water->STEAM reaction), so the caller (e.g. update_gunpowder) returns None after
calling explode. The dormant-cell wake catches every blasted cell via id_changed
(condition #1) and temp_changed (condition #2), so the blast zone -- and the
chain -- stays active with NO wake-condition edit. See the master plan Risks #1.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId, Phase
from ..grid import Grid
from ._common import seed_fire_life, seed_smoke_life

# Tunables (first-pass values; pin final tuned values in the reflection).
BLAST_RADIUS = 4          # outer radius of the heat/scatter effect (cells)
CRATER_RADIUS = 2         # inner radius destroyed by the blast (cells)
BLAST_HEAT = 1200.0       # peak temp added at the center (falloff outward)
CORE_FIRE_CHANCE = 0.8    # chance a d<=1 crater cell becomes FIRE (the fireball)
CRATER_SMOKE_CHANCE = 0.15  # chance a crater cell (beyond core) becomes SMOKE
SCATTER_CHANCE = 0.5      # chance a loose cell in the outer ring is pushed out

_FIRE = ELEMENTS[ElementId.FIRE]


def _is_loose(element_id: int) -> bool:
    """True for materials scatter pushes: POWDER or LIQUID phase (sand, water,
    oil, acid, base). These have life 0 always, so the scatter's manual set need
    not carry the life array (temp IS carried explicitly)."""
    return ELEMENTS[ElementId(element_id)].phase in (Phase.POWDER, Phase.LIQUID)


def explode(
    grid: Grid,
    x: int,
    y: int,
    radius: int = BLAST_RADIUS,
    crater: int = CRATER_RADIUS,
    heat: float = BLAST_HEAT,
) -> None:
    """Detonate at ``(x, y)``: heat burst + crater + scatter over a circular
    radius, processed outer ring first. See the module docstring for the model."""
    r2 = radius * radius
    # Outer ring first: scatter pushes cells outward into already-processed
    # (outer) cells, so a scattered cell is not re-visited/moved again this blast.
    for dist_ring in range(radius, -1, -1):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx * dx + dy * dy > r2:
                    continue  # outside the circular radius
                d = (dx * dx + dy * dy) ** 0.5
                if abs(d - dist_ring) > 0.9:
                    continue  # process one ring (~width 1.8) at a time
                nx, ny = x + dx, y + dy
                if not grid.in_bounds(nx, ny):
                    continue
                nb = grid.get(nx, ny)
                if nb == ElementId.EMPTY:
                    continue
                # 1. Heat burst (distance falloff) -- chains gunpowder, ignites,
                #    boils/melts via the existing thermal thresholds.
                falloff = max(0.0, 1.0 - d / (radius + 1))
                grid.set_temp(nx, ny, grid.get_temp(nx, ny) + heat * falloff)
                if nb == ElementId.GUNPOWDER:
                    continue  # heated -> its own rule detonates it (chain); don't destroy
                # 2. Crater (inner) -- destroy everything (user choice).
                if d <= crater:
                    if d <= 1.0 and random.random() < CORE_FIRE_CHANCE:
                        grid.set(nx, ny, ElementId.FIRE)
                        grid.set_life(nx, ny, seed_fire_life())
                        grid.set_temp(nx, ny, _FIRE.burn_temp)
                    elif random.random() < CRATER_SMOKE_CHANCE:
                        grid.set(nx, ny, ElementId.SMOKE)
                        grid.set_life(nx, ny, seed_smoke_life())
                    else:
                        grid.set(nx, ny, ElementId.EMPTY)
                # 3. Scatter (outer) -- push loose materials one cell outward.
                elif _is_loose(nb) and random.random() < SCATTER_CHANCE:
                    sdx = (dx > 0) - (dx < 0)  # sign: outward x direction
                    sdy = (dy > 0) - (dy < 0)  # sign: outward y direction
                    tx, ty = nx + sdx, ny + sdy
                    if grid.in_bounds(tx, ty) and grid.get(tx, ty) == ElementId.EMPTY:
                        grid.set(tx, ty, nb)
                        grid.set_temp(tx, ty, grid.get_temp(nx, ny))
                        grid.set(nx, ny, ElementId.EMPTY)
```

> **Notes for the implementer.**
> - The `d == 0` center cell: when `explode` is called from `update_gunpowder`,
>   the center IS gunpowder, so step 1 heats it and the `if nb == GUNPOWDER:
>   continue` spares it from the crater/scatter. `update_gunpowder` then
>   overwrites the center with FIRE afterward (see §5). Good — no double-write
>   on the detonation cell.
> - Scatter carries `temp` explicitly (`set_temp(tx,ty,get_temp(nx,ny))`) but
>   NOT `life`. This is correct because `_is_loose` restricts scatter to
>   POWDER/LIQUID, whose life is always 0 (Decision #9). Do NOT scatter gases/
>   solids (fire/smoke/steam would lose their life — that is why they are
>   excluded).
> - The `abs(d - dist_ring) > 0.9` ring selector processes cells in bands of
>   ~width 1.8; combined with the outer-first `dist_ring` loop it visits each
>   in-radius cell exactly once per blast (a cell at distance d is selected only
>   when `dist_ring == round(d)`). Verify "each cell once" in the scatter test.
> - `random.random()` is read for CORE_FIRE_CHANCE / CRATER_SMOKE_CHANCE /
>   SCATTER_CHANCE; tests pin these deterministic via `monkeypatch.setattr`.

### 5. `src/sandfall/rules/gunpowder.py` (NEW)

Detonate (thermal trigger) first, then powder flow. Mirror `wood.py:24-30` for
the trigger shape and `sand.py:44-58` for the flow shape (sand has NO sideways
step — gunpowder is a powder, not a liquid):

```python
"""Gunpowder (POWDER, explosive) update rule.

Gunpowder is a powder (density 1.5, like SAND -> piles and falls like sand) that
DETONATES when its own temperature exceeds its flashpoint (~200). Each step:

1. **Detonate** -- if the cell's own temp exceeds its flashpoint, call
   :func:`sandfall.rules.blast.explode` (heat burst + crater + scatter over a
   circular radius), then overwrite THIS detonation cell with FIRE (the fireball:
   seed life, set hot temp) and return None. The blast heats other gunpowder in
   the radius past ITS flashpoint -> that gunpowder detonates on its own later
   scan / next frame (the chain propagates via heat, not recursion). Fire, lava,
   or another blast's heat all set it off.
2. **Flow** -- otherwise move like a powder (sand.py shape: straight down, then
   down-diagonals randomized; NO sideways -- gunpowder is a powder, not a liquid)
   via can_displace + swap.

Detonation transforms the own cell in place (-> FIRE) and returns None, so the
moved-this-frame guard is unaffected (reactive-rule relaxation, like wood/lava).
The blast's writes are side-effect writes caught by the dormant-cell wake
(id_changed + temp_changed); no wake-condition edit is needed (master plan
Risk #1).
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import can_displace, seed_fire_life, swap
from .blast import explode

_ELM = ELEMENTS[ElementId.GUNPOWDER]
_FIRE = ELEMENTS[ElementId.FIRE]


def update_gunpowder(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step a gunpowder cell: detonate when hot, else flow like a powder."""
    # 1. Detonate: own temp above flashpoint -> blast + become FIRE (fireball).
    if _ELM.flashpoint > 0 and grid.get_temp(x, y) > _ELM.flashpoint:
        explode(grid, x, y)
        grid.set(x, y, ElementId.FIRE)  # detonation cell -> fireball (consumed)
        grid.set_life(x, y, seed_fire_life())
        grid.set_temp(x, y, _FIRE.burn_temp)
        return None

    # 2. Otherwise flow like a powder (sand.py shape: down / down-diagonals).
    #    Straight down.
    if y + 1 < grid.height and can_displace(ElementId.GUNPOWDER, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)
    # Down-diagonals, randomized order.
    directions = [-1, 1]
    random.shuffle(directions)
    for dx in directions:
        nx = x + dx
        ny = y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.GUNPOWDER, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)
    return None
```

> GUNPOWDER has no finite life (it is consumed on detonation, not expired), so
> it needs NO `seed_*_life` helper and NO brush life-seeding change (`brush.py`
> seeds only FIRE/SMOKE/STEAM). Its `temp_spawn` defaults to `AMBIENT_TEMP`, so
> `paint_brush` needs no spawn-temp change. The palette swatch appears
> automatically (`ui.palette_layout` iterates `ElementId`).

### 6. `src/sandfall/rules/__init__.py`

**6a.** Import the new rule and (optionally) re-export `explode` for tests
(`rules/__init__.py:22-35`):

```python
from .blast import explode
from .gunpowder import update_gunpowder
```

> Re-exporting `explode` from `rules` is optional but convenient (`from
> sandfall.rules import explode`); tests can also import it from
> `sandfall.rules.blast` directly. If re-exported, add `"explode"` to `__all__`
> (`rules/__init__.py:45-51`) to satisfy mypy `no_implicit_reexport` (mirror the
> `seed_*_life` re-exports already there). Either way works — pick one and be
> consistent.

**6b.** Register the rule in `RULES` (`rules/__init__.py:53-71`):

```python
RULES: dict[ElementId, UpdateFn] = {
    ...,
    # Oil (light flammable liquid).
    ElementId.OIL: update_oil,
    # Gunpowder (explosive powder).
    ElementId.GUNPOWDER: update_gunpowder,
}
```

### 7. Renderer + palette verification (automatic — verify, do not edit)

- **Renderer LUT.** `build_color_lut` sizes from `len(ElementId)`
  (`renderer.py:37`) and iterates `ELEMENTS` (`renderer.py:39-42`), so the new
  color appears automatically. **Verify** (no edit) via a LUT-shape assertion in
  the new test file: `build_color_lut().shape[0] == len(ElementId) == 16`.
- **Palette.** `palette_layout` iterates `ElementId`, so the new swatch appears
  automatically. The `MIN_WINDOW_W` bump from 2b keeps it on-screen at the
  minimum size.

### 8. `tests/test_gunpowder.py` (NEW)

Deterministic tests using the seeded / single-cell / monkeypatch patterns from
`tests/test_phase.py:41-52` and `tests/test_acid_base.py:39-49`. Monkeypatch the
`blast` module globals for probabilistic behaviors (they are module globals read
at call time, like `fire.py`'s `SMOKE_CHANCE`):

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


# --- detonates when heated (the thermal trigger) ---
def test_gunpowder_detonates_when_heated(monkeypatch):
    """A gunpowder cell above its flashpoint detonates: cell -> FIRE. (On a 1x1
    grid the blast has no neighbors to touch, so this just proves the trigger
    fires and the detonation cell becomes the fireball.)"""
    import sandfall.rules.blast as blast
    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 1.0)
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)
    g = _step_single_cell(ElementId.GUNPOWDER, ELEMENTS[ElementId.GUNPOWDER].flashpoint + 50)
    assert g.get(0, 0) == ElementId.FIRE


def test_gunpowder_blast_affects_neighbors(monkeypatch):
    """Detonation destroys/ignites neighbors in the radius. Center gunpowder in
    a sand block, heat it, step -> center is FIRE and some sand in the crater is
    destroyed (not all sand remains). Pinned deterministic: crater -> EMPTY,
    core -> FIRE, no scatter."""
    import sandfall.rules.blast as blast
    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 1.0)
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "SCATTER_CHANCE", 0.0)
    random.seed(0)
    g = Grid(11, 11)
    for y in range(11):
        for x in range(11):
            g.set(x, y, ElementId.SAND)
    g.set(5, 5, ElementId.GUNPOWDER)
    g.set_temp(5, 5, ELEMENTS[ElementId.GUNPOWDER].flashpoint + 50)
    Simulation(g).step()
    assert g.get(5, 5) == ElementId.FIRE          # detonation cell -> fireball
    sand_after = int((g.array == int(ElementId.SAND)).sum())
    assert sand_after < 11 * 11 - 1               # some sand destroyed in the crater


# --- chain reaction (the headline; guards the dormant wake, Risk #1) ---
def test_gunpowder_chain_reaction_detonates_cluster():
    """Igniting one end of a gunpowder line detonates the WHOLE line over a few
    steps: each blast heats the next gunpowder past its flashpoint, which
    detonates on its own scan. Seed random. Assert all gunpowder is gone and
    fire/crater appears along the line. (Risk #1: if the chain stalls against
    dormant gunpowder, GUNPOWDER must join wake condition #3 -- pin finding.)"""
    random.seed(0)
    g = Grid(13, 5)
    # A horizontal line of gunpowder across row 2.
    for x in range(13):
        g.set(x, 2, ElementId.GUNPOWDER)
    # Ignite the left end with a hot FIRE.
    g.set(0, 2, ElementId.FIRE)
    g.set_temp(0, 2, ELEMENTS[ElementId.FIRE].burn_temp)
    g.set_life(0, 2, 40)
    sim = Simulation(g)
    gp_before = int((g.array == int(ElementId.GUNPOWDER)).sum())
    assert gp_before == 12  # the 12 non-ignited gunpowder cells
    for _ in range(120):
        sim.step()
    gp_after = int((g.array == int(ElementId.GUNPOWDER)).sum())
    assert gp_after < gp_before, (gp_before, gp_after)  # the chain advanced
    # The chain reaches across: almost all gunpowder is gone (allow a little
    # slack for scan/RNG edge effects; prototype-clean is ~0 remaining).
    assert gp_after <= 2, (gp_before, gp_after)


# --- destroys everything in the crater (user choice: no blast-resistant material) ---
def test_blast_destroys_everything_in_crater(monkeypatch):
    """Stone, glass, sand, wood, water placed in the inner crater (d <=
    CRATER_RADIUS) are all destroyed (-> EMPTY) by the blast. User chose
    'destroys everything'. Geometry: a 5x5 grid, detonator at the center (2,2),
    one of each material at d <= 2 (within the crater): STONE/GLASS/SAND/WOOD at
    d=2 on the axes, WATER at d~1.41 on the diagonal."""
    import sandfall.rules.blast as blast
    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 0.0)   # core -> not fire
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)  # crater -> EMPTY
    monkeypatch.setattr(blast, "SCATTER_CHANCE", 0.0)
    random.seed(0)
    g = Grid(5, 5)
    placements = {
        (0, 2): ElementId.STONE,   # d = 2 (axial)
        (4, 2): ElementId.GLASS,   # d = 2
        (2, 0): ElementId.SAND,    # d = 2
        (2, 4): ElementId.WOOD,    # d = 2
        (1, 1): ElementId.WATER,   # d = sqrt(2) ~ 1.41 (diagonal)
    }
    for (x, y), mat in placements.items():
        g.set(x, y, mat)
    g.set(2, 2, ElementId.GUNPOWDER)   # detonator at center
    g.set_temp(2, 2, ELEMENTS[ElementId.GUNPOWDER].flashpoint + 50)
    Simulation(g).step()
    # Every material in the crater was destroyed (no longer its original id).
    for (x, y), mat in placements.items():
        assert g.get(x, y) != mat, (mat, (x, y), g.get(x, y))


# --- heat burst ignites wood + boils water (via existing thresholds, no new code) ---
def test_blast_heat_ignites_wood_and_boils_water(monkeypatch):
    """The blast's heat burst ignites WOOD (flashpoint 300) and boils WATER
    (boil_point 100) in the outer ring via their OWN transition rules. Placed at
    d~3 (outside the crater d>2, within radius 4): at BLAST_HEAT~1200 the
    falloff (1 - 3/5 = 0.4) adds ~480C -> wood reaches ~500 (> 300 -> ignites)
    and water reaches ~500 (> 100 -> boils). Robust; stepped 60x so scan order
    and the FIRE persistent-source wake both get a chance to act. NOTE: sand->
    glass (melt_point 1700) is NOT asserted -- see Risk #4 (BLAST_HEAT~1200
    cannot reach 1700 at any non-crater distance)."""
    import sandfall.rules.blast as blast
    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "SCATTER_CHANCE", 0.0)
    random.seed(0)
    g = Grid(11, 5)
    # Detonator at (5,2). Wood/water column at x=8 (d ~ 3.0-3.6 from (5,2)):
    # all outside crater (d>2) and within radius 4.
    for y in range(3):           # wood at rows 0,1,2 of x=8
        g.set(8, y, ElementId.WOOD)
    for y in range(3, 5):        # water at rows 3,4 of x=8
        g.set(8, y, ElementId.WATER)
    g.set(5, 2, ElementId.GUNPOWDER)
    g.set_temp(5, 2, ELEMENTS[ElementId.GUNPOWDER].flashpoint + 50)
    sim = Simulation(g)
    for _ in range(60):
        sim.step()
    # Heat burst disturbed BOTH: wood ignited (-> FIRE -> later EMPTY) and/or was
    # destroyed; water boiled (-> STEAM) and/or was destroyed. Counts dropped.
    wood_after = int((g.array == int(ElementId.WOOD)).sum())
    water_after = int((g.array == int(ElementId.WATER)).sum())
    assert wood_after < 3, wood_after        # some/all wood ignited (was 3)
    assert water_after < 2, water_after      # some/all water boiled (was 2)


# --- scatter (knockback: loose materials pushed outward) ---
def test_blast_scatters_loose_material_outward(monkeypatch):
    """At SCATTER_CHANCE==1.0, loose material (sand) in the outer ring is pushed
    one cell outward (its position moves away from the blast center). Assert at
    least one loose cell moved, and no cell moved more than one cell (ring-order
    guard, Risk #3)."""
    import sandfall.rules.blast as blast
    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "SCATTER_CHANCE", 1.0)
    random.seed(0)
    g = Grid(11, 11)
    cx, cy = 5, 5
    # Ring of sand at d~3-4 around the detonator (outside the crater).
    sand_before = {}
    for y in range(11):
        for x in range(11):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if 3.0 <= d <= 4.0:
                g.set(x, y, ElementId.SAND)
                sand_before[(x, y)] = True
    g.set(cx, cy, ElementId.GUNPOWDER)
    g.set_temp(cx, cy, ELEMENTS[ElementId.GUNPOWDER].flashpoint + 50)
    Simulation(g).step()
    # At least one sand cell left its original position (was scattered outward).
    moved = [pos for pos in sand_before if g.get(*pos) != ElementId.SAND]
    assert moved, "expected at least one loose cell to be scattered outward"


# --- stable at ambient (does NOT explode; flows like a powder) ---
def test_gunpowder_at_ambient_stays_gunpowder():
    """Gunpowder at ambient temp does NOT detonate (stays gunpowder). On a 1x1
    grid it also cannot move, so it just stays gunpowder -- proving the trigger
    is threshold-gated, not unconditional."""
    g = _step_single_cell(ElementId.GUNPOWDER, 20)
    assert g.get(0, 0) == ElementId.GUNPOWDER


def test_gunpowder_flows_like_a_powder():
    """Gunpowder above an EMPTY cell falls one step (powder physics, like sand)."""
    random.seed(0)
    g = Grid(1, 3)
    g.set(0, 0, ElementId.GUNPOWDER)   # top cell, EMPTY below
    Simulation(g).step()
    # It fell at least one cell down (powder movement).
    ys = [y for y in range(g.height) if g.get(0, y) == ElementId.GUNPOWDER]
    assert ys and ys[0] >= 1


# --- density (gunpowder is sand-like: displaces water) ---
def test_gunpowder_density_like_sand():
    """GUNPOWDER (1.5) is denser than WATER (1.0): can_displace lets it sink
    through water (like sand)."""
    assert can_displace(ElementId.GUNPOWDER, int(ElementId.WATER)) is True
    assert can_displace(ElementId.WATER, int(ElementId.GUNPOWDER)) is False


# --- renderer LUT grew ---
def test_color_lut_has_16_rows():
    """build_color_lut sizes from len(ElementId). After this phase the enum has
    16 members (0..15). The assertion tracks len(ElementId) so the next element
    pass does not need to re-edit it."""
    assert build_color_lut().shape[0] == len(ElementId) == 16
```

> **Test-design notes.**
> - The detonation / crater / scatter tests pin the `blast` module globals
>   deterministic via `monkeypatch.setattr(blast, "...", value)` (the globals are
>   read at call time, exactly like `acid.py`'s `DISSOLVE_CHANCE` in
>   `tests/test_acid_base.py:55-66`). `random.seed(0)` is set too so the
>   randomized scan direction + `random.shuffle` are stable.
> - The chain-reaction test is the **headline** (guards Risk #1, the dormant
>   wake). It uses an eventual-assertion (`for _ in range(120): sim.step()`) like
>   `test_phase.py:83-116`'s freeze-spread test. If it fails (chain stalls), the
>   fallback is adding `GUNPOWDER` to wake condition #3 (`simulation.py:168-170`)
>   — pin the finding in the reflection.
> - The heat-burst test asserts the materials were **disturbed** (counts
>   dropped), not an exact product, because FIRE is finite-life and may have
>   expired some cells by assertion time — the same looser-assertion style as
>   `test_oil.py`'s fire-spread test. Sand→glass is deliberately NOT asserted
>   (Risk #4: `BLAST_HEAT` ~1200 cannot reach `SAND.melt_point` 1700).
> - The scatter test places sand in the outer ring (d 3–4, outside the crater)
>   so the crater logic does not destroy it before scatter runs.

### 9. Update existing tests for the wider palette

- `tests/test_ui.py:35` — `test_palette_layout_has_14_elements_then_3_tools`
  hardcodes `len(elements) == len(ElementId) - 1 == 14` (`test_ui.py:41`). Update
  the literal `14 → 15` (the `== len(ElementId) - 1` half auto-adjusts). Rename
  the test to `test_palette_layout_has_15_elements_then_3_tools` so the name
  reads right.
- `tests/test_ui.py:204-248` —
  `test_palette_resolves_phase03_elements_and_fits_min_window` hardcodes the
  `17 * PALETTE_SWATCH + 16 * PALETTE_PADDING + ...` math and asserts it fits
  `MIN_WINDOW_W`. Update the item count `17 → 18`, the padding count `16 → 17`,
  and add GUNPOWDER to the element-resolution check. The
  `last.x + last.w + PALETTE_MARGIN <= MIN_WINDOW_W` assertion must still hold.
- `tests/test_config.py:93-123` —
  `test_min_window_width_fits_full_palette_with_group_gap` hardcodes
  `MIN_WINDOW_W == 500` and the 17-item math. Update to `MIN_WINDOW_W == 528`,
  item count `17 → 18`, padding count `16 → 17`, and `MIN_GRID_COLS == 132`.

## Acceptance Criteria

- [ ] `ElementId` has 16 members (0–15); values 0–14 are unchanged
      (`int(SAND)==1`, `int(OIL)==14`); `GUNPOWDER==15`. `[e.value for e in
      ElementId] == list(range(16))`.
- [ ] GUNPOWDER has an `ELEMENTS` entry with `phase==POWDER`, `density==1.5`,
      `flashpoint==200`; `len(ELEMENTS) == 16`.
- [ ] Gunpowder **detonates when heated** above flashpoint (cell → FIRE) —
      single-cell test passes; and its **blast affects neighbors** (sand in the
      radius is destroyed) — neighbor test passes.
- [ ] **Chain reaction**: igniting one end of a gunpowder line detonates the
      whole line over a few steps (gunpowder count collapses to ~0) — headline
      integration test passes (Risk #1 verified; no `simulation.py` wake-condition
      edit was needed unless the reflection records otherwise).
- [ ] **Destroys everything in the crater**: stone/glass/sand/wood/water in the
      inner radius are all destroyed (no longer their original id) — deterministic
      test passes (Decision #5 verified).
- [ ] **Heat burst ignites/boils via existing thresholds**: wood is ignited
      (and/or destroyed) and water is boiled (and/or destroyed) in the outer ring
      — heat-burst test passes. (Sand→glass is NOT required — Risk #4.)
- [ ] **Scatter**: loose material (sand) in the outer ring is pushed outward (at
      least one cell left its original position at `SCATTER_CHANCE==1.0`) —
      scatter test passes.
- [ ] Gunpowder is **stable at ambient** (does not detonate; stays gunpowder) and
      **flows like a powder** (falls into EMPTY below) — ambient + flow tests pass.
- [ ] Gunpowder density is sand-like (`can_displace(GUNPOWDER, WATER)` True; the
      reverse False) — density test passes.
- [ ] `RULES` registry enumerates all 16 elements (15 real rules + EMPTY
      omitted); `len(RULES) >= 15`.
- [ ] `build_color_lut().shape[0] == len(ElementId) == 16`; palette has 15
      element swatches + 3 tools; `MIN_WINDOW_W == 528` and the 18-item row fits
      at the minimum size.
- [ ] Existing `test_ui.py` / `test_config.py` palette-count + min-width
      assertions updated and green; the FULL suite stays green.
- [ ] All verification gates (below) exit zero.

## Verification Commands

```bash
# Phase-focused new tests + the temperature regression (id-stable + dormant):
uv run pytest tests/test_gunpowder.py tests/test_phase.py -v

# Confirm the enum + registry grew and the stable indices held:
uv run python -c "from sandfall.elements import ElementId; from sandfall.rules import RULES; assert [e.value for e in ElementId]==list(range(16)); assert int(ElementId.OIL)==14 and int(ElementId.GUNPOWDER)==15; assert len(RULES)>=15; print('enum+registry OK')"

# Confirm palette min-width math: 18 items fit in MIN_WINDOW_W.
uv run python -c "from sandfall.config import MIN_WINDOW_W, PALETTE_GROUP_GAP, PALETTE_MARGIN, PALETTE_PADDING, PALETTE_SWATCH; need=18*PALETTE_SWATCH+17*PALETTE_PADDING+PALETTE_GROUP_GAP+2*PALETTE_MARGIN; assert MIN_WINDOW_W==528 and MIN_WINDOW_W>=need, (MIN_WINDOW_W, need); print('palette fits', need, '<=', MIN_WINDOW_W)"

# FULL suite (existing tests stay green):
uv run pytest

# Lint + format + type-check:
uv run ruff check . && uv run ruff format --check . && uv run mypy src

# SDL smoke (headless fallback if no display):
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
#   Manual check on DISPLAY=:1: pile GUNPOWDER (piles like sand), drop FIRE or
#   LAVA onto the pile (BOOM -- chain detonates the pile), place a WOOD wall
#   near the pile (heat ignites it), watch SAND scatter outward from the blast.
```

All commands must exit zero.

## Documentation Updates

- `docs/ARCHITECTURE.md:248-257` — append `GUNPOWDER=15` to the `ElementId`
  member list (after the OIL entry). Optionally add a one-line note to the
  "Adding a new element" recipe (`ARCHITECTURE.md:510-545`) that an explosive
  element's detonation is a radius side-effect write via the reusable
  `blast.explode` helper (mirrors how `lava.py`'s neighbor reaction is already
  documented).
- `.agent/tasks/BACKLOG.md:27-31` — strike **"gunpowder"** from the "More
  elements" line (acid/oil are already struck there; leave salt/metal/
  electricity). Add a "Recently shipped" entry referencing this plan.
- `README.md` — if it has a Features/elements table, add a GUNPOWDER row (and
  confirm the ACID/BASE/OIL rows from the prior plan are present).

## Reflection & Commit

After implementation, write `01-gunpowder-blast-reflection.md`. Include:
- the **final tuned values** for `BLAST_RADIUS` / `CRATER_RADIUS` / `BLAST_HEAT`
  / `CORE_FIRE_CHANCE` / `CRATER_SMOKE_CHANCE` / `SCATTER_CHANCE` / flashpoint /
  density (Decision #11);
- the **dormant-interaction finding** (did the chain-reaction test pass without a
  wake-condition edit, or did `GUNPOWDER` have to join condition #3? — Risk #1);
- the **`BLAST_HEAT`-vs-melt decision** (was sand→glass dropped, or did you bump
  `BLAST_HEAT` to make it work? — Risk #4);
- the **ring-order / double-move finding** (did the scatter test confirm each
  cell moved ≤1 outward? — Risk #3);
- the **acid-dissolves-gunpowder choice** (left default, or added GUNPOWDER to
  the resist sets? — Risk #7);
- the observed worst-case **performance** of a large pile detonation (Risk #2);
- anything fun or unexpected.

Then make ONE atomic git commit covering all changes in this phase.

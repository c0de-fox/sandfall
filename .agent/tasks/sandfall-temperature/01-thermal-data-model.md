# Phase 01: Thermal data model (temp array + diffusion + plumbing)

## Objective

Add a per-cell **temperature field** to the simulation as a third parallel array
on `Grid` (`_temp`, `int16`), wire it through every seam the existing `_life`
array already crosses (`swap`, `fill_circle`, `migrate_grid`, `paint_brush`),
extend the `Element` dataclass with thermal fields, add `AMBIENT_TEMP` and
diffusion tunables to `config.py`, create a new pure module
`src/sandfall/thermal.py` with a numerically-stable vectorized `diffuse_temps`
plus a conductivity LUT builder, and run the diffusion pass **before** the
movement scan in `Simulation.step`. **No visible behavior change** in this phase
— pure plumbing. The new field exists, flows, and is tested; Phase 02 makes it
do something.

## Depends On

none — first phase.

## Can Parallelize With

none — every later phase builds on this data model.

## Recommended Agent

@implementer — foundational data-model change rippling through 6 files plus a
new pure module. Read each file before editing; mypy is strict throughout and
the frozen `Element` dataclass addition needs care (defaults for every field).

## Changes Required

- `src/sandfall/config.py` — add `AMBIENT_TEMP`, `TEMP_MIN`, `TEMP_MAX`, and the
  diffusion tunables `DIFFUSION_RATE` + `COND_*` per-material conductivities.
- `src/sandfall/elements.py` — extend the `Element` dataclass with thermal
  fields (`temp_spawn`, `flashpoint`, `conductivity`, `burn_temp`, plus
  transition thresholds used in Phase 03); set sensible defaults on every field
  so the existing `ELEMENTS` entries still construct.
- `src/sandfall/grid.py` — add `_temp: NDArray[int16]` + `get_temp`/`set_temp`
  (clip to `[TEMP_MIN, TEMP_MAX]`); carry temp in `swap`, `fill_circle`
  (→`AMBIENT_TEMP`), and `migrate_grid`.
- `src/sandfall/rules/_common.py` — `swap` must now carry temp (id + life + temp).
- `src/sandfall/brush.py` — `paint_brush` sets spawn-temp after `fill_circle`
  (mirrors its life-seeding pass).
- `src/sandfall/thermal.py` (NEW) — pure `diffuse_temps(temp, ids, cond_lut,
  rate)` + `build_conductivity_lut()`; pygame-free → unit-tested headlessly.
- `src/sandfall/simulation.py` — call diffusion once at the top of `step`,
  before the movement scan.
- `tests/test_grid.py` — temp get/set/clip/swap/fill_circle/migrate.
- `tests/test_thermal.py` (NEW) — diffusion math (heat flows hot→cold;
  low-conductivity transfers slowly; equilibrium reached; no overshoot when
  `rate*cond<=0.25`; `int16` clip).
- `tests/test_brush.py` — `paint_brush` sets spawn-temp for FIRE (and leaves
  non-thermal elements at `AMBIENT_TEMP`).

## Implementation Instructions

> Re-read each file before editing — line numbers below are current as of the
> v1 + improvements source and will not shift *within* this phase, but the
> frozen-dataclass change in particular must be applied in one coherent edit.

### 1. `src/sandfall/config.py`

**1a. Add the temperature band + ambient constant** in a new section near the
"Loop" / "Colors" blocks (after line 55 `FPS = 60` is a fine spot):

```python
# --- Temperature field (Phase 01) ------------------------------------------
# Per-cell temperature, integer degrees-C-like, stored as int16 on Grid.
# AMBIENT_TEMP is the resting temperature every cell initializes to and that
# fill_circle resets to (mirrors how it zeroes life). The clip band is wide
# enough for sand melting (~1700) and sub-zero freezing; int16 headroom is huge.
AMBIENT_TEMP = 20
TEMP_MIN = -200
TEMP_MAX = 3000

# Diffusion pre-pass tunables. diffuse_temps advances each cell toward the
# 4-neighborhood average weighted by the cell's OWN conductivity:
#     new = temp + rate * cond[cell] * (left+right+up+down - 4*temp)
# Stability of this explicit stencil requires rate * max(cond) <= 0.25; the
# defaults below (0.20 * 0.5 == 0.10) sit comfortably inside that bound, and
# diffuse_temps additionally clips the result to [TEMP_MIN, TEMP_MAX].
DIFFUSION_RATE = 0.20

# Per-material heat conductivity (0.0 = perfect insulator, 1.0 = max). Indexed
# by element id via build_conductivity_lut(). EMPTY is given a small non-zero
# value so heat propagates through air (otherwise fire could not warm fuel it
# is not adjacent to); high-conductivity materials (FIRE, metals) equilibrate
# fast, insulators (STONE) equilibrate slowly.
COND_EMPTY = 0.10
COND_SAND = 0.15
COND_WATER = 0.35
COND_STONE = 0.08
COND_WOOD = 0.12
COND_FIRE = 0.50
COND_SMOKE = 0.20
COND_PLANT = 0.12
```

(Phase 03 will add `COND_STEAM`, `COND_ICE`, `COND_LAVA`, `COND_GLASS` here; do
not add them yet.)

### 2. `src/sandfall/elements.py`

**2a. Extend the `Element` dataclass** (currently `elements.py:35-44`) with the
thermal fields. Every new field MUST have a default so the existing `ELEMENTS`
entries (which don't mention them) still construct unchanged:

```python
@dataclass(frozen=True, slots=True)
class Element:
    """Static definition of an element kind."""

    id: ElementId
    name: str
    color: tuple[int, int, int]  # RGB 0..255
    density: float
    phase: Phase
    flammability: float = 0.0  # 0.0 = never burns; 1.0 = always burns on contact
    # --- Thermal fields (Phase 01) -----------------------------------------
    # Temperature a freshly painted/spawned cell of this element starts at
    # (AMBIENT_TEMP for most; high for FIRE/LAVA — Phase 02/03). Mirrors how
    # brush.paint_brush seeds life for FIRE/SMOKE.
    temp_spawn: int = AMBIENT_TEMP
    # Auto-ignition threshold: a cell of this element ignites (becomes FIRE)
    # when its OWN temp exceeds flashpoint. 0 means NEVER (the default) — the
    # Phase 02 reactive wood/plant rules check `flashpoint > 0 and temp >
    # flashpoint`. Replaces the old probabilistic SPREAD_FACTOR.
    flashpoint: int = 0
    # Heat conductivity scalar in [0.0, 1.0]; also stored in the conductivity
    # LUT (config.COND_*). Kept on Element too so ELEMENTS is the single
    # registry a contributor edits when adding a material.
    conductivity: float = 0.0
    # Temperature a FIRE cell (or other heat source) of this material holds
    # while burning. Phase 02 sets WOOD/PLANT burn_temp on the cell when they
    # ignite; FIRE's own rule maintains its burn_temp each step.
    burn_temp: int = AMBIENT_TEMP
    # --- Phase-change thresholds (used in Phase 03; declared here so the
    # dataclass shape is stable across phases). 0 means "this element does not
    # undergo this transition".
    melt_point: int = 0      # above this temp, this element melts (ice->water)
    boil_point: int = 0      # above this temp, this element boils (water->steam)
    freeze_point: int = 0    # below this temp, this element freezes (water->ice)
    condense_point: int = 0  # below this temp, this element condenses (steam->water)
```

Add `from .config import AMBIENT_TEMP` to the imports at the top of
`elements.py`. **Watch for a circular import:** `config.py` imports
`from .elements import ElementId` (`config.py:9`). Break the cycle by importing
`AMBIENT_TEMP` lazily inside the dataclass default via `field(default_factory=...)`
OR — cleaner — move `AMBIENT_TEMP`/`TEMP_*` into a tiny constants block at the
TOP of `elements.py` (above the dataclass) and have `config.py` re-import them
from `elements`. **Recommended: put `AMBIENT_TEMP`/`TEMP_MIN`/`TEMP_MAX` in
`elements.py` and re-export from `config.py`** so `elements.py` has no dependency
on `config.py`. Document whichever you pick in the reflection.

**2b. Populate the thermal fields on the existing entries** that need non-default
values (the rest inherit the defaults). FIRE and WOOD/PLANT get the values
Phase 02 tunes against:

```python
ElementId.WOOD: Element(
    ...,
    flammability=0.25,   # flammability is now legacy/unused for spread but kept
    temp_spawn=AMBIENT_TEMP,
    flashpoint=300,      # ignites when its own temp exceeds 300
    conductivity=0.12,
    burn_temp=800,       # holds ~800 while burning
),
ElementId.PLANT: Element(
    ...,
    flammability=0.4,
    temp_spawn=AMBIENT_TEMP,
    flashpoint=250,
    conductivity=0.12,
    burn_temp=700,
),
ElementId.FIRE: Element(
    ...,
    temp_spawn=800,      # a painted fire starts hot
    conductivity=0.50,
    burn_temp=800,
),
ElementId.SAND: Element(..., conductivity=0.15),
ElementId.WATER: Element(..., conductivity=0.35, boil_point=100, freeze_point=0),
ElementId.STONE: Element(..., conductivity=0.08),
ElementId.SMOKE: Element(..., conductivity=0.20),
ElementId.EMPTY: Element(..., conductivity=0.10),
```

(`boil_point`/`freeze_point` on WATER are set now so the dataclass is populated;
the WATER rule that reads them lands in Phase 03.) Leave the `flammability` field
in place for now — Phase 02 removes its only reader (`SPREAD_FACTOR`); removing
the field itself is out of scope (it's a harmless registry datum) unless mypy/ruff
flag an unused field (they won't — it's data, not code).

### 3. `src/sandfall/grid.py`

**3a. Add the `_temp` array** alongside `_data`/`_life` (`grid.py:33-44`). Add
the attribute declaration and allocate in `__init__`:

```python
_temp: npt.NDArray[np.int16]

def __init__(self, width: int, height: int) -> None:
    ...
    self._data = np.zeros((height, width), dtype=np.uint8)
    self._life = np.zeros((height, width), dtype=np.uint8)
    self._temp = np.full((height, width), AMBIENT_TEMP, dtype=np.int16)
```

Import `AMBIENT_TEMP`, `TEMP_MIN`, `TEMP_MAX` (from wherever 2a settled them).

**3b. Add a `temp` property** mirroring the `life` property (`grid.py:62-69`):

```python
@property
def temp(self) -> npt.NDArray[np.int16]:
    """Raw ``(height, width)`` int16 view of per-cell temperature.

    Intended read-only access (e.g. for the diffusion pass and the heat
    overlay); mutate via :meth:`set_temp` so clipping is applied consistently.
    """
    return self._temp
```

**3c. Add `get_temp`/`set_temp`** mirroring `get_life`/`set_life`
(`grid.py:99-122`), but clipping to `[TEMP_MIN, TEMP_MAX]` instead of `[0, 255]`:

```python
def get_temp(self, x: int, y: int) -> int:
    """Return the temperature at ``(x, y)`` as a plain ``int``.

    Raises ``IndexError`` if out of bounds.
    """
    if not self.in_bounds(x, y):
        raise IndexError(
            f"({x}, {y}) out of bounds for {self._width}x{self._height} grid"
        )
    return int(self._temp[y, x])

def set_temp(self, x: int, y: int, value: int) -> None:
    """Set the temperature at ``(x, y)`` (clipped to ``[TEMP_MIN, TEMP_MAX]``).

    Out-of-bounds writes are silently ignored to mirror :meth:`set` /
    :meth:`set_life`.
    """
    if not self.in_bounds(x, y):
        return
    if value < TEMP_MIN:
        value = TEMP_MIN
    elif value > TEMP_MAX:
        value = TEMP_MAX
    self._temp[y, x] = value
```

**3d. Carry temp in `fill_circle`.** Both the `radius == 0` path
(`grid.py:137-140`) and the loop (`grid.py:147-153`) currently zero life; now
also reset temp to `AMBIENT_TEMP` (mirrors "brushes that overwrite a burning
cell should not leave stale state"):

```python
if radius == 0:
    self.set(cx, cy, element_id)
    self.set_life(cx, cy, 0)
    self.set_temp(cx, cy, AMBIENT_TEMP)
    return
...
    if dx * dx + dy * dy <= r2:
        self._data[y, x] = eid
        self._life[y, x] = 0
        self._temp[y, x] = AMBIENT_TEMP
```

**3e. Carry temp in `migrate_grid`.** Add one line to copy the temp overlap
(`grid.py:169-173`):

```python
if w > 0 and h > 0:
    new._data[:h, :w] = old._data[:h, :w]
    new._life[:h, :w] = old._life[:h, :w]
    new._temp[:h, :w] = old._temp[:h, :w]
```

Update the `migrate_grid` docstring to say "ids AND life AND temp".

### 4. `src/sandfall/rules/_common.py`

**4a. Carry temp in `swap`.** Add the temp exchange to `swap` (`_common.py:61-75`)
so moves keep all three arrays consistent:

```python
def swap(grid: Grid, x1: int, y1: int, x2: int, y2: int) -> None:
    """Swap the contents (element id AND life AND temp) of two in-bounds cells."""
    a = grid.get(x1, y1)
    b = grid.get(x2, y2)
    grid.set(x1, y1, b)
    grid.set(x2, y2, a)
    la = grid.get_life(x1, y1)
    lb = grid.get_life(x2, y2)
    grid.set_life(x1, y1, lb)
    grid.set_life(x2, y2, la)
    ta = grid.get_temp(x1, y1)
    tb = grid.get_temp(x2, y2)
    grid.set_temp(x1, y1, tb)
    grid.set_temp(x2, y2, ta)
```

Update the module docstring's mention of "id AND life" to "id AND life AND temp"
where relevant.

### 5. `src/sandfall/brush.py`

**5a. Set spawn-temp after `fill_circle`.** `paint_brush` already does a
life-seeding pass for FIRE/SMOKE (`brush.py:37-52`); mirror it for temp. After
the `fill_circle` call (which resets every painted cell to `AMBIENT_TEMP`), walk
the disk once more and set each painted cell's temp to its element's
`temp_spawn`. The cleanest form covers ALL elements uniformly (read
`ELEMENTS[element_id].temp_spawn`), which also future-proofs LAVA's hot
spawn-temp in Phase 03:

```python
from .elements import ELEMENTS, ElementId
...
def paint_brush(grid, gx, gy, radius, element_id):
    grid.fill_circle(gx, gy, radius, element_id)
    spawn_temp = ELEMENTS[element_id].temp_spawn
    # life-seeding for FIRE/SMOKE (unchanged)
    seed = seed_fire_life if element_id == ElementId.FIRE else (
        seed_smoke_life if element_id == ElementId.SMOKE else None
    )
    r2 = radius * radius
    x0 = max(0, gx - radius)
    x1 = min(grid.width - 1, gx + radius)
    y0 = max(0, gy - radius)
    y1 = min(grid.height - 1, gy + radius)
    for y in range(y0, y1 + 1):
        dy = y - gy
        for x in range(x0, x1 + 1):
            dx = x - gx
            if dx * dx + dy * dy <= r2 and grid.get(x, y) == element_id:
                if spawn_temp != AMBIENT_TEMP:
                    grid.set_temp(x, y, spawn_temp)
                if seed is not None:
                    grid.set_life(x, y, seed())
```

Keep the existing structure if you prefer (early-return for non-FIRE/SMOKE) —
the contract is "painted cell has `ELEMENTS[id].temp_spawn` after the brush".
The `AMBIENT_TEMP` short-circuit is a minor perf nicety (skip writes that would
be no-ops since `fill_circle` already set `AMBIENT_TEMP`).

### 6. `src/sandfall/thermal.py` (NEW)

**6a. Create the module.** Pure (numpy-only), pygame-free, headless-testable.
Two functions:

```python
"""Temperature field diffusion + visualization (Phase 01/04).

Pure numpy module: no pygame import, so the diffusion math and the heat->RGB
mapping are unit-testable headlessly. ``diffuse_temps`` is the per-frame heat
pre-pass run by :class:`sandfall.simulation.Simulation` BEFORE the movement
scan; ``build_conductivity_lut`` mirrors :func:`sandfall.renderer.build_color_lut`
to turn the per-material ``COND_*`` scalars into an id-indexed LUT.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .config import (
    COND_EMPTY, COND_FIRE, COND_PLANT, COND_SAND, COND_SMOKE,
    COND_STONE, COND_WATER, DIFFUSION_RATE, TEMP_MAX, TEMP_MIN,
)
from .elements import ElementId


def build_conductivity_lut() -> npt.NDArray[np.float64]:
    """Build the element-id -> conductivity LUT (mirrors build_color_lut).

    Shape ``(len(ElementId),)`` float64; row ``int(eid)`` is that material's
    heat conductivity. Indexed by the grid's id array to get a per-cell
    conductivity field for ``diffuse_temps``.
    """
    lut = np.zeros(len(ElementId), dtype=np.float64)
    lut[int(ElementId.EMPTY)] = COND_EMPTY
    lut[int(ElementId.SAND)] = COND_SAND
    lut[int(ElementId.WATER)] = COND_WATER
    lut[int(ElementId.STONE)] = COND_STONE
    lut[int(ElementId.WOOD)] = COND_WOOD
    lut[int(ElementId.FIRE)] = COND_FIRE
    lut[int(ElementId.SMOKE)] = COND_SMOKE
    lut[int(ElementId.PLANT)] = COND_PLANT
    return lut
```

(`COND_WOOD` must be added to `config.py` — add `COND_WOOD = 0.12` alongside the
others in 1a.) Then the diffusion kernel:

```python
def diffuse_temps(
    temp: npt.NDArray[np.int16],
    ids: npt.NDArray[np.uint8],
    cond_lut: npt.NDArray[np.float64],
    rate: float = DIFFUSION_RATE,
) -> npt.NDArray[np.int16]:
    """Advance the temperature field one diffusion step. Returns a NEW array.

    Each cell moves toward the 4-neighborhood average weighted by its OWN
    conductivity:

        new = temp + rate * cond[cell] * (left+right+up+down - 4*temp)

    Boundaries are edge-padded (replicate) so the grid walls act as insulators
    (no heat flux across the edge). Computation is done in float64 to avoid
    int16 overflow in the Laplacian (4*temp up to 4*TEMP_MAX), then the result
    is clipped to ``[TEMP_MIN, TEMP_MAX]`` and cast back to int16. The explicit
    stencil is stable when ``rate * max(cond) <= 0.25``; the defaults
    (0.20 * 0.50 == 0.10) sit well inside that bound. Pure / pygame-free ->
    unit-tested headlessly.
    """
    # Edge-pad so neighbor sums at the border use the border cell itself
    # (insulated walls: no heat crosses the grid edge).
    padded = np.pad(temp, pad_width=1, mode="edge").astype(np.float64)
    left = padded[1:-1, 0:-2]
    right = padded[1:-1, 2:]
    up = padded[0:-2, 1:-1]
    down = padded[2:, 1:-1]
    neighbor_sum = left + right + up + down

    cond = cond_lut[ids]  # per-cell conductivity, shape (H, W) float64
    t = temp.astype(np.float64)
    delta = rate * cond * (neighbor_sum - 4.0 * t)
    new_temp = t + delta
    np.clip(new_temp, TEMP_MIN, TEMP_MAX, out=new_temp)
    return new_temp.astype(np.int16)
```

Note the function is **pure and returns a new array** (it does not mutate
`temp` in place). `Simulation.step` assigns the result back to the grid's
`_temp` (see 7a). This makes it trivially unit-testable and avoids aliasing
surprises in the movement scan that follows.

### 7. `src/sandfall/simulation.py`

**7a. Run diffusion before the scan.** At the top of `step`
(`simulation.py:32-56`), before the `moved` guard allocation, diffuse the grid's
temp in place. `Simulation` caches the conductivity LUT once (it never changes
unless `ELEMENTS`/`config` change, which is static for a run):

```python
from .thermal import build_conductivity_lut, diffuse_temps
...
class Simulation:
    def __init__(self, grid: Grid) -> None:
        self._grid = grid
        self._cond_lut = build_conductivity_lut()

    def step(self) -> None:
        grid = self._grid
        # Heat diffusion pre-pass (Phase 01): one vectorized op BEFORE the
        # movement scan, so every rule reads a freshly-diffused temperature.
        grid._temp = diffuse_temps(grid._temp, grid._data, self._cond_lut)
        moved = ...
```

> Accessing `grid._temp` directly is fine — `Simulation` and `Grid` are sibling
> modules in the same package and the existing code already reaches into
> `grid._data`/`grid._life` via the public `array`/`life` properties. If you
> prefer not to touch the underscore attribute, expose a `set_temp_array(...)`
> helper or assign through a new `Grid.temp` setter — either is acceptable; pin
> the choice in the reflection. The `migrate_grid` precedent (`grid.py:172`)
> already reaches into the private arrays from a sibling, so direct assignment
> is consistent with the codebase.

### 8. Tests

**8a. `tests/test_grid.py`** — add a temperature block mirroring the life block
(`test_grid.py:123-181`):

```python
def test_temp_array_defaults_to_ambient() -> None:
    from sandfall.config import AMBIENT_TEMP
    grid = Grid(width=4, height=4)
    assert grid.temp.shape == (4, 4)
    assert grid.temp.dtype == np.int16
    for y in range(grid.height):
        for x in range(grid.width):
            assert grid.get_temp(x, y) == AMBIENT_TEMP

def test_set_temp_get_temp_round_trip() -> None:
    grid = Grid(width=3, height=3)
    grid.set_temp(1, 1, 1500)
    assert grid.get_temp(1, 1) == 1500
    assert grid.get_temp(0, 0) == 20  # AMBIENT

def test_set_temp_clips_to_band() -> None:
    from sandfall.config import TEMP_MAX, TEMP_MIN
    grid = Grid(width=3, height=3)
    grid.set_temp(0, 0, -5000)
    assert grid.get_temp(0, 0) == TEMP_MIN
    grid.set_temp(0, 0, 99999)
    assert grid.get_temp(0, 0) == TEMP_MAX

def test_set_temp_out_of_bounds_is_silent() -> None:
    grid = Grid(width=3, height=3)
    grid.set_temp(-1, 0, 100)
    grid.set_temp(0, 5, 100)
    grid.set_temp(3, 3, 100)

def test_get_temp_out_of_bounds_raises() -> None:
    grid = Grid(width=3, height=3)
    with pytest.raises(IndexError):
        grid.get_temp(-1, 0)
    with pytest.raises(IndexError):
        grid.get_temp(3, 0)

def test_swap_carries_temp() -> None:
    from sandfall.rules._common import swap
    grid = Grid(width=3, height=3)
    grid.set(0, 0, ElementId.SAND)
    grid.set_temp(0, 0, 900)
    grid.set(1, 1, ElementId.WATER)
    grid.set_temp(1, 1, 10)
    swap(grid, 0, 0, 1, 1)
    assert grid.get(0, 0) == ElementId.WATER
    assert grid.get_temp(0, 0) == 10
    assert grid.get(1, 1) == ElementId.SAND
    assert grid.get_temp(1, 1) == 900

def test_fill_circle_resets_temp_to_ambient() -> None:
    from sandfall.config import AMBIENT_TEMP
    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.FIRE)
    grid.set_temp(2, 2, 1200)
    grid.fill_circle(2, 2, 0, ElementId.SAND)
    assert grid.get(2, 2) == ElementId.SAND
    assert grid.get_temp(2, 2) == AMBIENT_TEMP
```

And extend the existing `migrate_grid` tests (`test_grid.py:187-295`) to assert
temp is carried in the overlap and dropped outside (add a `set_temp` + assert
on at least the grow and same-size cases). Pattern:

```python
def test_migrate_grid_grow_carries_temp_in_overlap() -> None:
    old = Grid(3, 3)
    old.set_temp(1, 1, 500)
    new = Grid(5, 5)
    migrate_grid(old, new)
    assert new.get_temp(1, 1) == 500
    assert new.get_temp(4, 4) == 20  # AMBIENT default in the new exposed cell
```

**8b. `tests/test_thermal.py` (NEW)** — the diffusion math. Seed small grids and
assert directional/quantitative outcomes:

```python
import numpy as np
from sandfall.config import AMBIENT_TEMP, TEMP_MAX
from sandfall.elements import ElementId
from sandfall.thermal import build_conductivity_lut, diffuse_temps

def _ids_fill(shape, eid): ...

def test_heat_flows_hot_to_cold():
    # One hot cell in a uniform-conductivity field warms its neighbors next step.
    temp = np.full((3, 3), AMBIENT_TEMP, dtype=np.int16)
    temp[1, 1] = 1000
    ids = np.full((3, 3), int(ElementId.EMPTY), dtype=np.uint8)  # COND_EMPTY
    lut = build_conductivity_lut()
    out = diffuse_temps(temp, ids, lut, rate=0.2)
    # Center cooled; the 4 orthogonal neighbors warmed above ambient.
    assert out[1, 1] < 1000
    for (y, x) in [(0, 1), (2, 1), (1, 0), (1, 2)]:
        assert out[y, x] > AMBIENT_TEMP
    # Corners are NOT 4-neighbors of center -> unchanged at ambient.
    for (y, x) in [(0, 0), (0, 2), (2, 0), (2, 2)]:
        assert out[y, x] == AMBIENT_TEMP

def test_low_conductivity_transfers_slowly():
    # An insulator (STONE, low cond) moves less heat than a conductor (EMPTY).
    base = np.zeros((1, 3), dtype=np.int16); base[0, 0] = 0; base[0, 1] = 1000; base[0, 2] = 0
    lut = build_conductivity_lut()
    ids_stone = np.full((1, 3), int(ElementId.STONE), dtype=np.uint8)
    ids_empty = np.full((1, 3), int(ElementId.EMPTY), dtype=np.uint8)
    out_stone = diffuse_temps(base.copy(), ids_stone, lut, rate=0.2)
    out_empty = diffuse_temps(base.copy(), ids_empty, lut, rate=0.2)
    # The middle cell cooled more (transferred more) under the higher conductor.
    assert out_empty[0, 1] < out_stone[0, 1]

def test_uniform_field_is_equilibrium():
    # A uniform-temperature field does not change.
    temp = np.full((5, 5), 300, dtype=np.int16)
    ids = np.full((5, 5), int(ElementId.SAND), dtype=np.uint8)
    out = diffuse_temps(temp, ids, build_conductivity_lut(), rate=0.2)
    assert np.array_equal(out, temp)

def test_no_overshoot_at_stability_bound():
    # rate*cond == 0.25 (the stability limit) must not overshoot the neighbor
    # mean: a 0/1000 pair cannot swing past [0, 1000].
    temp = np.zeros((1, 2), dtype=np.int16); temp[0, 1] = 1000
    ids = np.zeros((1, 2), dtype=np.uint8)  # EMPTY
    lut = build_conductivity_lut()
    out = diffuse_temps(temp, ids, lut, rate=0.25 / lut[int(ElementId.EMPTY)])
    assert out.min() >= 0
    assert out.max() <= 1000

def test_clips_to_int16_band():
    temp = np.full((2, 2), TEMP_MAX, dtype=np.int16)
    ids = np.full((2, 2), int(ElementId.FIRE), dtype=np.uint8)
    out = diffuse_temps(temp, ids, build_conductivity_lut(), rate=1.0)
    assert out.max() <= TEMP_MAX

def test_diffuse_returns_new_array_does_not_mutate_input():
    temp = np.full((3, 3), AMBIENT_TEMP, dtype=np.int16)
    temp[1, 1] = 800
    ids = np.full((3, 3), int(ElementId.EMPTY), dtype=np.uint8)
    before = temp.copy()
    diffuse_temps(temp, ids, build_conductivity_lut(), rate=0.2)
    assert np.array_equal(temp, before)  # input untouched
```

**8c. `tests/test_brush.py`** — assert spawn-temp:

```python
def test_paint_brush_fire_sets_spawn_temp():
    from sandfall.elements import ELEMENTS
    grid = Grid(20, 20)
    paint_brush(grid, 10, 10, 2, ElementId.FIRE)
    for x, y in _painted_cells(grid, ElementId.FIRE):
        assert grid.get_temp(x, y) == ELEMENTS[ElementId.FIRE].temp_spawn

def test_paint_brush_non_thermal_elements_at_ambient():
    from sandfall.config import AMBIENT_TEMP
    grid = Grid(20, 20)
    for eid in (ElementId.SAND, ElementId.WATER, ElementId.STONE):
        paint_brush(grid, 10, 10, 2, eid)
        for x, y in _painted_cells(grid, eid):
            assert grid.get_temp(x, y) == AMBIENT_TEMP
```

## Acceptance Criteria

- [ ] `Grid` has an `int16` `_temp` array initialized to `AMBIENT_TEMP` (20)
      everywhere; `temp` property exposes it read-only.
- [ ] `get_temp`/`set_temp` round-trip; `set_temp` clips to `[TEMP_MIN,
      TEMP_MAX]`; out-of-bounds writes are silent; out-of-bounds reads raise
      `IndexError` (tests pass).
- [ ] `swap` carries id + life + temp; `fill_circle` resets temp to
      `AMBIENT_TEMP`; `migrate_grid` copies the temp overlap (tests pass).
- [ ] `Element` dataclass has the thermal fields, all defaulted, and every
      existing `ELEMENTS` entry still constructs (import succeeds, no
      `TypeError`).
- [ ] `thermal.diffuse_temps` is pure, returns a new `int16` array, does not
      mutate its input, flows heat hot→cold, transfers slower for insulators,
      leaves a uniform field unchanged, does not overshoot at `rate*cond==0.25`,
      and clips to the band (tests pass).
- [ ] `thermal.build_conductivity_lut` returns a `(len(ElementId),)` float64
      array indexed by element id.
- [ ] `Simulation.step` runs diffusion once before the movement scan; the
      conductivity LUT is built once in `__init__`.
- [ ] `paint_brush` sets `ELEMENTS[id].temp_spawn` on painted cells (FIRE hot,
      others ambient) (tests pass).
- [ ] **No visible behavior change** — the v1 game still plays identically
      (fire still spreads via the OLD probabilistic path this phase does NOT
      touch; that removal is Phase 02). The `SANDFALL_FRAMES=60` smoke runs
      clean.
- [ ] All six gates exit zero. **Record the measured per-frame cost** of the
      diffusion pass in the reflection (see Risk #2 in the overview).

## Verification Commands

```bash
# Phase-specific (pure helpers + plumbing):
uv run pytest tests/test_thermal.py tests/test_grid.py tests/test_brush.py -v
# Confirm no circular import between config <-> elements:
uv run python -c "import sandfall.config, sandfall.elements, sandfall.thermal, sandfall.simulation; print('imports clean')"

# The six gates (all must exit zero):
uv run python -c "import sandfall"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
```

All commands must exit zero. Do NOT proceed to Phase 02 until all pass.

## Documentation Updates

- `docs/ARCHITECTURE.md` — Phase 04 writes the thermal section in one coherent
  pass; this phase only needs the code in place. If you add any inline docstring
  clarifying the config↔elements import direction (Decision 2a), leave it; the
  full ARCHITECTURE write-up is Phase 04.

## Reflection & Commit

After implementation, write `01-thermal-data-model-reflection.md` in this
directory. **Specifically include the measured per-frame diffusion cost** (e.g.
`%timeit diffuse_temps(...)` on a 200×140 grid, and the FPS reported by the
`SANDFALL_FRAMES` smoke) — this is the data point Risk #2 in the overview asks
for. Then make ONE atomic git commit covering all changes in this phase.

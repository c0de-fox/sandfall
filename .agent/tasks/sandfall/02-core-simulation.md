# Phase 02: Core Simulation Engine (Grid + Element Model + Sand)

## Objective

Build the heart of the game: a numpy-backed `Grid`, the element model/registry (`ElementId`, `Phase`, `Element`, `ELEMENTS`), a `Simulation` step loop that dispatches each non-empty cell to its element's rule function, the `sand` rule (proof-of-concept powder physics), and unit tests proving sand falls, piles, and rests on a solid floor.

## Depends On

Phase 01 (project must scaffold & all gates must pass).

## Can Parallelize With

None. Phases 03 and 04 both depend on this; this must land first.

## Recommended Agent

@implementer

## Changes Required

- `src/sandfall/grid.py` — NEW. `Grid` class wrapping `numpy.uint8`.
- `src/sandfall/elements.py` — NEW. Enums + dataclass + `ELEMENTS` registry (EMPTY + SAND fully populated; other members defined but minimal).
- `src/sandfall/rules/__init__.py` — NEW. `RULES` registry of `ElementId → update callable`.
- `src/sandfall/rules/sand.py` — NEW. `update_sand(grid, x, y) -> bool`.
- `src/sandfall/simulation.py` — NEW. `Simulation` with `step()`.
- `tests/test_grid.py` — NEW.
- `tests/test_simulation.py` — NEW.
- `src/sandfall/__main__.py` — no change (still stub).

## Implementation Instructions

### Coordinate convention (BINDING for all phases)

- Origin (0,0) is **top-left**.
- **+y is DOWN** (gravity). `+x` is right.
- The numpy array shape is `(rows, cols)` i.e. `(height, width)`. Access is `array[y, x]`. (Keep the array indexed `[y, x]`; expose x/y on the Grid API.)

### `src/sandfall/elements.py`

Define the full enum up front so Phase 03 does NOT touch it (it only fills in registry data):

```python
"""Element model and registry for the sandfall simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ElementId(IntEnum):
    """Stable integer IDs stored in the grid (uint8)."""

    EMPTY = 0
    SAND = 1
    WATER = 2
    STONE = 3
    WOOD = 4
    FIRE = 5
    SMOKE = 6
    PLANT = 7


class Phase(IntEnum):
    """Physical phase of an element; drives default behavior."""

    SOLID = 0   # static (stone, wood, plant)
    POWDER = 1  # falls, piles (sand)
    LIQUID = 2  # falls + spreads (water)
    GAS = 3     # rises + diffuses (smoke); fire is gas-like


@dataclass(frozen=True, slots=True)
class Element:
    id: ElementId
    name: str
    color: tuple[int, int, int]   # RGB 0..255
    density: float
    phase: Phase
    flammability: float = 0.0     # 0.0 = never burns; 1.0 = always burns on contact


ELEMENTS: dict[ElementId, Element] = {
    ElementId.EMPTY: Element(
        id=ElementId.EMPTY, name="empty", color=(0, 0, 0),
        density=0.0, phase=Phase.GAS,
    ),
    ElementId.SAND: Element(
        id=ElementId.SAND, name="sand",
        color=(194, 178, 128), density=1.5, phase=Phase.POWDER,
    ),
    # Phase 03 fills in WATER, STONE, WOOD, FIRE, SMOKE, PLANT with real colors/props.
    # For now define neutral placeholders so lookups never KeyError during development.
    ElementId.WATER: Element(
        id=ElementId.WATER, name="water",
        color=(40, 80, 200), density=1.0, phase=Phase.LIQUID,
    ),
    ElementId.STONE: Element(
        id=ElementId.STONE, name="stone",
        color=(120, 120, 120), density=10.0, phase=Phase.SOLID,
    ),
    ElementId.WOOD: Element(
        id=ElementId.WOOD, name="wood",
        color=(120, 72, 32), density=8.0, phase=Phase.SOLID, flammability=0.25,
    ),
    ElementId.FIRE: Element(
        id=ElementId.FIRE, name="fire",
        color=(255, 120, 20), density=0.1, phase=Phase.GAS,
    ),
    ElementId.SMOKE: Element(
        id=ElementId.SMOKE, name="smoke",
        color=(90, 90, 90), density=0.05, phase=Phase.GAS,
    ),
    ElementId.PLANT: Element(
        id=ElementId.PLANT, name="plant",
        color=(40, 160, 60), density=8.0, phase=Phase.SOLID, flammability=0.4,
    ),
}
```

> Rationale for populating all entries now: Phase 02's renderer/tests can reference any color; Phase 03 only *adjusts* values & *adds rules*, never adds enum members or new registry entries. Keeps the enum immutable across phases.

### `src/sandfall/grid.py`

```python
"""The simulation grid: a uint8 numpy array of element IDs."""

from __future__ import annotations

import numpy as np

from .elements import ElementId


class Grid:
    """2D grid of element IDs. Origin top-left; +y is down."""

    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"width and height must be positive ({width=}, {height=})")
        self._width = width
        self._height = height
        self._data = np.zeros((height, width), dtype=np.uint8)

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def array(self) -> np.ndarray:
        """Raw (height, width) uint8 view. Read-only intent; do not mutate externally."""
        return self._data

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self._width and 0 <= y < self._height

    def get(self, x: int, y: int) -> int:
        """Return the element id at (x, y). Out-of-bounds raises IndexError."""
        if not self.in_bounds(x, y):
            raise IndexError(f"({x}, {y}) out of bounds for {self._width}x{self._height} grid")
        return int(self._data[y, x])

    def set(self, x: int, y: int, element_id: ElementId | int) -> None:
        if not self.in_bounds(x, y):
            return  # silently ignore out-of-bounds paints (brushes at edges)
        self._data[y, x] = int(element_id)

    def fill_circle(self, cx: int, cy: int, radius: int, element_id: ElementId | int) -> None:
        """Fill all cells within `radius` (Chebyshev/rounded disk) of (cx, cy)."""
        if radius < 0:
            raise ValueError(f"radius must be non-negative ({radius=})")
        if radius == 0:
            self.set(cx, cy, element_id)
            return
        r2 = radius * radius
        x0 = max(0, cx - radius)
        x1 = min(self._width - 1, cx + radius)
        y0 = max(0, cy - radius)
        y1 = min(self._height - 1, cy + radius)
        eid = int(element_id)
        for y in range(y0, y1 + 1):
            dy = y - cy
            for x in range(x0, x1 + 1):
                dx = x - cx
                if dx * dx + dy * dy <= r2:
                    self._data[y, x] = eid
```

### `src/sandfall/rules/sand.py`

Powder physics. Returns `True` if the cell moved. Swaps into EMPTY or a **lower-density LIQUID** (sand sinks in water — full liquid behavior arrives in Phase 03; the swap helper here is enough for sand).

```python
"""Sand (POWDER) update rule."""

from __future__ import annotations

import random

from ..elements import ElementId, Phase
from ..grid import Grid


def _can_displace(target_id: int) -> bool:
    """Sand may move into EMPTY, or into a lower-density LIQUID (sinks)."""
    if target_id == ElementId.EMPTY:
        return True
    # Defer detailed liquid interaction to phase 03; keep the seam here.
    from ..elements import ELEMENTS  # local import avoids cycle at module load
    target = ELEMENTS[ElementId(target_id)]
    sand = ELEMENTS[ElementId.SAND]
    return target.phase == Phase.LIQUID and target.density < sand.density


def update_sand(grid: Grid, x: int, y: int) -> bool:
    """Move a sand cell at (x, y) one step. Returns True if it moved."""
    # Below
    if y + 1 < grid.height and _can_displace(grid.get(x, y + 1)):
        _swap(grid, x, y, x, y + 1)
        return True
    # Diagonals, randomized order to avoid left bias
    dirs = [-1, 1]
    random.shuffle(dirs)
    for dx in dirs:
        nx, ny = x + dx, y + 1
        if grid.in_bounds(nx, ny) and _can_displace(grid.get(nx, ny)):
            _swap(grid, x, ny - 1, nx, ny)
            return True
    return False


def _swap(grid: Grid, x1: int, y1: int, x2: int, y2: int) -> None:
    a = grid.get(x1, y1)
    b = grid.get(x2, y2)
    grid.set(x1, y1, b)
    grid.set(x2, y2, a)
```

### `src/sandfall/rules/__init__.py`

```python
"""Registry of element update rules."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from ..elements import ElementId

if TYPE_CHECKING:
    from ..grid import Grid

UpdateFn = Callable[["Grid", int, int], bool]

# Phase 02 registers only sand. Phase 03 adds water/stone/wood/fire/smoke/plant.
RULES: dict[ElementId, UpdateFn] = {}


def _register() -> None:
    from .sand import update_sand

    RULES[ElementId.SAND] = update_sand


_register()
```

### `src/sandfall/simulation.py`

Step loop. Bottom-to-top (so a grain falls at most one cell per step), randomized x direction per row, "moved-this-frame" guard.

```python
"""The simulation: steps the grid one tick at a time."""

from __future__ import annotations

import random

from .elements import ElementId
from .grid import Grid
from .rules import RULES


class Simulation:
    """Owns a Grid and advances it one step per call to step()."""

    def __init__(self, grid: Grid) -> None:
        self._grid = grid

    @property
    def grid(self) -> Grid:
        return self._grid

    def step(self) -> None:
        """Advance the simulation by one frame."""
        grid = self._grid
        # moved[y, x] == 1 means this cell was already moved *into* this frame;
        # do not re-dispatch it. uint8 to keep it tiny.
        moved = Grid(grid.width, grid.height)  # lightweight bool grid via Grid wrapper
        # We need raw bool access; use a numpy array directly for the guard.
        import numpy as np

        moved_arr = np.zeros((grid.height, grid.width), dtype=np.bool_)
        for y in range(grid.height - 1, -1, -1):       # bottom -> top
            left_to_right = random.random() < 0.5
            xs = range(grid.width) if left_to_right else range(grid.width - 1, -1, -1)
            for x in xs:
                if moved_arr[y, x]:
                    continue
                eid = grid.get(x, y)
                if eid == ElementId.EMPTY:
                    continue
                fn = RULES.get(ElementId(eid))
                if fn is None:
                    continue
                before = _snapshot(grid, x, y)
                moved_flag = fn(grid, x, y)
                if moved_flag:
                    # mark the destination cell so it isn't re-updated this frame
                    # (find the cell whose value is now the original element)
                    _mark_destination(grid, moved_arr, x, y, before)
        # `moved` Grid above is unused for the guard; left as a placeholder for
        # future dirty-cell tracking. Remove if linter complains, OR prefer the
        # numpy-only approach below (see cleanup note).
```

**Cleanup note for the implementer**: the `moved = Grid(...)` placeholder in the snippet above is illustrative. The actual implementation MUST use a single `numpy.bool_` array as the guard and MUST NOT allocate a second `Grid`. Simplify: drop the `moved` Grid line entirely; keep only `moved_arr`. After the rule runs, the source cell is now EMPTY (or a lower-density liquid) and the destination cell holds the element — mark the destination `(y, x)` in `moved_arr`. A simple, correct implementation:

```python
def step(self) -> None:
    import numpy as np
    grid = self._grid
    moved = np.zeros((grid.height, grid.width), dtype=np.bool_)
    for y in range(grid.height - 1, -1, -1):
        xs = range(grid.width) if random.random() < 0.5 else range(grid.width - 1, -1, -1)
        for x in xs:
            if moved[y, x]:
                continue
            eid = grid.get(x, y)
            if eid == ElementId.EMPTY:
                continue
            fn = RULES.get(ElementId(eid))
            if fn is None:
                continue
            old_val = grid.get(x, y)
            if fn(grid, x, y):
                # The element moved; find & mark its new cell.
                # Common case: it moved to a neighbor below/diagonal. Scan the
                # 4 candidate neighbors and mark whichever now holds old_val.
                for (nx, ny) in ((x, y + 1), (x - 1, y + 1), (x + 1, y + 1)):
                    if grid.in_bounds(nx, ny) and grid.get(nx, ny) == old_val and (nx, ny) != (x, y):
                        moved[ny, nx] = True
                        break
```

Note: gas rules (fire/smoke in Phase 03) move **up** (y-1), so the candidate-neighbor scan must also check `(x, y-1), (x-1, y-1), (x+1, y-1)` and horizontal `(x-1, y), (x+1, y)` to be fully general. A simpler, robust alternative is to have each rule function **return the destination `(x, y)` it moved to** (or `None`). **PREFERRED**: change the rule signature to return `tuple[int,int] | None` in Phase 02 so Phase 03 rules are uniform:

> **Decision encoded here (applies to all rules in Phases 02 & 03):** Every `update_*` function has signature `(grid: Grid, x: int, y: int) -> tuple[int, int] | None`, returning the destination cell it moved into, or `None` if it did not move. The `Simulation.step` then does `dest = fn(grid, x, y); if dest is not None: moved[dest[1], dest[0]] = True`. Update `sand.py` and the `UpdateFn` type alias accordingly. This avoids fragile "find where it went" scans.

Implement the rules with that signature. Update `tests/test_simulation.py` accordingly (rules tested via `Simulation.step`, not by checking the return value directly — keep tests black-box where possible).

### Tests

`tests/test_grid.py` — cover:
- `in_bounds` true/false at edges.
- `get`/`set` round-trip; `set` out of bounds is a no-op (no raise).
- `get` out of bounds raises `IndexError`.
- `array` shape is `(height, width)` and dtype `uint8`.
- `fill_circle(cx, cy, 0, SAND)` sets exactly one cell; `fill_circle(cx, cy, 2, SAND)` sets a disk of the expected count (count the set cells, assert within radius).

`tests/test_simulation.py` — cover (seed `random` via `random.seed(...)` at the top of each test for determinism):
- **Falls one row per step**: place one SAND at (x=5, y=2) on a 10×10 grid; `sim.step()`; assert SAND now at y=3 and (5,2) is EMPTY.
- **Does not fall through floor**: bottom row filled with STONE; sand above; after several steps the sand rests on row `height-2` and stays there over N further steps.
- **Piles (does not sink through stone)**: a small column of sand piles into a stack at the bottom.
- **Does not move when supported**: sand with a STONE cell directly beneath stays put across `step()`.

## Acceptance Criteria

- [ ] `src/sandfall/grid.py`, `src/sandfall/elements.py`, `src/sandfall/simulation.py`, `src/sandfall/rules/__init__.py`, `src/sandfall/rules/sand.py` all exist.
- [ ] `Grid` exposes `width`, `height`, `array`, `in_bounds`, `get`, `set`, `fill_circle` per spec.
- [ ] `ElementId` enum has all 7 members + EMPTY with the exact integer IDs from the spec.
- [ ] `ELEMENTS` registry is fully populated for EMPTY and SAND (other entries present with placeholder values, to be tuned in Phase 03).
- [ ] Every `update_*` rule returns `tuple[int, int] | None` (destination cell or None); `Simulation.step` uses the returned destination to mark the moved-guard.
- [ ] `Simulation.step` scans bottom→top, randomized x direction per row, skips already-moved cells.
- [ ] All grid + simulation tests pass.
- [ ] All five verification gates exit zero.

## Verification Commands

```bash
uv run python -c "import sandfall; from sandfall.simulation import Simulation; from sandfall.grid import Grid; print('ok')"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Phase-specific extra:
```bash
uv run pytest tests/test_grid.py tests/test_simulation.py -v
```

ALL must exit zero. Do NOT proceed to Phase 03 / 04 until they do.

## Documentation Updates

- Write `.agent/tasks/sandfall/02-core-simulation-reflection.md` after completion.
- If the rule-signature decision (`-> tuple[int,int] | None`) deviated from the plan, note it in the reflection so Phase 03 uses the same convention.

"""Sand (POWDER) update rule.

Rule contract (BINDING for all phases):
    Every ``update_*`` function has signature
    ``(grid: Grid, x: int, y: int) -> tuple[int, int] | None`` and returns
    the ``(x, y)`` cell the element moved *into*, or ``None`` if it did not
    move this step. ``Simulation.step`` uses the returned destination to mark
    the moved-this-frame guard, so rule functions must NOT mutate the grid
    in any other way.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId, Phase
from ..grid import Grid


def _can_displace(target_id: int) -> bool:
    """True if sand may move *into* a cell currently holding ``target_id``.

    Sand may move into EMPTY, or into a lower-density LIQUID (sand sinks in
    water). Full liquid behavior arrives in Phase 03; this seam is enough.
    """
    if target_id == ElementId.EMPTY:
        return True
    target = ELEMENTS[ElementId(target_id)]
    sand = ELEMENTS[ElementId.SAND]
    return target.phase == Phase.LIQUID and target.density < sand.density


def update_sand(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Move a sand cell at ``(x, y)`` one step.

    Powder physics: try directly below; if blocked, try down-left and
    down-right in randomized order (to avoid left-bias). Returns the
    destination ``(x, y)`` or ``None`` if the cell did not move.
    """
    # Straight down.
    if y + 1 < grid.height and _can_displace(grid.get(x, y + 1)):
        _swap(grid, x, y, x, y + 1)
        return (x, y + 1)

    # Down-diagonals, randomized order.
    directions = [-1, 1]
    random.shuffle(directions)
    for dx in directions:
        nx = x + dx
        ny = y + 1
        if grid.in_bounds(nx, ny) and _can_displace(grid.get(nx, ny)):
            _swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None


def _swap(grid: Grid, x1: int, y1: int, x2: int, y2: int) -> None:
    """Swap the contents of two in-bounds cells."""
    a = grid.get(x1, y1)
    b = grid.get(x2, y2)
    grid.set(x1, y1, b)
    grid.set(x2, y2, a)

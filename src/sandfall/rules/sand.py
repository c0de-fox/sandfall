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

from ..elements import ElementId
from ..grid import Grid
from ._common import can_displace, swap


def update_sand(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Move a sand cell at ``(x, y)`` one step.

    Powder physics: try directly below; if blocked, try down-left and
    down-right in randomized order (to avoid left-bias). Returns the
    destination ``(x, y)`` or ``None`` if the cell did not move.
    """
    # Straight down.
    if y + 1 < grid.height and can_displace(ElementId.SAND, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)

    # Down-diagonals, randomized order.
    directions = [-1, 1]
    random.shuffle(directions)
    for dx in directions:
        nx = x + dx
        ny = y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.SAND, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None

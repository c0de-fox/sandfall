"""Water (LIQUID) update rule.

Falls straight down; else down-diagonals; else spreads one cell sideways
into EMPTY (horizontal flow). Displacement uses the shared
:func:`can_displace` helper, which for water is effectively "EMPTY only" in
v1 (no lower-density liquid exists yet), but keeps the seam consistent so a
future lighter liquid would let water sink through it.
"""

from __future__ import annotations

import random

from ..elements import ElementId
from ..grid import Grid
from ._common import can_displace, swap


def update_water(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Move a water cell at ``(x, y)`` one step.

    Liquid physics: try directly below; else down-diagonals in randomized
    order; else left/right in randomized order (one-cell horizontal flow).
    Returns the destination ``(x, y)`` or ``None`` if it did not move.
    """
    # Straight down.
    if y + 1 < grid.height and can_displace(ElementId.WATER, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)

    # Down-diagonals, randomized order.
    diagonals = [-1, 1]
    random.shuffle(diagonals)
    for dx in diagonals:
        nx = x + dx
        ny = y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.WATER, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    # Horizontal flow: left/right into EMPTY, randomized order.
    sideways = [-1, 1]
    random.shuffle(sideways)
    for dx in sideways:
        nx = x + dx
        ny = y
        if grid.in_bounds(nx, ny) and can_displace(ElementId.WATER, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None

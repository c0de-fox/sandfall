"""Sand (POWDER) update rule.

Rule contract (BINDING for all phases):
    Every ``update_*`` function has signature
    ``(grid: Grid, x: int, y: int) -> tuple[int, int] | None`` and returns
    the ``(x, y)`` cell the element moved *into*, or ``None`` if it did not
    move this step. ``Simulation.step`` uses the returned destination to mark
    the moved-this-frame guard, so rule functions must NOT mutate the grid
    in any other way.

Phase 03 adds a temperature-driven transition at the TOP of the rule, before
any movement (reactive-rule relaxation: transform the own cell in place and
return None, so a cell that melts does not also move): melt -> GLASS when
``get_temp > melt_point`` (~1700). ``SAND.melt_point > 0`` so the guard is
harmless; only sand has a melt rule.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import can_displace, swap

_SAND = ELEMENTS[ElementId.SAND]


def update_sand(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Move a sand cell at ``(x, y)`` one step.

    Powder physics: try directly below; if blocked, try down-left and
    down-right in randomized order (to avoid left-bias). Returns the
    destination ``(x, y)`` or ``None`` if the cell did not move.

    Temperature transition (checked first; a melting cell does not also
    move this step): melt -> GLASS above ``melt_point``.
    """
    # Melt -> GLASS (reactive; checked before movement).
    if _SAND.melt_point > 0 and grid.get_temp(x, y) > _SAND.melt_point:
        grid.set(x, y, ElementId.GLASS)
        return None

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

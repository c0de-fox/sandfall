"""Plant (SOLID, grows near water) update rule.

A plant cell is static unless it has WATER in its 8-neighborhood. When
water is adjacent, with a small per-step probability (``GROW_CHANCE``) the
plant converts one EMPTY neighbor into a new PLANT cell. Water is NOT
consumed (proximity-only growth — see the master-plan decision log).

The newly grown PLANT cell is returned as the move destination so the
simulation's moved-guard prevents it from growing again in the same frame.
Plant has no per-cell life, so no life bookkeeping is needed here.
"""

from __future__ import annotations

import random

from ..elements import ElementId
from ..grid import Grid

GROW_CHANCE = 0.02

# 8-neighborhood (dx, dy); +y is DOWN.
_NEIGHBORS: tuple[tuple[int, int], ...] = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-1, -1),
    (1, -1),
    (-1, 1),
    (1, 1),
)


def update_plant(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Grow a plant cell into an EMPTY neighbor if water is adjacent."""
    has_water = any(
        grid.in_bounds(x + dx, y + dy) and grid.get(x + dx, y + dy) == ElementId.WATER
        for dx, dy in _NEIGHBORS
    )
    if not has_water:
        return None

    if random.random() < GROW_CHANCE:
        empty = [
            (x + dx, y + dy)
            for dx, dy in _NEIGHBORS
            if grid.in_bounds(x + dx, y + dy)
            and grid.get(x + dx, y + dy) == ElementId.EMPTY
        ]
        if empty:
            nx, ny = random.choice(empty)
            grid.set(nx, ny, ElementId.PLANT)
            return (nx, ny)

    return None

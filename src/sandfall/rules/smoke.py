"""Smoke (gas, finite life) update rule.

Each step a smoke cell:

1. Ages (decrements its per-cell ``life``). When life hits 0 the cell
   becomes EMPTY and the rule returns ``None``.
2. Rises: straight up into EMPTY; else up-diagonals randomized; else with a
   small chance drifts one cell sideways into EMPTY.

Like fire, smoke only enters EMPTY cells in v1 (no gas-gas displacement).
"""

from __future__ import annotations

import random

from ..elements import ElementId
from ..grid import Grid
from ._common import swap

# Per-step chance to drift sideways when rising straight up is blocked.
_DRIFT_CHANCE = 0.25


def update_smoke(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step a smoke cell: age, then try to rise / drift."""
    # 1. Age; expire to EMPTY when life is exhausted.
    life = grid.get_life(x, y) - 1
    if life <= 0:
        grid.set(x, y, ElementId.EMPTY)
        grid.set_life(x, y, 0)
        return None
    grid.set_life(x, y, life)

    # 2. Rise: straight up into EMPTY first; else up-diagonals randomized.
    if y - 1 >= 0 and grid.get(x, y - 1) == ElementId.EMPTY:
        swap(grid, x, y, x, y - 1)
        return (x, y - 1)
    diagonals = [(-1, -1), (1, -1)]
    random.shuffle(diagonals)
    for dx, dy in diagonals:
        nx, ny = x + dx, y + dy
        if grid.in_bounds(nx, ny) and grid.get(nx, ny) == ElementId.EMPTY:
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    # 3. Else maybe drift sideways into EMPTY.
    if random.random() < _DRIFT_CHANCE:
        sideways = [(-1, 0), (1, 0)]
        random.shuffle(sideways)
        for dx, dy in sideways:
            nx, ny = x + dx, y + dy
            if grid.in_bounds(nx, ny) and grid.get(nx, ny) == ElementId.EMPTY:
                swap(grid, x, y, nx, ny)
                return (nx, ny)

    return None

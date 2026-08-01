"""Smoke (gas, finite life) update rule.

Each step a smoke cell:

1. Ages (decrements its per-cell ``life``). When life hits 0 the cell
   becomes EMPTY and the rule returns ``None``.
2. Rises: straight up into EMPTY or a LIQUID (buoyancy); else up-diagonals
   randomized; else with a small chance drifts one cell sideways into EMPTY.

Steam and smoke rise into EMPTY or a LIQUID (buoyancy -- the gas swaps with
the liquid above it) and drift sideways into EMPTY only. No gas-gas
displacement in v1. (FIRE still rises into EMPTY only.)
"""

from __future__ import annotations

import random

from ..elements import ElementId
from ..grid import Grid
from ._common import is_riseable, maybe_convect, swap

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

    # Convection: a hot fluid cell rises through the cooler same-phase cell
    # above it (intra-phase buoyancy). Checked AFTER reactive transitions and
    # BEFORE gravity flow: a convecting cell swaps up this step instead of
    # falling/spreading (one move per step).
    convect = maybe_convect(grid, x, y)
    if convect is not None:
        return convect

    # 2. Rise: straight up into EMPTY or a LIQUID (buoyancy -- gas rises, liquid
    #    sinks); else up-diagonals randomized.
    if y - 1 >= 0 and is_riseable(grid.get(x, y - 1)):
        swap(grid, x, y, x, y - 1)
        return (x, y - 1)
    diagonals = [(-1, -1), (1, -1)]
    random.shuffle(diagonals)
    for dx, dy in diagonals:
        nx, ny = x + dx, y + dy
        if grid.in_bounds(nx, ny) and is_riseable(grid.get(nx, ny)):
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

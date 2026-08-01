"""Gunpowder (POWDER, explosive) update rule.

Gunpowder is a powder (density 1.5, like SAND -> piles and falls like sand) that
DETONATES when its own temperature exceeds its flashpoint (~200). Each step:

1. **Detonate** -- if the cell's own temp exceeds its flashpoint, call
   :func:`sandfall.rules.blast.explode` (heat burst + crater + scatter over a
   circular radius), then overwrite THIS detonation cell with FIRE (the fireball:
   seed life, set hot temp) and return ``None``. The blast heats other gunpowder
   in the radius past ITS flashpoint -> that gunpowder detonates on its own
   later scan / next frame (the chain propagates via heat, not recursion). Fire,
   lava, or another blast's heat all set it off.
2. **Flow** -- otherwise move like a powder (sand.py shape: straight down, then
   down-diagonals randomized; NO sideways -- gunpowder is a powder, not a
   liquid) via ``can_displace`` + ``swap``.

Detonation transforms the own cell in place (-> FIRE) and returns ``None``, so
the moved-this-frame guard is unaffected (reactive-rule relaxation, like
wood/lava). The blast's writes are side-effect writes caught by the dormant-cell
wake (id_changed + temp_changed); no wake-condition edit is needed (master plan
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
        if grid.in_bounds(nx, ny) and can_displace(
            ElementId.GUNPOWDER, grid.get(nx, ny)
        ):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None

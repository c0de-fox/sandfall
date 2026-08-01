"""Oil (LIQUID, light, flammable) update rule.

Oil is a light liquid (density 0.8, less than WATER 1.0 -> floats on water via
can_displace) that ignites when heated. Each step:

1. **Burn** -- if the cell's own temp exceeds its flashpoint (~150), become FIRE
   (seed life, set burn-temp). Mirrors wood/plant reactive ignition. Once oil
   ignites it becomes ElementId.FIRE, a persistent heat source whose diffusion
   heats neighboring oil above its flashpoint -> fire spreads across an oil
   slick (including oil floating on water).
2. **Flow** -- otherwise move like a light liquid: straight down, down-diagonals
   randomized, one-cell sideways randomized, all via can_displace + swap. Because
   oil is LIGHTER than water, water displaces oil (can_displace(WATER, OIL) is
   True) so water sinks and oil rises/floats -- oil ends up on top.

No dissolve/dilute (unlike acid/base). Burning oil on water spreads fire across
the surface because FIRE is already a persistent heat source + neighborhood wake
(simulation.py wake condition #3).
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import can_displace, maybe_convect, seed_fire_life, swap

_ELM = ELEMENTS[ElementId.OIL]
_FIRE = ELEMENTS[ElementId.FIRE]


def update_oil(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an oil cell: burn when hot, else flow like a light liquid."""
    # 1. Burn: own temp above flashpoint -> FIRE.
    if _ELM.flashpoint > 0 and grid.get_temp(x, y) > _ELM.flashpoint:
        grid.set(x, y, ElementId.FIRE)
        grid.set_life(x, y, seed_fire_life())
        grid.set_temp(x, y, _FIRE.burn_temp)
        return None

    # Convection: a hot fluid cell rises through the cooler same-phase cell
    # above it (intra-phase buoyancy). Checked AFTER reactive transitions and
    # BEFORE gravity flow: a convecting cell swaps up this step instead of
    # falling/spreading (one move per step).
    convect = maybe_convect(grid, x, y)
    if convect is not None:
        return convect

    # 2. Flow like a light liquid (water.py shape via can_displace + swap).
    if y + 1 < grid.height and can_displace(ElementId.OIL, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)
    diagonals = [-1, 1]
    random.shuffle(diagonals)
    for dx in diagonals:
        nx, ny = x + dx, y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.OIL, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)
    sideways = [-1, 1]
    random.shuffle(sideways)
    for dx in sideways:
        nx, ny = x + dx, y
        if grid.in_bounds(nx, ny) and can_displace(ElementId.OIL, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None

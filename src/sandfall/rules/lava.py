"""Lava (LIQUID, very hot, heat source + reactor) update rule.

Lava behaves as a dense liquid (density 2.5, denser than water 1.0) and a
heat source. Each step, in priority order:

1. **React with adjacent WATER -> STONE + STEAM.** If any of the 4 orthogonal
   neighbors is WATER, the lava solidifies to STONE and that water neighbor
   flashes to STEAM (hot, with a freshly seeded steam life). This side-effect
   write on a neighbor cell is the same unreturned-neighbor-write pattern
   ``fire.py`` already documents (the rule contract allows only one return
   value, so the side-effected cell is not marked moved — a chain reaction
   that is bounded by grid size and usually desirable).
2. **Cool -> STONE** when the cell's temperature drops below
   :data:`LAVA_SOLIDIFY_TEMP` (the diffusion pre-pass carries lava's heat
   away into cooler surroundings; once it cools enough it freezes to stone).
3. **Otherwise move like a dense liquid** — straight down, then down-diagonals
   randomized, then one-cell sideways flow — reusing water's displacement
   shape via :func:`can_displace` / :func:`swap`. Because lava is denser than
   water, it sinks under water (that adjacency is what drives reaction 1).

The reaction and the solidify check both transform the own cell in place and
return None (reactive-rule relaxation), so a transforming lava does not also
move this step. Lava is a heat source via its high spawn-temp (1500) and
conductivity; the diffusion pre-pass carries that heat outward (enough to
melt adjacent SAND into GLASS, ignite flammables, etc.).
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import can_displace, seed_steam_life, swap

# Below this temperature a lava cell solidifies into STONE. Well below the
# spawn-temp (1500) so a freshly painted lava flows before it cools.
LAVA_SOLIDIFY_TEMP = 700

# Orthogonal neighborhood for the water-reaction check (matches the
# 4-neighborhood the diffusion pre-pass uses).
_REACT_NEIGHBORS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (0, 1),
    (-1, 0),
    (1, 0),
)

_STEAM = ELEMENTS[ElementId.STEAM]


def update_lava(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step a lava cell: react with water, else cool, else flow like a dense liquid."""
    # 1. React with an adjacent WATER neighbor -> STONE (here) + STEAM (there).
    for dx, dy in _REACT_NEIGHBORS:
        nx, ny = x + dx, y + dy
        if grid.in_bounds(nx, ny) and grid.get(nx, ny) == ElementId.WATER:
            grid.set(x, y, ElementId.STONE)
            grid.set(nx, ny, ElementId.STEAM)
            # Hot enough to not instantly condense (>= STEAM.condense_point).
            grid.set_temp(nx, ny, _STEAM.temp_spawn)
            grid.set_life(nx, ny, seed_steam_life())
            return None

    # 2. Cool -> STONE when below the solidify threshold.
    if grid.get_temp(x, y) < LAVA_SOLIDIFY_TEMP:
        grid.set(x, y, ElementId.STONE)
        return None

    # 3. Otherwise move like a dense liquid (water-style fall/diagonal/flow).
    #    Straight down.
    if y + 1 < grid.height and can_displace(ElementId.LAVA, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)

    # Down-diagonals, randomized order.
    diagonals = [-1, 1]
    random.shuffle(diagonals)
    for dx in diagonals:
        nx = x + dx
        ny = y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.LAVA, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    # Horizontal flow: left/right, randomized order.
    sideways = [-1, 1]
    random.shuffle(sideways)
    for dx in sideways:
        nx = x + dx
        ny = y
        if grid.in_bounds(nx, ny) and can_displace(ElementId.LAVA, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None

"""Water (LIQUID) update rule.

Falls straight down; else down-diagonals; else spreads one cell sideways
into EMPTY (horizontal flow). Displacement uses the shared
:func:`can_displace` helper, which for water is effectively "EMPTY only" in
v1 (no lower-density liquid exists yet), but keeps the seam consistent so a
future lighter liquid would let water sink through it.

Phase 03 adds temperature-driven phase transitions at the TOP of the rule,
before any movement (reactive-rule relaxation: transform the own cell in
place and return None, so a cell that boils/freezes does not also move):

* boil -> STEAM when ``get_temp > boil_point`` (carries a warm temp so the
  newborn steam does not instantly condense);
* freeze -> ICE when ``get_temp <= freeze_point`` (the new ice keeps the
  water's already-<=0 temp; a colder-than-freezing cold source -- dry ice /
  liquid nitrogen -- drives the freeze via diffusion).

``WATER.boil_point == 100`` and ``WATER.freeze_point == 0`` are both VALID
active thresholds (0 is meaningful for water — it freezes at/below 0°C), so
neither check is guarded by a ``> 0`` / ``!= 0`` predicate (the guard pattern
used by WOOD/PLANT exists because their default ``flashpoint == 0`` means
"never"; water's 0 means "freezes here").
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import can_displace, seed_steam_life, swap

_WATER = ELEMENTS[ElementId.WATER]


def update_water(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Move a water cell at ``(x, y)`` one step.

    Liquid physics: try directly below; else down-diagonals in randomized
    order; else left/right in randomized order (one-cell horizontal flow).
    Returns the destination ``(x, y)`` or ``None`` if it did not move.

    Temperature transitions (checked first; a transforming cell does not
    also move this step): boil -> STEAM, freeze -> ICE.
    """
    t = grid.get_temp(x, y)

    # Boil -> STEAM. Carry a warm temp so the newborn steam does not instantly
    # condense, and seed a steam lifetime so it lingers (the same helper the
    # lava reaction and the brush use) rather than expiring one step later.
    if t > _WATER.boil_point:
        grid.set(x, y, ElementId.STEAM)
        grid.set_temp(x, y, ELEMENTS[ElementId.STEAM].temp_spawn)  # 120
        grid.set_life(x, y, seed_steam_life())
        return None

    # Freeze -> ICE (at or below freeze_point; freeze_point == 0 is valid).
    # The new ice keeps the water's already-<=0 temp (realistic: no cold-source
    # seeding). It melts again once it warms above melt_point via diffusion.
    if t <= _WATER.freeze_point:
        grid.set(x, y, ElementId.ICE)
        return None

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

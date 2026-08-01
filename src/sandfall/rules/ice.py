"""Ice (SOLID, frozen water) update rule.

Ice is **realistic frozen water**: it melts to WATER when its own temperature
exceeds its ``melt_point`` (0C) -- so a lone ice block in 20C ambient melts,
and ice warming at the edge of a freeze patch reverts to water. Ice does NOT
freeze water on its own (it sits at ~0C and cannot pull 20C water below 0);
freezing water now requires a colder-than-freezing cold source whose diffusion
cools adjacent water to/below 0C, at which point the WATER rule freezes it. See
``rules/dry_ice.py`` (persistent, -78C) and ``rules/ln2.py`` (transient, -196C).

Ice is still destroyed quickly by direct fire/lava contact (the real-world way):
a FIRE neighbor -> WATER; a LAVA neighbor -> STEAM (the lava reaction flashes
the melt to steam). This is checked FIRST so a hot contact destroys the ice
before the ambient-melt branch runs.

This reverts the interim persistent-cold-source model (re-asserting an
``ICE_COLD_TARGET`` and disabling ambient melt) that shipped so ice could freeze
water before real cold-source elements existed; dry ice now fills that role. See
the ``thermal-realism`` plan and BACKLOG ("Thermal realism rework").

This is the formal use of the reactive-rule contract relaxation (transform own
cell in place, return None); the cell does not MOVE so the simulation's
moved-this-frame guard is unaffected.
"""

from __future__ import annotations

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import seed_steam_life

_ICE = ELEMENTS[ElementId.ICE]
_STEAM = ELEMENTS[ElementId.STEAM]

# Orthogonal neighborhood for the fire/lava melt check (matches the
# 4-neighborhood the diffusion pre-pass and lava.py use).
_MELT_NEIGHBORS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (0, 1),
    (-1, 0),
    (1, 0),
)


def update_ice(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an ice cell: melt via direct fire/lava contact, else melt in place
    when warmer than melt_point (realistic ambient melt).

    1. **Melt via direct fire/lava contact.** A FIRE neighbor -> become WATER; a
       LAVA neighbor -> become STEAM (the lava reaction flashes the melt to
       steam). Checked FIRST so a hot contact destroys the ice immediately.
    2. **Thermal melt.** Otherwise, if the cell's own temp exceeds its
       melt_point (0C), become WATER -- a lone ice block in ambient melts. (The
       melt_point is now USED, unlike under the interim cold-source model where
       it was declared-but-unread.)
    """
    # 1. Direct fire/lava contact melts the ice (dramatic reactions first).
    for dx, dy in _MELT_NEIGHBORS:
        nx, ny = x + dx, y + dy
        if not grid.in_bounds(nx, ny):
            continue
        neighbor = grid.get(nx, ny)
        if neighbor == ElementId.LAVA:
            grid.set(x, y, ElementId.STEAM)
            grid.set_temp(x, y, _STEAM.temp_spawn)  # warm gas on melt-by-lava
            grid.set_life(x, y, seed_steam_life())
            return None
        if neighbor == ElementId.FIRE:
            grid.set(x, y, ElementId.WATER)
            return None

    # 2. Thermal melt: warmer than melt_point -> WATER (realistic ambient melt).
    if grid.get_temp(x, y) > _ICE.melt_point:
        grid.set(x, y, ElementId.WATER)
        return None

    return None

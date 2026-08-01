"""Ice (SOLID, persistent cold source) update rule.

Ice is a **persistent cold source**: each step it re-asserts its cold target
temperature (`ICE_COLD_TARGET`), exactly as a living fire cell re-asserts its
burn_temp (`rules/fire.py`). The Simulation's vectorized diffusion pre-pass
carries that cold outward into adjacent water; once the water cools to/below its
freeze_point the WATER rule freezes it (and seeds the new ice cold, so the freeze
front advances immediately). This is how ice freezes water *through the thermal
system* rather than as a diffusion-bug side-effect.

Ice melts **only via direct fire/lava contact** (the real-world way ice is
destroyed quickly): if any orthogonal neighbor is FIRE the ice becomes WATER; if
any is LAVA the ice becomes STEAM (mirroring `rules/lava.py`'s reaction shape).
It does NOT melt from ambient warmth: a cell that re-asserts ICE_COLD_TARGET
every step can never exceed its melt_point through diffusion, and allowing
thermal melt would be logically incompatible with being a cold source (a warm
enough ice to melt would also be too warm to freeze anything). This is a
**deliberate, temporary** model: once colder-than-freezing cold-source elements
exist (dry ice ~-78C, liquid nitrogen ~-196C), ice will revert to a realistic
melt-at->0 "frozen water" non-source -- see BACKLOG ("Thermal realism" rework).

This is the formal use of the reactive-rule contract relaxation (transform own
cell in place, return None); the cell does not MOVE so the simulation's
moved-this-frame guard is unaffected.
"""

from __future__ import annotations

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import seed_steam_life

# The cold temperature an ice cell holds (and re-asserts) each step. A cold
# source: diffusion carries this cold outward, but cannot warm the ice above
# this value while the rule keeps re-asserting it. NOT a physical temperature --
# it is a tunable knob for freeze spread rate (colder -> faster spread).
# Prototype-validated at -50 (an ice cube in water spreads 1->3->5->9 cells over
# ~120 steps). Mirrors the LAVA_SOLIDIFY_TEMP pattern in rules/lava.py.
ICE_COLD_TARGET = -50

# Orthogonal neighborhood for the fire/lava melt check (matches the
# 4-neighborhood the diffusion pre-pass and lava.py use).
_MELT_NEIGHBORS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (0, 1),
    (-1, 0),
    (1, 0),
)

_STEAM = ELEMENTS[ElementId.STEAM]


def update_ice(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an ice cell: melt via direct fire/lava contact, else re-assert cold.

    1. **Melt via direct fire/lava contact.** A FIRE neighbor -> become WATER; a
       LAVA neighbor -> become STEAM (the lava reaction flashes the melt to
       steam). Checked FIRST so a hot contact destroys the ice before it can
       re-assert cold. (Ice does NOT melt from ambient -- see module docstring.)
    2. **Re-assert the cold target.** While still ice, clamp the cell's temp
       DOWN to ICE_COLD_TARGET each step so it remains a persistent cold source
       the diffusion pre-pass draws from (mirrors fire's burn-temp re-assert).
    """
    # 1. Direct fire/lava contact melts the ice.
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

    # 2. Re-assert cold: a living ice is a persistent cold source.
    if grid.get_temp(x, y) > ICE_COLD_TARGET:
        grid.set_temp(x, y, ICE_COLD_TARGET)

    return None

"""Ice (SOLID, thermally meltable) update rule.

Ice is static: it never moves. It melts -> WATER when its temperature rises
above its ``melt_point`` (0°C). This is the formal use of the reactive-rule
contract relaxation (transform own cell in place, return None); the cell
does not MOVE so the simulation's moved-this-frame guard is unaffected.

Note: ``ICE.melt_point == 0`` is a VALID active threshold (ice melts above
0°C), so — unlike the WOOD/PLANT ``flashpoint > 0`` guard (whose default 0
means "never ignites") — this check is NOT guarded by a ``> 0`` / ``!= 0``
predicate. Only ICE has a melt rule, so the threshold value is unambiguous
here. Ambient-temperature ice (20°C) therefore melts, which is physically
correct and the intended water-cycle behavior; painted ice starts at -5°C
and melts once diffusion warms it above 0.
"""

from __future__ import annotations

from ..elements import ELEMENTS, ElementId
from ..grid import Grid

_ICE = ELEMENTS[ElementId.ICE]


def update_ice(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Ice never moves; it melts to WATER when its own temp exceeds melt_point."""
    if grid.get_temp(x, y) > _ICE.melt_point:
        grid.set(x, y, ElementId.WATER)
    return None

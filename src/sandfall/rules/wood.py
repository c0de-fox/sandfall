"""Wood (SOLID, thermally ignitable) update rule.

Wood is static: it never moves. It does, however, react to its OWN
temperature: when ``get_temp(x,y)`` exceeds the WOOD ``flashpoint`` the
cell becomes FIRE (seeds life + sets burn-temp) and returns ``None``. This
is the formal use of the reactive-rule contract relaxation documented in
the temperature master plan (transform own cell in place, return None).

The cell does not MOVE on ignition, so the simulation's moved-this-frame
guard is unaffected. A ``flashpoint == 0`` means "never ignites"; wood's
flashpoint is set in ``ELEMENTS``.
"""

from __future__ import annotations

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import seed_fire_life

_ELM = ELEMENTS[ElementId.WOOD]
_FIRE = ELEMENTS[ElementId.FIRE]


def update_wood(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Wood never moves; it ignites to FIRE when its own temp exceeds flashpoint."""
    if _ELM.flashpoint > 0 and grid.get_temp(x, y) > _ELM.flashpoint:
        grid.set(x, y, ElementId.FIRE)
        grid.set_life(x, y, seed_fire_life())
        grid.set_temp(x, y, _FIRE.burn_temp)
    return None

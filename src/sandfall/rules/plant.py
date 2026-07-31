"""Plant (SOLID, grows near water, thermally ignitable) update rule.

A plant cell is static unless it has WATER in its 8-neighborhood. When
water is adjacent, with a small per-step probability (``GROW_CHANCE``) the
plant converts one EMPTY neighbor into a new PLANT cell. Water is NOT
consumed (proximity-only growth — see the master-plan decision log).

Thermal ignition (Phase 02) takes priority over growth: when
``get_temp(x,y)`` exceeds the PLANT ``flashpoint`` the cell becomes FIRE
(seeds life + sets burn-temp) and returns ``None``. A burning plant
neither grows nor needs water. This is the formal use of the reactive-rule
contract relaxation (transform own cell in place, return None); the cell
does not MOVE so the moved-this-frame guard is unaffected.

Plant has no per-cell life, so no life bookkeeping is needed for growth.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import seed_fire_life

GROW_CHANCE = 0.02

_ELM = ELEMENTS[ElementId.PLANT]
_FIRE = ELEMENTS[ElementId.FIRE]

# 8-neighborhood (dx, dy); +y is DOWN.
_NEIGHBORS: tuple[tuple[int, int], ...] = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
    (-1, -1),
    (1, -1),
    (-1, 1),
    (1, 1),
)


def update_plant(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Grow a plant cell into an EMPTY neighbor if water is adjacent, OR ignite
    when hot (thermal ignition takes priority over growth)."""
    # Thermal ignition: a hot plant catches fire and stops growing.
    if _ELM.flashpoint > 0 and grid.get_temp(x, y) > _ELM.flashpoint:
        grid.set(x, y, ElementId.FIRE)
        grid.set_life(x, y, seed_fire_life())
        grid.set_temp(x, y, _FIRE.burn_temp)
        return None

    has_water = any(
        grid.in_bounds(x + dx, y + dy) and grid.get(x + dx, y + dy) == ElementId.WATER
        for dx, dy in _NEIGHBORS
    )
    if not has_water:
        return None

    if random.random() < GROW_CHANCE:
        empty = [
            (x + dx, y + dy)
            for dx, dy in _NEIGHBORS
            if grid.in_bounds(x + dx, y + dy)
            and grid.get(x + dx, y + dy) == ElementId.EMPTY
        ]
        if empty:
            nx, ny = random.choice(empty)
            grid.set(nx, ny, ElementId.PLANT)
            return (nx, ny)

    return None

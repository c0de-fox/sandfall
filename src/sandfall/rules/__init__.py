"""Registry of element update rules.

Maps each ``ElementId`` to its ``update_*`` callable. Phase 02 registered
only SAND; Phase 03 adds WATER, STONE, WOOD, FIRE, SMOKE, PLANT.

STONE and WOOD are static solids. They are registered as explicit no-op
rules (returning ``None``) rather than omitted, so the registry enumerates
every element and the phase-03 verification gate (``len(RULES) >= 6``)
holds. Functionally a no-op rule and an absent entry are identical —
``Simulation.step`` would skip either — but the explicit no-op documents
intent.
"""

from __future__ import annotations

from collections.abc import Callable

from ..elements import ElementId
from ..grid import Grid
from .fire import update_fire
from .plant import update_plant
from .sand import update_sand
from .smoke import update_smoke
from .stone import update_stone
from .water import update_water
from .wood import update_wood

# A rule function returns the destination (x, y) it moved into, or None if it
# did not move. See rules/sand.py for the full contract.
UpdateFn = Callable[[Grid, int, int], "tuple[int, int] | None"]

RULES: dict[ElementId, UpdateFn] = {
    ElementId.SAND: update_sand,
    ElementId.WATER: update_water,
    ElementId.STONE: update_stone,
    ElementId.WOOD: update_wood,
    ElementId.FIRE: update_fire,
    ElementId.SMOKE: update_smoke,
    ElementId.PLANT: update_plant,
}

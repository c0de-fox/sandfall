"""Registry of element update rules.

Maps each ``ElementId`` to its ``update_*`` callable. v1 registered only
SAND; Phase 03 added WATER, STONE, WOOD, FIRE, SMOKE, PLANT; the temperature
feature's Phase 03 adds STEAM, ICE, LAVA, GLASS.

STONE, WOOD, and GLASS are static solids. They are registered as explicit
no-op rules (returning ``None``) rather than omitted, so the registry
enumerates every element and the phase-03 verification gate
(``len(RULES) >= 11``) holds. Functionally a no-op rule and an absent entry
are identical — ``Simulation.step`` would skip either — but the explicit
no-op documents intent.
"""

from __future__ import annotations

from collections.abc import Callable

from ..elements import ElementId
from ..grid import Grid
from ._common import seed_fire_life, seed_smoke_life, seed_steam_life
from .fire import update_fire
from .glass import update_glass
from .ice import update_ice
from .lava import update_lava
from .plant import update_plant
from .sand import update_sand
from .smoke import update_smoke
from .steam import update_steam
from .stone import update_stone
from .water import update_water
from .wood import update_wood

# A rule function returns the destination (x, y) it moved into, or None if it
# did not move. See rules/sand.py for the full contract.
UpdateFn = Callable[[Grid, int, int], "tuple[int, int] | None"]

# ``seed_fire_life`` / ``seed_smoke_life`` / ``seed_steam_life`` are
# re-exported here so the painting path (brush) and tests can import the
# canonical lifetime ranges from a single stable location:
# ``from sandfall.rules import seed_steam_life``.
__all__ = [
    "RULES",
    "UpdateFn",
    "seed_fire_life",
    "seed_smoke_life",
    "seed_steam_life",
]

RULES: dict[ElementId, UpdateFn] = {
    ElementId.SAND: update_sand,
    ElementId.WATER: update_water,
    ElementId.STONE: update_stone,
    ElementId.WOOD: update_wood,
    ElementId.FIRE: update_fire,
    ElementId.SMOKE: update_smoke,
    ElementId.PLANT: update_plant,
    # Phase 03 (temperature feature) new elements.
    ElementId.STEAM: update_steam,
    ElementId.ICE: update_ice,
    ElementId.LAVA: update_lava,
    ElementId.GLASS: update_glass,
}

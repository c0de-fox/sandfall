"""Registry of element update rules.

Maps each ``ElementId`` to its ``update_*`` callable. Phase 02 registers
only SAND; Phase 03 adds WATER, STONE, WOOD, FIRE, SMOKE, PLANT.
"""

from __future__ import annotations

from collections.abc import Callable

from ..elements import ElementId
from ..grid import Grid
from .sand import update_sand

# A rule function returns the destination (x, y) it moved into, or None if it
# did not move. See rules/sand.py for the full contract.
UpdateFn = Callable[[Grid, int, int], "tuple[int, int] | None"]

RULES: dict[ElementId, UpdateFn] = {
    ElementId.SAND: update_sand,
}

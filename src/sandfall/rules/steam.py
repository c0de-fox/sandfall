"""Steam (gas, finite life) update rule.

Mirrors :mod:`sandfall.rules.smoke` (rises + drifts + ages), with two
differences:

1. Steam **condenses -> WATER** when its temperature drops below its
   ``condense_point`` (~60). This is the closing half of the water cycle
   (WATER boils -> STEAM -> ... -> condenses -> WATER).
2. Steam has its own (wider) lifetime window via :func:`seed_steam_life` so
   it lingers longer than smoke before expiring to EMPTY.

Like smoke, steam rises into EMPTY or a LIQUID (buoyancy -- the gas swaps with
the liquid above it, gas up / liquid down) and drifts sideways into EMPTY only.
No gas-gas displacement in v1 (a gas does not rise into another gas).
The condense check runs FIRST (before aging), so a cool steam becomes water
even on its last step of life. The rule is reactive: a condensing cell
transforms in place and returns None (it does not also move).

STEAM life is seeded by the brush (:func:`sandfall.brush.paint_brush`) and by
the lava+water reaction (:mod:`sandfall.rules.lava`) via
:func:`seed_steam_life`; this rule only *decrements* an already-seeded life.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import is_riseable, maybe_convect, swap

# Per-step chance to drift sideways when rising straight up is blocked.
_DRIFT_CHANCE = 0.25

_STEAM = ELEMENTS[ElementId.STEAM]


def update_steam(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step a steam cell: condense, age, then try to rise / drift."""
    # 1. Condense -> WATER when cool enough (checked before aging so a cool
    #    steam becomes water even on its last step of life).
    if grid.get_temp(x, y) < _STEAM.condense_point:
        grid.set(x, y, ElementId.WATER)
        return None

    # 2. Age; expire to EMPTY when life is exhausted.
    life = grid.get_life(x, y) - 1
    if life <= 0:
        grid.set(x, y, ElementId.EMPTY)
        grid.set_life(x, y, 0)
        return None
    grid.set_life(x, y, life)

    # Convection: a hot fluid cell rises through the cooler same-phase cell
    # above it (intra-phase buoyancy). Checked AFTER reactive transitions and
    # BEFORE gravity flow: a convecting cell swaps up this step instead of
    # falling/spreading (one move per step).
    convect = maybe_convect(grid, x, y)
    if convect is not None:
        return convect

    # 3. Rise: straight up into EMPTY or a LIQUID (buoyancy -- gas rises, liquid
    #    sinks); else up-diagonals randomized.
    if y - 1 >= 0 and is_riseable(grid.get(x, y - 1)):
        swap(grid, x, y, x, y - 1)
        return (x, y - 1)
    diagonals = [(-1, -1), (1, -1)]
    random.shuffle(diagonals)
    for dx, dy in diagonals:
        nx, ny = x + dx, y + dy
        if grid.in_bounds(nx, ny) and is_riseable(grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    # 4. Else maybe drift sideways into EMPTY.
    if random.random() < _DRIFT_CHANCE:
        sideways = [(-1, 0), (1, 0)]
        random.shuffle(sideways)
        for dx, dy in sideways:
            nx, ny = x + dx, y + dy
            if grid.in_bounds(nx, ny) and grid.get(nx, ny) == ElementId.EMPTY:
                swap(grid, x, y, nx, ny)
                return (nx, ny)

    return None

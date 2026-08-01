"""Liquid nitrogen (LIQUID, transient cold source) update rule.

Liquid nitrogen is a light cryogenic liquid (density 0.8 < WATER 1.0 -> floats
on water via can_displace, like oil) and the coldest cold source: it re-asserts
``LN2_COLD_TARGET`` = -196C (its boiling point) each step WHILE ALIVE, so its
diffusion freezes adjacent water AGGRESSIVELY (much colder than dry ice's -78).

Unlike dry ice, LN2 is **transient**: it boils off at ambient (room temperature
is far above its -196 boiling point). It carries a per-cell ``life`` countdown
(seeded by :func:`sandfall.rules._common.seed_nitrogen_life`); when life is
exhausted the cell becomes EMPTY (boiled away). The short window is tuned so a
painted blob visibly freezes a patch of water before it boils off. (A cold SMOKE
puff on boil-off is a noted visual option, deferred for scope; EMPTY is the
minimal choice -- see the thermal-realism plan Out of Scope.)

Each step, in fixed precedence:

1. **Age / boil off** -- decrement life; at <= 0 become EMPTY (boiled away). This
   mirrors the smoke/steam age idiom (``rules/smoke.py``).
2. **Re-assert cold** -- while alive, clamp temp DOWN to LN2_COLD_TARGET so the
   diffusion pre-pass keeps drawing extreme cold from it (mirrors dry ice's /
   fire's re-assert).
3. **Flow** -- move like a light liquid (water.py / oil.py shape via can_displace
   + swap): straight down, down-diagonals randomized, one-cell sideways
   randomized. Because LN2 is LIGHTER than water, water displaces it (it floats).

No burn/dissolve of its own. ``swap`` carries life AND temp on every flow move,
so a flowing LN2 cell keeps its remaining life and its -196 cold. This is the
formal use of the reactive-rule relaxation for the age/re-assert steps
(transform own cell in place, return None); the flow step returns a destination.
"""

from __future__ import annotations

import random

from ..elements import ElementId
from ..grid import Grid
from ._common import can_displace, swap

# The cold temperature an LN2 cell holds (and re-asserts) each step while alive.
# A cold source: diffusion carries this cold outward. NOT a physical temperature
# beyond being LN2's boiling point (-196C) -- it is a tunable knob for freeze
# spread rate. Far colder than DRY_ICE_COLD_TARGET (-78), so LN2 freezes water
# much faster than dry ice -- but only for as long as its finite life lasts.
LN2_COLD_TARGET = -196


def update_ln2(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an LN2 cell: age (boil off), re-assert cold, else flow like a light
    liquid."""
    # 1. Age; boil off to EMPTY when life is exhausted (mirrors smoke/steam).
    life = grid.get_life(x, y) - 1
    if life <= 0:
        grid.set(x, y, ElementId.EMPTY)
        grid.set_life(x, y, 0)
        return None
    grid.set_life(x, y, life)

    # 2. Re-assert cold while alive (persistent extreme-cold source).
    if grid.get_temp(x, y) > LN2_COLD_TARGET:
        grid.set_temp(x, y, LN2_COLD_TARGET)

    # 3. Flow like a light liquid (water.py / oil.py shape via can_displace + swap).
    if y + 1 < grid.height and can_displace(ElementId.LN2, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)
    diagonals = [-1, 1]
    random.shuffle(diagonals)
    for dx in diagonals:
        nx, ny = x + dx, y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.LN2, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)
    sideways = [-1, 1]
    random.shuffle(sideways)
    for dx in sideways:
        nx, ny = x + dx, y
        if grid.in_bounds(nx, ny) and can_displace(ElementId.LN2, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None

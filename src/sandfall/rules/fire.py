"""Fire (gas-like, finite life) update rule.

Each step a fire cell:

1. Ages (decrements its per-cell ``life``). When life hits 0 the cell
   becomes EMPTY and the rule returns ``None``.
2. May ignite flammable neighbors (WOOD/PLANT). The per-step probability
   is ``min(1.0, target.flammability * SPREAD_FACTOR)``; on ignition the
   neighbor becomes FIRE with a freshly seeded life.
3. With a small chance, spawns a SMOKE cell in an EMPTY neighbor above.
4. Tries to rise: straight up into EMPTY; else up-diagonals randomized.

Fire rises only into EMPTY (it does not displace other gases or liquids in
v1). The rule returns the cell it rose into, or ``None`` if it stayed.
Side effects (spread, smoke) do NOT mark the new cells moved — the binding
rule contract allows only one return value — so a newly ignited fire above
the current cell may also update later in the same bottom-to-top scan. With
the tuned low probabilities this is the desired "chain reaction" feel and
is bounded by grid size.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import swap

# Tunables (feel-free-to-nudge knobs documented in the phase-03 reflection).
SPREAD_FACTOR = 0.3  # multiplied by target flammability per neighbor per step
SMOKE_CHANCE = 0.05  # per-step chance to emit one smoke puff

# 8-neighborhood (dx, dy); +y is DOWN, so "above" is dy = -1.
_NEIGHBORS_8: tuple[tuple[int, int], ...] = (
    (-1, -1),
    (0, -1),
    (1, -1),
    (-1, 0),
    (1, 0),
    (-1, 1),
    (0, 1),
    (1, 1),
)
# Cells directly above (up, up-left, up-right) — preferred smoke spawn sites.
_ABOVE: tuple[tuple[int, int], ...] = ((0, -1), (-1, -1), (1, -1))


def _seed_fire_life() -> int:
    return random.randint(20, 40)


def _seed_smoke_life() -> int:
    return random.randint(60, 120)


def update_fire(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step a fire cell: age, maybe spread, maybe smoke, then rise."""
    # 1. Age; expire to EMPTY when life is exhausted.
    life = grid.get_life(x, y) - 1
    if life <= 0:
        grid.set(x, y, ElementId.EMPTY)
        grid.set_life(x, y, 0)
        return None
    grid.set_life(x, y, life)

    # 2. Ignite flammable neighbors.
    for dx, dy in _NEIGHBORS_8:
        nx, ny = x + dx, y + dy
        if not grid.in_bounds(nx, ny):
            continue
        target_id = grid.get(nx, ny)
        if target_id == ElementId.EMPTY:
            continue
        target = ELEMENTS[ElementId(target_id)]
        if target.flammability <= 0.0:
            continue
        if random.random() < min(1.0, target.flammability * SPREAD_FACTOR):
            grid.set(nx, ny, ElementId.FIRE)
            grid.set_life(nx, ny, _seed_fire_life())

    # 3. Maybe emit smoke into an EMPTY cell above.
    if random.random() < SMOKE_CHANCE:
        spots = [
            (x + dx, y + dy)
            for dx, dy in _ABOVE
            if grid.in_bounds(x + dx, y + dy)
            and grid.get(x + dx, y + dy) == ElementId.EMPTY
        ]
        if spots:
            sx, sy = random.choice(spots)
            grid.set(sx, sy, ElementId.SMOKE)
            grid.set_life(sx, sy, _seed_smoke_life())

    # 4. Rise: straight up into EMPTY first; else up-diagonals randomized.
    if y - 1 >= 0 and grid.get(x, y - 1) == ElementId.EMPTY:
        swap(grid, x, y, x, y - 1)
        return (x, y - 1)
    diagonals = [(-1, -1), (1, -1)]
    random.shuffle(diagonals)
    for dx, dy in diagonals:
        nx, ny = x + dx, y + dy
        if grid.in_bounds(nx, ny) and grid.get(nx, ny) == ElementId.EMPTY:
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None

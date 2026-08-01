"""Acid (LIQUID, dense, consumed-on-dissolve) update rule.

Acid is a dense liquid (density 1.2, denser than WATER 1.0 -> sinks through
water) that DISSOLVES adjacent materials (Powder Toy's consumed-on-dissolve
model). Each step, in fixed precedence:

1. **Burn** -- if the cell's own temp exceeds its flashpoint, become FIRE (seed
   life, set burn-temp). Mirrors wood/plant reactive ignition.
2. **Neutralize** -- if any orthogonal neighbor is BASE, BOTH this cell and
   that neighbor become hot STEAM (`NEUTRALIZE_TEMP`, seeded life). The STEAM
   then condenses to WATER via the steam rule (temp < condense_point -> WATER),
   so the end state is still water but via a hot, gaseous intermediate
   (exothermic). Idempotent across scan orders: the base rule performs the
   identical STEAM write, so whichever scans first wins.
3. **Dissolve** -- with per-step chance DISSOLVE_CHANCE, eat ONE adjacent
   dissolvable neighbor: the target becomes EMPTY (or, with chance
   DISSOLVE_SMOKE_CHANCE, SMOKE seeded via seed_smoke_life for visual feedback),
   and the acid cell itself becomes EMPTY (consumed). Acid dissolves everything
   EXCEPT the ACID_RESIST set (glass resists acid -> glass containers hold it).
4. **Flow** -- otherwise move like a dense liquid (water.py shape: straight
   down, down-diagonals randomized, one-cell sideways randomized) via
   can_displace + swap.

There is intentionally NO dilute step. Acid + WATER simply coexist (acid is
denser, 1.2 > 1.0, so it sinks through water via the Flow step). A prior
`dilute` rule (acid adjacent to WATER -> become WATER/EMPTY) was autocatalytic:
one water cell -- e.g. condensed from neutralization steam -- dissolved the
whole acid pool, defeating ~1:1 neutralization. Removing it entirely is what
guarantees a single base cannot clear a whole pool.

Because dissolve consumes the acid cell (id-changed) every time it fires, the
dormant-cell wake condition (id_changed | moved, dilated) keeps the front
alive without ACID joining the FIRE/LAVA persistent-source wake. See the master
plan Risks #1.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import (
    can_displace,
    maybe_convect,
    seed_fire_life,
    seed_smoke_life,
    seed_steam_life,
    swap,
)

# Tunables (first-pass values; pin final tuned values in the reflection).
DISSOLVE_CHANCE = 0.5  # per-step chance to eat one dissolvable neighbor
DISSOLVE_SMOKE_CHANCE = 0.10  # chance a dissolved target emits SMOKE (else EMPTY)
NEUTRALIZE_TEMP = 150  # temp (°C) the acid+base -> STEAM reaction heats both cells to

# Acid does NOT dissolve these (glass resists acid; the rest are the special
# non-dissolve cases). A neighbor is dissolvable iff grid.get != EMPTY and not
# in this set. EMPTY is included so the single `not in` test suffices.
ACID_RESIST: frozenset[int] = frozenset(
    int(e)
    for e in (
        ElementId.EMPTY,
        ElementId.GLASS,
        ElementId.ACID,
        ElementId.BASE,
        ElementId.WATER,
        ElementId.LAVA,
        ElementId.FIRE,
        ElementId.SMOKE,
        ElementId.STEAM,
    )
)

_ELM = ELEMENTS[ElementId.ACID]
_FIRE = ELEMENTS[ElementId.FIRE]

# Orthogonal 4-neighborhood (matches lava.py / fire.py / the diffusion pass).
_NEIGHBORS_4: tuple[tuple[int, int], ...] = ((0, -1), (0, 1), (-1, 0), (1, 0))


def update_acid(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an acid cell: burn, else neutralize, else dissolve, else flow like
    a dense liquid."""
    # 1. Burn: own temp above flashpoint -> FIRE.
    if _ELM.flashpoint > 0 and grid.get_temp(x, y) > _ELM.flashpoint:
        grid.set(x, y, ElementId.FIRE)
        grid.set_life(x, y, seed_fire_life())
        grid.set_temp(x, y, _FIRE.burn_temp)
        return None

    # Scan the 4-neighborhood once for the reactive checks.
    for dx, dy in _NEIGHBORS_4:
        nx, ny = x + dx, y + dy
        if not grid.in_bounds(nx, ny):
            continue
        nb = grid.get(nx, ny)

        # 2. Neutralize: acid adjacent to BASE -> BOTH become hot STEAM. The
        #    STEAM then condenses to WATER via the steam rule (temp <
        #    condense_point -> WATER), so the end state is still water but via
        #    a hot, gaseous intermediate (exothermic). There is no separate
        #    dilute step (see module docstring), so producing STEAM (not WATER)
        #    here is what leaves the surrounding acid alone (~1:1: one base
        #    neutralizes ~one acid cell, and the resulting water does NOT
        #    propagate through the pool). Idempotent across scan orders: the
        #    base rule performs the identical STEAM write, so whichever scans
        #    first wins. set_life/set_temp are MANDATORY: grid.set updates ONLY
        #    the element id (grid.py), so without them the cell keeps the stale
        #    acid life (0 -> steam expires) and temp (ambient 20 < condense_point
        #    60 -> instant condense).
        if nb == ElementId.BASE:
            grid.set(x, y, ElementId.STEAM)
            grid.set(nx, ny, ElementId.STEAM)
            grid.set_life(x, y, seed_steam_life())
            grid.set_life(nx, ny, seed_steam_life())
            grid.set_temp(x, y, NEUTRALIZE_TEMP)
            grid.set_temp(nx, ny, NEUTRALIZE_TEMP)
            return None

    # 3. Dissolve: with DISSOLVE_CHANCE, eat ONE dissolvable neighbor (consumed).
    if random.random() < DISSOLVE_CHANCE:
        targets = [
            (x + dx, y + dy)
            for dx, dy in _NEIGHBORS_4
            if grid.in_bounds(x + dx, y + dy)
            and grid.get(x + dx, y + dy) not in ACID_RESIST
        ]
        if targets:
            tx, ty = random.choice(targets)
            if random.random() < DISSOLVE_SMOKE_CHANCE:
                grid.set(tx, ty, ElementId.SMOKE)
                grid.set_life(tx, ty, seed_smoke_life())
            else:
                grid.set(tx, ty, ElementId.EMPTY)
            # Acid itself is consumed.
            grid.set(x, y, ElementId.EMPTY)
            return None

    # Convection: a hot fluid cell rises through the cooler same-phase cell
    # above it (intra-phase buoyancy). Checked AFTER reactive transitions and
    # BEFORE gravity flow: a convecting cell swaps up this step instead of
    # falling/spreading (one move per step).
    convect = maybe_convect(grid, x, y)
    if convect is not None:
        return convect

    # 4. Flow like a dense liquid (water.py shape via can_displace + swap).
    if y + 1 < grid.height and can_displace(ElementId.ACID, grid.get(x, y + 1)):
        swap(grid, x, y, x, y + 1)
        return (x, y + 1)
    diagonals = [-1, 1]
    random.shuffle(diagonals)
    for dx in diagonals:
        nx, ny = x + dx, y + 1
        if grid.in_bounds(nx, ny) and can_displace(ElementId.ACID, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)
    sideways = [-1, 1]
    random.shuffle(sideways)
    for dx in sideways:
        nx, ny = x + dx, y
        if grid.in_bounds(nx, ny) and can_displace(ElementId.ACID, grid.get(nx, ny)):
            swap(grid, x, y, nx, ny)
            return (nx, ny)

    return None

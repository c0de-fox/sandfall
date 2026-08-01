"""Acid (LIQUID, dense, consumed-on-dissolve) update rule.

Acid is a dense liquid (density 1.2, denser than WATER 1.0 -> sinks through
water) that DISSOLVES adjacent materials (Powder Toy's consumed-on-dissolve
model). Each step, in fixed precedence:

1. **Burn** -- if the cell's own temp exceeds its flashpoint, become FIRE (seed
   life, set burn-temp). Mirrors wood/plant reactive ignition.
2. **Neutralize** -- if any orthogonal neighbor is BASE, BOTH this cell and
   that neighbor become WATER (a side-effect write on the neighbor, like the
   LAVA+WATER reaction). Idempotent: setting WATER on already-WATER is harmless,
   so the randomized scan order does not matter.
3. **Dilute** -- if any orthogonal neighbor is WATER, with per-step chance
   DILUTE_CHANCE become WATER itself. If it does NOT dilute, fall through to
   dissolve/flow (so acid still sinks through water).
4. **Dissolve** -- with per-step chance DISSOLVE_CHANCE, eat ONE adjacent
   dissolvable neighbor: the target becomes EMPTY (or, with chance
   DISSOLVE_SMOKE_CHANCE, SMOKE seeded via seed_smoke_life for visual feedback),
   and the acid cell itself becomes EMPTY (consumed). Acid dissolves everything
   EXCEPT the ACID_RESIST set (glass resists acid -> glass containers hold it).
5. **Flow** -- otherwise move like a dense liquid (water.py shape: straight
   down, down-diagonals randomized, one-cell sideways randomized) via
   can_displace + swap.

Because dissolve consumes the acid cell (id-changed) every time it fires, the
dormant-cell wake condition (id_changed | moved, dilated) keeps the front
alive without ACID joining the FIRE/LAVA persistent-source wake. See the master
plan Risks #1.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import can_displace, seed_fire_life, seed_smoke_life, swap

# Tunables (first-pass values; pin final tuned values in the reflection).
DISSOLVE_CHANCE = 0.5  # per-step chance to eat one dissolvable neighbor
DILUTE_CHANCE = 0.08  # per-step chance to dilute into adjacent water
DISSOLVE_SMOKE_CHANCE = 0.10  # chance a dissolved target emits SMOKE (else EMPTY)

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
    """Step an acid cell: burn, else neutralize, else dilute, else dissolve,
    else flow like a dense liquid."""
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

        # 2. Neutralize: acid adjacent to BASE -> BOTH become WATER (side-effect
        #    write on the neighbor, idempotent across scan orders).
        if nb == ElementId.BASE:
            grid.set(x, y, ElementId.WATER)
            grid.set(nx, ny, ElementId.WATER)
            return None

        # 3. Dilute: acid adjacent to WATER -> probabilistically become WATER.
        #    (If it does not dilute, keep scanning; the dissolve/flow steps
        #    still run so it sinks through water.)
        if nb == ElementId.WATER and random.random() < DILUTE_CHANCE:
            grid.set(x, y, ElementId.WATER)
            return None

    # 4. Dissolve: with DISSOLVE_CHANCE, eat ONE dissolvable neighbor (consumed).
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

    # 5. Flow like a dense liquid (water.py shape via can_displace + swap).
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

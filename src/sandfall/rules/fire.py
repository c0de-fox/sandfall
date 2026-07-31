"""Fire (gas-like, finite life, heat source) update rule.

Fire is a heat SOURCE, not a spreader. Each step a fire cell:

1. Ages (decrements its per-cell ``life``). When life hits 0 the cell
   becomes EMPTY, resets its temperature to ``AMBIENT_TEMP``, and the
   rule returns ``None``.
2. Re-asserts its burn-temp (~800): while it still has life it is a heat
   source, so the cell's temperature is clamped up to ``burn_temp`` each
   step. The Simulation's vectorized diffusion pre-pass carries that heat
   to neighbors; it cannot quench the source while it still has life.
3. With a small chance (``SMOKE_CHANCE``), spawns a SMOKE cell in an EMPTY
   neighbor above. (Unchanged from v1.)
4. Rises — *unless* a flammable neighbor is in reach, in which case the fire
   CLINGS to it (stays put to sustain heating). Without clinging, a fire
   cell rises away from fuel in 1-2 steps, faster than the diffusion pre-pass
   can raise the fuel to its flashpoint, so combustion would never chain.
   Once the fuel ignites it becomes FIRE (no longer flammable), so the fire
   then rises normally.

Fire does NOT ignite its neighbors directly — there is no per-neighbor
spread loop anymore. A flammable neighbor ignites ITSELF when its OWN
temperature exceeds its ``flashpoint`` (see the WOOD / PLANT reactive
rules, which check ``get_temp(x,y) > flashpoint``). This decouples
ignition from fire's scan: one physical cause (heat diffusion) instead of
two competing models (probability + heat).

Fire rises only into EMPTY (it does not displace other gases or liquids in
v1). The rule returns the cell it rose into, or ``None`` if it stayed.
Side effects (smoke) do NOT mark the new cells moved — the binding rule
contract allows only one return value — so a newly spawned smoke above
the current cell may also update later in the same bottom-to-top scan.
This is the desired "chain reaction" feel and is bounded by grid size.
"""

from __future__ import annotations

import random

from ..elements import AMBIENT_TEMP, ELEMENTS, ElementId
from ..grid import Grid
from ._common import seed_smoke_life, swap

# Tunables (feel-free-to-nudge knobs documented in the phase-02 reflection).
SMOKE_CHANCE = 0.05  # per-step chance to emit one smoke puff

# The temperature a living fire cell holds (and re-asserts) each step. A
# heat source: diffusion carries this heat outward, but cannot cool the fire
# below this value while it still has life. Sourced from ELEMENTS so tuning
# the value in one place (the registry) propagates everywhere.
_BURN_TEMP = ELEMENTS[ElementId.FIRE].burn_temp  # ~800

# Cells directly above (up, up-left, up-right) — preferred smoke spawn sites.
_ABOVE: tuple[tuple[int, int], ...] = ((0, -1), (-1, -1), (1, -1))

# Orthogonal neighborhood used by the cling check (matches the 4-neighborhood
# the diffusion pre-pass uses, so "in reach" and "being heated" agree).
_NEIGHBORS_4: tuple[tuple[int, int], ...] = ((-1, 0), (1, 0), (0, -1), (0, 1))


def _has_flammable_neighbor(grid: Grid, x: int, y: int) -> bool:
    """True if any orthogonal neighbor is a flammable element (``flashpoint > 0``).

    Drives the cling behavior: a fire with fuel in reach stays put so the
    diffusion pre-pass can raise the fuel to its flashpoint. EMPTY and
    non-flammable cells (stone, sand, water, ...) do not count.
    """
    for dx, dy in _NEIGHBORS_4:
        nx, ny = x + dx, y + dy
        if grid.in_bounds(nx, ny):
            nid = grid.get(nx, ny)
            if nid != ElementId.EMPTY and ELEMENTS[ElementId(nid)].flashpoint > 0:
                return True
    return False


def update_fire(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step a fire cell: age, maintain burn-temp, maybe smoke, then rise."""
    # 1. Age; expire to EMPTY when life is exhausted. An expired fire cools
    #    back to ambient (it is no longer a heat source).
    life = grid.get_life(x, y) - 1
    if life <= 0:
        grid.set(x, y, ElementId.EMPTY)
        grid.set_life(x, y, 0)
        grid.set_temp(x, y, AMBIENT_TEMP)
        return None
    grid.set_life(x, y, life)

    # 2. Maintain burn-temp: a living fire is a heat source. Re-assert >=
    #    burn_temp each step so the diffusion pre-pass carries heat outward
    #    but cannot quench the source while it still has life.
    if grid.get_temp(x, y) < _BURN_TEMP:
        grid.set_temp(x, y, _BURN_TEMP)

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
            grid.set_life(sx, sy, seed_smoke_life())

    # 4. Rise — unless a flammable neighbor is in reach. Fire CLINGS to fuel
    #    (stays put to sustain heating) so combustion can chain: see the rule
    #    docstring. Once the fuel ignites it is FIRE (not flammable), so the
    #    fire then rises normally.
    if _has_flammable_neighbor(grid, x, y):
        return None
    # Rise: straight up into EMPTY first; else up-diagonals randomized.
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

"""Dry ice (SOLID, persistent cold source) update rule.

Dry ice is the **persistent cold source** that ice used to be (interim): each
step it re-asserts its cold target temperature (``DRY_ICE_COLD_TARGET`` = -78C,
the sublimation point of CO2), exactly as a living fire cell re-asserts its
burn_temp (``rules/fire.py``). The Simulation's vectorized diffusion pre-pass
carries that cold outward; adjacent water cools to/below its freeze_point and
the WATER rule freezes it to ICE. Because dry ice is much colder than ice (-78
vs ~0), cold propagates THROUGH the resulting ice shell (ice conducts heat) to
reach ever-farther water, so the freeze front advances while the dry ice
persists. This is the realistic Powder Toy / Sandboxels cold source.

Dry ice sublimates ONLY via direct fire/lava contact (NOT ambient -- it
re-asserts cold): a FIRE neighbor -> EMPTY (gentle sublimation); a LAVA neighbor
-> SMOKE (intense heat -> a visible CO2 vapor puff, seeded with smoke life). It
persists indefinitely in ambient.

This is the formal use of the reactive-rule contract relaxation (transform own
cell in place, return None); the cell does not MOVE so the simulation's
moved-this-frame guard is unaffected.
"""

from __future__ import annotations

from ..elements import ElementId
from ..grid import Grid
from ._common import seed_smoke_life

# The cold temperature a dry-ice cell holds (and re-asserts) each step. A cold
# source: diffusion carries this cold outward, but cannot warm the dry ice above
# this value while the rule keeps re-asserting it. NOT a physical temperature --
# it is a tunable knob for freeze spread rate (colder -> faster spread). -78 is
# CO2's sublimation point; colder than the interim ICE_COLD_TARGET (-50), so it
# freezes water faster than interim ice did. Mirrors the LAVA_SOLIDIFY_TEMP
# pattern in rules/lava.py.
DRY_ICE_COLD_TARGET = -78

# Orthogonal neighborhood for the fire/lava sublimation check (matches the
# 4-neighborhood the diffusion pre-pass and lava.py use).
_SUBLIMATE_NEIGHBORS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (0, 1),
    (-1, 0),
    (1, 0),
)


def update_dry_ice(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step a dry-ice cell: sublimate via direct fire/lava contact, else
    re-assert cold.

    1. **Sublimate via direct fire/lava contact.** A FIRE neighbor -> EMPTY
       (gentle sublimation); a LAVA neighbor -> SMOKE (intense heat flashes it
       to a vapor puff). Checked FIRST so a hot contact destroys the dry ice
       before it can re-assert cold. (Dry ice does NOT sublimate from ambient --
       it re-asserts cold each step.)
    2. **Re-assert the cold target.** While still dry ice, clamp the cell's temp
       DOWN to DRY_ICE_COLD_TARGET each step so it remains a persistent cold
       source the diffusion pre-pass draws from (mirrors fire's burn-temp
       re-assert and the retired interim-ice behavior).
    """
    # 1. Direct fire/lava contact sublimates the dry ice.
    for dx, dy in _SUBLIMATE_NEIGHBORS:
        nx, ny = x + dx, y + dy
        if not grid.in_bounds(nx, ny):
            continue
        neighbor = grid.get(nx, ny)
        if neighbor == ElementId.LAVA:
            grid.set(x, y, ElementId.SMOKE)
            grid.set_life(x, y, seed_smoke_life())
            return None
        if neighbor == ElementId.FIRE:
            grid.set(x, y, ElementId.EMPTY)
            return None

    # 2. Re-assert cold: a living dry-ice cell is a persistent cold source.
    if grid.get_temp(x, y) > DRY_ICE_COLD_TARGET:
        grid.set_temp(x, y, DRY_ICE_COLD_TARGET)

    return None

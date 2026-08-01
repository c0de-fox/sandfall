"""Reusable explosion helper (heat burst + crater + scatter).

``explode(grid, x, y, ...)`` models a blast as three effects applied over a
circular radius (``dx*dx+dy*dy <= radius*radius``), processed **outer-first**
(so scatter pushes cells into already-processed outer positions, preventing a
scattered cell from being moved again this blast):

1. **Heat burst** (distance falloff) -- raises the temp of every non-empty cell
   in the radius. This is what CHAINS gunpowder (other gunpowder heated past its
   flashpoint detonates on its own scan / next frame), ignites flammables
   (wood/plant/oil -> FIRE via their own flashpoint rules), and boils water
   (-> STEAM) -- all through the existing thermal thresholds, no new transition
   code.
2. **Crater** (inner radius) -- destroys everything (user choice: no blast-
   resistant material). The very core (d <= 1) becomes FIRE (the fireball, hot,
   seeded life) with ``CORE_FIRE_CHANCE``; the rest of the crater -> EMPTY (or
   SMOKE with ``CRATER_SMOKE_CHANCE`` for visual). EXCEPTION: GUNPOWDER in the
   radius is NOT destroyed here -- it is only HEATED (step 1), so it chains via
   its own rule (destroying it would break the chain).
3. **Scatter** (outer radius) -- loose materials (POWDER/LIQUID phase) are
   pushed one cell OUTWARD (away from the blast center) with ``SCATTER_CHANCE``
   if the outward target is EMPTY, for the "stuff goes flying" feel.

All writes are side-effect writes (direct ``grid.set`` / ``set_temp``, like
``lava.py``'s water->STEAM reaction), so the caller (e.g. ``update_gunpowder``)
returns ``None`` after calling ``explode``. The dormant-cell wake catches every
blasted cell via ``id_changed`` (condition #1, dilated) and ``temp_changed``
(condition #2), so the blast zone -- and the chain -- stays active with NO
wake-condition edit. See the master plan Risks #1.

**Visit order.** The in-radius offsets are collected into one flat list and
sorted by distance DESCENDING, so each cell is visited EXACTLY once per blast
and the outer ring is processed before the inner. (The original plan sketch used
an ``abs(d - dist_ring) > 0.9`` band selector, but a width-1.8 band double-
selects cells near a half-integer distance -- e.g. d=sqrt(2)~=1.41 lies within
0.9 of BOTH ring 1 and ring 2, so it would be heated/destroyed twice. The flat
descending sort keeps the exact contract -- heat everything / spare GUNPOWDER /
crater the inner / scatter loose outward -- while guaranteeing exactly-once.)
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId, Phase
from ..grid import Grid
from ._common import seed_fire_life, seed_smoke_life

# Tunables (first-pass values; pin final tuned values in the reflection).
# Module globals read at call time (like fire.py's SMOKE_CHANCE), so tests pin
# them deterministic via monkeypatch.setattr(blast, "...", ...).
BLAST_RADIUS = 4  # outer radius of the heat/scatter effect (cells)
CRATER_RADIUS = 2  # inner radius destroyed by the blast (cells)
BLAST_HEAT = 1200.0  # peak temp added at the center (falloff outward)
CORE_FIRE_CHANCE = 0.8  # chance a d<=1 crater cell becomes FIRE (the fireball)
CRATER_SMOKE_CHANCE = 0.15  # chance a crater cell (beyond core) becomes SMOKE
SCATTER_CHANCE = 0.5  # chance a loose cell in the outer ring is pushed out

_FIRE = ELEMENTS[ElementId.FIRE]


def _is_loose(element_id: int) -> bool:
    """True for materials scatter pushes: POWDER or LIQUID phase (sand, water,
    oil, acid, base, gunpowder-when-not-the-detonator). These have life 0
    always, so the scatter's manual ``set`` need not carry the ``life`` array
    (temp IS carried explicitly)."""
    return ELEMENTS[ElementId(element_id)].phase in (Phase.POWDER, Phase.LIQUID)


def explode(
    grid: Grid,
    x: int,
    y: int,
    radius: int = BLAST_RADIUS,
    crater: int = CRATER_RADIUS,
    heat: float = BLAST_HEAT,
) -> None:
    """Detonate at ``(x, y)``: heat burst + crater + scatter over a circular
    radius, processed outer-first. See the module docstring for the model.

    Parameters mirror the module-level tunables so future explosives (TNT,
    bombs) can call ``explode`` with their own radius/heat without touching
    gunpowder's defaults.
    """
    r2 = radius * radius
    # Collect every in-radius offset ONCE with its Euclidean distance, then
    # sort by distance DESCENDING. Outer-first means scatter (which pushes a
    # cell one step OUTWARD, to a strictly larger distance) always lands in a
    # position already processed this blast, so a scattered cell is never
    # revisited/moved twice. Each offset is visited exactly once.
    offsets: list[tuple[float, int, int]] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            d2 = dx * dx + dy * dy
            if d2 > r2:
                continue  # outside the circular radius
            offsets.append((d2**0.5, dx, dy))
    offsets.sort(key=lambda o: o[0], reverse=True)

    for d, dx, dy in offsets:
        nx, ny = x + dx, y + dy
        if not grid.in_bounds(nx, ny):
            continue
        nb = grid.get(nx, ny)
        if nb == ElementId.EMPTY:
            continue

        # 1. Heat burst (distance falloff) -- chains gunpowder, ignites,
        #    boils/melts via the existing thermal thresholds.
        falloff = max(0.0, 1.0 - d / (radius + 1))
        grid.set_temp(nx, ny, grid.get_temp(nx, ny) + heat * falloff)
        if nb == ElementId.GUNPOWDER:
            # Heated -> its own rule detonates it (the chain). Do NOT destroy:
            # destroying it here would break the chain (master plan Decision #6).
            continue

        # 2. Crater (inner) -- destroy everything (user choice, Decision #5).
        if d <= crater:
            if d <= 1.0 and random.random() < CORE_FIRE_CHANCE:
                grid.set(nx, ny, ElementId.FIRE)
                grid.set_life(nx, ny, seed_fire_life())
                grid.set_temp(nx, ny, _FIRE.burn_temp)
            elif random.random() < CRATER_SMOKE_CHANCE:
                grid.set(nx, ny, ElementId.SMOKE)
                grid.set_life(nx, ny, seed_smoke_life())
            else:
                grid.set(nx, ny, ElementId.EMPTY)
            continue

        # 3. Scatter (outer) -- push loose materials one cell outward.
        if _is_loose(nb) and random.random() < SCATTER_CHANCE:
            # Outward direction = sign of the offset (away from blast center).
            # For an axial cell (dx==0 or dy==0) only the nonzero axis moves;
            # that still pushes the cell strictly further from the center.
            sdx = (dx > 0) - (dx < 0)
            sdy = (dy > 0) - (dy < 0)
            tx, ty = nx + sdx, ny + sdy
            if grid.in_bounds(tx, ty) and grid.get(tx, ty) == ElementId.EMPTY:
                grid.set(tx, ty, nb)
                grid.set_temp(tx, ty, grid.get_temp(nx, ny))
                grid.set(nx, ny, ElementId.EMPTY)

"""Brush painting: write the selected element through a disk or square.

This is the link between the mouse and the grid. :func:`paint_brush` wraps
:meth:`Grid.fill_circle` (which takes a :class:`~sandfall.grid.BrushShape` to
paint either a disk or a square) and adds the per-cell lifetime seeding that
FIRE/SMOKE/STEAM/LN2 require, plus the per-cell spawn-temperature seeding
(Phase 01) that every element's ``temp_spawn`` defines. It is a pure helper (no pygame)
so the life-seeding / temp-seeding behavior is unit-testable headlessly —
which is how the Phase 04 deferred bug ("painted fire dies instantly because
``fill_circle`` zeros life") is covered by a regression test in
``tests/test_brush.py``. The shape-aware seeding pass (covers the SQUARE
bounding box, not just the disk) is the Phase-02 correctness crux and has its
own regression test there too.

Lifetime ranges come from :mod:`sandfall.rules._common` so a user-brushed
fire and a rule-ignited fire live for the same window of steps. Spawn temps
come from :data:`sandfall.elements.ELEMENTS[id].temp_spawn` (Phase 02/03 set
hot spawn-temp for FIRE/LAVA).
"""

from __future__ import annotations

from collections.abc import Callable

from .elements import AMBIENT_TEMP, ELEMENTS, ElementId
from .grid import BrushShape, Grid
from .rules import (
    seed_fire_life,
    seed_nitrogen_life,
    seed_smoke_life,
    seed_steam_life,
)


def paint_brush(
    grid: Grid,
    gx: int,
    gy: int,
    radius: int,
    element_id: ElementId,
    shape: BrushShape = BrushShape.DISK,
) -> None:
    """Paint a filled disk or square of ``element_id`` centered on ``(gx, gy)``.

    Wraps :meth:`Grid.fill_circle` (passing ``shape``; it paints the element
    id and zeros life and resets temp to ``AMBIENT_TEMP`` on every cell of the
    footprint) and then:

    * walks the SAME footprint once more setting each painted cell's
      temperature to its element's ``temp_spawn`` (uniformly for ALL elements
      — most default to ``AMBIENT_TEMP`` so the write is skipped; FIRE and
      LAVA are hot, ICE is cold);
    * for FIRE, SMOKE, STEAM, and LN2 only, seeds each painted cell's life via
      the canonical :func:`seed_fire_life` / :func:`seed_smoke_life` /
      :func:`seed_steam_life` / :func:`seed_nitrogen_life` helpers. Without
      this seeding pass, painted FIRE/SMOKE/STEAM/LN2 would have life 0 and
      expire on the very next step.

    The footprint walk respects ``shape``: SQUARE walks the whole bounding
    box (corners included); DISK walks only the radius-tested disk. This is
    the shape-aware correctness fix (Decision Log #9): without it, a painted
    FIRE/SMOKE/STEAM in a square's CORNER would have life 0 and expire
    instantly (the classic Phase-04 bug resurfacing for the square).

    Out-of-bounds centers are clipped silently (delegated to ``fill_circle``'s
    own clipping plus the bounded loops below). A negative ``radius`` raises
    ``ValueError`` (also delegated to ``fill_circle``).
    """
    grid.fill_circle(gx, gy, radius, element_id, shape)

    spawn_temp = ELEMENTS[element_id].temp_spawn
    if element_id == ElementId.FIRE:
        seed: Callable[[], int] | None = seed_fire_life
    elif element_id == ElementId.SMOKE:
        seed = seed_smoke_life
    elif element_id == ElementId.STEAM:
        seed = seed_steam_life
    elif element_id == ElementId.LN2:
        seed = seed_nitrogen_life
    else:
        seed = None
    # No work to do unless this element needs a hot spawn-temp or life seeding.
    if spawn_temp == AMBIENT_TEMP and seed is None:
        return

    r2 = radius * radius
    x0 = max(0, gx - radius)
    x1 = min(grid.width - 1, gx + radius)
    y0 = max(0, gy - radius)
    y1 = min(grid.height - 1, gy + radius)
    for y in range(y0, y1 + 1):
        dy = y - gy
        for x in range(x0, x1 + 1):
            dx = x - gx
            # SQUARE walks the whole bbox (corners included); DISK keeps the
            # radius test. Either way, only re-seed cells we actually painted.
            in_footprint = shape == BrushShape.SQUARE or dx * dx + dy * dy <= r2
            if in_footprint and grid.get(x, y) == element_id:
                if spawn_temp != AMBIENT_TEMP:
                    grid.set_temp(x, y, spawn_temp)
                if seed is not None:
                    grid.set_life(x, y, seed())

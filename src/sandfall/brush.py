"""Brush painting: write the selected element through a circular disk.

This is the link between the mouse and the grid. :func:`paint_brush` wraps
:meth:`Grid.fill_circle` and adds the per-cell lifetime seeding that
FIRE/SMOKE require. It is a pure helper (no pygame) so the life-seeding
behavior is unit-testable headlessly — which is how the Phase 04 deferred
bug ("painted fire dies instantly because ``fill_circle`` zeros life") is
covered by a regression test in ``tests/test_brush.py``.

Lifetime ranges come from :mod:`sandfall.rules._common` so a user-brushed
fire and a rule-ignited fire live for the same window of steps.
"""

from __future__ import annotations

from .elements import ElementId
from .grid import Grid
from .rules import seed_fire_life, seed_smoke_life


def paint_brush(
    grid: Grid, gx: int, gy: int, radius: int, element_id: ElementId
) -> None:
    """Paint a filled disk of ``element_id`` centered on grid cell ``(gx, gy)``.

    Wraps :meth:`Grid.fill_circle` (which paints the element id and zeros life
    on every cell of the disk) and then, for FIRE and SMOKE only, walks the
    same disk again and seeds each painted cell's life via the canonical
    :func:`seed_fire_life` / :func:`seed_smoke_life` helpers. Without this
    seeding pass, painted FIRE/SMOKE would have life 0 and expire on the very
    next step.

    Out-of-bounds centers are clipped silently (delegated to ``fill_circle``'s
    own clipping plus the bounded loops below). A negative ``radius`` raises
    ``ValueError`` (also delegated to ``fill_circle``).
    """
    grid.fill_circle(gx, gy, radius, element_id)
    if element_id != ElementId.FIRE and element_id != ElementId.SMOKE:
        return

    seed = seed_fire_life if element_id == ElementId.FIRE else seed_smoke_life
    r2 = radius * radius
    x0 = max(0, gx - radius)
    x1 = min(grid.width - 1, gx + radius)
    y0 = max(0, gy - radius)
    y1 = min(grid.height - 1, gy + radius)
    for y in range(y0, y1 + 1):
        dy = y - gy
        for x in range(x0, x1 + 1):
            dx = x - gx
            if dx * dx + dy * dy <= r2 and grid.get(x, y) == element_id:
                grid.set_life(x, y, seed())

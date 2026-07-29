"""Shared helpers for element update rules.

These encode the cross-rule contracts used throughout the simulation:

* :func:`can_displace` — the density/phase swap test (sand sinks in water;
  water itself only displaces EMPTY in v1 since no lower-density liquid
  exists yet).
* :func:`swap` — exchange two cells' element ids AND their per-cell life
  values. Every rule that moves a cell must go through this helper so the
  parallel ``life`` array stays consistent with the element id array.
* :func:`seed_fire_life` / :func:`seed_smoke_life` — the canonical lifetime
  ranges for FIRE and SMOKE cells. Both the rules (when they ignite/spawn)
  and the painting path (when the user brushes FIRE/SMOKE onto the grid) go
  through these so a painted fire burns for the same duration as a
  rule-spawned one. Centralizing them here is what lets Phase 05's brush
  fix the "painted fire dies instantly" bug without duplicating magic
  numbers.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId, Phase
from ..grid import Grid


def can_displace(src_id: ElementId, target_id: int) -> bool:
    """True if an element ``src_id`` may move into a cell holding ``target_id``.

    A cell is displacable if it is EMPTY, or if it holds a strictly
    lower-density LIQUID (so denser powders/liquids sink through lighter
    liquids). Solids, gases, and same/higher-density liquids are not
    displacable.
    """
    if target_id == ElementId.EMPTY:
        return True
    src = ELEMENTS[src_id]
    target = ELEMENTS[ElementId(target_id)]
    return target.phase == Phase.LIQUID and target.density < src.density


def seed_fire_life() -> int:
    """Return a freshly seeded lifetime (in steps) for a new FIRE cell.

    The single source of truth for FIRE duration: both the fire rule's
    spread/spawn paths and the user-facing FIRE brush call this so a painted
    fire and a rule-ignited fire live for the same window of time.
    """
    return random.randint(20, 40)


def seed_smoke_life() -> int:
    """Return a freshly seeded lifetime (in steps) for a new SMOKE cell.

    The single source of truth for SMOKE duration (see :func:`seed_fire_life`).
    """
    return random.randint(60, 120)


def swap(grid: Grid, x1: int, y1: int, x2: int, y2: int) -> None:
    """Swap the contents (element id AND life) of two in-bounds cells.

    Both cells must be in bounds. Carrying life along on every move is what
    keeps FIRE/SMOKE lifetimes correct when those cells get pushed around
    (e.g. fire rising, sand displacing a cell that later becomes fire).
    """
    a = grid.get(x1, y1)
    b = grid.get(x2, y2)
    grid.set(x1, y1, b)
    grid.set(x2, y2, a)
    la = grid.get_life(x1, y1)
    lb = grid.get_life(x2, y2)
    grid.set_life(x1, y1, lb)
    grid.set_life(x2, y2, la)

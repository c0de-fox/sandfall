"""The simulation: steps the grid one tick at a time."""

from __future__ import annotations

import random

import numpy as np
import numpy.typing as npt

from .elements import ElementId
from .grid import Grid
from .rules import RULES


class Simulation:
    """Owns a ``Grid`` and advances it one step per call to ``step``.

    Scan order: ``y`` descending (bottom → top) so a single grain falls at
    most one cell per step (prevents teleporting through the grid in one
    frame). The ``x`` direction is randomized per row to avoid left bias.
    A moved-this-frame guard prevents re-dispatching a cell that was moved
    *into* earlier in the same scan.
    """

    def __init__(self, grid: Grid) -> None:
        self._grid = grid

    @property
    def grid(self) -> Grid:
        return self._grid

    def step(self) -> None:
        """Advance the simulation by exactly one frame."""
        grid = self._grid
        moved: npt.NDArray[np.bool_] = np.zeros(
            (grid.height, grid.width), dtype=np.bool_
        )
        for y in range(grid.height - 1, -1, -1):
            xs = (
                range(grid.width)
                if random.random() < 0.5
                else range(grid.width - 1, -1, -1)
            )
            for x in xs:
                if moved[y, x]:
                    continue
                eid = grid.get(x, y)
                if eid == ElementId.EMPTY:
                    continue
                fn = RULES.get(ElementId(eid))
                if fn is None:
                    continue
                dest = fn(grid, x, y)
                if dest is not None:
                    dx, dy = dest
                    moved[dy, dx] = True

"""The simulation: steps the grid one tick at a time."""

from __future__ import annotations

import random

import numpy as np
import numpy.typing as npt

from .elements import ElementId
from .grid import Grid
from .rules import RULES
from .thermal import build_conductivity_lut, build_heat_capacity_lut, diffuse_temps


class Simulation:
    """Owns a ``Grid`` and advances it one step per call to ``step``.

    Scan order: ``y`` descending (bottom → top) so a single grain falls at
    most one cell per step (prevents teleporting through the grid in one
    frame). The ``x`` direction is randomized per row to avoid left bias.
    A moved-this-frame guard prevents re-dispatching a cell that was moved
    *into* earlier in the same scan.

    The x scan is SPARSE: only the non-empty cells of each row are visited
    (``np.nonzero`` on the row), so empty rows and empty cells are skipped
    cheaply instead of being iterated as no-ops. This is a performance
    optimization only -- empty cells were no-ops before, so the result is
    identical to the old full-row scan.

    Each ``step`` first runs ONE vectorized heat-diffusion pass over the
    grid's temperature field (Phase 01), so every rule below it reads a
    freshly-diffused temperature. The conductivity LUT and the heat-capacity
    LUT are both built once in ``__init__`` (they are static for the run —
    they only depend on ``config.COND_*`` / ``config.CP_*`` / ``ELEMENTS``).
    """

    def __init__(self, grid: Grid) -> None:
        self._grid = grid
        # Static for the whole run: only depends on config.COND_* / CP_* / ELEMENTS.
        self._cond_lut = build_conductivity_lut()
        self._cp_lut = build_heat_capacity_lut()

    @property
    def grid(self) -> Grid:
        return self._grid

    def step(self) -> None:
        """Advance the simulation by exactly one frame."""
        grid = self._grid
        # Heat diffusion pre-pass (Phase 01): one vectorized op BEFORE the
        # movement scan, so every rule reads a freshly-diffused temperature.
        # diffuse_temps returns a NEW int16 array (does not mutate grid._temp
        # in place), avoiding aliasing surprises in the scan that follows.
        grid._temp = diffuse_temps(grid._temp, grid._data, self._cond_lut, self._cp_lut)
        moved: npt.NDArray[np.bool_] = np.zeros(
            (grid.height, grid.width), dtype=np.bool_
        )
        # Movement scan: y-descending (bottom -> top) so a single grain falls
        # at most one cell per step (no teleporting through the grid). The x
        # direction is randomized per row to avoid left bias. SPARSE: only
        # non-empty cells of each row are visited (np.nonzero on the row),
        # skipping the (frequently many) empty cells that were no-ops before.
        data = grid.array  # raw (H, W) uint8; read directly, no per-cell get() overhead
        for y in range(grid.height - 1, -1, -1):  # y-descending -- UNCHANGED
            xs = np.nonzero(data[y])[0]  # non-empty x's this row (ascending)
            if xs.size == 0:
                continue  # empty row -> skipped in one numpy call
            if random.random() < 0.5:  # per-row random direction -- UNCHANGED
                xs = xs[::-1]
            for x in xs:
                x = int(x)  # numpy intp -> plain int (mypy + rule args)
                if moved[y, x]:
                    continue
                # Mid-scan re-check: a cell non-empty at nonzero-time may have
                # emptied/transformed earlier in this scan (fire expired,
                # erased, displaced). Re-read the raw array and skip if now empty.
                eid = int(data[y, x])
                if eid == int(ElementId.EMPTY):
                    continue
                fn = RULES.get(ElementId(eid))
                if fn is None:
                    continue
                dest = fn(grid, x, y)
                if dest is not None:
                    dx, dy = dest
                    moved[dy, dx] = True

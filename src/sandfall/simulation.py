"""The simulation: steps the grid one tick at a time."""

from __future__ import annotations

import random

import numpy as np
import numpy.typing as npt

from .elements import ElementId
from .grid import Grid
from .rules import RULES
from .thermal import build_conductivity_lut, build_heat_capacity_lut, diffuse_temps


def _dilate(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """Dilate ``mask`` by one cell in the 4-neighborhood (von Neumann).

    A cell in the result is True if it OR any of its up/down/left/right
    neighbors was True in ``mask``. Used to propagate wake signals: when a
    cell moves / changes / is a heat source, the cells that could be affected
    by that (resting on it, beside it, heated by it) must wake next frame.

    Four zero-padded shifted ORs against the ORIGINAL ``mask`` (so the shifts
    do not compound into a 2-cell dilation). O(H*W), one allocation. ``out``
    is written; ``mask`` is only read, so all four shifts see consistent
    original values (no aliasing).
    """
    out = mask.copy()
    out[:, :-1] |= mask[:, 1:]  # right neighbor  -> this cell
    out[:, 1:] |= mask[:, :-1]  # left neighbor   -> this cell
    out[:-1, :] |= mask[1:, :]  # below neighbor  -> this cell
    out[1:, :] |= mask[:-1, :]  # above neighbor  -> this cell
    return out


class Simulation:
    """Owns a ``Grid`` and advances it one step per call to ``step``.

    Scan order: ``y`` descending (bottom → top) so a single grain falls at
    most one cell per step (prevents teleporting through the grid in one
    frame). The ``x`` direction is randomized per row to avoid left bias.
    A moved-this-frame guard prevents re-dispatching a cell that was moved
    *into* earlier in the same scan.

    The x scan is DORMANT-CELL-AWARE: only cells that are BOTH ``active`` AND
    non-empty are visited (``np.nonzero(active[y] & (data[y] != 0))`` per
    row). A settled, ambient-temperature pile with no heat source nearby goes
    *dormant* (``active`` False) and is skipped entirely next frame, while the
    movement front and every reactive cell stay awake. The result is
    identical to the old sparse scan: a dormant cell's rule, when dispatched,
    returned "no move" and drew no RNG, so skipping it changes nothing
    observable -- it was a no-op before.

    Each ``step`` rebuilds ``_active`` from scratch (an OVERWRITE, not ``|=``
    -- carrying the old set forward would let cells marked once stay active
    forever and never sleep) from four wake conditions:

    1. **Movement / identity-change + dilation** -- a cell that moved,
       changed identity, or is orthogonally adjacent to one (so eroding
       support / opening a hole wakes the cells above/beside to fall/flow).
    2. **Thermal change** -- a cell whose temperature changed (via diffusion
       from a heat source, or a rule) must be rescanned: phase transitions
       (water boil/freeze, wood ignite) check the cell's OWN temp.
    3. **FIRE/LAVA persistent heat sources + their neighborhood** -- a
       clinging fire / a lava cell re-asserts its burn-temp and reacts each
       step but may neither move nor change identity nor (if already at
       burn-temp) change temp, so without this rule fire/lava and their fuel
       neighbors would go dormant and combustion/reactions would never chain.
    4. **Brush-painted/erased cells** -- OR-marked into ``_active`` between
       steps by :meth:`Grid.fill_circle` and consumed by the next scan (not
       carried into ``active_next`` unless the sim dynamics woke them).

    A cell firing none of the four goes dormant. Between steps
    ``Grid.fill_circle`` OR marks into ``_active`` so the brush wakes the cells
    it paints/erases; those marks survive exactly one scan. (``Grid.set`` does
    NOT mark active -- it is on the hottest path via ``swap`` and regressed busy
    scenes; ``id_changed`` below covers rule-driven ``set`` calls during the
    scan.) Each ``step`` first runs ONE vectorized heat-diffusion pass over
    the whole grid's temperature field (Phase 01; UNCHANGED -- it MUST stay
    whole-grid so dormant cells' temps still propagate and wake them via
    condition 2), so every rule below it reads a freshly-diffused temperature.
    The conductivity LUT and the heat-capacity LUT are both built once in
    ``__init__`` (they are static for the run — they only depend on
    ``config.COND_*`` / ``config.CP_*`` / ``ELEMENTS``).
    """

    def __init__(self, grid: Grid) -> None:
        self._grid = grid
        # Static for the whole run: only depends on config.COND_* / CP_* / ELEMENTS.
        self._cond_lut = build_conductivity_lut()
        self._cp_lut = build_heat_capacity_lut()
        # Bootstrap: no prior active set exists, so seed the first step with
        # "every non-empty cell is active". This covers the common test pattern
        # ``Grid(); set(...); Simulation(g); step()`` (set before init is
        # overwritten by this seed, which marks the same non-empty cells) and
        # the initial frame of a real game. (Grid.set does NOT itself mark
        # active -- it is on the hottest path via swap; id_changed in step()
        # covers rule-driven set calls, and fill_circle covers the brush.)
        grid._active[:] = grid._data != int(ElementId.EMPTY)

    @property
    def grid(self) -> Grid:
        return self._grid

    def step(self) -> None:
        """Advance the simulation by exactly one frame."""
        grid = self._grid
        # Heat diffusion pre-pass: one vectorized op BEFORE the movement scan, so
        # every rule reads a freshly-diffused temperature. diffuse_temps returns a
        # NEW int16 array (does not mutate grid._temp in place), so keep the OLD
        # reference for the thermal-wake mask below (no copy needed). Stays
        # WHOLE-GRID: dormant cells' temps must still propagate so a heat source
        # reaching one raises its temp and wakes it (condition 2).
        temp_before = grid._temp
        grid._temp = diffuse_temps(grid._temp, grid._data, self._cond_lut, self._cp_lut)

        data = grid._data  # raw (H, W) uint8; read directly, no per-cell get() overhead
        data_before = data.copy()  # for id_changed (cheap ~0.05 ms at 200x140)
        active = grid._active
        moved = np.zeros((grid.height, grid.width), dtype=np.bool_)

        # Movement scan: y-descending (bottom -> top) so a single grain falls at
        # most one cell per step (no teleporting through the grid). x direction
        # randomized per row to avoid left bias. DORMANT-CELL: only cells that
        # are BOTH active AND non-empty are visited -- a settled pile goes
        # dormant (active=False) and is skipped, while the movement front stays
        # awake. All scan semantics (y-descending, per-row random dir, moved
        # guard, mid-scan empty re-check) are UNCHANGED from the sparse scan --
        # only the x-index source narrows from non-empty to active & non-empty.
        for y in range(grid.height - 1, -1, -1):  # y-descending -- UNCHANGED
            xs = np.nonzero(active[y] & (data[y] != 0))[0]  # active & non-empty
            if xs.size == 0:
                continue  # no active non-empty cell this row -> skipped in one call
            if random.random() < 0.5:  # per-row random direction -- UNCHANGED
                xs = xs[::-1]
            for x in xs:
                x = int(x)  # numpy intp -> plain int (mypy + rule args)
                if moved[y, x]:
                    continue
                # Mid-scan re-check: a cell active at nonzero-time may have
                # emptied/transformed earlier in this scan. Re-read and skip.
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

        # Rebuild the active set for NEXT frame from the four wake conditions.
        # (1) Movement / identity-change wake: a cell that moved or changed, or
        #     is orthogonally adjacent to one (so eroding support / opening a
        #     hole wakes the cells above/beside to fall/flow).
        id_changed = data != data_before
        active_next = _dilate(id_changed | moved)
        # (2) Thermal wake: a cell whose temperature changed (via diffusion from
        #     a heat source, or a rule) must be rescanned -- phase transitions
        #     (water boil/freeze, wood ignite) check the cell's OWN temp.
        active_next |= grid._temp != temp_before
        # (3) Persistent heat sources: FIRE and LAVA re-assert burn_temp / react
        #     each step but may neither move nor change identity nor (if already
        #     at burn_temp) change temp. Keep them and their neighborhood awake
        #     so combustion chains and lava reactions proceed.
        active_next |= _dilate(
            (data == int(ElementId.FIRE)) | (data == int(ElementId.LAVA))
        )
        # (4) Brush-painted/erased cells were OR-ed into grid._active between
        #     steps (by Grid.fill_circle) and were scanned above. They are NOT
        #     carried into active_next unless the sim dynamics woke them via
        #     (1)/(2)/(3) -- which is correct. (Do NOT do `active_next |=
        #     grid._active`: that would let cells marked once stay active forever
        #     and never sleep.)
        grid._active = active_next

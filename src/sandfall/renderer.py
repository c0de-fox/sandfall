"""Render the simulation grid to a pygame :class:`~pygame.Surface`.

The hot path is a numpy lookup: a precomputed ``(num_elements, 3)`` uint8
palette is indexed by the grid's element-id array to produce an ``(H, W, 3)``
RGB image, which is then pushed onto a grid-sized pygame Surface via
:func:`pygame.surfarray.blit_array`. The :class:`Game` scales that small
surface up to the window each frame with :func:`pygame.transform.scale`
(nearest-neighbor, so the crisp pixel look is preserved).

The palette construction (``build_color_lut``) and the id->RGB mapping
(``grid_to_rgb``) are extracted as pure numpy functions so they can be unit
tested headlessly without importing a display.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pygame

from .config import BG_COLOR, GRID_HEIGHT, GRID_WIDTH
from .elements import ELEMENTS, ElementId
from .grid import Grid
from .simulation import FLOW_DOWN, FLOW_LEFT, FLOW_NONE, FLOW_RIGHT, FLOW_UP
from .thermal import thermal_to_rgb


def build_color_lut(
    bg_color: tuple[int, int, int] = BG_COLOR,
) -> npt.NDArray[np.uint8]:
    """Build the element-id -> RGB lookup table used by the renderer.

    The returned array has shape ``(len(ElementId), 3)`` and dtype ``uint8``.
    Row ``int(ElementId.EMPTY)`` (index 0) is set to ``bg_color`` so that empty
    cells paint as the window background; every other row is the element's
    registered color from :data:`ELEMENTS`.
    """
    lut = np.zeros((len(ElementId), 3), dtype=np.uint8)
    lut[int(ElementId.EMPTY)] = bg_color
    for eid, element in ELEMENTS.items():
        if eid == ElementId.EMPTY:
            continue
        lut[int(eid)] = element.color
    return lut


def grid_to_rgb(grid: Grid, lut: npt.NDArray[np.uint8]) -> npt.NDArray[np.uint8]:
    """Map ``grid``'s element-id array to an ``(H, W, 3)`` ``uint8`` RGB array.

    Pure (numpy-only) helper extracted from :meth:`Renderer.render` so the
    color mapping is unit-testable without a display.
    """
    return lut[grid.array]


# Map a flow code (0..4) to its (dx, dy) unit vector in GRID coords (+y is
# DOWN), matching how the renderer maps grid cells to screen pixels. Indexed by
# code; row 0 (FLOW_NONE) is (0, 0). The assert below pins that each row agrees
# with its named FLOW_* constant, so renumbering FLOW_* in simulation.py
# without reordering these rows fails loudly at import.
_FLOW_VEC: npt.NDArray[np.int16] = np.array(
    [
        [0, 0],  # FLOW_NONE
        [0, -1],  # FLOW_UP    (dy < 0)
        [0, 1],  # FLOW_DOWN  (dy > 0)
        [-1, 0],  # FLOW_LEFT  (dx < 0)
        [1, 0],  # FLOW_RIGHT (dx > 0)
    ],
    dtype=np.int16,
)
assert (
    _FLOW_VEC[FLOW_NONE].tolist() == [0, 0]
    and _FLOW_VEC[FLOW_UP].tolist() == [0, -1]
    and _FLOW_VEC[FLOW_DOWN].tolist() == [0, 1]
    and _FLOW_VEC[FLOW_LEFT].tolist() == [-1, 0]
    and _FLOW_VEC[FLOW_RIGHT].tolist() == [1, 0]
), "FLOW_* codes and _FLOW_VEC rows must agree"


def flow_arrow_samples(
    flow: npt.NDArray[np.uint8], stride: int = 10, threshold: int | None = None
) -> list[tuple[int, int, int, int]]:
    """Sample the per-step flow array at ``stride``-cell blocks and return arrow
    descriptors for each block's DOMINANT flow.

    Returns a list of ``(cx, cy, vx, vy)``: ``(cx, cy)`` is the block center in
    GRID coords; ``(vx, vy)`` is the block's net flow vector (a small int pair,
    NOT normalized -- the renderer normalizes for drawing). Blocks whose net flow
    magnitude is below ``threshold`` (default ``stride``: roughly "fewer than
    ``stride`` net directional cells") produce NO arrow (still or turbulent/
    balanced blocks are omitted).

    Each cell's code is mapped to a unit vector (up/down/left/right); the block's
    resultant is the vector SUM over the block (so a half-up/half-down block
    cancels to ~zero -> no arrow, while a uniform updraft sums to a strong up
    vector). Pure numpy / pygame-free -> unit-tested headlessly.
    """
    h, w = flow.shape
    if threshold is None:
        threshold = stride
    half = stride // 2
    samples: list[tuple[int, int, int, int]] = []
    for cy in range(half, h, stride):
        for cx in range(half, w, stride):
            y0, y1 = max(0, cy - half), min(h, cy + half + 1)
            x0, x1 = max(0, cx - half), min(w, cx + half + 1)
            block = flow[y0:y1, x0:x1]
            vsum = _FLOW_VEC[block].sum(axis=(0, 1))  # (2,) int16 resultant
            vx, vy = int(vsum[0]), int(vsum[1])
            if abs(vx) + abs(vy) < threshold:
                continue  # still / mixed / balanced -> no arrow
            samples.append((cx, cy, vx, vy))
    return samples


class Renderer:
    """Converts a :class:`Grid` into a pygame :class:`~pygame.Surface`.

    :meth:`render` returns a *grid-sized* surface (``GRID_WIDTH x
    GRID_HEIGHT``); the caller scales it up to the window. Returning the same
    underlying surface each frame (mutated in place by ``blit_array``) avoids a
    per-frame allocation; the caller must consume it before the next call.
    """

    _lut: npt.NDArray[np.uint8]
    _cell_surface: pygame.Surface

    def __init__(self) -> None:
        self._lut = build_color_lut()
        self._cell_surface = pygame.Surface((GRID_WIDTH, GRID_HEIGHT))

    def render(self, grid: Grid) -> pygame.Surface:
        """Paint ``grid`` onto the grid-sized cell surface and return it."""
        # Reallocate if the grid size changed (e.g. after a window resize) so
        # surfarray.blit_array never sees a size mismatch.
        if self._cell_surface.get_size() != (grid.width, grid.height):
            self._cell_surface = pygame.Surface((grid.width, grid.height))
        rgb = grid_to_rgb(grid, self._lut)  # (H, W, 3)
        # pygame.surfarray works in (width, height, 3) column-major order, so
        # transpose the row-major grid image before blitting.
        rgb_t = np.transpose(rgb, (1, 0, 2))  # (W, H, 3)
        pygame.surfarray.blit_array(self._cell_surface, rgb_t)
        return self._cell_surface

    def render_heat(self, grid: Grid) -> pygame.Surface:
        """Paint the grid's TEMPERATURE field (heat-overlay mode) and return it.

        Same surface/sizing contract as :meth:`render`: returns the grid-sized
        ``_cell_surface`` (reallocated on a size mismatch), mutated in place
        by ``blit_array``. Used by ``Game._draw`` when the ``H`` heat-overlay
        toggle is on. Only the grid surface is replaced — the caller still
        blits the palette + HUD on top, so the player can select elements
        while viewing heat.
        """
        # Self-heal against resize exactly as render does.
        if self._cell_surface.get_size() != (grid.width, grid.height):
            self._cell_surface = pygame.Surface((grid.width, grid.height))
        rgb = thermal_to_rgb(grid.temp)  # (H, W, 3)
        # Same column-major transpose as render (thermal_to_rgb is row-major).
        rgb_t = np.transpose(rgb, (1, 0, 2))  # (W, H, 3)
        pygame.surfarray.blit_array(self._cell_surface, rgb_t)
        return self._cell_surface

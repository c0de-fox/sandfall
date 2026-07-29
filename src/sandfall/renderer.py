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

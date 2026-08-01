"""Headless tests for the renderer.

No real display is required: a session-scoped fixture initializes pygame with
the ``dummy`` SDL video driver. The pure helpers (``build_color_lut`` and
``grid_to_rgb``) are tested directly for color correctness, and
``Renderer.render`` is exercised to confirm it yields a grid-sized Surface.
These tests never block on the real event loop.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

from sandfall.config import BG_COLOR, GRID_HEIGHT, GRID_WIDTH
from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.renderer import Renderer, build_color_lut, grid_to_rgb


@pytest.fixture(scope="session", autouse=True)
def _headless_pygame() -> object:
    """Initialize pygame with the dummy video driver for the whole session.

    ``SDL_VIDEODRIVER`` is honored by SDL at ``pygame.init()`` time, so setting
    it here (before the first ``init``) is sufficient. A tiny display surface
    is created so any code that calls ``Surface.convert()`` would also work,
    though :class:`Renderer` does not require it.
    """
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame

    pygame.init()
    pygame.display.set_mode((GRID_WIDTH, GRID_HEIGHT))
    yield
    pygame.quit()


def test_build_color_lut_shape_and_dtype() -> None:
    lut = build_color_lut()

    assert lut.shape == (len(ElementId), 3)
    assert lut.dtype == np.uint8


def test_build_color_lut_empty_is_background() -> None:
    lut = build_color_lut()

    assert tuple(lut[int(ElementId.EMPTY)]) == BG_COLOR


def test_build_color_lut_matches_registered_colors() -> None:
    lut = build_color_lut()

    for eid, element in ELEMENTS.items():
        if eid == ElementId.EMPTY:
            continue  # EMPTY is overridden to the background color.
        assert tuple(lut[int(eid)]) == element.color


def test_build_color_lut_grew_with_new_elements() -> None:
    """Phase 03 grew ElementId 8 -> 12; the acid/base pair grew it 12 -> 14;
    oil grows it 14 -> 15; gunpowder grows it 15 -> 16; dry ice grows it
    16 -> 17; liquid nitrogen grows it 17 -> 18. The LUT must auto-resize (it
    sizes from ``len(ElementId)``) and rows 8..17 must carry the new element
    colors at the correct stable indices. No ``renderer.py`` edit was needed
    for this -- the LUT builder iterates ``ELEMENTS`` and sizes from the enum.
    """
    lut = build_color_lut()

    # The enum has exactly 18 members (v1 values 0..7 unchanged + 8..17 new).
    assert len(ElementId) == 18
    assert [e.value for e in ElementId] == list(range(18))
    # LUT shape tracks the enum width.
    assert lut.shape == (18, 3)
    # The Phase-03 elements land at indices 8..11.
    phase03_elements = [ElementId.STEAM, ElementId.ICE, ElementId.LAVA, ElementId.GLASS]
    assert [int(e) for e in phase03_elements] == [8, 9, 10, 11]
    for eid in phase03_elements:
        assert tuple(lut[int(eid)]) == ELEMENTS[eid].color
    # The acid/base pair lands at indices 12..13 and carries its registered colors.
    acid_base = [ElementId.ACID, ElementId.BASE]
    assert [int(e) for e in acid_base] == [12, 13]
    for eid in acid_base:
        assert tuple(lut[int(eid)]) == ELEMENTS[eid].color
    # Oil lands at index 14 and carries its registered color.
    assert int(ElementId.OIL) == 14
    assert tuple(lut[int(ElementId.OIL)]) == ELEMENTS[ElementId.OIL].color
    # Gunpowder lands at index 15 and carries its registered color.
    assert int(ElementId.GUNPOWDER) == 15
    assert tuple(lut[int(ElementId.GUNPOWDER)]) == ELEMENTS[ElementId.GUNPOWDER].color
    # Dry ice lands at index 16 and carries its registered color.
    assert int(ElementId.DRY_ICE) == 16
    assert tuple(lut[int(ElementId.DRY_ICE)]) == ELEMENTS[ElementId.DRY_ICE].color
    # Liquid nitrogen lands at index 17 and carries its registered color.
    assert int(ElementId.LN2) == 17
    assert tuple(lut[int(ElementId.LN2)]) == ELEMENTS[ElementId.LN2].color


def test_grid_to_rgb_shape() -> None:
    grid = Grid(5, 3)
    lut = build_color_lut()
    rgb = grid_to_rgb(grid, lut)

    assert rgb.shape == (3, 5, 3)
    assert rgb.dtype == np.uint8


def test_grid_to_rgb_maps_cells_to_their_colors() -> None:
    # A 2x2 grid with one of each: EMPTY top-left, SAND top-right, WATER
    # bottom-left, STONE bottom-right.
    grid = Grid(2, 2)
    grid.set(1, 0, ElementId.SAND)  # (x=1, y=0)
    grid.set(0, 1, ElementId.WATER)  # (x=0, y=1)
    grid.set(1, 1, ElementId.STONE)  # (x=1, y=1)

    rgb = grid_to_rgb(grid, build_color_lut())

    assert tuple(rgb[0, 0]) == BG_COLOR
    assert tuple(rgb[0, 1]) == ELEMENTS[ElementId.SAND].color
    assert tuple(rgb[1, 0]) == ELEMENTS[ElementId.WATER].color
    assert tuple(rgb[1, 1]) == ELEMENTS[ElementId.STONE].color


def test_renderer_render_returns_grid_sized_surface() -> None:
    grid = Grid(GRID_WIDTH, GRID_HEIGHT)
    grid.set(0, 0, ElementId.SAND)

    renderer = Renderer()
    surface = renderer.render(grid)

    assert surface.get_size() == (GRID_WIDTH, GRID_HEIGHT)


def test_renderer_render_heat_returns_grid_sized_surface() -> None:
    """Phase 04 heat-overlay path: render_heat paints the temperature field
    onto the same self-healing ``_cell_surface`` and returns it. Reuses the
    session-scoped ``_headless_pygame`` fixture (SDL dummy driver) at the top
    of this file — no new SDL init.
    """
    grid = Grid(GRID_WIDTH, GRID_HEIGHT)
    grid.set_temp(0, 0, 900)

    renderer = Renderer()
    surf = renderer.render_heat(grid)

    assert surf.get_size() == (GRID_WIDTH, GRID_HEIGHT)


def test_renderer_render_self_heals_on_grid_resize() -> None:
    """A renderer constructed at the default size re-renders a resized grid.

    Phase 03 makes the grid resizable at runtime. ``Renderer._cell_surface``
    is sized at construction; if it were never reallocated, a later call
    with a differently-sized grid would crash inside
    ``pygame.surfarray.blit_array`` (size mismatch). ``render`` detects the
    mismatch and rebuilds the surface, so a single Renderer instance serves
    any grid shape.
    """
    import pygame

    # Build a renderer; its _cell_surface starts at the default grid size.
    renderer = Renderer()
    assert renderer._cell_surface.get_size() == (GRID_WIDTH, GRID_HEIGHT)

    # Render a smaller grid: surface must shrink to match, no exception.
    small = Grid(10, 6)
    small.set(0, 0, ElementId.SAND)
    surf_small = renderer.render(small)
    assert surf_small.get_size() == (10, 6)

    # Render a larger grid: surface must grow to match, no exception.
    big = Grid(GRID_WIDTH + 50, GRID_HEIGHT + 20)
    big.set(0, 0, ElementId.WATER)
    surf_big = renderer.render(big)
    assert surf_big.get_size() == (GRID_WIDTH + 50, GRID_HEIGHT + 20)

    # Render the default size again: must shrink back. Also smoke-check that
    # the surface actually carries the painted color (column-major pixel at
    # (0,0)).
    grid = Grid(GRID_WIDTH, GRID_HEIGHT)
    grid.set(0, 0, ElementId.SAND)
    surf = renderer.render(grid)
    assert surf.get_size() == (GRID_WIDTH, GRID_HEIGHT)
    assert tuple(pygame.surfarray.array3d(surf)[0, 0]) == ELEMENTS[ElementId.SAND].color

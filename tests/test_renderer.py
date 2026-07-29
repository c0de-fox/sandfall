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

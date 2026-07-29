"""Headless tests for the pygame.Window-driven resize path in :class:`Game`.

The resize fix swapped ``pygame.display.set_mode()`` (which destroyed the
window on every call -> flicker) for the ``pygame.Window`` API, whose
``get_surface()`` returns a surface that auto-tracks the window size.
:meth:`Game._apply_resize_if_changed` now detects a resize by polling
``self._window.size`` once per frame, instead of handling ``VIDEORESIZE``
events.

These drive that path headlessly under ``SDL_VIDEODRIVER=dummy``. The dummy
driver honors ``Window.size`` (it is settable) and ``get_surface()``
(returns a surface matching the new size), so the per-frame resize mechanism
can be exercised without a real display. ``compute_grid_dims`` /
``migrate_grid`` themselves have their own headless unit tests
(``tests/test_config.py``, ``tests/test_grid.py``); these tests cover the
Game-level wiring that ties them to a window-size change.

``SDL_VIDEODRIVER`` is set at module top (before any ``pygame.init()``);
``sandfall.game`` is imported lazily inside each test so that merely
collecting this module does not violate the lazy-import contract pinned by
``tests/test_package.py`` (importing ``sandfall.__main__`` must not load
``sandfall.game``).
"""

from __future__ import annotations

import os

# Must be set before the first ``pygame.init()`` (``Game.__init__`` calls it).
# Pytest imports this module during collection, before any test in it runs, so
# the env is in place even though test_resize sorts before test_renderer.
os.environ["SDL_VIDEODRIVER"] = "dummy"

from sandfall.config import (  # noqa: E402
    GRID_HEIGHT,
    GRID_WIDTH,
    INITIAL_WINDOW_H,
    INITIAL_WINDOW_W,
    MIN_WINDOW_H,
    MIN_WINDOW_W,
    PALETTE_BAR_HEIGHT,
    compute_grid_dims,
)
from sandfall.elements import ElementId  # noqa: E402


def test_constructor_uses_window_api_and_starts_at_default_size() -> None:
    """Game creates a pygame.Window at the initial size; the screen tracks it.

    Pins the Window-API swap: there is no display.set_mode call anywhere in
    Game (verified separately by the frame-cap smoke), and the screen surface
    returned by ``Window.get_surface()`` is 1:1 with the window pixels so the
    existing mouse -> grid mapping (``mx // CELL_SIZE``) is unchanged.
    """
    import pygame

    from sandfall.game import Game

    game = Game()
    try:
        assert isinstance(game._window, pygame.Window)
        assert game._window.size == (INITIAL_WINDOW_W, INITIAL_WINDOW_H)
        assert game._window.minimum_size == (MIN_WINDOW_W, MIN_WINDOW_H)
        assert game._screen.get_size() == (INITIAL_WINDOW_W, INITIAL_WINDOW_H)
        assert (game._grid.width, game._grid.height) == (GRID_WIDTH, GRID_HEIGHT)
    finally:
        game._window.destroy()


def test_apply_resize_if_changed_grows_grid_and_preserves_content() -> None:
    """Growing the window grows the grid and keeps the overlapping content.

    Exercises the documented resize invariant end-to-end at the Game level:
    new grid dims track ``compute_grid_dims`` for the new window size, the
    surface reference is refreshed to the new size, the UI layout is rebuilt,
    and ``migrate_grid`` preserves any cell that lies inside the overlap.
    """
    from sandfall.game import Game

    game = Game()
    try:
        seed_x, seed_y = 5, 5
        game._grid.set(seed_x, seed_y, ElementId.STONE)
        assert game._grid.get(seed_x, seed_y) == int(ElementId.STONE)

        new_w, new_h = INITIAL_WINDOW_W + 200, INITIAL_WINDOW_H + 100
        game._window.size = (new_w, new_h)
        game._apply_resize_if_changed()

        # Grid dims track the new window via compute_grid_dims.
        cols, rows = compute_grid_dims(new_w, new_h)
        assert (game._grid.width, game._grid.height) == (cols, rows)
        assert (game._window_w, game._window_h) == (new_w, new_h)
        # Screen surface refreshed to the new window size.
        assert game._screen.get_size() == (new_w, new_h)
        # UI layout was rebuilt for the new size (palette bar pinned to bottom).
        assert game._ui.bar_y == new_h - PALETTE_BAR_HEIGHT
        # The seed cell is inside the overlap -> preserved by migrate_grid.
        assert game._grid.get(seed_x, seed_y) == int(ElementId.STONE)
    finally:
        game._window.destroy()


def test_apply_resize_if_changed_is_noop_when_size_unchanged() -> None:
    """When ``window.size`` matches the cached size, nothing is rebuilt.

    Guards the early-return so the per-frame poll does not thrash the grid /
    sim / UI on every frame of a stable window.
    """
    from sandfall.game import Game

    game = Game()
    try:
        grid_before = game._grid
        sim_before = game._sim
        screen_before = game._screen
        # No size change -> early return, all references unchanged.
        game._apply_resize_if_changed()
        assert game._grid is grid_before
        assert game._sim is sim_before
        assert game._screen is screen_before
    finally:
        game._window.destroy()


def test_apply_resize_if_changed_shrinks_grid_and_crops_content() -> None:
    """Shrinking the window crops content outside the new overlap permanently.

    The complement of the grow test: ``migrate_grid`` only copies the
    overlap, so a cell that was near the old bottom-right corner and lies
    outside the new smaller grid is lost (its old coordinates are now out of
    bounds).
    """
    from sandfall.game import Game

    game = Game()
    try:
        keep_x, keep_y = 3, 3
        lost_x, lost_y = GRID_WIDTH - 1, GRID_HEIGHT - 1
        game._grid.set(keep_x, keep_y, ElementId.STONE)
        game._grid.set(lost_x, lost_y, ElementId.WATER)

        new_w, new_h = INITIAL_WINDOW_W // 2, INITIAL_WINDOW_H // 2
        game._window.size = (new_w, new_h)
        game._apply_resize_if_changed()

        cols, rows = compute_grid_dims(new_w, new_h)
        assert (game._grid.width, game._grid.height) == (cols, rows)
        # Kept cell still present.
        assert game._grid.get(keep_x, keep_y) == int(ElementId.STONE)
        # Lost cell's old coords are now outside the smaller grid.
        assert lost_x >= cols
        assert lost_y >= rows
    finally:
        game._window.destroy()

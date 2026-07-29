"""Headless tests for the pure ``compute_grid_dims`` geometry helper.

``compute_grid_dims`` converts a (window_w, window_h) pixel size into a
``(cols, rows)`` cell-count grid, floor-dividing so cells stay square and
clamping to a minimum usable cell count. It is pure (no pygame) so it is
covered headlessly here.
"""

from __future__ import annotations

from sandfall.config import (
    CELL_SIZE,
    MIN_GRID_COLS,
    MIN_GRID_ROWS,
    PALETTE_BAR_HEIGHT,
    compute_grid_dims,
)


def test_compute_grid_dims_default_window_is_two_hundred_by_one_forty() -> None:
    """The default 800x600 window yields the documented 200x140 initial grid.

    This pins the Phase 02 default-window invariant (the initial grid is
    200 wide x 140 tall, derived from the initial window size) against the
    Phase 03 dynamic-geometry helper.
    """
    cols, rows = compute_grid_dims(800, 600)
    assert cols == 200
    assert rows == 140


def test_compute_grid_dims_floor_division_exact_multiple() -> None:
    cols, rows = compute_grid_dims(800, 600)
    assert cols == 800 // CELL_SIZE
    assert rows == (600 - PALETTE_BAR_HEIGHT) // CELL_SIZE


def test_compute_grid_dims_floors_non_multiple() -> None:
    """Leftover pixels (window not a whole-cell multiple) are dropped.

    803 // 4 == 200 (3 leftover px -> BG_COLOR); (603-40) // 4 == 140.
    """
    cols, rows = compute_grid_dims(803, 603)
    assert cols == 200
    assert rows == 140


def test_compute_grid_dims_clamps_to_minimum() -> None:
    """An absurdly small window still yields a usable grid + palette."""
    cols, rows = compute_grid_dims(10, 10)
    assert cols == MIN_GRID_COLS
    assert rows == MIN_GRID_ROWS


def test_compute_grid_dims_clamps_width_only() -> None:
    """A too-narrow window keeps the requested height but min cols."""
    cols, rows = compute_grid_dims(10, 600)
    assert cols == MIN_GRID_COLS
    assert rows == (600 - PALETTE_BAR_HEIGHT) // CELL_SIZE


def test_compute_grid_dims_clamps_height_only() -> None:
    """A too-short window keeps the requested width but min rows."""
    cols, rows = compute_grid_dims(800, 10)
    assert cols == 800 // CELL_SIZE
    assert rows == MIN_GRID_ROWS


def test_compute_grid_dims_grow_grows_cells_monotonically() -> None:
    """Growing the window never shrinks the grid."""
    small = compute_grid_dims(900, 700)
    big = compute_grid_dims(1200, 900)
    assert big[0] > small[0]
    assert big[1] > small[1]


def test_compute_grid_dims_palette_bar_excluded_from_rows() -> None:
    """Rows count only the sim area above the palette (height - bar height)."""
    cols, rows = compute_grid_dims(800, 640)
    assert cols == 200
    assert rows == (640 - PALETTE_BAR_HEIGHT) // CELL_SIZE  # 600 // 4 == 150
    assert rows == 150


def test_compute_grid_dims_min_constants_are_consistent() -> None:
    """MIN_GRID_* are derived from MIN_WINDOW_* with the same formula."""
    from sandfall.config import MIN_WINDOW_H, MIN_WINDOW_W

    assert MIN_GRID_COLS == MIN_WINDOW_W // CELL_SIZE
    assert MIN_GRID_ROWS == (MIN_WINDOW_H - PALETTE_BAR_HEIGHT) // CELL_SIZE

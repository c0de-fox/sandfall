"""Tests for the :class:`sandfall.grid.Grid` class."""

from __future__ import annotations

import numpy as np
import pytest

from sandfall.elements import ElementId
from sandfall.grid import BrushShape, Grid, migrate_grid


def test_construction_and_shape() -> None:
    grid = Grid(width=10, height=6)
    assert grid.width == 10
    assert grid.height == 6
    arr = grid.array
    assert arr.shape == (6, 10)
    assert arr.dtype == np.uint8


def test_default_grid_is_empty() -> None:
    grid = Grid(width=5, height=5)
    for y in range(grid.height):
        for x in range(grid.width):
            assert grid.get(x, y) == ElementId.EMPTY


def test_in_bounds_edges_and_corners() -> None:
    grid = Grid(width=4, height=3)
    assert grid.in_bounds(0, 0)
    assert grid.in_bounds(3, 2)  # top-right of in-bounds region
    assert not grid.in_bounds(-1, 0)
    assert not grid.in_bounds(0, -1)
    assert not grid.in_bounds(4, 0)
    assert not grid.in_bounds(0, 3)


def test_set_get_round_trip() -> None:
    grid = Grid(width=4, height=4)
    grid.set(2, 1, ElementId.SAND)
    assert grid.get(2, 1) == ElementId.SAND
    # Untouched cells remain EMPTY.
    assert grid.get(0, 0) == ElementId.EMPTY


def test_set_accepts_plain_int() -> None:
    grid = Grid(width=3, height=3)
    grid.set(1, 1, int(ElementId.STONE))
    assert grid.get(1, 1) == ElementId.STONE


def test_set_out_of_bounds_is_silent() -> None:
    grid = Grid(width=3, height=3)
    # None of these should raise.
    grid.set(-1, 0, ElementId.SAND)
    grid.set(0, 5, ElementId.SAND)
    grid.set(3, 3, ElementId.SAND)


def test_get_out_of_bounds_raises() -> None:
    grid = Grid(width=3, height=3)
    with pytest.raises(IndexError):
        grid.get(-1, 0)
    with pytest.raises(IndexError):
        grid.get(3, 0)
    with pytest.raises(IndexError):
        grid.get(0, 3)


def test_invalid_dimensions_raise() -> None:
    with pytest.raises(ValueError):
        Grid(width=0, height=5)
    with pytest.raises(ValueError):
        Grid(width=5, height=0)
    with pytest.raises(ValueError):
        Grid(width=-1, height=5)


def test_fill_circle_radius_zero_paints_one_cell() -> None:
    grid = Grid(width=7, height=7)
    grid.fill_circle(3, 3, 0, ElementId.SAND)
    sand_count = int((grid.array == int(ElementId.SAND)).sum())
    assert sand_count == 1
    assert grid.get(3, 3) == ElementId.SAND


def test_fill_circle_radius_two_count() -> None:
    grid = Grid(width=11, height=11)
    cx = cy = 5
    radius = 2
    grid.fill_circle(cx, cy, radius, ElementId.SAND)
    sand_mask = grid.array == int(ElementId.SAND)
    expected = sum(
        1
        for dy in range(-radius, radius + 1)
        for dx in range(-radius, radius + 1)
        if dx * dx + dy * dy <= radius * radius
    )
    assert int(sand_mask.sum()) == expected
    # Every painted cell lies within the disk.
    for y in range(grid.height):
        for x in range(grid.width):
            if sand_mask[y, x]:
                dx = x - cx
                dy = y - cy
                assert dx * dx + dy * dy <= radius * radius


def test_fill_circle_clipped_at_corner() -> None:
    grid = Grid(width=5, height=5)
    grid.fill_circle(0, 0, 2, ElementId.SAND)
    assert grid.get(0, 0) == ElementId.SAND
    # Should not raise; some cells painted, clipped cells skipped.
    assert int((grid.array == int(ElementId.SAND)).sum()) > 0


def test_fill_circle_negative_radius_raises() -> None:
    grid = Grid(width=5, height=5)
    with pytest.raises(ValueError):
        grid.fill_circle(2, 2, -1, ElementId.SAND)


def test_fill_circle_square_paints_whole_bounding_box() -> None:
    """SQUARE shape paints the whole bbox (corners included); DISK does not.

    The defaulted ``shape`` param keeps every existing disk call site green;
    this additive test pins the SQUARE contract: every cell in
    [cx-r, cx+r] x [cy-r, cy+r] is painted, life is reset to 0, and temp is
    reset to AMBIENT (mirroring the disk contract on the wider footprint).
    """
    from sandfall.config import AMBIENT_TEMP

    grid = Grid(width=20, height=20)
    grid.fill_circle(10, 10, 3, ElementId.SAND, BrushShape.SQUARE)
    # Every cell in the bbox is painted (corners included).
    for y in range(10 - 3, 10 + 4):
        for x in range(10 - 3, 10 + 4):
            assert grid.get(x, y) == ElementId.SAND, (x, y)
    # Life + temp reset on the whole square (mirrors disk contract).
    assert grid.get_life(10 - 3, 10 - 3) == 0
    assert grid.get_temp(10 - 3, 10 - 3) == AMBIENT_TEMP
    # And the square strictly contains the disk: a SQUARE paint paints at
    # least every cell a DISK paint would (the corners are the extra cells).
    disk_grid = Grid(width=20, height=20)
    disk_grid.fill_circle(10, 10, 3, ElementId.SAND)  # default DISK
    disk_mask = disk_grid.array == int(ElementId.SAND)
    square_mask = grid.array == int(ElementId.SAND)
    assert int(square_mask.sum()) == 7 * 7  # full 7x7 bbox
    assert int(disk_mask.sum()) < int(square_mask.sum())  # disk < square
    # DISK did not paint a corner that SQUARE did.
    assert disk_grid.get(10 - 3, 10 - 3) == ElementId.EMPTY


def test_life_array_defaults_to_zero() -> None:
    grid = Grid(width=4, height=4)
    assert grid.life.shape == (4, 4)
    assert grid.life.dtype == np.uint8
    for y in range(grid.height):
        for x in range(grid.width):
            assert grid.get_life(x, y) == 0


def test_set_life_get_life_round_trip() -> None:
    grid = Grid(width=3, height=3)
    grid.set_life(1, 1, 42)
    assert grid.get_life(1, 1) == 42
    # Other cells still zero.
    assert grid.get_life(0, 0) == 0


def test_set_life_clips_to_uint8_range() -> None:
    grid = Grid(width=3, height=3)
    grid.set_life(0, 0, -5)
    assert grid.get_life(0, 0) == 0
    grid.set_life(0, 0, 999)
    assert grid.get_life(0, 0) == 255


def test_set_life_out_of_bounds_is_silent() -> None:
    grid = Grid(width=3, height=3)
    # None of these should raise.
    grid.set_life(-1, 0, 10)
    grid.set_life(0, 5, 10)
    grid.set_life(3, 3, 10)


def test_get_life_out_of_bounds_raises() -> None:
    grid = Grid(width=3, height=3)
    with pytest.raises(IndexError):
        grid.get_life(-1, 0)
    with pytest.raises(IndexError):
        grid.get_life(3, 0)


def test_set_does_not_touch_life() -> None:
    """``set`` updates only the element id; life is managed separately."""
    grid = Grid(width=3, height=3)
    grid.set_life(1, 1, 30)
    grid.set(1, 1, ElementId.FIRE)
    assert grid.get(1, 1) == ElementId.FIRE
    # set() must not have clobbered the life value.
    assert grid.get_life(1, 1) == 30


def test_fill_circle_resets_life() -> None:
    """Painting over a cell with life zeroes its life (no stale state)."""
    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.FIRE)
    grid.set_life(2, 2, 50)
    grid.fill_circle(2, 2, 0, ElementId.SAND)
    assert grid.get(2, 2) == ElementId.SAND
    assert grid.get_life(2, 2) == 0


# --- Temperature field (Phase 01) -------------------------------------------


def test_temp_array_defaults_to_ambient() -> None:
    from sandfall.config import AMBIENT_TEMP

    grid = Grid(width=4, height=4)
    assert grid.temp.shape == (4, 4)
    assert grid.temp.dtype == np.float32
    for y in range(grid.height):
        for x in range(grid.width):
            assert grid.get_temp(x, y) == AMBIENT_TEMP


def test_set_temp_get_temp_round_trip() -> None:
    grid = Grid(width=3, height=3)
    grid.set_temp(1, 1, 1500)
    assert grid.get_temp(1, 1) == 1500
    assert grid.get_temp(0, 0) == 20  # AMBIENT


def test_set_temp_clips_to_band() -> None:
    from sandfall.config import TEMP_MAX, TEMP_MIN

    grid = Grid(width=3, height=3)
    grid.set_temp(0, 0, -5000)
    assert grid.get_temp(0, 0) == TEMP_MIN
    grid.set_temp(0, 0, 99999)
    assert grid.get_temp(0, 0) == TEMP_MAX


def test_set_temp_out_of_bounds_is_silent() -> None:
    grid = Grid(width=3, height=3)
    grid.set_temp(-1, 0, 100)
    grid.set_temp(0, 5, 100)
    grid.set_temp(3, 3, 100)


def test_get_temp_out_of_bounds_raises() -> None:
    grid = Grid(width=3, height=3)
    with pytest.raises(IndexError):
        grid.get_temp(-1, 0)
    with pytest.raises(IndexError):
        grid.get_temp(3, 0)


def test_swap_carries_temp() -> None:
    from sandfall.rules._common import swap

    grid = Grid(width=3, height=3)
    grid.set(0, 0, ElementId.SAND)
    grid.set_temp(0, 0, 900)
    grid.set(1, 1, ElementId.WATER)
    grid.set_temp(1, 1, 10)
    swap(grid, 0, 0, 1, 1)
    assert grid.get(0, 0) == ElementId.WATER
    assert grid.get_temp(0, 0) == 10
    assert grid.get(1, 1) == ElementId.SAND
    assert grid.get_temp(1, 1) == 900


def test_grid_move_swaps_id_life_and_temp() -> None:
    """Grid.move exchanges id AND life AND temp across the two cells (raw swap).

    Pins the fast-path used by rules._common.swap: a single numpy
    tuple-assignment per array with no bounds check and no clip. Verifies the
    tuple-swap evaluates the RHS before assigning (so each cell ends up with the
    OTHER cell's value, not its own) and that all three parallel arrays carry.
    """
    grid = Grid(width=3, height=3)
    # Cell A: SAND, life 12, hot.
    grid.set(0, 0, ElementId.SAND)
    grid.set_life(0, 0, 12)
    grid.set_temp(0, 0, 900)
    # Cell B: WATER, life 0, cold.
    grid.set(1, 1, ElementId.WATER)
    grid.set_life(1, 1, 0)
    grid.set_temp(1, 1, 10)

    grid.move(0, 0, 1, 1)

    # All three arrays swapped: A took B's values, B took A's values.
    assert grid.get(0, 0) == ElementId.WATER
    assert grid.get_life(0, 0) == 0
    assert grid.get_temp(0, 0) == 10
    assert grid.get(1, 1) == ElementId.SAND
    assert grid.get_life(1, 1) == 12
    assert grid.get_temp(1, 1) == 900


def test_fill_circle_resets_temp_to_ambient() -> None:
    from sandfall.config import AMBIENT_TEMP

    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.FIRE)
    grid.set_temp(2, 2, 1200)
    grid.fill_circle(2, 2, 0, ElementId.SAND)
    assert grid.get(2, 2) == ElementId.SAND
    assert grid.get_temp(2, 2) == AMBIENT_TEMP


# --- migrate_grid (Phase 03 resizable window) --------------------------------


def test_migrate_grid_grow_preserves_overlap_ids_and_life() -> None:
    """Growing the grid carries the overlap (ids + life + temp) into the new grid."""
    old = Grid(3, 3)
    old.set(0, 0, ElementId.SAND)
    old.set(2, 2, ElementId.FIRE)
    old.set_life(2, 2, 77)
    old.set_temp(1, 1, 500)
    new = Grid(5, 5)
    migrate_grid(old, new)
    # Overlap preserved (ids + life + temp).
    assert new.get(0, 0) == ElementId.SAND
    assert new.get(2, 2) == ElementId.FIRE
    assert new.get_life(2, 2) == 77
    assert new.get_temp(1, 1) == 500
    # Newly exposed cells (outside the 3x3 overlap) keep their defaults.
    assert new.get(4, 4) == ElementId.EMPTY
    assert new.get_life(4, 4) == 0
    assert new.get_temp(4, 4) == 20  # AMBIENT default in the new exposed cell


def test_migrate_grid_shrink_crops_overflow() -> None:
    """Shrinking the grid drops old content outside the new (smaller) overlap."""
    old = Grid(5, 5)
    old.set(4, 4, ElementId.STONE)  # outside the 2x2 overlap -> lost
    old.set(1, 1, ElementId.WATER)  # inside the 2x2 overlap -> kept
    new = Grid(2, 2)
    migrate_grid(old, new)
    # (4,4) doesn't even exist in new (2x2); (0,0) inside overlap was EMPTY.
    assert new.get(0, 0) == ElementId.EMPTY
    assert new.get(1, 1) == ElementId.WATER


def test_migrate_grid_shrink_carries_life_in_overlap() -> None:
    """Life is carried for cells inside the overlap, dropped outside."""
    old = Grid(4, 4)
    old.set(1, 1, ElementId.FIRE)
    old.set_life(1, 1, 42)
    old.set(3, 3, ElementId.FIRE)  # outside the 2x2 overlap
    old.set_life(3, 3, 99)
    new = Grid(2, 2)
    migrate_grid(old, new)
    assert new.get(1, 1) == ElementId.FIRE
    assert new.get_life(1, 1) == 42  # life carried in overlap


def test_migrate_grid_new_outside_overlap_left_untouched() -> None:
    """Cells in ``new`` outside the overlap are NOT overwritten by migration.

    The contract is "copy the overlap, leave the rest of ``new`` alone" — so
    a cell pre-populated outside the overlap survives the migration rather
    than being reset to EMPTY. (In practice ``new`` starts all-EMPTY so this
    is moot for the Game's resize path, but the contract is pinned here.)
    """
    old = Grid(2, 2)
    new = Grid(4, 4)
    new.set(3, 3, ElementId.PLANT)  # outside the 2x2 overlap
    migrate_grid(old, new)
    assert new.get(3, 3) == ElementId.PLANT  # untouched
    assert new.get_life(3, 3) == 0


def test_migrate_grid_does_not_mutate_old() -> None:
    """``old`` is read-only: its contents survive the migration."""
    old = Grid(3, 3)
    old.set(0, 0, ElementId.SAND)
    old.set_life(0, 0, 5)
    new = Grid(3, 3)
    migrate_grid(old, new)
    assert old.get(0, 0) == ElementId.SAND
    assert old.get_life(0, 0) == 5


def test_migrate_grid_one_dim_grow_one_dim_shrink() -> None:
    """Wider but shorter: overlap is min(5,3) x min(3,5) == 3 x 3."""
    old = Grid(5, 3)
    for x in range(5):
        old.set(x, 0, ElementId.SAND)
    old.set(4, 2, ElementId.STONE)  # x=4 is outside the new width of 3
    new = Grid(3, 5)
    migrate_grid(old, new)
    # The 3x3 overlap was carried: x in [0,3), y in [0,3).
    assert new.get(0, 0) == ElementId.SAND
    assert new.get(2, 0) == ElementId.SAND
    # x=4 is gone (new is only 3 wide); (3, 0) is outside overlap -> EMPTY.
    assert new.get(0, 3) == ElementId.EMPTY  # y=3 outside old height 3
    assert new.get(0, 4) == ElementId.EMPTY


def test_migrate_grid_same_size_is_a_full_copy() -> None:
    """When old and new are the same shape, the entire grid is copied."""
    old = Grid(3, 3)
    old.set(0, 0, ElementId.SAND)
    old.set(2, 2, ElementId.FIRE)
    old.set_life(2, 2, 12)
    old.set_temp(1, 1, 350)
    new = Grid(3, 3)
    migrate_grid(old, new)
    assert new.get(0, 0) == ElementId.SAND
    assert new.get(2, 2) == ElementId.FIRE
    assert new.get_life(2, 2) == 12
    assert new.get_temp(1, 1) == 350


def test_migrate_grid_empty_overlap_when_either_dim_is_zero() -> None:
    """A zero-size grid has no overlap; migration is a no-op (and silent)."""
    # Grid rejects zero dimensions, so the smallest case is 1x1 vs 1x1 with
    # full overlap. The defensive guard `if w > 0 and h > 0` short-circuits
    # only if min(...) is 0, which cannot happen with valid Grids; we still
    # confirm a 1x1 -> 1x1 migrate copies the single cell.
    old = Grid(1, 1)
    old.set(0, 0, ElementId.WATER)
    new = Grid(1, 1)
    migrate_grid(old, new)
    assert new.get(0, 0) == ElementId.WATER

"""Tests for the :class:`sandfall.grid.Grid` class."""

from __future__ import annotations

import numpy as np
import pytest

from sandfall.elements import ElementId
from sandfall.grid import Grid


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

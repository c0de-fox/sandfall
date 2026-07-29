"""Tests for WATER physics (LIQUID): falls and spreads horizontally."""

from __future__ import annotations

import random

from sandfall.elements import ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation


def _seed() -> None:
    random.seed(0)


def test_water_falls_one_row_per_step() -> None:
    _seed()
    grid = Grid(width=6, height=8)
    grid.set(3, 1, ElementId.WATER)
    sim = Simulation(grid)

    sim.step()

    assert grid.get(3, 1) == ElementId.EMPTY
    assert grid.get(3, 2) == ElementId.WATER


def test_water_falls_until_floor() -> None:
    _seed()
    width, height = 5, 6
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    grid.set(2, 0, ElementId.WATER)
    sim = Simulation(grid)

    for _ in range(20):
        sim.step()

    # Water rests somewhere on the floor row (just above it).
    water_mask = grid.array == int(ElementId.WATER)
    assert int(water_mask.sum()) == 1
    # No water lost through the floor.
    for x in range(width):
        assert grid.get(x, height - 1) == ElementId.STONE


def test_water_spreads_out_on_flat_floor() -> None:
    """A column of water on a flat floor spreads into a wider, shorter blob."""
    _seed()
    width, height = 11, 8
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    # Stack a few water cells in the middle column just above the floor.
    for y in range(height - 4, height - 1):
        grid.set(width // 2, y, ElementId.WATER)
    sim = Simulation(grid)

    initial_mask = grid.array == int(ElementId.WATER)
    initial_width = initial_mask.any(axis=0).sum()
    initial_height = initial_mask.any(axis=1).sum()

    for _ in range(200):
        sim.step()

    final_mask = grid.array == int(ElementId.WATER)
    # No water lost (floor holds it).
    assert int(final_mask.sum()) == int(initial_mask.sum())
    final_width = final_mask.any(axis=0).sum()
    final_height = final_mask.any(axis=1).sum()
    # Spread is wider and shorter than the initial column.
    assert final_width > initial_width
    assert final_height <= initial_height


def test_sand_sinks_through_water_via_stacked_column() -> None:
    """Sand (denser) ends up on the floor with the water above/around it."""
    _seed()
    grid = Grid(width=3, height=6)
    for x in range(3):
        grid.set(x, 5, ElementId.STONE)
    # Water column sitting on the floor, sand dropped in on top.
    grid.set(1, 4, ElementId.WATER)
    grid.set(1, 3, ElementId.WATER)
    grid.set(1, 2, ElementId.SAND)
    sim = Simulation(grid)

    for _ in range(60):
        sim.step()

    sand_mask = grid.array == int(ElementId.SAND)
    water_mask = grid.array == int(ElementId.WATER)
    # Conservation.
    assert int(sand_mask.sum()) == 1
    assert int(water_mask.sum()) == 2
    # Sand (densest) settles directly on the floor; water is never below it.
    sand_ys = [y for y in range(grid.height) if sand_mask[y].any()]
    assert min(sand_ys) == 4
    # Floor intact.
    for x in range(3):
        assert grid.get(x, 5) == ElementId.STONE

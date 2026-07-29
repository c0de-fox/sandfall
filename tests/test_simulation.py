"""Black-box tests for the ``Simulation`` step loop and sand physics.

The simulation uses randomness (per-row x-scan direction; sand's
down-diagonal shuffle). Each test seeds ``random`` for determinism and
asserts *physical* outcomes (counts, rows occupied) rather than exact
cell positions when the answer is shuffle-dependent.
"""

from __future__ import annotations

import random

from sandfall.elements import ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation


def _seed() -> None:
    """Reset the global RNG to a fixed state for deterministic tests."""
    random.seed(0)


def test_sand_falls_one_row_per_step() -> None:
    _seed()
    grid = Grid(width=10, height=10)
    grid.set(5, 2, ElementId.SAND)
    sim = Simulation(grid)

    sim.step()

    assert grid.get(5, 2) == ElementId.EMPTY
    assert grid.get(5, 3) == ElementId.SAND


def test_sand_falls_multiple_rows_over_multiple_steps() -> None:
    _seed()
    grid = Grid(width=4, height=10)
    grid.set(1, 0, ElementId.SAND)
    sim = Simulation(grid)

    # One row per step => needs (height - 1) steps to reach the bottom.
    for _ in range(20):
        sim.step()

    assert grid.get(1, 0) == ElementId.EMPTY
    assert grid.get(1, 9) == ElementId.SAND


def test_sand_does_not_fall_through_floor() -> None:
    _seed()
    width, height = 6, 6
    grid = Grid(width=width, height=height)
    # Solid stone floor across the entire bottom row.
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    grid.set(2, height - 2, ElementId.SAND)
    sim = Simulation(grid)

    for _ in range(20):
        sim.step()

    # Sand rests directly on the floor and does not pass through.
    assert grid.get(2, height - 2) == ElementId.SAND
    assert grid.get(2, height - 1) == ElementId.STONE

    # Stays settled over further steps.
    for _ in range(20):
        sim.step()
    assert grid.get(2, height - 2) == ElementId.SAND
    assert grid.get(2, height - 1) == ElementId.STONE


def test_sand_piles_on_floor_without_sinking() -> None:
    _seed()
    width, height = 3, 6
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    # Three grains stacked in a column well above the floor.
    grid.set(1, 0, ElementId.SAND)
    grid.set(1, 1, ElementId.SAND)
    grid.set(1, 2, ElementId.SAND)
    sim = Simulation(grid)

    for _ in range(50):
        sim.step()

    sand_mask = grid.array == int(ElementId.SAND)
    # No sand is lost and none sinks below the floor.
    assert int(sand_mask.sum()) == 3
    # Every grain settles in the row directly above the floor.
    for y in range(height):
        for x in range(width):
            if sand_mask[y, x]:
                assert y == height - 2
    # The floor is entirely intact.
    for x in range(width):
        assert grid.get(x, height - 1) == ElementId.STONE


def test_sand_does_not_move_when_fully_supported() -> None:
    """Sand with blocked down + down-diagonals stays put across steps.

    A literal "stone directly beneath" interpretation is physically
    inconsistent with the powder rule (sand rolls down an open diagonal),
    so this test uses a wide floor to block all three fall targets.
    """
    _seed()
    width, height = 5, 4
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    grid.set(2, height - 2, ElementId.SAND)
    sim = Simulation(grid)

    for _ in range(10):
        sim.step()

    assert grid.get(2, height - 2) == ElementId.SAND


def test_empty_grid_steps_without_error() -> None:
    _seed()
    grid = Grid(width=4, height=4)
    sim = Simulation(grid)

    sim.step()

    assert int((grid.array != int(ElementId.EMPTY)).sum()) == 0


def test_sand_sinks_through_water() -> None:
    """Sand displaces lower-density liquids (water density 1.0 < sand 1.5).

    Phase 03 gives water its own (flowing) rule, so to test the swap
    invariant in isolation the water is trapped in a one-cell-wide column:
    it cannot flee sideways, leaving displacement as its only exit.
    """
    _seed()
    grid = Grid(width=1, height=4)
    grid.set(0, 3, ElementId.WATER)
    grid.set(0, 2, ElementId.SAND)
    sim = Simulation(grid)

    sim.step()

    # Sand swaps with the water directly below it.
    assert grid.get(0, 2) == ElementId.WATER
    assert grid.get(0, 3) == ElementId.SAND

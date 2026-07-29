"""Tests for static SOLID elements (STONE, WOOD): they never move."""

from __future__ import annotations

import random

from sandfall.elements import ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation


def _seed() -> None:
    random.seed(0)


def test_stone_never_moves() -> None:
    _seed()
    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.STONE)
    sim = Simulation(grid)

    for _ in range(10):
        sim.step()

    # Stone stays exactly where it started; nothing else spawned.
    assert grid.get(2, 2) == ElementId.STONE
    assert int((grid.array == int(ElementId.STONE)).sum()) == 1


def test_wood_never_moves() -> None:
    _seed()
    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.WOOD)
    sim = Simulation(grid)

    for _ in range(10):
        sim.step()

    assert grid.get(2, 2) == ElementId.WOOD
    assert int((grid.array == int(ElementId.WOOD)).sum()) == 1


def test_solids_support_sand_without_sinking() -> None:
    """A stone+wood platform holds sand up; neither solid shifts."""
    _seed()
    width, height = 6, 5
    grid = Grid(width=width, height=height)
    # Floor: half stone, half wood.
    for x in range(3):
        grid.set(x, height - 1, ElementId.STONE)
    for x in range(3, width):
        grid.set(x, height - 1, ElementId.WOOD)
    grid.set(2, height - 2, ElementId.SAND)
    grid.set(3, height - 2, ElementId.SAND)
    sim = Simulation(grid)

    for _ in range(30):
        sim.step()

    # Solids are untouched.
    for x in range(3):
        assert grid.get(x, height - 1) == ElementId.STONE
    for x in range(3, width):
        assert grid.get(x, height - 1) == ElementId.WOOD
    # Sand is conserved and stays above the floor.
    assert int((grid.array == int(ElementId.SAND)).sum()) == 2

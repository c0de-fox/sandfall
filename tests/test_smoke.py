"""Tests for SMOKE physics: rises and dissipates when life expires."""

from __future__ import annotations

import random

from sandfall.elements import ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation


def _seed() -> None:
    random.seed(0)


def _smoke_cells(grid: Grid) -> list[tuple[int, int]]:
    mask = grid.array == int(ElementId.SMOKE)
    return [(x, y) for y in range(grid.height) for x in range(grid.width) if mask[y, x]]


def test_smoke_rises_over_steps() -> None:
    """Smoke placed low ends up at a smaller y after several steps."""
    _seed()
    grid = Grid(width=7, height=12)
    start_x, start_y = 3, 10
    grid.set(start_x, start_y, ElementId.SMOKE)
    grid.set_life(start_x, start_y, 40)
    sim = Simulation(grid)

    for _ in range(8):
        sim.step()

    cells = _smoke_cells(grid)
    assert cells, "smoke should still exist after a few rising steps"
    # At least one smoke cell is strictly above the starting row.
    assert any(y < start_y for _x, y in cells)


def test_smoke_dissipates_when_life_expires() -> None:
    """Smoke with a short life vanishes entirely within a bounded window."""
    _seed()
    grid = Grid(width=5, height=8)
    grid.set(2, 6, ElementId.SMOKE)
    grid.set_life(2, 6, 4)
    sim = Simulation(grid)

    for _ in range(40):
        sim.step()

    assert int((grid.array == int(ElementId.SMOKE)).sum()) == 0


def test_smoke_does_not_sink() -> None:
    """Smoke never moves to a row below its starting row."""
    _seed()
    width, height = 7, 12
    grid = Grid(width=width, height=height)
    start_x, start_y = 3, 8
    grid.set(start_x, start_y, ElementId.SMOKE)
    grid.set_life(start_x, start_y, 30)
    sim = Simulation(grid)

    for _ in range(20):
        sim.step()
        for _x, y in _smoke_cells(grid):
            assert y <= start_y

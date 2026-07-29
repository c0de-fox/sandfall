"""Tests for FIRE physics: ignites flammable neighbors and expires with life.

Fire behavior is probabilistic (spread + smoke emission). Tests seed
``random`` and assert *eventual* / *within-bounds* outcomes (counts
decreasing, at-least-one ignition) rather than exact per-frame state.
"""

from __future__ import annotations

import random

import pytest

import sandfall.rules.fire as fire_mod
from sandfall.elements import ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation


def _seed() -> None:
    random.seed(0)


def _count(grid: Grid, eid: ElementId) -> int:
    return int((grid.array == int(eid)).sum())


def test_isolated_fire_expires_to_empty() -> None:
    """A fire with no fuel and a short life goes out within a few steps."""
    _seed()
    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.FIRE)
    grid.set_life(2, 2, 5)
    sim = Simulation(grid)

    # Generous bound: life 5 → gone within ~6 steps; run extra to be sure.
    for _ in range(30):
        sim.step()

    assert _count(grid, ElementId.FIRE) == 0


def test_fire_ignites_wood_neighbor() -> None:
    """Fire next to wood eventually ignites (consumes) at least one cell."""
    _seed()
    grid = Grid(width=5, height=5)
    # Ring the fire with wood so the spread target set is rich.
    grid.set(2, 2, ElementId.FIRE)
    grid.set_life(2, 2, 80)  # long-lived source so it has many spread rolls
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        grid.set(2 + dx, 2 + dy, ElementId.WOOD)
    initial_wood = _count(grid, ElementId.WOOD)
    sim = Simulation(grid)

    for _ in range(200):
        sim.step()

    # Some wood was ignited (converted to FIRE then to EMPTY as it burned).
    final_wood = _count(grid, ElementId.WOOD)
    assert final_wood < initial_wood


def test_fire_ignites_plant_neighbor() -> None:
    """Plant (flammability 0.4) ignites even more readily than wood."""
    _seed()
    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.FIRE)
    grid.set_life(2, 2, 60)
    grid.set(2, 1, ElementId.PLANT)  # directly above
    grid.set(1, 2, ElementId.PLANT)
    grid.set(3, 2, ElementId.PLANT)
    initial_plant = _count(grid, ElementId.PLANT)
    sim = Simulation(grid)

    for _ in range(120):
        sim.step()

    assert _count(grid, ElementId.PLANT) < initial_plant


def test_fire_emits_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """A long-lived fire emits smoke when SMOKE_CHANCE is cranked to 1.0."""
    # The real SMOKE_CHANCE (0.05) is too low to assert against reliably in a
    # fixed seed — crank it to 1.0 so every step with an EMPTY cell above
    # emits a puff. This exercises the smoke-spawn code path deterministically.
    monkeypatch.setattr(fire_mod, "SMOKE_CHANCE", 1.0)
    _seed()
    grid = Grid(width=7, height=9)
    # Floor to keep debris contained.
    for x in range(grid.width):
        grid.set(x, grid.height - 1, ElementId.STONE)
    grid.set(3, grid.height - 3, ElementId.FIRE)
    grid.set_life(3, grid.height - 3, 120)
    sim = Simulation(grid)

    saw_smoke = False
    for _ in range(50):
        sim.step()
        if _count(grid, ElementId.SMOKE) > 0:
            saw_smoke = True
            break

    assert saw_smoke


def test_fire_does_not_ignite_stone() -> None:
    """Stone is non-flammable; it survives a long fire unchanged."""
    _seed()
    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.FIRE)
    grid.set_life(2, 2, 50)
    grid.set(2, 1, ElementId.STONE)
    grid.set(1, 2, ElementId.STONE)
    sim = Simulation(grid)

    for _ in range(80):
        sim.step()

    # Both stone cells are still stone.
    assert grid.get(2, 1) == ElementId.STONE
    assert grid.get(1, 2) == ElementId.STONE

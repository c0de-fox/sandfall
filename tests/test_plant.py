"""Tests for PLANT physics: grows into EMPTY neighbors only near WATER.

Growth is probabilistic (``GROW_CHANCE`` per step). To keep the growth test
deterministic and fast, ``GROW_CHANCE`` is monkeypatched up to 1.0; the
no-water test uses the real low chance over many steps and asserts no
growth at all.
"""

from __future__ import annotations

import random

import pytest

import sandfall.rules.plant as plant_mod
from sandfall.elements import ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation


def _seed() -> None:
    random.seed(0)


def _plant_count(grid: Grid) -> int:
    return int((grid.array == int(ElementId.PLANT)).sum())


def test_plant_grows_when_water_adjacent(monkeypatch: pytest.MonkeyPatch) -> None:
    """With growth chance cranked to 1.0 and water adjacent, plant count rises."""
    monkeypatch.setattr(plant_mod, "GROW_CHANCE", 1.0)
    _seed()
    width, height = 5, 5
    grid = Grid(width=width, height=height)
    # Stone floor to keep the water sitting right under the plant.
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    grid.set(2, 2, ElementId.PLANT)
    grid.set(2, 3, ElementId.WATER)  # directly below plant, above floor
    sim = Simulation(grid)

    initial = _plant_count(grid)
    assert initial == 1

    for _ in range(25):
        sim.step()

    assert _plant_count(grid) > initial


def test_plant_does_not_grow_without_water() -> None:
    """No water anywhere ⇒ plant never grows, no matter how long we wait."""
    _seed()
    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.PLANT)
    sim = Simulation(grid)

    for _ in range(200):
        sim.step()

    assert _plant_count(grid) == 1
    assert grid.get(2, 2) == ElementId.PLANT


def test_plant_growth_does_not_consume_water(monkeypatch: pytest.MonkeyPatch) -> None:
    """Growth requires water proximity only; the water cell is NOT spent."""
    monkeypatch.setattr(plant_mod, "GROW_CHANCE", 1.0)
    _seed()
    width, height = 5, 5
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    grid.set(2, 2, ElementId.PLANT)
    grid.set(2, 3, ElementId.WATER)
    initial_water = int((grid.array == int(ElementId.WATER)).sum())
    sim = Simulation(grid)

    for _ in range(25):
        sim.step()

    # Plant grew (precondition) and water count is unchanged.
    assert _plant_count(grid) > 1
    assert int((grid.array == int(ElementId.WATER)).sum()) == initial_water

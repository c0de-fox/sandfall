"""Tests for FIRE physics and temperature-driven combustion.

Phase 02 replaced fire's probabilistic per-neighbor spread with a thermal
model: a living FIRE cell is a *heat source* (it re-asserts its
``burn_temp`` each step and lets the Simulation's diffusion pre-pass carry
that heat outward), and a flammable neighbor ignites ITSELF when its own
temperature exceeds its ``flashpoint`` (see the reactive WOOD / PLANT
rules). The smoke spawn and fire's rise/expire behavior are unchanged.

Accordingly these tests are DETERMINISTIC (no probabilistic spread to
seed around): they assert the heat-source behavior, the reactive
ignition of WOOD/PLANT above their flashpoint, non-ignition below it,
end-to-end combustion chaining (a long-lived fire warms adjacent wood
until it ignites within a bounded step budget), and that STONE (whose
``flashpoint`` defaults to 0 = "never") never ignites however hot. The
legacy smoke + isolated-fire-expiry tests are kept (those code paths are
unchanged).
"""

from __future__ import annotations

import random

import pytest

import sandfall.rules.fire as fire_mod
from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation


def _seed() -> None:
    random.seed(0)


def _count(grid: Grid, eid: ElementId) -> int:
    return int((grid.array == int(eid)).sum())


def test_isolated_fire_expires_to_empty() -> None:
    """A fire with no fuel and a short life goes out within a few steps.

    Unchanged from v1: the age/expire path still empties the cell when life
    hits 0 (Phase 02 additionally cools it to AMBIENT_TEMP on expiry).
    """
    _seed()
    grid = Grid(width=5, height=5)
    grid.set(2, 2, ElementId.FIRE)
    grid.set_life(2, 2, 5)
    sim = Simulation(grid)

    # Generous bound: life 5 → gone within ~6 steps; run extra to be sure.
    for _ in range(30):
        sim.step()

    assert _count(grid, ElementId.FIRE) == 0


def test_fire_heats_neighbors_deterministically() -> None:
    """A fire cell raises the temp of its orthogonal neighbors within a few
    steps (no randomness — pure diffusion). Fire is a heat SOURCE."""
    _seed()
    grid = Grid(width=5, height=5)
    # Floor + ring of EMPTY so the fire sits at (2,2) surrounded by air.
    for x in range(grid.width):
        grid.set(x, grid.height - 1, ElementId.STONE)
    grid.set(2, 2, ElementId.FIRE)
    grid.set_life(2, 2, 200)  # long-lived source
    grid.set_temp(2, 2, ELEMENTS[ElementId.FIRE].burn_temp)  # 800
    sim = Simulation(grid)
    # The cell directly above the fire, measured before any heat is applied.
    before = grid.get_temp(2, 1)
    for _ in range(5):
        sim.step()
    after = grid.get_temp(2, 1)
    assert after > before + 20  # warmed noticeably via diffusion
    assert after < ELEMENTS[ElementId.FIRE].burn_temp  # never hotter than source


def test_wood_ignites_above_flashpoint() -> None:
    """A wood cell hotter than its flashpoint becomes FIRE on its next step."""
    grid = Grid(width=3, height=3)
    grid.set(1, 1, ElementId.WOOD)
    grid.set_temp(1, 1, ELEMENTS[ElementId.WOOD].flashpoint + 50)
    Simulation(grid).step()
    assert grid.get(1, 1) == ElementId.FIRE
    assert grid.get_life(1, 1) > 0
    assert grid.get_temp(1, 1) == ELEMENTS[ElementId.FIRE].burn_temp


def test_wood_below_flashpoint_does_not_ignite() -> None:
    """A wood cell below its flashpoint stays wood (ignition is threshold-gated)."""
    grid = Grid(width=3, height=3)
    grid.set(1, 1, ElementId.WOOD)
    grid.set_temp(1, 1, ELEMENTS[ElementId.WOOD].flashpoint - 1)
    Simulation(grid).step()
    assert grid.get(1, 1) == ElementId.WOOD


def test_plant_ignites_above_flashpoint() -> None:
    """A plant cell hotter than its flashpoint becomes FIRE (reactive plant rule)."""
    grid = Grid(width=3, height=3)
    grid.set(1, 1, ElementId.PLANT)
    grid.set_temp(1, 1, ELEMENTS[ElementId.PLANT].flashpoint + 50)
    Simulation(grid).step()
    assert grid.get(1, 1) == ElementId.FIRE
    assert grid.get_life(1, 1) > 0
    assert grid.get_temp(1, 1) == ELEMENTS[ElementId.FIRE].burn_temp


def test_fire_next_to_wood_eventually_ignites_it() -> None:
    """End-to-end: a long-lived fire warms adjacent wood until it ignites.

    Deterministic (heat diffusion only); bounded step budget. This is the
    Phase 02 tuning gate — combustion must actually CHAIN: a single fire
    cell must ignite fuel within reach via the diffusion pre-pass.
    """
    _seed()
    grid = Grid(width=5, height=5)
    for x in range(grid.width):
        grid.set(x, grid.height - 1, ElementId.STONE)
    grid.set(2, 3, ElementId.FIRE)
    grid.set_life(2, 3, 300)
    grid.set_temp(2, 3, ELEMENTS[ElementId.FIRE].burn_temp)  # 800
    grid.set(2, 2, ElementId.WOOD)  # directly above the fire
    sim = Simulation(grid)
    ignited = False
    for _ in range(400):
        sim.step()
        if grid.get(2, 2) == ElementId.FIRE:
            ignited = True
            break
    assert ignited


def test_stone_never_ignites_even_when_hot() -> None:
    """``flashpoint == 0`` means never; a hot stone stays stone (no reactive
    stone rule exists, and a no-op rule never transforms it)."""
    grid = Grid(width=3, height=3)
    grid.set(1, 1, ElementId.STONE)
    grid.set_temp(1, 1, 2000)  # far above any flashpoint
    Simulation(grid).step()
    assert grid.get(1, 1) == ElementId.STONE


def test_fire_emits_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """A long-lived fire emits smoke when SMOKE_CHANCE is cranked to 1.0.

    Unchanged from v1: the smoke-spawn code path is intact, and SMOKE_CHANCE
    remains a module-level attribute on ``fire.py``.
    """
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

"""Tests for temperature-driven convection (intra-phase buoyancy).

Hot fluid rises through cooler same-phase fluid; cold sinks. Covers liquids
(water pool), gases (steam column), the pool-equilibration speedup over
conduction-only, and the negatives (powders/solids, below-threshold, 1x1).

Convection is the INTRA-phase complement of the existing cross-phase buoyancy
(``is_riseable`` / ``can_displace``): hot WATER rises THROUGH cooler WATER, hot
STEAM rises THROUGH cooler STEAM. Powders (sand) and solids never convect.

NOTE on temp assertions: the Simulation runs ONE vectorized heat-diffusion pre-
pass BEFORE the movement scan, so every rule reads a freshly-diffused
temperature -- the exact value a cell holds after a step is NOT the value the
test set (diffusion moves heat between neighbors first). These tests therefore
assert INEQUALITIES that prove the convective swap happened (the hotter cell is
now ABOVE the cooler one) rather than exact float temps, which makes them robust
to the diffusion arithmetic. Mirrors the test_phase.py 1x1 diffusion-no-op
philosophy where applicable, and the test_gas_buoyancy.py whole-grid-uniform-
temp trick where a near-zero Laplacian is needed.
"""

from __future__ import annotations

import random

import pytest

import sandfall.rules.water as water_mod
from sandfall.elements import AMBIENT_TEMP, ElementId
from sandfall.grid import Grid
from sandfall.rules._common import CONVECTION_THRESHOLD
from sandfall.simulation import Simulation


def _seed() -> None:
    random.seed(0)


def test_hot_water_rises_through_cold_water() -> None:
    """A hot WATER cell directly below a cold WATER cell swaps UP in one step.

    The hot cell (bottom) is set just under WATER.boil_point (100) so it does
    NOT boil (boil is a reactive check that fires before convection and would
    transform the cell to STEAM). After one step the hot cell has risen one row
    (it is now the middle cell) and the cold middle cell has sunk to the
    bottom -- proven by the middle cell being far hotter than the bottom cell.
    Both stay WATER (no phase transition).
    """
    _seed()
    grid = Grid(width=1, height=3)
    grid.set(0, 0, ElementId.WATER)  # top (cold)
    grid.set(0, 1, ElementId.WATER)  # middle (cold)
    grid.set(0, 2, ElementId.WATER)  # bottom (hot)
    grid.set_temp(0, 0, AMBIENT_TEMP)  # 20
    grid.set_temp(0, 1, AMBIENT_TEMP)  # 20
    grid.set_temp(0, 2, 99)  # hot, but below boil_point (100) -> no boil
    sim = Simulation(grid)

    sim.step()

    # The hot cell convected up to y=1; the cold middle cell sank to y=2. The
    # middle cell is now far hotter than the bottom cell (the swap carried the
    # heat up). Temps are post-diffusion (slightly equalized) so assert a wide
    # inequality margin rather than exact equality.
    assert grid.get(0, 1) == ElementId.WATER
    assert grid.get(0, 2) == ElementId.WATER
    assert grid.get_temp(0, 1) > grid.get_temp(0, 2) + 30
    # And the top cell is still cold (the hot cell only rose one row this step).
    assert grid.get_temp(0, 0) < grid.get_temp(0, 1) - 30


def test_hot_gas_rises_through_cold_gas() -> None:
    """A hot STEAM cell below cooler STEAM swaps UP (gas-gas convection).

    This is the NEW gas-gas displacement path convection adds (today gases only
    rise into EMPTY/LIQUID via is_riseable; they never displaced another gas).
    All temps are above STEAM.condense_point (60) so no cell condenses to WATER,
    and life is seeded long so none expires.
    """
    _seed()
    grid = Grid(width=1, height=3)
    for y in range(3):
        grid.set(0, y, ElementId.STEAM)
        grid.set_life(0, y, 200)  # long life so age does not expire it
    grid.set_temp(0, 0, 200)  # top -- well above condense_point (60)
    grid.set_temp(0, 1, 200)
    grid.set_temp(0, 2, 500)  # bottom -- hotter
    sim = Simulation(grid)

    sim.step()

    # Hot steam convected up: y=1 now holds the (formerly bottom) hot cell, y=2
    # the cooler cell. All stay STEAM (no condense). Inequality proves the swap.
    assert grid.get(0, 1) == ElementId.STEAM
    assert grid.get(0, 2) == ElementId.STEAM
    assert grid.get_temp(0, 1) > grid.get_temp(0, 2) + 30


def test_convection_accelerates_pool_equilibration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A heat source at the bottom of a water column warms the TOP far faster
    than conduction alone could (water cp=4.0 makes the diffusion coefficient
    ~0.0175/step -- glacial over 20 cells).

    The bottom cell is PINNED to a hot-but-sub-boil temp (99C) each step so it
    is a continuous heat source that does not boil away (plan-permitted: "pin a
    cell at a high temp"). With convection, the hot cell physically bubbles up
    one row per step (hot rises, cool sinks -> circulation), so the top warms
    within tens of steps; via pure conduction the top stays essentially at
    ambient. We assert BOTH the convection outcome (top clearly warm) AND the
    conduction-only baseline (top at ambient) -- the contrast is the headline
    proof that convection is the dominant fluid heat-transfer mechanism.

    (The top does NOT reach the source's 99C in 60 steps: once the column's
    local gradients drop below CONVECTION_THRESHOLD convection stops firing and
    slow diffusion takes over, so the top asymptotes well below the source.
    Measured ~62C with convection vs ~20C without.)
    """
    h = 20

    def run(disable_convect: bool) -> float:
        _seed()
        grid = Grid(width=1, height=h)
        for y in range(h):
            grid.set(0, y, ElementId.WATER)
            grid.set_temp(0, y, AMBIENT_TEMP)
        if disable_convect:
            # Only WATER is present in this column, so patching the water rule's
            # bound maybe_convect is sufficient to get a conduction-only run.
            monkeypatch.setattr(water_mod, "maybe_convect", lambda g, x, y: None)
        sim = Simulation(grid)
        for _ in range(60):
            grid.set_temp(0, h - 1, 99)  # pin bottom: continuous sub-boil source
            sim.step()
        return grid.get_temp(0, 0)

    top_with_convection = run(disable_convect=False)
    top_conduction_only = run(disable_convect=True)

    # Headline: convection warms the top dramatically; conduction does not.
    assert top_with_convection > 50, top_with_convection
    assert top_conduction_only < AMBIENT_TEMP + 5, top_conduction_only
    # And the contrast is large (convection is the dominant mechanism).
    assert top_with_convection > top_conduction_only + 30


def test_no_convection_for_powders() -> None:
    """Hot SAND below cold SAND does NOT convect (powders pile, not convect).

    Sand is Phase.POWDER, excluded by the ``my_phase not in (LIQUID, GAS)``
    guard. The hot bottom cell keeps its heat (it does not rise through the
    cold sand above). Sand at the floor does not move (supported from below),
    so the bottom cell is still the hot one after a step.
    """
    _seed()
    grid = Grid(width=1, height=3)
    grid.set(0, 0, ElementId.SAND)  # top (cold)
    grid.set(0, 1, ElementId.SAND)  # middle (cold)
    grid.set(0, 2, ElementId.SAND)  # bottom (hot)
    grid.set_temp(0, 0, AMBIENT_TEMP)
    grid.set_temp(0, 1, AMBIENT_TEMP)
    grid.set_temp(0, 2, 500)
    sim = Simulation(grid)

    sim.step()

    # No convective swap: the hot cell stayed at the bottom (still clearly hot,
    # only marginally cooled by one diffusion step toward the middle cell).
    assert grid.get(0, 2) == ElementId.SAND
    assert grid.get_temp(0, 2) > 400
    assert grid.get_temp(0, 1) < 100  # middle stayed cool (no hot cell rose into it)


def test_no_convection_below_threshold() -> None:
    """A temp difference < CONVECTION_THRESHOLD does not convect.

    Two water cells with the bottom just-under-threshold warmer than the top:
    no swap, so the bottom cell is still the (slightly) warmer one after a step.
    """
    _seed()
    grid = Grid(width=1, height=2)
    grid.set(0, 0, ElementId.WATER)
    grid.set(0, 1, ElementId.WATER)
    grid.set_temp(0, 0, AMBIENT_TEMP)
    grid.set_temp(0, 1, AMBIENT_TEMP + CONVECTION_THRESHOLD - 1)  # just under
    sim = Simulation(grid)

    sim.step()

    # No swap: the bottom cell is still warmer than the top (diffusion slightly
    # equalized them, but the ordering is preserved because no swap occurred).
    assert grid.get_temp(0, 1) > grid.get_temp(0, 0)


def test_convection_is_noop_on_single_cell() -> None:
    """A 1x1 grid has no cell above -> maybe_convect returns None (no crash).

    Temp is set between freeze_point (0) and boil_point (100) so the cell does
    not transform via the water rule's reactive checks -- the point is that the
    maybe_convect call (a no-op here, no neighbor above) does not raise and the
    cell is untouched.
    """
    _seed()
    grid = Grid(width=1, height=1)
    grid.set(0, 0, ElementId.WATER)
    grid.set_temp(0, 0, 50)  # 0 < 50 < 100: neither freezes nor boils
    sim = Simulation(grid)

    sim.step()  # must not raise

    assert grid.get(0, 0) == ElementId.WATER

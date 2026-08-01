"""Tests for gas buoyancy: STEAM and SMOKE rise through liquids.

STEAM and SMOKE rise into EMPTY (open air, as before) OR any LIQUID (buoyancy --
the gas swaps with the liquid above it: gas up, liquid down). The sideways
DRIFT stays EMPTY-only (buoyancy is upward, not lateral). FIRE is unchanged
(EMPTY-only) -- out of scope.

Isolating buoyancy from condensation: STEAM condenses below its condense_point
(60C). A steam cell set without an explicit warm temp defaults to ambient (20C)
and condenses on step 1 -- before it can rise. So the steam tests set a uniform
warm temp (> 60) across the steam + liquid column so the diffusion Laplacian is
~zero and the steam stays gaseous while rising (mirrors the test_phase.py 1x1
diffusion-no-op philosophy). SMOKE has no condense path, so it needs only life.

Temp choice for steam tests: 80C. This is safely above STEAM.condense_point (60
-> steam stays gaseous) AND at/under WATER.boil_point (100 -> water does NOT
boil, since the water rule boils at strictly > 100). The whole grid is warmed
uniformly so diffusion is a no-op and neither phase transition can fire
regardless of scan order -- this keeps the buoyancy swap the ONLY thing under
test (a water boiling to steam at the steam's old cell would otherwise be a
false-positive "swap").
"""

from __future__ import annotations

import random

from sandfall.elements import ElementId
from sandfall.grid import Grid
from sandfall.simulation import Simulation

# 60 < _WARM <= 100: above STEAM.condense_point (no condense), at/under
# WATER.boil_point (no boil). Used for every steam test (whole-grid uniform).
_WARM = 80


def _warm_all(grid: Grid, temp: float = _WARM) -> None:
    """Set every cell's temperature to ``temp`` so diffusion is a uniform no-op.

    Mirrors the test_phase.py 1x1 diffusion-no-op philosophy extended to a whole
    grid: a uniform temp field has a zero Laplacian, so the diffusion pre-pass
    changes nothing and the rule under test sees exactly the temp we set.
    """
    for y in range(grid.height):
        for x in range(grid.width):
            grid.set_temp(x, y, temp)


def test_steam_rises_through_water() -> None:
    """STEAM below WATER swaps up (buoyancy): after one step the steam is in the
    water's old cell (one row up) and the water is in the steam's old cell. Stone
    side walls prevent sideways drift / diagonal escape so only the straight-up
    rise is exercised; a uniform warm temp (> condense_point 60, <= boil_point
    100) across the grid keeps the diffusion Laplacian ~zero so the steam does
    not condense before rising and the water does not boil.
    """
    random.seed(0)
    g = Grid(3, 4)
    # Stone walls left/right + floor to box the column.
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)  # floor
    # Steam at (1,2), WATER directly above at (1,1), open air at (1,0).
    g.set(1, 2, ElementId.STEAM)
    g.set_life(1, 2, 200)
    g.set(1, 1, ElementId.WATER)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM  # steam rose into the water's cell
    assert g.get(1, 2) == ElementId.WATER  # water sank into the steam's old cell


def test_steam_rises_to_surface_of_water_pool() -> None:
    """Steam released at the bottom of a water column bubbles up through the
    water (buoyancy, one swap per step) and emerges above the water line into
    air. Uniform warm temp (> condense_point, <= boil_point) keeps it gaseous for
    the climb."""
    random.seed(0)
    g = Grid(3, 8)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 7, ElementId.STONE)  # floor
    # Water column rows 1-5; open air at row 0.
    for y in range(1, 6):
        g.set(1, y, ElementId.WATER)
    g.set(1, 6, ElementId.STEAM)  # steam at the bottom of the pool
    g.set_life(1, 6, 255)  # clipped to uint8 max; > 200 steps of climbing budget
    _warm_all(g)
    sim = Simulation(g)
    for _ in range(200):
        sim.step()
    steam_ys = [y for y in range(g.height) if g.get(1, y) == ElementId.STEAM]
    assert steam_ys, "steam expired/condensed before surfacing -- bump life/temp"
    # Steam climbed above the water line (water occupied rows 1-5; row 0 is air).
    assert min(steam_ys) <= 1, f"steam did not reach the surface: y={steam_ys}"


def test_smoke_rises_through_water() -> None:
    """SMOKE below WATER swaps up (buoyancy), mirroring steam. Smoke has no
    condense path, so only life is seeded (no temp setup needed)."""
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)
    g.set(1, 2, ElementId.SMOKE)
    g.set_life(1, 2, 200)
    g.set(1, 1, ElementId.WATER)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.SMOKE
    assert g.get(1, 2) == ElementId.WATER


def test_steam_rises_through_oil() -> None:
    """Buoyancy is generic over Phase.LIQUID, not water-specific: steam below
    OIL (the lightest liquid, density 0.8) still rises through it."""
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)
    g.set(1, 2, ElementId.STEAM)
    g.set_life(1, 2, 200)
    g.set(1, 1, ElementId.OIL)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM
    assert g.get(1, 2) == ElementId.OIL


def test_steam_does_not_rise_through_solid_or_gas() -> None:
    """is_riseable is False for SOLIDS and other GASES: steam fully boxed in by
    stone (above + up-diagonals + sides) does NOT swap with the stone, and steam
    boxed in by smoke above does NOT swap with the smoke. The steam stays put."""
    random.seed(0)

    # (a) Stone directly above + stone up-diagonals + stone sides + stone floor.
    g = Grid(3, 3)
    for y in range(g.height):
        for x in range(g.width):
            g.set(x, y, ElementId.STONE)
    g.set(1, 1, ElementId.STEAM)  # carve a steam pocket in solid stone
    g.set_life(1, 1, 200)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM  # did not rise into stone

    # (b) SMOKE directly above the steam (gas-gas: not riseable). Fully boxed:
    # stone cap at (1,0) so the smoke cannot rise away (otherwise it would swap
    # with the open air above and leave (1,1) empty -- the spec note flags this
    # and recommends boxing tighter; pinning the capped geometry here).
    g2 = Grid(3, 4)
    for y in range(g2.height):
        g2.set(0, y, ElementId.STONE)
        g2.set(2, y, ElementId.STONE)
    g2.set(1, 0, ElementId.STONE)  # cap -- blocks smoke from rising out
    g2.set(1, 3, ElementId.STONE)  # floor
    g2.set(1, 1, ElementId.SMOKE)  # smoke directly above
    g2.set_life(1, 1, 200)
    g2.set(1, 2, ElementId.STEAM)
    g2.set_life(1, 2, 200)
    _warm_all(g2)
    Simulation(g2).step()
    assert g2.get(1, 2) == ElementId.STEAM  # did not rise into smoke
    assert g2.get(1, 1) == ElementId.SMOKE


def test_drift_does_not_go_sideways_through_liquid() -> None:
    """Buoyancy is UPWARD only. A steam cell blocked above by STONE and flanked
    left/right by WATER cannot rise (stone is not riseable) and must NOT drift
    sideways through the water (drift is EMPTY-only). The steam stays put.

    Fully boxed geometry (all border cells STONE, steam in the center, WATER
    flanking left/right): the up-diagonal corners are STONE (so the steam cannot
    escape diagonally into an open corner), and the floor under the water is
    STONE (so the water cannot fall away). This makes "stays put" deterministic
    for both the steam and the water (see the spec note recommending the corners
    be filled).
    """
    random.seed(0)
    g = Grid(3, 3)
    # Stone border on all four sides (top row, bottom row, left/right cols).
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    for x in range(g.width):
        g.set(x, 0, ElementId.STONE)
        g.set(x, 2, ElementId.STONE)
    # Steam in the middle; WATER on both sides (drift targets, but not EMPTY).
    g.set(1, 1, ElementId.STEAM)
    g.set_life(1, 1, 200)
    g.set(0, 1, ElementId.WATER)
    g.set(2, 1, ElementId.WATER)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM  # did not drift into the water
    assert g.get(0, 1) == ElementId.WATER
    assert g.get(2, 1) == ElementId.WATER

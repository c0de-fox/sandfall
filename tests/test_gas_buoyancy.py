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

This file also tests the COMPLEMENT of buoyancy -- a denser phase flowing
THROUGH a gas (can_displace's gas clause): WATER flows sideways through a
steam wall, WATER sinks through STEAM, and SAND falls through STEAM. The two
directions are symmetric (denser phase down/in, lighter phase up) and must
coexist: a steam wall no longer dams flowing water, while steam still rises
through water (test_steam_rises_through_water). One legacy drift test was
repurposed to flank with STONE instead of WATER: once gases became
displacable the water-flanks shove the boxed steam (the new correct
liquid-through-gas behavior), which would confound the drift-is-air-only
assertion -- drift rejects any non-EMPTY cell identically, so stone flanks
preserve that lock.
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


def test_drift_does_not_go_sideways_into_non_empty() -> None:
    """Buoyancy is UPWARD only and DRIFT is EMPTY-only. A steam cell blocked
    above by STONE and flanked left/right by STONE cannot rise (stone is not
    riseable) and must NOT drift sideways into the stone (drift is EMPTY-only).
    The steam stays put.

    Flanks are STONE (not WATER) because, post gas-displacement fix, a WATER
    flank would shove the boxed steam sideways (the new correct
    liquid-through-gas behavior -- see test_water_flows_through_steam_sideways),
    which would confound this drift-is-air-only assertion. Drift rejects any
    non-EMPTY cell identically, so stone flanks lock the invariant without
    collision.
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
    # Steam in the middle; STONE on both sides (drift targets, but not EMPTY).
    g.set(1, 1, ElementId.STEAM)
    g.set_life(1, 1, 200)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM  # did not drift into the stone
    assert g.get(0, 1) == ElementId.STONE
    assert g.get(2, 1) == ElementId.STONE


def test_water_flows_through_steam_sideways() -> None:
    """Complement of buoyancy: a denser phase flows THROUGH a gas. WATER beside
    a STEAM wall (both on a stone floor, stone bookends boxing the row) swaps
    sideways -- the water enters the steam's old cell and the steam is pushed
    to the water's old cell (then it would continue rising via is_riseable
    next step). Uniform warm temp (> STEAM.condense_point 60, <= WATER.boil_point
    100) keeps the steam gaseous so it isn't lost to condensation.

    Robust to scan order and the per-row x-randomization: if the steam is
    visited first it cannot rise (y-1 out of bounds) nor drift (both neighbors
    non-EMPTY), so it stays; the water then shoves it. If the water is visited
    first it shoves the steam directly. Either order yields the same swap.
    """
    random.seed(0)
    g = Grid(4, 2)
    # Row 1 (floor): all stone so neither cell can fall.
    for x in range(g.width):
        g.set(x, 1, ElementId.STONE)
    # Row 0: stone | WATER | STEAM | stone  (water boxed left by stone).
    g.set(0, 0, ElementId.STONE)
    g.set(1, 0, ElementId.WATER)
    g.set(2, 0, ElementId.STEAM)
    g.set_life(2, 0, 200)
    g.set(3, 0, ElementId.STONE)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(2, 0) == ElementId.WATER  # water flowed into the steam's cell
    assert g.get(1, 0) == ElementId.STEAM  # steam shoved to the water's old cell


def test_water_falls_through_steam() -> None:
    """Complement of buoyancy: WATER directly above STEAM sinks THROUGH it.
    After one step the water is below (in the steam's old cell) and the steam
    is above (in the water's old cell); the steam then continues rising via
    is_riseable. Stone walls box the column; warm temp keeps the steam gaseous.

    Robust to scan order: bottom->top visits the steam first -- it rises into
    the water above via is_riseable (the buoyancy path). Top->down would let
    the water sink via can_displace. Both yield the identical swap, so the
    assertions hold unseeded.
    """
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)  # floor
    g.set(1, 1, ElementId.WATER)  # water above...
    g.set(1, 2, ElementId.STEAM)  # ...steam below
    g.set_life(1, 2, 200)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 2) == ElementId.WATER  # water sank through the steam
    assert g.get(1, 1) == ElementId.STEAM  # steam bubbled up


def test_sand_falls_through_steam() -> None:
    """Complement of buoyancy extends to POWDERs too: SAND directly above STEAM
    sinks through it. After one step the sand is below and the steam above.

    Robust to scan order: if the steam is visited first it tries to rise into
    the sand -- is_riseable(SAND) is False (sand is POWDER, not EMPTY/LIQUID)
    -- so it stays; the sand then sinks via can_displace. The warm temp keeps
    the steam gaseous; sand does not melt at 80C (melt_point 1700).
    """
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)  # floor
    g.set(1, 1, ElementId.SAND)  # sand above...
    g.set(1, 2, ElementId.STEAM)  # ...steam below
    g.set_life(1, 2, 200)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 2) == ElementId.SAND  # sand sank through the steam
    assert g.get(1, 1) == ElementId.STEAM  # steam bubbled up


def test_water_displaces_fire_edge() -> None:
    """EDGE (current behavior, not a feature): the gas clause also lets WATER
    displace FIRE (a GAS) -- water shoves fire aside rather than dousing it,
    because there is no fire+water extinguish mechanic yet. The fire is pushed
    to the water's old cell and keeps its life; a proper extinguish is tracked
    as future work. Locked here so a later extinguish feature changes this test
    deliberately.

    NOTE: FIRE.temp_spawn is 800C (>> WATER.boil_point 100). The heat-diffusion
    pre-pass can boil the water cell before it moves, so this test forces the
    water cell cold via ``set_temp`` and asserts the shove on step 1. Verified
    deterministic across seeds 0..7 (one diffusion step from 20C toward an 800C
    neighbor stays under the >100 boil threshold, so the water survives to shove
    the fire).
    """
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)  # floor
    g.set(1, 1, ElementId.WATER)
    g.set_temp(1, 1, 20)  # AMBIENT; keep the water from boiling this step
    g.set(1, 2, ElementId.FIRE)
    g.set_life(1, 2, 30)
    Simulation(g).step()
    assert g.get(1, 2) == ElementId.WATER  # water shoved the fire
    assert g.get(1, 1) == ElementId.FIRE  # fire pushed to the water's old cell

"""Black-box tests for the ``Simulation`` step loop and sand physics.

The simulation uses randomness (per-row x-scan direction; sand's
down-diagonal shuffle). Each test seeds ``random`` for determinism and
asserts *physical* outcomes (counts, rows occupied) rather than exact
cell positions when the answer is shuffle-dependent.
"""

from __future__ import annotations

import random

from sandfall.brush import paint_brush
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


def test_sparse_scan_piles_sand_on_floor_in_mostly_empty_grid() -> None:
    """Regression guard for the sparse (non-empty-only) scan path.

    A wide, mostly-empty grid with a full floor and a column of sand well
    above it: the sparse scan must still settle every grain into a stable
    pile on the floor. The empty cells that are now skipped were no-ops
    before, so the result is identical to the old full-row scan. Pins that
    sparsifying the scan did not break movement at scale.

    Asserts the physical settling invariant (every grain supported from
    below, the pile reaches the floor, no grain lost) rather than exact
    positions -- four grains of sand pile into a pyramid with one apex
    grain one row above the base, which is the correct stable shape (and
    what the old full-scan also produced).
    """
    _seed()
    width, height = 20, 12
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    # A column of sand in the upper-middle, surrounded by air on all sides.
    for y in range(0, 4):
        grid.set(width // 2, y, ElementId.SAND)
    sim = Simulation(grid)

    for _ in range(60):
        sim.step()

    sand_mask = grid.array == int(ElementId.SAND)
    assert int(sand_mask.sum()) == 4  # no sand lost
    # Settled invariant: every grain is supported (the cell directly below is
    # non-empty -- floor or another grain), so no sand is suspended over air.
    for y in range(height - 1):
        for x in range(width):
            if sand_mask[y, x]:
                assert grid.get(x, y + 1) != int(ElementId.EMPTY), (x, y)
    # The pile reached the floor: at least one grain rests directly on it.
    assert bool(sand_mask[height - 2].any())
    # The floor is entirely intact.
    for x in range(width):
        assert grid.get(x, height - 1) == ElementId.STONE


def test_sparse_scan_water_finds_its_level() -> None:
    """Water in a mostly-empty grid settles so no grain is suspended over air.

    Liquid flow is randomized; the test seeds the RNG and asserts the settled
    physical invariant (no water cell with an empty cell directly below it)
    after a generous step budget. Pins that liquid flow still works under the
    sparse scan (empty cells skipped were no-ops before).
    """
    _seed()
    width, height = 12, 10
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    # A blob of water in the upper-left, surrounded by air.
    for y in range(0, 3):
        for x in range(0, 4):
            grid.set(x, y, ElementId.WATER)
    sim = Simulation(grid)

    for _ in range(120):
        sim.step()

    water_mask = grid.array == int(ElementId.WATER)
    assert int(water_mask.sum()) == 12  # no water lost
    # Settled invariant: no water cell has an empty cell directly below it
    # (every water cell rests on the floor or on another water cell).
    for y in range(height - 1):
        for x in range(width):
            if water_mask[y, x]:
                assert grid.get(x, y + 1) != int(ElementId.EMPTY), (x, y)


def test_settled_pile_goes_dormant() -> None:
    """A settled, ambient-temperature sand pile collapses to a dormant active set.

    After settling, no grain moves, no temp changes (uniform ambient), and there
    are no heat sources -- so the wake set is provably empty and the whole pile
    is skipped next frame. Pins the headline dormancy win: the active set is the
    (tiny) movement front, NOT the whole pile.
    """
    _seed()
    width, height = 12, 10
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    n_grains = 6
    for y in range(0, n_grains):
        grid.set(width // 2, y, ElementId.SAND)  # column above the floor
    sim = Simulation(grid)

    sim.step()  # bootstrap made every non-empty cell active
    initial_active = int(grid.active.sum())
    assert initial_active > 0  # the pile was scanned this frame

    for _ in range(80):
        sim.step()  # let the pile fully settle

    # No sand lost; all grains supported from below.
    sand_mask = grid.array == int(ElementId.SAND)
    assert int(sand_mask.sum()) == n_grains
    for y in range(height - 1):
        for x in range(width):
            if sand_mask[y, x]:
                assert grid.get(x, y + 1) != int(ElementId.EMPTY), (x, y)
    # Settled + uniform ambient + no heat source => the active set is empty
    # (the movement front is zero). This is the dormancy guard.
    final_active = int(grid.active.sum())
    assert final_active == 0, final_active


def test_eroding_support_wakes_dormant_pile() -> None:
    """Erasing the floor under a dormant pile wakes it and the grains fall.

    Erasing is done via the brush path (fill_circle), which marks the erased
    cell's neighborhood active -- including the dormant grain directly above.
    Next step that grain is scanned, finds the cell below now empty, and falls.
    (Direct grid.set(x, y, EMPTY) between steps intentionally does NOT wake --
    only non-empty set marks active; erase-wake is fill_circle's job.)
    """
    _seed()
    width, height = 6, 8
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    grid.set(width // 2, height - 2, ElementId.SAND)  # grain resting on floor
    sim = Simulation(grid)

    for _ in range(10):
        sim.step()  # grain settled + dormant
    assert grid.get(width // 2, height - 2) == ElementId.SAND
    assert not grid.active[height - 2, width // 2]  # dormant

    # Erase the floor cell directly beneath the dormant grain (brush path).
    grid.fill_circle(width // 2, height - 1, 0, ElementId.EMPTY)
    sim.step()

    # The grain was woken and fell one row into the opened hole.
    assert grid.get(width // 2, height - 1) == ElementId.SAND
    assert grid.get(width // 2, height - 2) == ElementId.EMPTY


def test_dormant_water_next_to_lava_flashes_to_steam() -> None:
    """A dormant (trapped, unmoving) water cell still flashes to STEAM when lava
    arrives beside it. Lava is a persistent heat source (wake 3), so the lava
    cell stays scanned and its rule side-effects the adjacent water to steam
    (lava.py reaction). Dormancy must not starve the reaction.
    """
    _seed()
    width, height = 4, 3
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    grid.set(0, 1, ElementId.STONE)  # left wall
    grid.set(2, 1, ElementId.STONE)  # right wall (becomes lava later)
    grid.set(1, 1, ElementId.WATER)  # trapped water: cannot move
    sim = Simulation(grid)

    for _ in range(5):
        sim.step()  # water trapped -> dormant
    assert grid.get(1, 1) == ElementId.WATER
    assert not grid.active[1, 1]  # water dormant

    # Lava arrives beside the dormant water (paint_brush sets spawn_temp=1500).
    paint_brush(grid, 2, 1, 0, ElementId.LAVA)
    sim.step()

    # The lava reacted with the adjacent water: water -> STEAM, lava -> STONE.
    assert grid.get(1, 1) == ElementId.STEAM
    assert grid.get(2, 1) == ElementId.STONE


def test_dormant_wood_next_to_fire_ignites() -> None:
    """A dormant (static) wood cell next to fire ignites to FIRE.

    Wood ignites when its OWN temp exceeds flashpoint (wood.py), so the wood
    cell MUST be scanned. Fire is a persistent heat source (wake 3) and clings
    to flammable neighbors (fire.py), so the wood stays awake across steps,
    heats via diffusion, and ignites. Pins that dormancy does not pin a cell
    that a heat source is actively heating.
    """
    _seed()
    width, height = 5, 4
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    grid.set(1, height - 2, ElementId.WOOD)  # static wood
    sim = Simulation(grid)

    for _ in range(5):
        sim.step()  # wood is static -> dormant
    assert grid.get(1, height - 2) == ElementId.WOOD
    assert not grid.active[height - 2, 1]  # wood dormant

    # Fire appears directly beside the dormant wood (paint_brush seeds fire life).
    paint_brush(grid, 2, height - 2, 0, ElementId.FIRE)

    # Fire clings to the flammable wood and heats it; once the wood's temp
    # crosses flashpoint it ignites. Detect the moment of ignition (the cell
    # becomes FIRE); robust to the fire later rising away.
    ignited = False
    for _ in range(60):
        sim.step()
        if grid.get(1, height - 2) == ElementId.FIRE:
            ignited = True
            break
    assert ignited, "dormant wood next to fire never ignited"


def test_painting_into_dormant_region_wakes_it() -> None:
    """Painting a cell into a dormant (empty) region wakes it so it is scanned.

    After a pile settles and the scene goes dormant, painting a single sand
    grain high above must mark it active (fill_circle) so the next step scans
    and drops it -- dormancy must not pin freshly painted cells.
    """
    _seed()
    width, height = 8, 8
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    for y in range(0, 2):
        grid.set(width // 2, y, ElementId.SAND)  # small pile
    sim = Simulation(grid)

    for _ in range(40):
        sim.step()  # pile settles -> dormant
    assert int((grid.array == int(ElementId.SAND)).sum()) == 2

    # Paint one sand grain at the top of the dormant region.
    grid.fill_circle(width // 2, 0, 0, ElementId.SAND)
    assert grid.active[0, width // 2]  # the brush woke it
    sim.step()

    # The painted grain was scanned and fell one row (dormancy did not pin it).
    assert grid.get(width // 2, 0) == ElementId.EMPTY
    assert grid.get(width // 2, 1) == ElementId.SAND

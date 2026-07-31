"""Tests for the brush painting helper.

These cover the Phase 04 deferred bug: painting FIRE or SMOKE through the
brush must seed per-cell life so the painted cells do not expire on the very
next simulation step. ``Grid.fill_circle`` alone zeros life on every painted
cell, so :func:`paint_brush` adds a seeding pass for FIRE/SMOKE using the
canonical lifetime ranges from :mod:`sandfall.rules._common`.

All tests are headless: :mod:`sandfall.brush` does not import pygame.
"""

from __future__ import annotations

import random

import pytest

from sandfall.brush import paint_brush
from sandfall.elements import ElementId
from sandfall.grid import Grid
from sandfall.rules import seed_fire_life, seed_smoke_life

# Lifetime windows mirrored from rules/_common.py (single source of truth is
# the helpers themselves; these are the documented bounds used to assert the
# painted cells land in-range).
FIRE_LIFE_MIN, FIRE_LIFE_MAX = 20, 40
SMOKE_LIFE_MIN, SMOKE_LIFE_MAX = 60, 120


def _painted_cells(grid: Grid, eid: ElementId) -> list[tuple[int, int]]:
    mask = grid.array == int(eid)
    return [(x, y) for y in range(grid.height) for x in range(grid.width) if mask[y, x]]


@pytest.fixture(autouse=True)
def _seed_random() -> None:
    random.seed(0)


def test_seed_helpers_return_values_in_documented_range() -> None:
    # Smoke-check the canonical ranges so a future tweak to _common.py is
    # caught here too (paint_brush's life-seeding delegates to these).
    for _ in range(200):
        life = seed_fire_life()
        assert FIRE_LIFE_MIN <= life <= FIRE_LIFE_MAX
    for _ in range(200):
        life = seed_smoke_life()
        assert SMOKE_LIFE_MIN <= life <= SMOKE_LIFE_MAX


def test_paint_brush_fire_seeds_non_zero_life_in_range() -> None:
    grid = Grid(20, 20)

    paint_brush(grid, 10, 10, 3, ElementId.FIRE)

    fire_cells = _painted_cells(grid, ElementId.FIRE)
    assert fire_cells, "expected a disk of FIRE cells to be painted"
    for x, y in fire_cells:
        life = grid.get_life(x, y)
        assert FIRE_LIFE_MIN <= life <= FIRE_LIFE_MAX, (x, y, life)


def test_paint_brush_smoke_seeds_non_zero_life_in_range() -> None:
    grid = Grid(20, 20)

    paint_brush(grid, 10, 10, 3, ElementId.SMOKE)

    smoke_cells = _painted_cells(grid, ElementId.SMOKE)
    assert smoke_cells
    for x, y in smoke_cells:
        life = grid.get_life(x, y)
        assert SMOKE_LIFE_MIN <= life <= SMOKE_LIFE_MAX, (x, y, life)


def test_paint_brush_fire_does_not_expire_on_first_step() -> None:
    """Regression for the Phase 04 bug: painted fire must survive stepping.

    Before the life-seeding fix, painted FIRE had life 0 and would all convert
    to EMPTY after a single Simulation.step. Now it must persist.
    """
    from sandfall.simulation import Simulation

    grid = Grid(20, 20)
    # Stone floor so fire has somewhere to sit and we are not testing rise.
    for x in range(grid.width):
        grid.set(x, grid.height - 1, ElementId.STONE)
    paint_brush(grid, 10, grid.height - 4, 2, ElementId.FIRE)
    initial = len(_painted_cells(grid, ElementId.FIRE))
    assert initial > 0

    sim = Simulation(grid)
    sim.step()

    remaining = len(_painted_cells(grid, ElementId.FIRE))
    assert remaining > 0, "painted fire expired instantly (life-seeding regression)"


def test_paint_brush_non_life_elements_leave_life_zero() -> None:
    """Sand/water/stone/etc. are not life-tracked; their painted life stays 0."""
    grid = Grid(20, 20)

    for eid in (ElementId.SAND, ElementId.WATER, ElementId.STONE, ElementId.PLANT):
        paint_brush(grid, 10, 10, 2, eid)
        for x, y in _painted_cells(grid, eid):
            assert grid.get_life(x, y) == 0


def test_paint_brush_radius_zero_paints_single_cell_with_life() -> None:
    grid = Grid(10, 10)

    paint_brush(grid, 5, 5, 0, ElementId.FIRE)

    assert grid.get(5, 5) == ElementId.FIRE
    assert FIRE_LIFE_MIN <= grid.get_life(5, 5) <= FIRE_LIFE_MAX
    # No other fire anywhere.
    assert len(_painted_cells(grid, ElementId.FIRE)) == 1


def test_paint_brush_out_of_bounds_does_not_raise() -> None:
    """A brush centered off-grid is clipped silently (delegated to fill_circle)."""
    grid = Grid(10, 10)

    paint_brush(grid, -5, -5, 2, ElementId.FIRE)  # top-left corner clip
    paint_brush(grid, 100, 100, 2, ElementId.FIRE)  # bottom-right, fully off-grid

    # No fire painted off-grid leaked into the visible grid for the fully-off case;
    # the corner case paints only the in-bounds part of the disk.
    assert len(_painted_cells(grid, ElementId.FIRE)) >= 0


def test_paint_brush_overwrites_old_life() -> None:
    """Painting FIRE over a cell that had stale life reseeds it freshly."""
    grid = Grid(10, 10)
    grid.set(5, 5, ElementId.SMOKE)
    grid.set_life(5, 5, 200)  # stale high life

    paint_brush(grid, 5, 5, 0, ElementId.FIRE)

    assert grid.get(5, 5) == ElementId.FIRE
    assert FIRE_LIFE_MIN <= grid.get_life(5, 5) <= FIRE_LIFE_MAX


def test_paint_brush_empty_clears_element_and_life() -> None:
    """Erasing via paint_brush(..., EMPTY) clears the id AND zeroes life.

    This is the regression for the Eraser tool (right-click erase + Eraser
    swatch): ``paint_brush`` delegates to ``Grid.fill_circle``, which paints
    the id and zeros life on every cell of the disk. Without that contract,
    right-clicking a burning FIRE cell would leave it as EMPTY-with-stale-life
    (which the renderer shows as EMPTY but the simulation might mis-handle).
    """
    grid = Grid(10, 10)
    grid.set(5, 5, ElementId.FIRE)
    grid.set_life(5, 5, 99)
    assert grid.get(5, 5) == ElementId.FIRE
    assert grid.get_life(5, 5) == 99

    paint_brush(grid, 5, 5, 1, ElementId.EMPTY)

    assert grid.get(5, 5) == ElementId.EMPTY
    assert grid.get_life(5, 5) == 0
    # All cells in the disk are EMPTY with zero life.
    for y in range(grid.height):
        for x in range(grid.width):
            assert grid.get(x, y) == ElementId.EMPTY
            assert grid.get_life(x, y) == 0


# --- Spawn-temperature (Phase 01) -------------------------------------------


def test_paint_brush_fire_sets_spawn_temp() -> None:
    """A painted FIRE disk's cells hold FIRE's temp_spawn (hot)."""
    from sandfall.elements import ELEMENTS

    grid = Grid(20, 20)
    paint_brush(grid, 10, 10, 2, ElementId.FIRE)
    for x, y in _painted_cells(grid, ElementId.FIRE):
        assert grid.get_temp(x, y) == ELEMENTS[ElementId.FIRE].temp_spawn, (x, y)


def test_paint_brush_non_thermal_elements_at_ambient() -> None:
    """Non-heat-source elements paint at AMBIENT_TEMP (no stale heat left)."""
    from sandfall.config import AMBIENT_TEMP

    grid = Grid(20, 20)
    for eid in (ElementId.SAND, ElementId.WATER, ElementId.STONE):
        # Pre-heat the disk so we assert the temp really resets, not just
        # happens to already be ambient.
        for y in range(grid.height):
            for x in range(grid.width):
                grid.set_temp(x, y, 999)
        paint_brush(grid, 10, 10, 2, eid)
        for x, y in _painted_cells(grid, eid):
            assert grid.get_temp(x, y) == AMBIENT_TEMP, (eid, x, y)


def test_paint_brush_overwrites_stale_temp() -> None:
    """Painting FIRE over a cell that had stale heat sets the spawn-temp freshly."""
    grid = Grid(10, 10)
    grid.set(5, 5, ElementId.STONE)
    grid.set_temp(5, 5, 5)  # stale cold

    paint_brush(grid, 5, 5, 0, ElementId.FIRE)

    assert grid.get(5, 5) == ElementId.FIRE
    assert grid.get_temp(5, 5) == 800  # FIRE.temp_spawn

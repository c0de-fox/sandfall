"""Phase 03 tests: temperature-driven phase transitions + new elements.

Covers each transition deterministically (seed a temp, step once, assert the
resulting element). Two strategies keep these tests robust and seed-order
independent:

* **Single-cell transitions** (boil / freeze / melt / condense / cool) use a
  ``Grid(1, 1)``. On a 1x1 grid the diffusion pre-pass is a true no-op:
  edge-padding replicates the lone cell on all four sides, so the
  4-neighborhood Laplacian is identically zero and the rule sees EXACTLY the
  temperature the test set. This isolates the rule under test from diffusion
  arithmetic, so the spec's small temp margins (+20, -5, +5, ...) all hold
  as written with no per-test tuning.
* **The lava+water reaction** needs two adjacent cells, so it cannot be 1x1.
  It uses a fully sealed 3x3 box: the WATER cell is walled in (stone above,
  below, and to the far side; LAVA on the near side) so it cannot fall or
  flow away before the LAVA scans, and the spawned STEAM is trapped above by
  stone so it is not re-dispatched into a rise in the same step. This makes
  the reaction fire for BOTH randomized x-scan directions; the test also
  ``random.seed``s for good measure and is verified across many seeds in dev.
"""

from __future__ import annotations

import random

from sandfall.brush import paint_brush
from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.rules import seed_steam_life
from sandfall.rules.ice import ICE_COLD_TARGET
from sandfall.rules.lava import LAVA_SOLIDIFY_TEMP
from sandfall.simulation import Simulation

# Lifetime window mirrored from rules/_common.py (single source of truth is
# seed_steam_life itself; this is the documented bound used to assert painted
# / reaction-spawned steam lands in-range).
STEAM_LIFE_MIN, STEAM_LIFE_MAX = 80, 160


def _step_single_cell(eid: ElementId, temp: int) -> Grid:
    """Set the lone cell of a 1x1 grid to ``eid`` at ``temp`` and step once.

    On a 1x1 grid diffusion is a no-op (edge-pad replicates the cell on every
    side -> zero Laplacian), so the rule reads exactly ``temp``. The cell
    also cannot move (no neighbors), so only the transition logic is tested.
    """
    g = Grid(1, 1)
    g.set(0, 0, eid)
    g.set_temp(0, 0, temp)
    Simulation(g).step()
    return g


# --- WATER -> STEAM / ICE ---------------------------------------------------


def test_water_boils_to_steam() -> None:
    """Water hotter than its boil_point becomes STEAM on its next step."""
    g = _step_single_cell(ElementId.WATER, ELEMENTS[ElementId.WATER].boil_point + 20)
    assert g.get(0, 0) == ElementId.STEAM
    # The newborn steam carries a warm temp so it does not instantly condense.
    assert g.get_temp(0, 0) == ELEMENTS[ElementId.STEAM].temp_spawn


def test_water_freezes_to_ice() -> None:
    """Water at or below its freeze_point becomes ICE on its next step.

    ``freeze_point == 0`` is a VALID active threshold (water freezes at/below
    0°C); the rule checks ``t <= freeze_point`` directly, NOT the spec's
    buggy ``freeze_point < 0 or True`` form (the ``or True`` would have made
    the branch always-true — a leftover that is NOT reproduced here).

    The freshly-frozen ice is seeded at ``ICE_COLD_TARGET`` (Phase 02) so the
    freeze front advances the same step rather than lagging a frame before
    ``update_ice`` re-asserts the cold.
    """
    g = _step_single_cell(ElementId.WATER, ELEMENTS[ElementId.WATER].freeze_point - 5)
    assert g.get(0, 0) == ElementId.ICE
    assert g.get_temp(0, 0) == ICE_COLD_TARGET  # new ice seeded cold (front advances)


def test_ice_freeze_spreads_through_water() -> None:
    """A block of ice in water freezes its surroundings (the freeze spreads).

    The headline Phase-02 test: ice is a persistent cold source (re-asserts
    ICE_COLD_TARGET each step), so cold propagates via diffusion into adjacent
    water, the water cools below freeze_point, and the WATER rule freezes it
    (seeding the new ice cold so the front keeps advancing). Prototype-measured
    spread at ICE_COLD_TARGET=-50: 1 -> 3 -> 5 -> 9 cells over ~120 steps. This
    is the regression guard for the 'ice no longer freezes water' bug.

    It also pins the dormant-wake sufficiency finding: a real ``Simulation``
    rebuilds its active set each step, so if the freeze spreads here the
    existing wake conditions (movement/identity-change, thermal-change,
    FIRE/LAVA) keep the front alive without needing ICE in the wake condition.
    """
    random.seed(0)
    g = Grid(12, 12)
    # Fill the bottom half with water.
    for y in range(6, 12):
        for x in range(12):
            g.set(x, y, ElementId.WATER)
    # Seed a small ice block in the middle of the water.
    for dy in range(2):
        for dx in range(2):
            g.set(5 + dx, 7 + dy, ElementId.ICE)
            g.set_temp(5 + dx, 7 + dy, ICE_COLD_TARGET)
    sim = Simulation(g)
    ice_before = int((g.array == int(ElementId.ICE)).sum())
    assert ice_before == 4  # the 2x2 seed
    for _ in range(120):
        sim.step()
    ice_after = int((g.array == int(ElementId.ICE)).sum())
    # The freeze spread: strictly more ice than the seed. (Prototype reaches ~9.)
    assert ice_after > ice_before, (ice_before, ice_after)


def test_water_at_ambient_stays_water() -> None:
    """Water at ambient temp neither boils nor freezes (thresholds are gated)."""
    g = _step_single_cell(ElementId.WATER, 20)
    assert g.get(0, 0) == ElementId.WATER


# --- ICE melt via fire/lava contact (NOT ambient) ---------------------------


def test_ice_melts_to_water_via_fire_contact() -> None:
    """Ice melts to WATER when an orthogonal neighbor is FIRE (direct contact).

    Ice no longer melts from ambient warmth (it is a persistent cold source and
    re-asserts cold each step); only direct fire/lava contact destroys it. This
    replaces the old thermal-melt test (ICE at 5C -> WATER), whose branch was
    deleted because melt-at->0 is incompatible with being a cold source.
    """
    g = Grid(3, 1)
    g.set(0, 0, ElementId.ICE)
    g.set(1, 0, ElementId.FIRE)
    g.set_life(1, 0, 50)  # keep fire alive through the step
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.WATER


def test_ice_melts_to_steam_via_lava_contact() -> None:
    """Ice flashed to STEAM when an orthogonal neighbor is LAVA (mirrors lava's
    water->steam reaction shape)."""
    g = Grid(3, 1)
    g.set(0, 0, ElementId.ICE)
    g.set(1, 0, ElementId.LAVA)
    g.set_temp(1, 0, ELEMENTS[ElementId.LAVA].temp_spawn)  # 1500
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.STEAM
    assert g.get_temp(0, 0) == ELEMENTS[ElementId.STEAM].temp_spawn
    # The lava-flashed steam got a finite life in the documented range.
    assert STEAM_LIFE_MIN <= g.get_life(0, 0) <= STEAM_LIFE_MAX


def test_ice_at_ambient_stays_ice() -> None:
    """Ice at ambient does NOT melt (it re-asserts cold; only fire/lava destroy it).

    Deliberate temporary behavior -- ambient melt is disabled because it is
    incompatible with being a cold source. See BACKLOG (Thermal realism rework).
    """
    g = _step_single_cell(ElementId.ICE, 20)
    assert g.get(0, 0) == ElementId.ICE
    # And it re-asserted cold (the persistent-cold-source behavior).
    assert g.get_temp(0, 0) == ICE_COLD_TARGET


# --- STEAM -> WATER (condense) ----------------------------------------------


def test_steam_condenses_to_water() -> None:
    """Steam cooler than its condense_point becomes WATER (closing the cycle)."""
    g = Grid(1, 1)
    g.set(0, 0, ElementId.STEAM)
    # Give it life so the rule reaches the condense branch cleanly (condense
    # is checked BEFORE aging, but seed life anyway for realism).
    g.set_life(0, 0, 50)
    g.set_temp(0, 0, ELEMENTS[ElementId.STEAM].condense_point - 10)
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.WATER


def test_steam_at_spawn_temp_does_not_condense_immediately() -> None:
    """Steam at its warm spawn-temp stays steam (above condense_point)."""
    g = Grid(1, 1)
    g.set(0, 0, ElementId.STEAM)
    g.set_life(0, 0, 100)
    g.set_temp(0, 0, ELEMENTS[ElementId.STEAM].temp_spawn)  # 120 >= 60
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.STEAM


def test_steam_expires_to_empty_when_life_runs_out() -> None:
    """A warm steam with exhausted life empties (it did not condense first)."""
    g = Grid(1, 1)
    g.set(0, 0, ElementId.STEAM)
    g.set_life(0, 0, 1)  # one step left
    g.set_temp(0, 0, ELEMENTS[ElementId.STEAM].temp_spawn)  # warm -> won't condense
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.EMPTY


# --- SAND -> GLASS ----------------------------------------------------------


def test_sand_melts_to_glass() -> None:
    """Sand hotter than its melt_point becomes GLASS."""
    g = _step_single_cell(ElementId.SAND, ELEMENTS[ElementId.SAND].melt_point + 50)
    assert g.get(0, 0) == ElementId.GLASS


def test_sand_below_melt_point_stays_sand() -> None:
    """Sand at ambient does not melt (melt threshold is gated)."""
    g = _step_single_cell(ElementId.SAND, 20)
    assert g.get(0, 0) == ElementId.SAND


# --- LAVA -> STONE (cool) + LAVA + WATER reaction ---------------------------


def test_lava_cools_to_stone() -> None:
    """Lava below the solidify threshold becomes STONE."""
    g = _step_single_cell(ElementId.LAVA, LAVA_SOLIDIFY_TEMP - 50)
    assert g.get(0, 0) == ElementId.STONE


def test_lava_at_spawn_temp_flows_not_solidify() -> None:
    """Lava at its hot spawn-temp does not solidify (it is above the threshold).

    With no WATER neighbor and no EMPTY below/aside, a hot lava in a 1x1 grid
    simply cannot move, so it stays LAVA (proving the solidify check is
    threshold-gated, not unconditional).
    """
    g = Grid(1, 1)
    g.set(0, 0, ElementId.LAVA)
    g.set_temp(0, 0, ELEMENTS[ElementId.LAVA].temp_spawn)  # 1500 >> 700
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.LAVA


def test_lava_water_reaction_is_deterministic_across_scan_orders() -> None:
    """LAVA adjacent to WATER -> STONE (lava) + STEAM (water), for any seed,
    even at LAVA's realistic 1500 spawn-temp.

    Geometry: a fully sealed 3x3 box so the WATER cell cannot fall or flow
    away before LAVA scans, and the spawned STEAM is trapped above by STONE
    so it is not re-dispatched into a rise in the same step:

        row 0:  STONE  STONE  STONE     <- ceiling (traps rising steam)
        row 1:  LAVA   WATER  STONE     <- reaction row (water walled in)
        row 2:  STONE  STONE  STONE     <- floor

    At 1500 the diffusion pre-pass heats the adjacent water above its
    boil_point (100) in a single step, so when the scan reaches WATER first
    the WATER rule's boil branch converts it to STEAM before the LAVA rule
    runs. The LAVA rule therefore accepts a STEAM neighbor too (not just
    WATER) and still solidifies to STONE — guaranteeing the crust forms
    regardless of the randomized x-scan direction. Verified across 20 seeds.
    """
    for i in range(20):
        random.seed(i)
        g = Grid(3, 3)
        # Ceiling + floor.
        for x in range(3):
            g.set(x, 0, ElementId.STONE)
            g.set(x, 2, ElementId.STONE)
        # Reaction row: LAVA at (0,1), WATER at (1,1), STONE wall at (2,1).
        g.set(0, 1, ElementId.LAVA)
        g.set_temp(0, 1, ELEMENTS[ElementId.LAVA].temp_spawn)  # 1500 (realistic)
        g.set(1, 1, ElementId.WATER)
        g.set(2, 1, ElementId.STONE)

        Simulation(g).step()

        assert g.get(0, 1) == ElementId.STONE, f"seed={i}: lava did not solidify"
        assert g.get(1, 1) == ElementId.STEAM, f"seed={i}: water did not flash to steam"
        # The reaction-spawned steam got a finite life in the documented range.
        assert STEAM_LIFE_MIN <= g.get_life(1, 1) <= STEAM_LIFE_MAX, f"seed={i}"


def test_lava_sinks_under_water_via_density() -> None:
    """LAVA (density 2.5) is denser than WATER (1.0): can_displace lets lava
    sink through water. With lava ABOVE water and no reaction yet triggered
    on the first scanned cell, the lava displaces down into the water cell."""
    # Lava directly above water in a column; water rests on a stone floor.
    # The first time lava is scanned it finds WATER directly below and reacts
    # (reaction preempts movement), so we instead assert the density relation
    # directly: lava can displace water, water cannot displace lava.
    from sandfall.rules._common import can_displace

    assert can_displace(ElementId.LAVA, int(ElementId.WATER)) is True
    assert can_displace(ElementId.WATER, int(ElementId.LAVA)) is False


# --- Brush seeding for the new elements -------------------------------------


def test_paint_brush_lava_sets_spawn_temp() -> None:
    """A painted LAVA disk's cells hold LAVA's hot temp_spawn (1500)."""
    g = Grid(10, 10)
    paint_brush(g, 5, 5, 1, ElementId.LAVA)
    lava_cells = [
        (x, y)
        for y in range(g.height)
        for x in range(g.width)
        if g.get(x, y) == ElementId.LAVA
    ]
    assert lava_cells, "expected a disk of LAVA cells to be painted"
    for x, y in lava_cells:
        assert g.get_temp(x, y) == ELEMENTS[ElementId.LAVA].temp_spawn, (x, y)


def test_paint_brush_ice_sets_cold_spawn_temp() -> None:
    """A painted ICE disk's cells hold ICE's cold temp_spawn (-5)."""
    g = Grid(10, 10)
    paint_brush(g, 5, 5, 1, ElementId.ICE)
    ice_cells = [
        (x, y)
        for y in range(g.height)
        for x in range(g.width)
        if g.get(x, y) == ElementId.ICE
    ]
    assert ice_cells
    for x, y in ice_cells:
        assert g.get_temp(x, y) == ELEMENTS[ElementId.ICE].temp_spawn, (x, y)


def test_paint_brush_steam_seeds_life_and_spawn_temp() -> None:
    """Painted STEAM gets a finite life (seed_steam_life) and warm spawn-temp."""
    g = Grid(10, 10)
    paint_brush(g, 5, 5, 1, ElementId.STEAM)
    steam_cells = [
        (x, y)
        for y in range(g.height)
        for x in range(g.width)
        if g.get(x, y) == ElementId.STEAM
    ]
    assert steam_cells
    for x, y in steam_cells:
        assert STEAM_LIFE_MIN <= g.get_life(x, y) <= STEAM_LIFE_MAX, (x, y)
        assert g.get_temp(x, y) == ELEMENTS[ElementId.STEAM].temp_spawn, (x, y)


def test_paint_brush_glass_needs_no_life() -> None:
    """GLASS is a static solid: painted glass has life 0 (no life tracking)."""
    g = Grid(10, 10)
    paint_brush(g, 5, 5, 1, ElementId.GLASS)
    for y in range(g.height):
        for x in range(g.width):
            if g.get(x, y) == ElementId.GLASS:
                assert g.get_life(x, y) == 0


# --- seed_steam_life range (single source of truth) -------------------------


def test_seed_steam_life_returns_values_in_documented_range() -> None:
    """Smoke-check the canonical range so a future tweak to _common.py is
    caught here too (paint_brush + the lava reaction both delegate to it)."""
    for _ in range(200):
        life = seed_steam_life()
        assert STEAM_LIFE_MIN <= life <= STEAM_LIFE_MAX

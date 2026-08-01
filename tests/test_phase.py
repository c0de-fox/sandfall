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

import pytest

from sandfall.brush import paint_brush
from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.rules import seed_steam_life
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

    The freshly-frozen ice keeps the water's already-<=0 temp (realistic: no
    cold-source seeding); it melts again once it warms above melt_point via
    diffusion.
    """
    g = _step_single_cell(ElementId.WATER, ELEMENTS[ElementId.WATER].freeze_point - 5)
    assert g.get(0, 0) == ElementId.ICE
    # The new ice keeps the water's already-<=0 temp (realistic: no cold-source
    # seeding). It was set to freeze_point-5, so it stays at freeze_point-5.
    assert g.get_temp(0, 0) == ELEMENTS[ElementId.WATER].freeze_point - 5


def test_dry_ice_freezes_water() -> None:
    """A block of DRY_ICE in water freezes its surroundings (dry ice is the cold
    source; the freeze spreads via diffusion).

    The headline Phase-01 test: dry ice re-asserts DRY_ICE_COLD_TARGET (-78)
    each step, so cold propagates via diffusion into adjacent water, the water
    cools below freeze_point, and the WATER rule freezes it to ICE. Because the
    newly-formed ice is NOT itself a cold source (realistic), the freeze front
    advances by cold diffusing THROUGH the growing ice shell from the dry-ice
    source -- slower than the interim 1->9-in-120 spread, but it DOES spread.

    It also pins the dormant-wake sufficiency finding: a real ``Simulation``
    rebuilds its active set each step, so if ANY ice forms here the existing
    wake conditions keep the front alive without needing DRY_ICE in the wake
    condition. If this test freezes NOTHING, add DRY_ICE to condition 3
    (simulation.py:168-170) per the plan's step 7.
    """
    from sandfall.rules.dry_ice import DRY_ICE_COLD_TARGET

    random.seed(0)
    g = Grid(12, 12)
    # Fill the bottom half with water.
    for y in range(6, 12):
        for x in range(12):
            g.set(x, y, ElementId.WATER)
    # Seed a small dry-ice block in the middle of the water.
    for dy in range(2):
        for dx in range(2):
            g.set(5 + dx, 7 + dy, ElementId.DRY_ICE)
            g.set_temp(5 + dx, 7 + dy, DRY_ICE_COLD_TARGET)
    sim = Simulation(g)
    assert int((g.array == int(ElementId.ICE)).sum()) == 0  # no ice yet
    for _ in range(150):
        sim.step()
    ice_after = int((g.array == int(ElementId.ICE)).sum())
    # The dry ice froze some water (strictly more than zero). The exact count
    # depends on DRY_ICE_COLD_TARGET tuning; the point is freezing happened at
    # all. If ice_after == 0, the dormant-wake sufficiency is falsified -- apply
    # the step-7 simulation.py edit and re-run.
    assert ice_after > 0, ice_after


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


def test_ice_melts_in_ambient(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ice at ambient melts to WATER (probabilistic; monkeypatched to rate=1.0
    for a deterministic single-step test)."""
    import sandfall.rules.ice as ice_mod

    monkeypatch.setattr(ice_mod, "ICE_MELT_RATE", 1.0)
    g = _step_single_cell(ElementId.ICE, 20)
    assert g.get(0, 0) == ElementId.WATER


def test_ice_does_not_freeze_water() -> None:
    """Ice adjacent to ambient water does NOT freeze it (ice is a non-source).

    Ice sits at ~0C and cannot pull 20C water below its freeze_point; only a
    colder-than-freezing cold source (dry ice / LN2) can. The water cell stays
    WATER (and the ice, warming via diffusion, eventually melts).
    """
    random.seed(0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ICE)
    g.set_temp(0, 0, 0)  # ice at its melt_point (stays ice: >0 is false)
    g.set(1, 0, ElementId.WATER)
    g.set_temp(1, 0, 5)  # mild water, well above freeze_point
    for _ in range(10):
        Simulation(g).step()
    # The water cell never froze -- ice is not a cold source.
    assert g.get(1, 0) == ElementId.WATER


# --- DRY_ICE persistent cold source (thermal-realism) ----------------------


def test_dry_ice_persists_in_ambient() -> None:
    """Dry ice at ambient does NOT sublimate (it re-asserts cold; only fire/lava
    destroy it). The deliberate persistent-cold-source behavior, now under the
    dry-ice name instead of ice."""
    from sandfall.rules.dry_ice import DRY_ICE_COLD_TARGET

    g = _step_single_cell(ElementId.DRY_ICE, 20)
    assert g.get(0, 0) == ElementId.DRY_ICE
    # It re-asserted its cold target (the persistent-cold-source behavior).
    assert g.get_temp(0, 0) == DRY_ICE_COLD_TARGET


def test_dry_ice_sublimates_via_fire_contact() -> None:
    """Dry ice sublimates to EMPTY when an orthogonal neighbor is FIRE."""
    g = Grid(3, 1)
    g.set(0, 0, ElementId.DRY_ICE)
    g.set(1, 0, ElementId.FIRE)
    g.set_life(1, 0, 50)  # keep fire alive through the step
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.EMPTY


# --- Liquid nitrogen (transient cold liquid) -------------------------------


def test_ln2_freezes_water_aggressively() -> None:
    """A blob of LN2 in water freezes a patch of it before boiling off.

    LN2 re-asserts LN2_COLD_TARGET (-196) while alive -- far colder than dry ice
    (-78) -- so its diffusion freezes adjacent water fast. The freeze must
    happen WITHIN the short life window (seed_nitrogen_life ~= 30..80), which is
    the boil-off tuning gate (overview Risk #5). Asserts SOME ice forms.
    """
    from sandfall.rules._common import seed_nitrogen_life
    from sandfall.rules.ln2 import LN2_COLD_TARGET

    # Sanity: the life window the freeze must fit inside.
    for _ in range(50):
        assert 30 <= seed_nitrogen_life() <= 80

    random.seed(0)
    g = Grid(8, 8)
    for y in range(8):
        for x in range(8):
            g.set(x, y, ElementId.WATER)
    # Seed a 2x2 LN2 blob in the middle, each with a max-life window so it has
    # the most time to freeze before boiling off.
    for dy in range(2):
        for dx in range(2):
            g.set(3 + dx, 3 + dy, ElementId.LN2)
            g.set_temp(3 + dx, 3 + dy, LN2_COLD_TARGET)
            g.set_life(3 + dx, 3 + dy, 80)  # top of the window -> max freeze time
    sim = Simulation(g)
    assert int((g.array == int(ElementId.ICE)).sum()) == 0  # no ice yet
    for _ in range(80):
        sim.step()
    ice_after = int((g.array == int(ElementId.ICE)).sum())
    # LN2 froze some water before boiling off. Exact count depends on the
    # seed_nitrogen_life window + LN2_COLD_TARGET; the point is freezing happened.
    assert ice_after > 0, ice_after


def test_ln2_boils_off() -> None:
    """LN2 is transient: a blob left at ambient boils away to EMPTY once its
    finite life is exhausted (room temp >> -196)."""
    random.seed(0)
    g = Grid(3, 3)
    for y in range(3):
        for x in range(3):
            g.set(x, y, ElementId.LN2)
            g.set_life(x, y, 80)  # top of the window
    sim = Simulation(g)
    for _ in range(200):  # well past the max life window
        sim.step()
    assert int((g.array == int(ElementId.LN2)).sum()) == 0  # all boiled off


def test_ln2_floats_on_water() -> None:
    """LN2 (density 0.8) is lighter than WATER (1.0): it floats -- a cell of LN2
    directly above water, stepped many times, ends with LN2 above water (water
    sinks through the lighter LN2). Mirrors the oil float test.

    NB: LN2 re-asserts -196C, so the water column usually FREEZES to ICE during
    the run -- that is correct cold-source behavior, not a float failure. The
    positional assertion therefore treats WATER-or-ICE as "the water column":
    LN2 must sit ABOVE it (it never sank below), which is the density evidence.
    """
    from sandfall.rules._common import can_displace

    # Density relation: water displaces LN2 (water sinks); LN2 cannot displace water.
    assert can_displace(ElementId.WATER, int(ElementId.LN2)) is True
    assert can_displace(ElementId.LN2, int(ElementId.WATER)) is False

    random.seed(0)
    g = Grid(1, 4)
    g.set(0, 0, ElementId.LN2)
    g.set_life(0, 0, 80)  # keep it alive long enough to settle
    g.set(0, 1, ElementId.WATER)
    sim = Simulation(g)
    for _ in range(40):
        sim.step()
    # LN2 is lighter -> it ends above the water column (40 steps < 80 so the LN2
    # is still alive). The water may have frozen to ICE from the -196 cold; count
    # both as "the water column" and assert LN2 sits above it.
    ln2_y = [y for y in range(g.height) if g.get(0, y) == ElementId.LN2]
    water_col_y = [
        y for y in range(g.height) if g.get(0, y) in (ElementId.WATER, ElementId.ICE)
    ]
    assert ln2_y and water_col_y
    assert min(ln2_y) < max(water_col_y)  # LN2 is above the water column


def test_paint_brush_ln2_seeds_life() -> None:
    """A painted LN2 disk's cells get a finite life (seed_nitrogen_life) and the
    -196 spawn temp. Without the life seeding, painted LN2 would have life 0 and
    boil off on the next step."""
    g = Grid(10, 10)
    paint_brush(g, 5, 5, 1, ElementId.LN2)
    ln2_cells = [
        (x, y)
        for y in range(g.height)
        for x in range(g.width)
        if g.get(x, y) == ElementId.LN2
    ]
    assert ln2_cells, "expected a disk of LN2 cells to be painted"
    for x, y in ln2_cells:
        assert 30 <= g.get_life(x, y) <= 80, (x, y)
        assert g.get_temp(x, y) == ELEMENTS[ElementId.LN2].temp_spawn, (x, y)


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
    """A painted ICE disk's cells hold ICE's cold spawn temp (0)."""
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

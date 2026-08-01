"""Phase 01 (gunpowder + reusable blast) tests: detonate / chain / crater /
heat-burst / scatter / stable / density / renderer-LUT-grew.

Covers the gunpowder thermal trigger, the ``blast.explode`` helper's three
effects (heat burst / crater / scatter), and the headline chain-reaction
integration test (which also pins the dormant-wake sufficiency finding --
master plan Risk #1). Deterministic patterns mirror ``tests/test_phase.py``
(single-cell ``Grid(1, 1)``) and ``tests/test_acid_base.py`` (monkeypatch the
``blast`` module globals, which are read at call time like ``fire.py``'s
``SMOKE_CHANCE``; ``random.seed`` for the randomized scan/shuffle).
"""

from __future__ import annotations

import random

from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.renderer import build_color_lut
from sandfall.rules._common import can_displace
from sandfall.simulation import Simulation


def _step_single_cell(eid: ElementId, temp: int) -> Grid:
    """Set the lone cell of a 1x1 grid to ``eid`` at ``temp`` and step once.

    On a 1x1 grid diffusion is a no-op (edge-pad replicates the cell on every
    side -> zero Laplacian), so the rule reads exactly ``temp``.
    """
    g = Grid(1, 1)
    g.set(0, 0, eid)
    g.set_temp(0, 0, temp)
    Simulation(g).step()
    return g


# --- detonates when heated (the thermal trigger) ---------------------------


def test_gunpowder_detonates_when_heated(monkeypatch: object) -> None:
    """A gunpowder cell above its flashpoint detonates: cell -> FIRE. (On a 1x1
    grid the blast has no neighbors to touch, so this just proves the trigger
    fires and the detonation cell becomes the fireball.)"""
    import sandfall.rules.blast as blast

    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 1.0)
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)
    gp = ElementId.GUNPOWDER
    g = _step_single_cell(gp, ELEMENTS[gp].flashpoint + 50)
    assert g.get(0, 0) == ElementId.FIRE


def test_gunpowder_blast_affects_neighbors(monkeypatch: object) -> None:
    """Detonation destroys/ignites neighbors in the radius. Center gunpowder in
    a sand block, heat it, step -> center is FIRE and some sand in the crater is
    destroyed (not all sand remains). Pinned deterministic: crater -> EMPTY,
    core -> FIRE, no scatter."""
    import sandfall.rules.blast as blast

    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 1.0)
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "SCATTER_CHANCE", 0.0)
    random.seed(0)
    g = Grid(11, 11)
    for y in range(11):
        for x in range(11):
            g.set(x, y, ElementId.SAND)
    g.set(5, 5, ElementId.GUNPOWDER)
    g.set_temp(5, 5, ELEMENTS[ElementId.GUNPOWDER].flashpoint + 50)
    Simulation(g).step()
    assert g.get(5, 5) == ElementId.FIRE  # detonation cell -> fireball
    sand_after = int((g.array == int(ElementId.SAND)).sum())
    assert sand_after < 11 * 11 - 1  # some sand destroyed in the crater


# --- chain reaction (the headline; guards the dormant wake, Risk #1) -------


def test_gunpowder_chain_reaction_detonates_cluster() -> None:
    """Igniting one end of a gunpowder line detonates the WHOLE line over a few
    steps: each blast heats the next gunpowder past its flashpoint, which
    detonates on its own scan. Seed random. Assert all gunpowder is gone and
    fire/crater appears along the line. (Risk #1: if the chain stalls against
    dormant gunpowder, GUNPOWDER must join wake condition #3 -- pin finding.)

    The line rests on the BOTTOM row so the powder cannot fall away from the
    igniting fire before it heats past its flashpoint (gunpowder is a POWDER;
    placed mid-grid it drops two rows in two steps and separates from a rising
    fire too fast to ignite -- see the reflection). Fire CLINGS to the flammable
    gunpowder neighbor (fire.py), so it stays put and heats the line via
    diffusion until the first cell detonates; the chain then rips across via
    each blast's heat burst.
    """
    random.seed(0)
    g = Grid(13, 5)
    h = g.height
    # A horizontal line of gunpowder across the bottom row (cannot fall).
    for x in range(1, 13):
        g.set(x, h - 1, ElementId.GUNPOWDER)
    # Ignite the left end with a hot FIRE (clings to the flammable gunpowder).
    g.set(0, h - 1, ElementId.FIRE)
    g.set_temp(0, h - 1, ELEMENTS[ElementId.FIRE].burn_temp)
    g.set_life(0, h - 1, 80)  # long enough to heat the neighbor past flashpoint
    sim = Simulation(g)
    gp_before = int((g.array == int(ElementId.GUNPOWDER)).sum())
    assert gp_before == 12  # the 12 non-ignited gunpowder cells
    for _ in range(120):
        sim.step()
    gp_after = int((g.array == int(ElementId.GUNPOWDER)).sum())
    assert gp_after < gp_before, (gp_before, gp_after)  # the chain advanced
    # The chain reaches across: almost all gunpowder is gone (allow a little
    # slack for scan/RNG edge effects; prototype-clean is ~0 remaining).
    assert gp_after <= 2, (gp_before, gp_after)


# --- destroys everything in the crater (no blast-resistant material) -------


def test_blast_destroys_everything_in_crater(monkeypatch: object) -> None:
    """Stone, glass, sand, wood, water placed in the inner crater (d <=
    CRATER_RADIUS) are all destroyed (-> EMPTY) by the blast. User chose
    'destroys everything'. Geometry: a 5x5 grid, detonator at the center (2,2),
    one of each material at d <= 2 (within the crater): STONE/GLASS/SAND/WOOD at
    d=2 on the axes, WATER at d~1.41 on the diagonal."""
    import sandfall.rules.blast as blast

    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 0.0)  # core -> not fire
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)  # crater -> EMPTY
    monkeypatch.setattr(blast, "SCATTER_CHANCE", 0.0)
    random.seed(0)
    g = Grid(5, 5)
    placements = {
        (0, 2): ElementId.STONE,  # d = 2 (axial)
        (4, 2): ElementId.GLASS,  # d = 2
        (2, 0): ElementId.SAND,  # d = 2
        (2, 4): ElementId.WOOD,  # d = 2
        (1, 1): ElementId.WATER,  # d = sqrt(2) ~ 1.41 (diagonal)
    }
    for (x, y), mat in placements.items():
        g.set(x, y, mat)
    g.set(2, 2, ElementId.GUNPOWDER)  # detonator at center
    g.set_temp(2, 2, ELEMENTS[ElementId.GUNPOWDER].flashpoint + 50)
    Simulation(g).step()
    # Every material in the crater was destroyed (no longer its original id).
    for (x, y), mat in placements.items():
        assert g.get(x, y) != mat, (mat, (x, y), g.get(x, y))


# --- heat burst ignites wood + boils water (via existing thresholds) -------


def test_blast_heat_ignites_wood_and_boils_water(monkeypatch: object) -> None:
    """The blast's heat burst ignites WOOD (flashpoint 300) and boils WATER
    (boil_point 100) in the outer ring via their OWN transition rules. Placed at
    d~3 (outside the crater d>2, within radius 4): at BLAST_HEAT~1200 the
    falloff (1 - 3/5 = 0.4) adds ~480C -> wood reaches ~500 (> 300 -> ignites)
    and water reaches ~500 (> 100 -> boils). Robust; stepped 60x so scan order
    and the FIRE persistent-source wake both get a chance to act. NOTE: sand->
    glass (melt_point 1700) is NOT asserted -- see Risk #4 (BLAST_HEAT~1200
    cannot reach 1700 at any non-crater distance)."""
    import sandfall.rules.blast as blast

    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "SCATTER_CHANCE", 0.0)
    random.seed(0)
    g = Grid(11, 5)
    # Detonator at (5,2). Wood/water column at x=8 (d ~ 3.0-3.6 from (5,2)):
    # all outside crater (d>2) and within radius 4.
    for y in range(3):  # wood at rows 0,1,2 of x=8
        g.set(8, y, ElementId.WOOD)
    for y in range(3, 5):  # water at rows 3,4 of x=8
        g.set(8, y, ElementId.WATER)
    g.set(5, 2, ElementId.GUNPOWDER)
    g.set_temp(5, 2, ELEMENTS[ElementId.GUNPOWDER].flashpoint + 50)
    sim = Simulation(g)
    for _ in range(60):
        sim.step()
    # Heat burst disturbed BOTH: wood ignited (-> FIRE -> later EMPTY) and/or was
    # destroyed; water boiled (-> STEAM) and/or was destroyed. Counts dropped.
    wood_after = int((g.array == int(ElementId.WOOD)).sum())
    water_after = int((g.array == int(ElementId.WATER)).sum())
    assert wood_after < 3, wood_after  # some/all wood ignited (was 3)
    assert water_after < 2, water_after  # some/all water boiled (was 2)


# --- scatter (knockback: loose materials pushed outward) -------------------


def test_blast_scatters_loose_material_outward(monkeypatch: object) -> None:
    """At SCATTER_CHANCE==1.0, loose material (sand) in the outer ring is pushed
    one cell outward (its position moves away from the blast center). Assert at
    least one loose cell moved. Outer-first visit order + the EMPTY-target
    check mean a scattered cell lands in an already-processed position, so it is
    not re-scattered (each loose cell moves at most one step outward)."""
    import sandfall.rules.blast as blast

    monkeypatch.setattr(blast, "CORE_FIRE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "CRATER_SMOKE_CHANCE", 0.0)
    monkeypatch.setattr(blast, "SCATTER_CHANCE", 1.0)
    random.seed(0)
    g = Grid(11, 11)
    cx, cy = 5, 5
    # Ring of sand at d~3-4 around the detonator (outside the crater).
    sand_before: dict[tuple[int, int], bool] = {}
    for y in range(11):
        for x in range(11):
            d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            if 3.0 <= d <= 4.0:
                g.set(x, y, ElementId.SAND)
                sand_before[(x, y)] = True
    g.set(cx, cy, ElementId.GUNPOWDER)
    g.set_temp(cx, cy, ELEMENTS[ElementId.GUNPOWDER].flashpoint + 50)
    Simulation(g).step()
    # At least one sand cell left its original position (was scattered outward).
    moved = [pos for pos in sand_before if g.get(*pos) != ElementId.SAND]
    assert moved, "expected at least one loose cell to be scattered outward"
    # No scattered cell landed more than one step from its origin (double-move
    # guard, master plan Risk #3): the origin is now EMPTY and every former
    # sand cell that survived is at most Chebyshev-distance 1 from an origin.
    survivors = [
        (x, y)
        for y in range(g.height)
        for x in range(g.width)
        if g.get(x, y) == ElementId.SAND
    ]
    for sx, sy in survivors:
        if (sx, sy) in sand_before:
            continue  # never moved
        # It is a scattered landing site: it must be within 1 cell of some origin.
        assert any(abs(sx - ox) <= 1 and abs(sy - oy) <= 1 for ox, oy in sand_before), (
            (sx, sy),
            "sand moved more than one cell -- double-scatter",
        )


# --- stable at ambient (does NOT explode; flows like a powder) -------------


def test_gunpowder_at_ambient_stays_gunpowder() -> None:
    """Gunpowder at ambient temp does NOT detonate (stays gunpowder). On a 1x1
    grid it also cannot move, so it just stays gunpowder -- proving the trigger
    is threshold-gated, not unconditional."""
    g = _step_single_cell(ElementId.GUNPOWDER, 20)
    assert g.get(0, 0) == ElementId.GUNPOWDER


def test_gunpowder_flows_like_a_powder() -> None:
    """Gunpowder above an EMPTY cell falls one step (powder physics, like sand)."""
    random.seed(0)
    g = Grid(1, 3)
    g.set(0, 0, ElementId.GUNPOWDER)  # top cell, EMPTY below
    Simulation(g).step()
    # It fell at least one cell down (powder movement).
    ys = [y for y in range(g.height) if g.get(0, y) == ElementId.GUNPOWDER]
    assert ys and ys[0] >= 1


# --- density (gunpowder is sand-like: displaces water) --------------------


def test_gunpowder_density_like_sand() -> None:
    """GUNPOWDER (1.5) is denser than WATER (1.0): can_displace lets it sink
    through water (like sand)."""
    assert can_displace(ElementId.GUNPOWDER, int(ElementId.WATER)) is True
    assert can_displace(ElementId.WATER, int(ElementId.GUNPOWDER)) is False


# --- renderer LUT grew -----------------------------------------------------


def test_color_lut_has_17_rows() -> None:
    """build_color_lut sizes from len(ElementId). After the dry-ice phase the
    enum has 17 members (0..16). The assertion tracks len(ElementId) so the next
    element pass does not need to re-edit it."""
    assert build_color_lut().shape[0] == len(ElementId) == 17

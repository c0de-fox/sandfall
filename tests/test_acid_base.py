"""Phase 01 (acid + base pair) tests: dissolve / neutralize / dilute / burn.

Covers the 5-step precedence of the two new reactive liquids deterministically.
Two strategies (mirrors tests/test_phase.py):

* **Single-cell transitions** (burn) use a ``Grid(1, 1)``: on a 1x1 grid the
  diffusion pre-pass is a true no-op (edge-padding replicates the lone cell on
  all four sides -> zero Laplacian), so the rule reads EXACTLY the temperature
  the test set.
* **Two-cell reactions** (dissolve / neutralize / dilute / smoke) use a
  ``Grid(2, 1)`` so the two cells are orthogonally adjacent. Both cells are
  set BEFORE constructing ``Simulation`` so the ``__init__`` bootstrap
  (``simulation.py``: seed active from all non-empty) marks both active.

Probabilistic behaviors are pinned deterministic by monkeypatching the module
globals (``DISSOLVE_CHANCE`` / ``DILUTE_CHANCE`` / ``DISSOLVE_SMOKE_CHANCE``),
which are read at call time (like ``fire.py``'s ``SMOKE_CHANCE``). The
neutralize test additionally loops ``random.seed`` over 20 seeds to verify the
idempotent side-effect write is scan-order-safe.
"""

from __future__ import annotations

import random

from sandfall.brush import paint_brush
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


# --- acid dissolves each dissolvable material (consumed-on-dissolve) --------


def test_acid_dissolves_sand(monkeypatch: object) -> None:
    """Acid eats SAND: target -> EMPTY, acid -> EMPTY (consumed)."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ACID)
    g.set(1, 0, ElementId.SAND)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY  # sand eaten
    assert g.get(0, 0) == ElementId.EMPTY  # acid consumed


def test_acid_dissolves_stone(monkeypatch: object) -> None:
    """Acid eats STONE (acid resists glass, NOT stone)."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ACID)
    g.set(1, 0, ElementId.STONE)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY
    assert g.get(0, 0) == ElementId.EMPTY


def test_acid_dissolves_wood(monkeypatch: object) -> None:
    """Acid eats WOOD."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ACID)
    g.set(1, 0, ElementId.WOOD)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY
    assert g.get(0, 0) == ElementId.EMPTY


def test_acid_dissolves_plant(monkeypatch: object) -> None:
    """Acid eats PLANT."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ACID)
    g.set(1, 0, ElementId.PLANT)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY
    assert g.get(0, 0) == ElementId.EMPTY


def test_acid_dissolves_ice(monkeypatch: object) -> None:
    """Acid eats ICE (ice does not melt from acid contact, but acid dissolves it)."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ACID)
    g.set(1, 0, ElementId.ICE)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY
    assert g.get(0, 0) == ElementId.EMPTY


def test_acid_does_not_dissolve_glass(monkeypatch: object) -> None:
    """GLASS resists acid (glass containers hold acid)."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ACID)
    g.set(1, 0, ElementId.GLASS)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.GLASS  # glass survives


# --- base mirror: base dissolves glass, NOT stone --------------------------


def test_base_dissolves_glass(monkeypatch: object) -> None:
    """Base eats GLASS (base resists stone, NOT glass)."""
    import sandfall.rules.base as base

    monkeypatch.setattr(base, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(base, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.BASE)
    g.set(1, 0, ElementId.GLASS)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY
    assert g.get(0, 0) == ElementId.EMPTY


def test_base_does_not_dissolve_stone(monkeypatch: object) -> None:
    """STONE resists base (stone resists base)."""
    import sandfall.rules.base as base

    monkeypatch.setattr(base, "DISSOLVE_CHANCE", 1.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.BASE)
    g.set(1, 0, ElementId.STONE)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.STONE  # stone survives


# --- neutralize (deterministic across scan orders) -------------------------


def test_acid_base_neutralize_both_become_water() -> None:
    """Acid adjacent to BASE -> BOTH become WATER, for any seed / scan order.

    The idempotent side-effect write (both rules set BOTH cells to WATER) is
    what makes the randomized scan order irrelevant. Verified across 20 seeds
    (mirrors tests/test_phase.py's lava+water reaction test).
    """
    for i in range(20):
        random.seed(i)
        g = Grid(2, 1)
        g.set(0, 0, ElementId.ACID)
        g.set(1, 0, ElementId.BASE)
        Simulation(g).step()
        assert g.get(0, 0) == ElementId.WATER, f"seed={i}"
        assert g.get(1, 0) == ElementId.WATER, f"seed={i}"


# --- dilute (monkeypatch DILUTE_CHANCE=1.0) --------------------------------


def test_acid_dilutes_into_water(monkeypatch: object) -> None:
    """Acid adjacent to WATER dilutes to WATER at DILUTE_CHANCE==1.0."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DILUTE_CHANCE", 1.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ACID)
    g.set(1, 0, ElementId.WATER)
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.WATER


# --- burn (flashpoint -> FIRE; single cell, diffusion no-op on 1x1) --------


def test_acid_ignites_to_fire_when_hot() -> None:
    """Acid above its flashpoint becomes FIRE (thermal ignition, like wood)."""
    g = _step_single_cell(ElementId.ACID, ELEMENTS[ElementId.ACID].flashpoint + 50)
    assert g.get(0, 0) == ElementId.FIRE


def test_base_ignites_to_fire_when_hot() -> None:
    """Base above its flashpoint becomes FIRE (mirror of acid)."""
    g = _step_single_cell(ElementId.BASE, ELEMENTS[ElementId.BASE].flashpoint + 50)
    assert g.get(0, 0) == ElementId.FIRE


# --- smoke on dissolve (monkeypatch DISSOLVE_SMOKE_CHANCE=1.0) -------------


def test_dissolve_emits_smoke(monkeypatch: object) -> None:
    """At DISSOLVE_SMOKE_CHANCE==1.0 the dissolved target becomes SMOKE; the
    acid cell is still consumed (-> EMPTY)."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 1.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ACID)
    g.set(1, 0, ElementId.SAND)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.SMOKE  # sand -> smoke
    assert g.get(0, 0) == ElementId.EMPTY  # acid consumed


# --- density (acid/base sink through water) --------------------------------


def test_acid_is_denser_than_water() -> None:
    """ACID (1.2) is denser than WATER (1.0): can_displace lets acid sink."""
    assert can_displace(ElementId.ACID, int(ElementId.WATER)) is True
    assert can_displace(ElementId.WATER, int(ElementId.ACID)) is False


def test_base_is_denser_than_water() -> None:
    """BASE (1.2) is denser than WATER (1.0): can_displace lets base sink."""
    assert can_displace(ElementId.BASE, int(ElementId.WATER)) is True
    assert can_displace(ElementId.WATER, int(ElementId.BASE)) is False


# --- dormant interaction: acid eats through a wall (Risks #1) --------------


def test_acid_eats_through_sand_wall() -> None:
    """A column of acid dropped onto a sand wall dissolves through it over many
    steps. Guards the dormant-wake sufficiency finding (consumed-on-dissolve
    keeps the front alive without ACID joining the FIRE/LAVA wake).

    Each dissolve changes BOTH the acid cell (-> EMPTY) and the eaten neighbor
    (-> EMPTY/SMOKE); their 1-cell dilation wakes the next wall cell and the
    next acid cell, so the dissolution front never stalls against a dormant
    wall. Mirrors tests/test_phase.py's ice-freeze-spread integration test.
    """
    random.seed(0)
    g = Grid(3, 8)
    # A 4-row sand wall at the bottom.
    for y in range(4, 8):
        for x in range(3):
            g.set(x, y, ElementId.SAND)
    # A column of acid above it.
    for y in range(4):
        g.set(1, y, ElementId.ACID)
    sim = Simulation(g)
    sand_before = int((g.array == int(ElementId.SAND)).sum())
    assert sand_before == 12
    for _ in range(200):
        sim.step()
    sand_after = int((g.array == int(ElementId.SAND)).sum())
    assert sand_after < sand_before, (sand_before, sand_after)


# --- consumed-on-dissolve: acid count drops as it eats ---------------------


def test_acid_is_consumed_when_it_dissolves(monkeypatch: object) -> None:
    """A pool of acid eating a sand block shrinks (acid is consumed per
    dissolve). Pinned deterministic at DISSOLVE_CHANCE==1.0 so every acid that
    reaches the wall is consumed within one step of contact."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 0.0)
    random.seed(0)
    g = Grid(2, 4)
    # Two acid cells stacked in the left column on top of a 2-row sand block.
    g.set(0, 0, ElementId.ACID)
    g.set(0, 1, ElementId.ACID)
    g.set(0, 2, ElementId.SAND)
    g.set(0, 3, ElementId.SAND)
    sim = Simulation(g)
    acid_before = int((g.array == int(ElementId.ACID)).sum())
    assert acid_before == 2
    for _ in range(40):
        sim.step()
    acid_after = int((g.array == int(ElementId.ACID)).sum())
    assert acid_after < acid_before, (acid_before, acid_after)


# --- paint_brush integration (the brush wakes acid for the dormant scan) ----


def test_paint_brush_acid_spawns_at_ambient() -> None:
    """A painted ACID disk has no life (acid has no finite life) and sits at
    AMBIENT_TEMP (its temp_spawn default), so the brush path needs no special
    acid seeding (mirrors the painted-glass regression in test_phase.py)."""
    from sandfall.elements import AMBIENT_TEMP

    g = Grid(10, 10)
    paint_brush(g, 5, 5, 1, ElementId.ACID)
    acid_cells = [
        (x, y)
        for y in range(g.height)
        for x in range(g.width)
        if g.get(x, y) == ElementId.ACID
    ]
    assert acid_cells, "expected a disk of ACID cells to be painted"
    for x, y in acid_cells:
        assert g.get_life(x, y) == 0, (x, y)  # no life tracking
        assert g.get_temp(x, y) == AMBIENT_TEMP, (x, y)


# --- renderer LUT grew -----------------------------------------------------


def test_color_lut_has_14_rows() -> None:
    """build_color_lut sizes from len(ElementId) -> 14 rows after ACID/BASE."""
    assert build_color_lut().shape == (14, 3)

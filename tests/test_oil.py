"""Phase 02 (oil) tests: floats on water / ignites / fire spreads / acid eats.

Oil is the simplest new element: a light flammable liquid (density 0.8 <
WATER 1.0 -> floats) that ignites to FIRE above its flashpoint (~150) and then
flows like water otherwise. No dissolve/dilute of its own. Covered
deterministically here with the same two strategies as tests/test_phase.py and
tests/test_acid_base.py:

* **Single-cell transitions** (burn / ambient) use a ``Grid(1, 1)``: on a 1x1
  grid the diffusion pre-pass is a true no-op (edge-padding replicates the
  lone cell on all four sides -> zero Laplacian), so the rule reads EXACTLY
  the temperature the test set.
* **Multi-cell reactions** (float / spread / dissolve) use a real grid so the
  density layering, the diffusion-driven fire front, and the acid-dissolve
  interaction all run through ``Simulation.step``.

Probabilistic behavior (acid's DISSOLVE_CHANCE) is pinned deterministic by
monkeypatching the module global, which is read at call time.
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


# --- floats on water (density) ---------------------------------------------


def test_oil_is_lighter_than_water() -> None:
    """OIL (0.8) is lighter than WATER (1.0): water sinks through oil (can
    displace it) and oil cannot sink through water (floats on top)."""
    assert can_displace(ElementId.WATER, int(ElementId.OIL)) is True
    assert can_displace(ElementId.OIL, int(ElementId.WATER)) is False


def test_oil_floats_above_water() -> None:
    """A cell of oil directly above water, stepped many times, ends with oil on
    top and water below (water sinks through the lighter oil -> oil rises)."""
    random.seed(0)
    g = Grid(1, 4)
    g.set(0, 0, ElementId.OIL)
    g.set(0, 1, ElementId.WATER)
    sim = Simulation(g)
    for _ in range(40):
        sim.step()
    # Oil is lighter -> it should have risen above the water.
    oil_y = [y for y in range(g.height) if g.get(0, y) == ElementId.OIL]
    water_y = [y for y in range(g.height) if g.get(0, y) == ElementId.WATER]
    assert oil_y and water_y
    assert min(oil_y) < max(water_y)  # oil is above at least some water


# --- ignites to FIRE --------------------------------------------------------


def test_oil_ignites_to_fire_when_hot() -> None:
    """Oil above its flashpoint becomes FIRE (thermal ignition, like wood)."""
    g = _step_single_cell(ElementId.OIL, ELEMENTS[ElementId.OIL].flashpoint + 50)
    assert g.get(0, 0) == ElementId.FIRE


def test_oil_at_ambient_stays_oil() -> None:
    """Oil at ambient temp neither ignites nor moves (1x1 grid -> no neighbor)."""
    g = _step_single_cell(ElementId.OIL, 20)
    assert g.get(0, 0) == ElementId.OIL


# --- burning oil spreads fire across water ----------------------------------


def test_burning_oil_spreads_fire_across_water() -> None:
    """An oil slick floating on water, ignited at one end, spreads FIRE across
    the slick: fire is a persistent heat source whose diffusion heats neighboring
    oil above its flashpoint, so the fire front advances along the surface."""
    random.seed(0)
    g = Grid(7, 3)
    # Bottom row: water; middle row: oil floating on it; top row: empty.
    for x in range(7):
        g.set(x, 2, ElementId.WATER)
        g.set(x, 1, ElementId.OIL)
    # Ignite the leftmost oil directly (give it FIRE's burn-temp + a long life).
    g.set(0, 1, ElementId.FIRE)
    g.set_temp(0, 1, ELEMENTS[ElementId.FIRE].burn_temp)
    g.set_life(0, 1, 40)
    sim = Simulation(g)
    oil_before = int((g.array == int(ElementId.OIL)).sum())
    assert oil_before == 6  # 7 slick cells minus the 1 ignited to FIRE
    for _ in range(120):
        sim.step()
    # Fire must have chained across the surface: at least one oil cell beyond
    # the ignition point combusted (oil count drops below the un-ignited 6).
    oil_after = int((g.array == int(ElementId.OIL)).sum())
    assert oil_after < oil_before, (oil_before, oil_after)


# --- acid dissolves oil (Decision #10) --------------------------------------


def test_acid_dissolves_oil(monkeypatch: object) -> None:
    """Acid eats OIL: oil is NOT in ACID_RESIST, so it is dissolvable. Target
    -> EMPTY (or SMOKE), acid -> EMPTY (consumed). Pinned deterministic at
    DISSOLVE_CHANCE==1.0 / DISSOLVE_SMOKE_CHANCE==0.0."""
    import sandfall.rules.acid as acid

    monkeypatch.setattr(acid, "DISSOLVE_CHANCE", 1.0)
    monkeypatch.setattr(acid, "DISSOLVE_SMOKE_CHANCE", 0.0)
    g = Grid(2, 1)
    g.set(0, 0, ElementId.ACID)
    g.set(1, 0, ElementId.OIL)
    Simulation(g).step()
    assert g.get(1, 0) == ElementId.EMPTY  # oil eaten (not in ACID_RESIST)
    assert g.get(0, 0) == ElementId.EMPTY  # acid consumed


def test_oil_not_in_acid_resist_set() -> None:
    """OIL is absent from ACID_RESIST (and BASE_RESIST) -- the static guarantee
    that makes acid/base dissolve oil by default (guards Decision #10 against a
    future contributor adding OIL to a resist set by mistake)."""
    from sandfall.rules.acid import ACID_RESIST
    from sandfall.rules.base import BASE_RESIST

    assert int(ElementId.OIL) not in ACID_RESIST
    assert int(ElementId.OIL) not in BASE_RESIST


# --- renderer LUT grew ------------------------------------------------------


def test_color_lut_has_18_rows() -> None:
    """build_color_lut sizes from len(ElementId) -> 18 rows after LN2
    (liquid nitrogen, added after dry ice, grew the enum to 18)."""
    assert build_color_lut().shape == (18, 3)

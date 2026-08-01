"""Shared helpers for element update rules.

These encode the cross-rule contracts used throughout the simulation:

* :func:`can_displace` — the density/phase swap test (sand sinks in water;
  water itself only displaces EMPTY in v1 since no lower-density liquid
  exists yet, but every liquid/powder also displaces any GAS -- the
  complement of :func:`is_riseable`: a denser phase flows through a gas, e.g.
  water through a steam wall, sand through steam).
* :func:`is_riseable` — the gas buoyancy test (EMPTY or any LIQUID). A gas may
  rise INTO an EMPTY cell (open air) or any LIQUID cell (buoyancy -- the gas
  swaps with the liquid above it, gas up / liquid down). Solids and other
  gases are not riseable. Used by the STEAM/SMOKE rise steps; the drift steps
  stay EMPTY-only.
* :func:`swap` — exchange two cells' element ids AND their per-cell life
  values AND their per-cell temperature. Every rule that moves a cell must
  go through this helper so the parallel ``life`` and ``temp`` arrays stay
  consistent with the element id array.
* :func:`seed_fire_life` / :func:`seed_smoke_life` / :func:`seed_steam_life` —
  the canonical lifetime ranges for FIRE, SMOKE, and STEAM cells. Both the
  rules (when they ignite/spawn) and the painting path (when the user
  brushes FIRE/SMOKE/STEAM onto the grid) go through these so a painted
  fire/smoke/steam lives for the same duration as a rule-spawned one.
  Centralizing them here is what lets Phase 05's brush fix the "painted fire
  dies instantly" bug without duplicating magic numbers.
"""

from __future__ import annotations

import random

from ..elements import ELEMENTS, ElementId, Phase
from ..grid import Grid

# Gases rise through liquids (buoyancy): a gas swaps with a LIQUID above it.
# Precomputed once (Phase is static) so the per-cell rise check is a set lookup.
_LIQUID_IDS: frozenset[int] = frozenset(
    int(e) for e in ElementId if ELEMENTS[e].phase == Phase.LIQUID
)


def can_displace(src_id: ElementId, target_id: int) -> bool:
    """True if an element ``src_id`` may move into a cell holding ``target_id``.

    A cell is displacable if it is EMPTY; or if it holds a strictly
    lower-density LIQUID (so denser powders/liquids sink through lighter
    liquids); or if it holds a GAS and ``src_id`` is a LIQUID or POWDER -- the
    complement of :func:`is_riseable` (a denser phase flows through a gas:
    water flows through a steam wall, sand falls through steam). Solids and
    same/higher-density liquids are not displacable; gas-gas and solid sources
    never displace (the gas clause's ``src.phase in (LIQUID, POWDER)`` guard).
    """
    if target_id == ElementId.EMPTY:
        return True
    src = ELEMENTS[src_id]
    target = ELEMENTS[ElementId(target_id)]
    # A denser liquid/powder sinks through a strictly-lighter liquid.
    if target.phase == Phase.LIQUID and target.density < src.density:
        return True
    # A liquid or powder flows through a gas -- the complement of is_riseable
    # (gas rises through liquid). E.g. water flows through a steam wall; sand
    # falls through steam. EMPTY is Phase.GAS but is already caught above, so
    # this only reaches FIRE / SMOKE / STEAM.
    if target.phase == Phase.GAS and src.phase in (Phase.LIQUID, Phase.POWDER):
        return True
    return False


def is_riseable(cell_id: int) -> bool:
    """True if a gas may rise INTO the cell holding ``cell_id``.

    EMPTY (open air) or any LIQUID (buoyancy -- the gas swaps with the liquid,
    gas up / liquid down). Solids and other gases are NOT riseable (a gas does
    not displace stone or another gas). Used by the STEAM/SMOKE rise steps;
    the sideways drift steps stay EMPTY-only (buoyancy is upward, not lateral).
    """
    return cell_id == int(ElementId.EMPTY) or cell_id in _LIQUID_IDS


def seed_fire_life() -> int:
    """Return a freshly seeded lifetime (in steps) for a new FIRE cell.

    The single source of truth for FIRE duration: both the fire rule's
    spread/spawn paths and the user-facing FIRE brush call this so a painted
    fire and a rule-ignited fire live for the same window of time.
    """
    return random.randint(20, 40)


def seed_smoke_life() -> int:
    """Return a freshly seeded lifetime (in steps) for a new SMOKE cell.

    The single source of truth for SMOKE duration (see :func:`seed_fire_life`).
    """
    return random.randint(60, 120)


def seed_steam_life() -> int:
    """Return a freshly seeded lifetime (in steps) for a new STEAM cell.

    Steam lingers longer than smoke (it is the boiled-off water vapor and
    should drift visibly before condensing back to WATER), so its window is
    wider than :func:`seed_smoke_life`. Both the lava+water reaction (which
    flashes water to steam) and the painting path (when the user brushes
    STEAM onto the grid) go through this so a reaction-spawned steam and a
    painted steam live for the same window of steps.
    """
    return random.randint(80, 160)


def seed_nitrogen_life() -> int:
    """Return a freshly seeded lifetime (in steps) for a new LN2 cell.

    Liquid nitrogen boils off rapidly at ambient (room temperature is far above
    its -196C boiling point), so its window is SHORT. Tuned (first-pass 30..80)
    so a painted blob visibly freezes a patch of adjacent water before boiling
    away to EMPTY; pin the final range in the reflection. Both the brush and any
    future reaction that spawns LN2 go through this so a painted LN2 and a
    reaction-spawned one live for the same window of steps.
    """
    return random.randint(30, 80)


def swap(grid: Grid, x1: int, y1: int, x2: int, y2: int) -> None:
    """Swap the contents (element id AND life AND temp) of two in-bounds cells.

    Delegates to :meth:`sandfall.grid.Grid.move`, the raw 3-array element swap
    (one numpy tuple-assignment per array, no per-access bounds check, no
    clipping) -- the fast path that replaced the old 12-call get/set sequence.
    Carrying life and temp along on every move is what keeps FIRE/SMOKE
    lifetimes and per-cell temperatures correct when those cells get pushed
    around (e.g. fire rising, sand displacing a cell that later becomes fire).

    Precondition (inherited from ``Grid.move``): both cells must be in bounds.
    Every caller pre-checks bounds today (see the audit in
    ``.agent/tasks/perf-grid-move/01-grid-move.md``); a raw index on an OOB
    cell raises ``IndexError`` rather than failing silently.
    """
    grid.move(x1, y1, x2, y2)


# Minimum temperature difference (degrees C) for a convective swap. Prevents
# jitter: a 1-2C diffusion ripple at a near-equilibrated interface must not flip
# cells every step. Tunable -- raise if playtesting shows flickering at an
# equilibrated boundary. Lives at the rule level (mirrors LAVA_SOLIDIFY_TEMP at
# lava.py:43 and LN2_COLD_TARGET at ln2.py:46); NOT a per-Element field.
CONVECTION_THRESHOLD = 10.0


def maybe_convect(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Temperature-driven buoyancy: if this cell is hotter than the same-phase
    cell directly above it (by > :data:`CONVECTION_THRESHOLD`), swap straight up
    (hot rises; the cooler cell sinks). Returns ``(x, y - 1)`` if it swapped,
    else ``None``.

    Intra-phase convection ONLY: both cells must be the SAME phase and that
    phase must be LIQUID or GAS. Cross-phase buoyancy is already handled
    elsewhere -- :func:`is_riseable` lets a gas rise INTO a liquid
    (gas/liquid buoyancy), and :func:`can_displace` lets a denser phase sink
    through a lighter one. This helper is the INTRA-phase complement: hot water
    rising WITHIN water, hot gas rising WITHIN gas. EMPTY above is explicitly
    skipped (EMPTY is handled by the existing fall/rise; treating it as
    convection would double-handle air). Straight-up only (no diagonal
    convection) so updrafts form clean vertical columns.

    Density guard (liquids only): a denser liquid does NOT buoy up through a
    lighter one even when hotter -- density stratification dominates in liquids
    (cold LN2 at density 0.8 floats on warm water at 1.0 regardless of the
    ~216C temperature difference; hot water under cold oil stays put). The
    compare is strict (``>``), so same-density pairs (water/water -- the main
    convection case, lava/lava, ...) still convect. Gases are EXEMPT (their
    densities are all negligible and close together, so temperature is the
    dominant buoyancy driver -- e.g. hot FIRE at ~800C rises through cooler
    SMOKE/STEAM). This preserves correct liquid layering while keeping the
    gas-gas convection path the plan calls for.

    Called by every liquid/gas rule AFTER its reactive checks (a boiling/
    freezing/condensing/aging cell transforms in place and returns None before
    reaching here) and BEFORE its fall/rise/spread/drift. If this returns a
    destination, the rule returns it (the cell convected; it does not also
    fall/rise this step -- one move per step).
    """
    if y - 1 < 0:
        return None  # top row -- nothing above
    above_id = grid.get(x, y - 1)
    if above_id == ElementId.EMPTY:
        return None  # EMPTY above is handled by the existing rise/fall
    my_id = grid.get(x, y)
    my_phase = ELEMENTS[ElementId(my_id)].phase
    above_phase = ELEMENTS[ElementId(above_id)].phase
    # Same-phase LIQUID/LIQUID or GAS/GAS only. Powders (hot sand) and solids
    # never convect (they pile / are rigid). Different phases use is_riseable /
    # can_displace instead.
    if my_phase != above_phase or my_phase not in (Phase.LIQUID, Phase.GAS):
        return None
    # Density guard (liquids only): a denser liquid does not buoy up through a
    # lighter one even when hotter (density stratification dominates in liquids).
    # Gases are exempt (density differences are negligible; temp dominates).
    # Strict ``>`` so same-density pairs (water/water) still convect.
    if my_phase == Phase.LIQUID:
        if ELEMENTS[ElementId(my_id)].density > ELEMENTS[ElementId(above_id)].density:
            return None
    if grid.get_temp(x, y) - grid.get_temp(x, y - 1) > CONVECTION_THRESHOLD:
        swap(grid, x, y, x, y - 1)
        return (x, y - 1)
    return None

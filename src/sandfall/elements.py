"""Element model and registry for the sandfall simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ElementId(IntEnum):
    """Stable integer IDs stored in the grid (uint8).

    Defined in full here so later phases only adjust registry data
    (colors, densities, rules) and never add new enum members.
    """

    EMPTY = 0
    SAND = 1
    WATER = 2
    STONE = 3
    WOOD = 4
    FIRE = 5
    SMOKE = 6
    PLANT = 7


class Phase(IntEnum):
    """Physical phase of an element; drives default behavior."""

    SOLID = 0  # static (stone, wood, plant)
    POWDER = 1  # falls, piles (sand)
    LIQUID = 2  # falls + spreads (water)
    GAS = 3  # rises + diffuses (smoke); fire is gas-like


@dataclass(frozen=True, slots=True)
class Element:
    """Static definition of an element kind."""

    id: ElementId
    name: str
    color: tuple[int, int, int]  # RGB 0..255
    density: float
    phase: Phase
    flammability: float = 0.0  # 0.0 = never burns; 1.0 = always burns on contact


ELEMENTS: dict[ElementId, Element] = {
    ElementId.EMPTY: Element(
        id=ElementId.EMPTY,
        name="empty",
        color=(0, 0, 0),
        density=0.0,
        phase=Phase.GAS,
    ),
    ElementId.SAND: Element(
        id=ElementId.SAND,
        name="sand",
        color=(194, 178, 128),
        density=1.5,
        phase=Phase.POWDER,
    ),
    # The entries below are populated now with realistic placeholder values so
    # registry lookups never KeyError during development; Phase 03 tunes the
    # numbers and adds rules but does NOT add enum members or new entries.
    ElementId.WATER: Element(
        id=ElementId.WATER,
        name="water",
        color=(40, 80, 200),
        density=1.0,
        phase=Phase.LIQUID,
    ),
    ElementId.STONE: Element(
        id=ElementId.STONE,
        name="stone",
        color=(120, 120, 120),
        density=10.0,
        phase=Phase.SOLID,
    ),
    ElementId.WOOD: Element(
        id=ElementId.WOOD,
        name="wood",
        color=(120, 72, 32),
        density=8.0,
        phase=Phase.SOLID,
        flammability=0.25,
    ),
    ElementId.FIRE: Element(
        id=ElementId.FIRE,
        name="fire",
        color=(255, 120, 20),
        density=0.1,
        phase=Phase.GAS,
    ),
    ElementId.SMOKE: Element(
        id=ElementId.SMOKE,
        name="smoke",
        color=(90, 90, 90),
        density=0.05,
        phase=Phase.GAS,
    ),
    ElementId.PLANT: Element(
        id=ElementId.PLANT,
        name="plant",
        color=(40, 160, 60),
        density=8.0,
        phase=Phase.SOLID,
        flammability=0.4,
    ),
}

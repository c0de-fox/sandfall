"""Element model and registry for the sandfall simulation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

# --- Temperature band + ambient (Phase 01) ----------------------------------
# These live HERE (top of elements.py) rather than in config.py so that this
# module has ZERO dependency on config.py: config.py imports ``ElementId`` from
# here (config.py:9), so importing AMBIENT_TEMP from config would close a
# circular-import loop. config.py re-exports these names for callers that
# already import from config; the canonical definition is this block.
# AMBIENT_TEMP is the resting temperature every cell initializes to and that
# fill_circle resets to (mirrors how it zeroes life). The clip band is wide
# enough for sand melting (~1700) and sub-zero freezing; float32 headroom is huge.
AMBIENT_TEMP = 20
TEMP_MIN = -200
TEMP_MAX = 3000


class ElementId(IntEnum):
    """Stable integer IDs stored in the grid (uint8).

    Extended in Phase 03 (temperature feature) with STEAM, ICE, LAVA, GLASS.
    Earlier v1 notes said "defined in full; never add new enum members";
    that was superseded by the temperature feature (user-approved, "Water
    cycle + lava + glass" — see the temperature master-plan Decision Log
    #5). Existing member values 0..7 are unchanged, so every LUT index the
    v1 code relies on (renderer color LUT, conductivity LUT) stays stable;
    new members take 8..11. ``uint8`` holds up to 255, so there is ample
    room for future elements.

    Extended again with the acid/base pair (ACID=12, BASE=13) — two dense
    reactive liquids that dissolve neighboring materials, neutralize each
    other into water, dilute in water, and burn to FIRE when heated. Same
    supported-operation status as the 8..11 members; existing values 0..11
    are unchanged so every LUT index stays stable.

    Extended once more with oil (OIL=14) — a light flammable liquid (density
    0.8, less than WATER 1.0 -> floats on water) that ignites to FIRE when
    heated above a low flashpoint. Same shape as the previous extensions;
    existing values 0..13 are unchanged so every LUT index stays stable.
    """

    EMPTY = 0
    SAND = 1
    WATER = 2
    STONE = 3
    WOOD = 4
    FIRE = 5
    SMOKE = 6
    PLANT = 7
    STEAM = 8
    ICE = 9
    LAVA = 10
    GLASS = 11
    # --- New elements (acid/base pair) ---
    ACID = 12
    BASE = 13
    # --- New element (oil) ---
    OIL = 14


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
    # --- Thermal fields (Phase 01) -----------------------------------------
    # Temperature a freshly painted/spawned cell of this element starts at
    # (AMBIENT_TEMP for most; high for FIRE/LAVA — Phase 02/03). Mirrors how
    # brush.paint_brush seeds life for FIRE/SMOKE.
    temp_spawn: int = AMBIENT_TEMP
    # Auto-ignition threshold: a cell of this element ignites (becomes FIRE)
    # when its OWN temp exceeds flashpoint. 0 means NEVER (the default) — the
    # Phase 02 reactive wood/plant rules check `flashpoint > 0 and temp >
    # flashpoint`. Replaces the old probabilistic per-neighbor spread.
    flashpoint: int = 0
    # Heat conductivity scalar in [0.0, 1.0]; also stored in the conductivity
    # LUT (config.COND_*). Kept on Element too so ELEMENTS is the single
    # registry a contributor edits when adding a material.
    conductivity: float = 0.0
    # Heat capacity / thermal inertia scalar (> 0). Divides the temperature
    # change in diffuse_temps: high cp = thermally massive (changes slowly);
    # also stored in the heat-capacity LUT (config.CP_*). Default 1.0 so every
    # existing entry still constructs.
    heat_capacity: float = 1.0
    # Temperature a FIRE cell (or other heat source) of this material holds
    # while burning. Phase 02 sets WOOD/PLANT burn_temp on the cell when they
    # ignite; FIRE's own rule maintains its burn_temp each step.
    burn_temp: int = AMBIENT_TEMP
    # --- Phase-change thresholds (used in Phase 03; declared here so the
    # dataclass shape is stable across phases). 0 means "this element does not
    # undergo this transition".
    melt_point: int = 0  # above this temp, this element melts (ice->water)
    boil_point: int = 0  # above this temp, this element boils (water->steam)
    freeze_point: int = 0  # below this temp, this element freezes (water->ice)
    condense_point: int = 0  # below this temp, this element condenses (steam->water)


ELEMENTS: dict[ElementId, Element] = {
    ElementId.EMPTY: Element(
        id=ElementId.EMPTY,
        name="empty",
        color=(0, 0, 0),
        density=0.0,
        phase=Phase.GAS,
        conductivity=0.10,
        heat_capacity=1.0,
    ),
    ElementId.SAND: Element(
        id=ElementId.SAND,
        name="sand",
        color=(194, 178, 128),
        density=1.5,
        phase=Phase.POWDER,
        conductivity=0.15,
        heat_capacity=1.5,
        melt_point=1700,  # above this temp, sand melts -> GLASS (Phase 03)
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
        conductivity=0.35,
        heat_capacity=4.0,
        boil_point=100,
        freeze_point=0,
    ),
    ElementId.STONE: Element(
        id=ElementId.STONE,
        name="stone",
        color=(120, 120, 120),
        density=10.0,
        phase=Phase.SOLID,
        conductivity=0.08,
        heat_capacity=2.0,
    ),
    ElementId.WOOD: Element(
        id=ElementId.WOOD,
        name="wood",
        color=(120, 72, 32),
        density=8.0,
        phase=Phase.SOLID,
        flammability=0.25,  # legacy/unused for spread (Phase 02 removes reader); kept
        conductivity=0.12,
        heat_capacity=1.5,
        flashpoint=300,  # ignites when its own temp exceeds 300
        burn_temp=800,  # holds ~800 while burning
    ),
    ElementId.FIRE: Element(
        id=ElementId.FIRE,
        name="fire",
        color=(255, 120, 20),
        density=0.1,
        phase=Phase.GAS,
        temp_spawn=800,  # a painted fire starts hot
        conductivity=0.50,
        heat_capacity=0.5,
        burn_temp=800,
    ),
    ElementId.SMOKE: Element(
        id=ElementId.SMOKE,
        name="smoke",
        color=(90, 90, 90),
        density=0.05,
        phase=Phase.GAS,
        conductivity=0.20,
        heat_capacity=0.5,
    ),
    ElementId.PLANT: Element(
        id=ElementId.PLANT,
        name="plant",
        color=(40, 160, 60),
        density=8.0,
        phase=Phase.SOLID,
        flammability=0.4,
        conductivity=0.12,
        heat_capacity=1.5,
        flashpoint=250,
        burn_temp=700,
    ),
    # --- Phase 03 new elements (STEAM / ICE / LAVA / GLASS) -----------------
    # Thermal thresholds drive their transitions (see rules/steam.py, ice.py,
    # lava.py, glass.py). STEAM is a finite-life gas (rises like smoke, then
    # condenses -> WATER when it cools); ICE is a cold static solid (melts ->
    # WATER above 0); LAVA is a very hot dense liquid (cools -> STONE, and
    # reacts with adjacent WATER -> STEAM + STONE); GLASS is a static solid
    # made only by SAND melting.
    ElementId.STEAM: Element(
        id=ElementId.STEAM,
        name="steam",
        color=(220, 220, 230),
        density=0.04,
        phase=Phase.GAS,
        conductivity=0.25,
        heat_capacity=0.5,
        temp_spawn=120,  # warm gas on spawn
        condense_point=60,  # below this temp, condenses -> WATER
    ),
    ElementId.ICE: Element(
        id=ElementId.ICE,
        name="ice",
        color=(180, 220, 240),
        density=0.92,
        phase=Phase.SOLID,
        conductivity=0.18,
        heat_capacity=2.0,
        temp_spawn=-5,  # painted ice starts cold
        melt_point=0,  # above 0 -> WATER (0 is a VALID active threshold for ice)
    ),
    ElementId.LAVA: Element(
        id=ElementId.LAVA,
        name="lava",
        color=(240, 90, 20),
        density=2.5,
        phase=Phase.LIQUID,
        conductivity=0.45,
        heat_capacity=5.0,
        temp_spawn=1500,  # painted lava starts very hot
        # LAVA solidifies -> STONE below LAVA_SOLIDIFY_TEMP (a rule-level
        # constant in rules/lava.py); there is no Element field for
        # "solidifies into X", so no threshold is declared here.
    ),
    ElementId.GLASS: Element(
        id=ElementId.GLASS,
        name="glass",
        color=(200, 230, 230),
        density=2.5,
        phase=Phase.SOLID,
        conductivity=0.10,
        heat_capacity=1.5,
        # Made only by SAND melting; static once formed (no transitions).
    ),
    # --- Acid + Base (dense reactive liquids; consumed-on-dissolve) ---------
    # Both are LIQUID (density 1.2, denser than WATER 1.0 -> sink through water).
    # flashpoint ~200 -> burn to FIRE when heated by lava/fire (thermal path);
    # burn_temp ~600 documents the fuel character (active heat comes from the
    # FIRE rule, same as WOOD/PLANT). The dissolve/neutralize/dilute logic lives
    # entirely in rules/acid.py + rules/base.py (no Element fields for it).
    ElementId.ACID: Element(
        id=ElementId.ACID,
        name="acid",
        color=(110, 220, 70),  # bright acid green
        density=1.2,
        phase=Phase.LIQUID,
        conductivity=0.30,
        heat_capacity=2.0,
        flashpoint=200,
        burn_temp=600,
    ),
    ElementId.BASE: Element(
        id=ElementId.BASE,
        name="base",
        color=(180, 90, 200),  # violet (alkali)
        density=1.2,
        phase=Phase.LIQUID,
        conductivity=0.30,
        heat_capacity=2.0,
        flashpoint=200,
        burn_temp=600,
    ),
    # --- Oil (light flammable liquid; floats on water) ----------------------
    # LIQUID with density 0.8 (< WATER 1.0 -> floats on water via can_displace).
    # Low flashpoint ~150 -> ignites to FIRE when heated by fire/lava (thermal
    # path). No dissolve/dilute of its own (rules/oil.py: burn first, then flow).
    # burn_temp is left at its default (AMBIENT_TEMP): when oil ignites it
    # becomes ElementId.FIRE, whose rule re-asserts _FIRE.burn_temp (800) --
    # the same shape as wood/plant where the active heat comes from FIRE, not
    # the fuel's own declared burn_temp (overview Risk #6).
    ElementId.OIL: Element(
        id=ElementId.OIL,
        name="oil",
        color=(70, 45, 25),  # dark oily brown
        density=0.8,
        phase=Phase.LIQUID,
        conductivity=0.12,  # oils are thermal insulators
        heat_capacity=1.5,
        flashpoint=150,
    ),
}

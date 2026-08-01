# Phase 02: Ice as a persistent cold source

## Objective

Rework `update_ice` (`ice.py:25-29`) so ice **re-asserts a cold temperature each
step** (mirroring how `fire.py:92-93` re-asserts `burn_temp`) — making ice freeze
water *through* the thermal system instead of as a diffusion-bug side-effect —
and so ice **melts ONLY via direct fire/lava contact** (mirroring `lava.py`'s
reaction shape), deleting the `if temp > melt_point: -> WATER` thermal-melt that
is incompatible with being a cold source and was the thing blocking the freeze.
Pair it with a one-line addition to `water.py`'s freeze branch so the freeze
front advances immediately, and verify (via an integration test) that the
existing dormant-wake conditions suffice to spread the freeze. This fixes root
cause #2 of the freeze regression on top of Phase 01's float precision.

## Depends On

Phase 01 (`01-float-temps.md`). Phase 02's headline acceptance — that a freeze
*spreads* through water — is only achievable with float temps: under the int16
rounding stall, the water between cold cells never crosses the `<= 0` threshold,
so re-asserting cold on ice would not propagate a freeze. Land Phase 01 first.

## Can Parallelize With

none — depends on Phase 01.

## Recommended Agent

@implementer — a focused rule rewrite + a one-line addition + a dormant-wake
*verification* (the unknown is whether the existing wake conditions keep the
freeze front alive without adding ICE to condition 3). Read `00-overview.md`
first (especially Decision Log #2-#5, Risks #3-#5), then re-read
`src/sandfall/rules/ice.py`, `src/sandfall/rules/water.py`,
`src/sandfall/rules/lava.py` (the reaction pattern to mirror),
`src/sandfall/rules/fire.py:92-93` (the re-assert pattern to mirror),
`src/sandfall/simulation.py:159-170` (the wake conditions), and
`tests/test_phase.py` before editing. **The integration test is the gate for the
dormant-wake question** — if the freeze stalls, add ICE to the wake and pin the
finding in the reflection.

## Changes Required

- `src/sandfall/rules/ice.py` — define `ICE_COLD_TARGET = -50` (module constant,
  mirrors `lava.py:43` `LAVA_SOLIDIFY_TEMP`); rewrite `update_ice` to (a)
  re-assert `ICE_COLD_TARGET` when the cell is warmer, and (b) melt to WATER/STEAM
  via direct fire/lava contact; **delete** the `if temp > melt_point` thermal-melt
  branch (`:27-28`); rewrite the module docstring to explain the persistent-cold-
  source model and the temporary "no ambient melt" behavior.
- `src/sandfall/rules/water.py` — in the freeze branch (`:56-59`), after
  `grid.set(x, y, ElementId.ICE)`, also `grid.set_temp(x, y, ICE_COLD_TARGET)`
  (imported from `ice.py`) so the freeze front advances the same step.
- `src/sandfall/simulation.py` — **audit-only unless the integration test fails.**
  Verify the dormant-wake conditions (`:159-170`) keep the freeze spreading
  WITHOUT adding ICE. Only if the integration test shows a stall: add
  `| (data == int(ElementId.ICE))` to the condition-3 dilate at `:168-170`.
- `tests/test_phase.py` — ADD a spreading-freeze integration test (seed ice in
  water, step ~80–120, assert ice count grows); REWORK `test_ice_melts_to_water`
  (`:86-95`) from a thermal-melt (now deleted) into a fire/lava-contact melt;
  optionally a direct-lava→steam-on-melt test mirroring `lava.py`'s reaction.
- `src/sandfall/elements.py` — **no change.** `ICE.melt_point` (`:214`) stays
  declared (it is now unused by the rule, but it is part of the dataclass shape
  and the realistic-rework BACKLOG item will restore its use). Do NOT delete it.

## Implementation Instructions

> Re-read each file before editing — line numbers below are current at the
> Phase-01-complete source and may have drifted. The `update_ice` rewrite and
> the `water.py` freeze-branch addition must land together (the new ice the
> water rule creates must immediately hold `ICE_COLD_TARGET`, else the front
> lags a frame before its own rule re-asserts).

### 1. `src/sandfall/rules/ice.py` — full rewrite

Replace the entire current file (`ice.py:1-29`). The new module defines
`ICE_COLD_TARGET`, a 4-neighbor reaction tuple (mirroring `lava.py:47-52`), and
a rewritten `update_ice` that re-asserts cold then checks for fire/lava contact.
Exact replacement:

```python
"""Ice (SOLID, persistent cold source) update rule.

Ice is a **persistent cold source**: each step it re-asserts its cold target
temperature (`ICE_COLD_TARGET`), exactly as a living fire cell re-asserts its
burn_temp (`rules/fire.py`). The Simulation's vectorized diffusion pre-pass
carries that cold outward into adjacent water; once the water cools to/below its
freeze_point the WATER rule freezes it (and seeds the new ice cold, so the freeze
front advances immediately). This is how ice freezes water *through the thermal
system* rather than as a diffusion-bug side-effect.

Ice melts **only via direct fire/lava contact** (the real-world way ice is
destroyed quickly): if any orthogonal neighbor is FIRE the ice becomes WATER; if
any is LAVA the ice becomes STEAM (mirroring `rules/lava.py`'s reaction shape).
It does NOT melt from ambient warmth: a cell that re-asserts ICE_COLD_TARGET
every step can never exceed its melt_point through diffusion, and allowing
thermal melt would be logically incompatible with being a cold source (a warm
enough ice to melt would also be too warm to freeze anything). This is a
**deliberate, temporary** model: once colder-than-freezing cold-source elements
exist (dry ice ~-78C, liquid nitrogen ~-196C), ice will revert to a realistic
melt-at->0 "frozen water" non-source -- see BACKLOG ("Thermal realism" rework).

This is the formal use of the reactive-rule contract relaxation (transform own
cell in place, return None); the cell does not MOVE so the simulation's
moved-this-frame guard is unaffected.
"""

from __future__ import annotations

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import seed_steam_life

# The cold temperature an ice cell holds (and re-asserts) each step. A cold
# source: diffusion carries this cold outward, but cannot warm the ice above
# this value while the rule keeps re-asserting it. NOT a physical temperature --
# it is a tunable knob for freeze spread rate (colder -> faster spread).
# Prototype-validated at -50 (an ice cube in water spreads 1->3->5->9 cells over
# ~120 steps). Mirrors the LAVA_SOLIDIFY_TEMP pattern in rules/lava.py.
ICE_COLD_TARGET = -50

# Orthogonal neighborhood for the fire/lava melt check (matches the
# 4-neighborhood the diffusion pre-pass and lava.py use).
_MELT_NEIGHBORS: tuple[tuple[int, int], ...] = (
    (0, -1),
    (0, 1),
    (-1, 0),
    (1, 0),
)

_STEAM = ELEMENTS[ElementId.STEAM]


def update_ice(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Step an ice cell: melt via direct fire/lava contact, else re-assert cold.

    1. **Melt via direct fire/lava contact.** A FIRE neighbor -> become WATER; a
       LAVA neighbor -> become STEAM (the lava reaction flashes the melt to
       steam). Checked FIRST so a hot contact destroys the ice before it can
       re-assert cold. (Ice does NOT melt from ambient -- see module docstring.)
    2. **Re-assert the cold target.** While still ice, clamp the cell's temp
       DOWN to ICE_COLD_TARGET each step so it remains a persistent cold source
       the diffusion pre-pass draws from (mirrors fire's burn-temp re-assert).
    """
    # 1. Direct fire/lava contact melts the ice.
    for dx, dy in _MELT_NEIGHBORS:
        nx, ny = x + dx, y + dy
        if not grid.in_bounds(nx, ny):
            continue
        neighbor = grid.get(nx, ny)
        if neighbor == ElementId.LAVA:
            grid.set(x, y, ElementId.STEAM)
            grid.set_temp(x, y, _STEAM.temp_spawn)  # warm gas on melt-by-lava
            grid.set_life(x, y, seed_steam_life())
            return None
        if neighbor == ElementId.FIRE:
            grid.set(x, y, ElementId.WATER)
            return None

    # 2. Re-assert cold: a living ice is a persistent cold source.
    if grid.get_temp(x, y) > ICE_COLD_TARGET:
        grid.set_temp(x, y, ICE_COLD_TARGET)

    return None
```

Notes for the implementer:
- The LAVA-contact branch is checked before FIRE so the more dramatic reaction
  (steam) wins when both are adjacent; this mirrors `lava.py`'s own priority
  (react before flow). Order between the two is a judgment call — FIRE→WATER is
  the safer fallback; document the chosen order in the reflection if you flip it.
- `seed_steam_life` is imported from `._common` (already exported there; `lava.py`
  and `water.py` both use it). Confirm it is importable from `ice.py` (sibling
  module, no cycle: `_common` imports only from `..elements`/`..grid`).
- The old `_ICE = ELEMENTS[ElementId.ICE]` binding (`ice.py:22`) is removed — the
  rule no longer reads `melt_point`. (Leave `ICE.melt_point` declared in
  `elements.py:214` for the realistic-rework BACKLOG item; it is now unused by
  the rule, which is fine.)

### 2. `src/sandfall/rules/water.py` — seed new ice cold

In the freeze branch (`water.py:56-59`), add the cold-temp write so the new ice
immediately holds `ICE_COLD_TARGET` (no 1-frame lag before its own rule
re-asserts). Add the import at the top, then the one line.

**2a. Import** (`water.py:30`, extend the existing `from ._common import ...`):
add `ICE_COLD_TARGET` from the sibling `ice` module:

```python
from ._common import can_displace, seed_steam_life, swap
from .ice import ICE_COLD_TARGET
```

**2b. The freeze branch** (`water.py:56-59`) becomes:

```python
    # Freeze -> ICE (at or below freeze_point; freeze_point == 0 is valid).
    # Seed the new ice cold (ICE_COLD_TARGET) so the freeze front advances this
    # same step rather than lagging a frame before update_ice re-asserts.
    if t <= _WATER.freeze_point:
        grid.set(x, y, ElementId.ICE)
        grid.set_temp(x, y, ICE_COLD_TARGET)
        return None
```

Notes for the implementer:
- The `water -> ice` import is one-way: `ice.py` imports only from `..elements`/
  `..grid`/`._common` (NOT `water`), so there is no import cycle. Confirm by
  re-reading `ice.py` after the Phase-1-and-2 edits.
- Update the `water.py` module docstring's freeze bullet (`:14-15`) to note the
  new ice is seeded cold (one phrase; do not rewrite the whole docstring).

### 3. `src/sandfall/simulation.py` — audit-only (verification gate)

**Do NOT edit `simulation.py` yet.** Re-read `simulation.py:159-170` (the four
wake conditions) and reason:

- The diffusion pre-pass (`:116`) runs WHOLE-GRID regardless of `active`, so cold
  from a dormant ice cell still propagates into adjacent water.
- That water cools (its temp changes) → condition 2 (`:163`,
  `grid._temp != temp_before`) wakes it → it is scanned → its freeze-check runs →
  it freezes (Phase-01 float precision lets it actually cross 0).
- The freshly-frozen cell changed identity → condition 1 (`:158-159`, `id_changed`
  + dilate) wakes it + its neighbors → its rule re-asserts cold.
- The *ice* cell itself warms slightly toward the warmer water (temp changes) →
  condition 2 wakes it → `update_ice` re-asserts `ICE_COLD_TARGET`.

So the analysis says the existing wake conditions **should** keep the freeze
front alive **without** adding ICE to condition 3 (`:164-170`, the FIRE/LAVA
dilate). **Verify this with the integration test in step 4 BEFORE deciding.**

**Only if the integration test shows the freeze stalls** (ice count does not
grow over ~120 steps in a real `Simulation`): add ICE to the persistent-source
wake condition at `simulation.py:168-170`:

```python
        active_next |= _dilate(
            (data == int(ElementId.FIRE))
            | (data == int(ElementId.LAVA))
            | (data == int(ElementId.ICE))
        )
```

…and update the comment to explain ICE is now a persistent cold source (mirrors
fire/lava). **Pin the decision and its evidence (the stall, or the lack of one)
in the reflection.** Default expectation per the analysis: NO edit needed.

### 4. `tests/test_phase.py`

**4a. ADD `test_ice_freeze_spreads_through_water`** — the headline Phase-02
integration test. Seed a small block of ice in a pool of water, step a real
`Simulation` ~80–120 times, assert the ice count GROWS (the freeze spreads).
Append near the existing ice/water tests (after `test_water_freezes_to_ice`,
around `:75`):

```python
def test_ice_freeze_spreads_through_water() -> None:
    """A block of ice in water freezes its surroundings (the freeze spreads).

    The headline Phase-02 test: ice is a persistent cold source (re-asserts
    ICE_COLD_TARGET each step), so cold propagates via diffusion into adjacent
    water, the water cools below freeze_point, and the WATER rule freezes it
    (seeding the new ice cold so the front keeps advancing). Prototype-measured
    spread at ICE_COLD_TARGET=-50: 1 -> 3 -> 5 -> 9 cells over ~120 steps. This
    is the regression guard for the 'ice no longer freezes water' bug.
    """
    from sandfall.rules.ice import ICE_COLD_TARGET

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
```

(The exact final count depends on `ICE_COLD_TARGET` tuning and RNG, so assert
strict growth, not an exact number — the point is that it spreads at all, which
the broken model could not do.) **If `ice_after == ice_before` (no spread), the
dormant-wake sufficiency is falsified — apply the step-3 `simulation.py` edit
and re-run.** Record which outcome held.

**4b. REWORK `test_ice_melts_to_water`** (`test_phase.py:86-95`). The old test
relied on the deleted thermal-melt branch (`ICE at 5°C → WATER`); it now fails
because ice no longer melts from ambient warmth. Replace it with a test of the
NEW melt path: direct fire/lava contact. Replace:

```python
def test_ice_melts_to_water() -> None:
    """Ice warmer than its melt_point (0) becomes WATER.
    ...
    """
    g = _step_single_cell(ElementId.ICE, ELEMENTS[ElementId.ICE].melt_point + 5)
    assert g.get(0, 0) == ElementId.WATER
```

with a contact-melt test (ice adjacent to FIRE -> WATER). Use a small grid with
ice + fire neighbors so the rule's neighbor scan sees the fire:

```python
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
    from sandfall.rules import seed_steam_life  # noqa: F401  (range asserted elsewhere)

    g = Grid(3, 1)
    g.set(0, 0, ElementId.ICE)
    g.set(1, 0, ElementId.LAVA)
    g.set_temp(1, 0, ELEMENTS[ElementId.LAVA].temp_spawn)  # 1500
    Simulation(g).step()
    assert g.get(0, 0) == ElementId.STEAM
    assert g.get_temp(0, 0) == ELEMENTS[ElementId.STEAM].temp_spawn
```

(Remove the now-dead `# noqa` import if you drop the lava-steam test; keep both
tests if cheap — they pin both melt branches. The `STEAM_LIFE_MIN/MAX` range
constants are already in scope at `test_phase.py:37` if you want to assert the
seeded life on the lava-melt steam.)

**4c. UPDATE `test_water_freezes_to_ice`** (`test_phase.py:65-74`) — add an
assertion that the new ice was seeded cold (the Phase-02 water-rule change).
After the existing `assert g.get(0, 0) == ElementId.ICE`:

```python
    from sandfall.rules.ice import ICE_COLD_TARGET
    ...
    assert g.get(0, 0) == ElementId.ICE
    assert g.get_temp(0, 0) == ICE_COLD_TARGET  # new ice seeded cold (front advances)
```

**4d. (Optional) confirm ambient ice persists.** A 1×1 ice at ambient (20°C)
stepped once must STAY ice (it re-asserts cold; it does NOT melt). This pins the
deliberate behavior change. Add if cheap:

```python
def test_ice_at_ambient_stays_ice() -> None:
    """Ice at ambient does NOT melt (it re-asserts cold; only fire/lava destroy it).

    Deliberate temporary behavior -- ambient melt is disabled because it is
    incompatible with being a cold source. See BACKLOG (Thermal realism rework).
    """
    g = _step_single_cell(ElementId.ICE, 20)
    assert g.get(0, 0) == ElementId.ICE
```

## Acceptance Criteria

- [ ] `rules/ice.py` defines `ICE_COLD_TARGET = -50` (module constant, mirrors
      `LAVA_SOLIDIFY_TEMP`); `update_ice` re-asserts `ICE_COLD_TARGET` when the
      cell is warmer; ice melts to WATER on a FIRE neighbor and to STEAM on a
      LAVA neighbor; the `if temp > melt_point` thermal-melt is DELETED; the
      module docstring explains the persistent-cold-source model and the
      temporary "no ambient melt" behavior.
- [ ] `rules/water.py` freeze branch sets the new ice's temp to
      `ICE_COLD_TARGET` (imported from `ice.py`); no import cycle (ice.py does
      not import water.py).
- [ ] **`test_ice_freeze_spreads_through_water` passes** — ice count strictly
      grows over ~120 steps in a real `Simulation` (the headline; the broken
      model could not spread). If it stalled, `simulation.py` condition-3 was
      extended with `| (data == ICE)` and the decision + evidence are in the
      reflection; otherwise `simulation.py` is unchanged (recorded).
- [ ] `test_ice_melts_to_water` is GONE (or renamed) and replaced by
      `test_ice_melts_to_water_via_fire_contact` (+ optionally the lava-steam
      variant); both pass.
- [ ] `test_water_freezes_to_ice` asserts the new ice is seeded at
      `ICE_COLD_TARGET`.
- [ ] `ICE.melt_point` is still declared in `elements.py` (left for the
      realistic-rework BACKLOG item; not deleted).
- [ ] The `H` heat-overlay shows ice as cold (re-assert keeps it at −50); sanity-
      check in the SDL smoke (`SANDFALL_FRAMES=60 uv run sandfall`) and note it.
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the spreading-freeze integration test + the reworked melt tests):
uv run pytest tests/test_phase.py tests/test_fire.py -v

# Import smoke (also catches the water->ice import-cycle check):
uv run python -c "import sandfall"

# FULL suite -- regression guard (lava+water reaction, fire heating, brush):
uv run pytest

# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy); paint ICE in WATER and
# watch the freeze spread; confirm ice shows cold on the H overlay:
SANDFALL_FRAMES=60 uv run sandfall
```

All commands must exit zero. If the spreading-freeze test fails (ice count does
not grow), apply the step-3 `simulation.py` dormant-wake extension and re-run
before concluding the phase is done. Do NOT weaken the spreading-freeze
assertion to `>=` the seed count — spreading is the whole point.

## Documentation Updates

- The `rules/ice.py` module docstring (step 1) is the source of truth for the
  persistent-cold-source model and the temporary no-ambient-melt behavior;
  `rules/water.py`'s freeze bullet (step 2b) gets a one-phrase note.
- `docs/ARCHITECTURE.md` — if it describes ice as "melts above 0°C" or lists the
  thermal-melt rule, update it to the persistent-cold-source + contact-melt
  model and note the realistic-rework BACKLOG item. If it does not describe
  ice's melt rule at that level, leave it. Note whichever you find in the
  reflection.

## Reflection & Commit

After implementation, write `02-ice-cold-source-reflection.md` in this directory.
**Specifically include:**
- The **dormant-wake decision and its evidence**: did the freeze spread WITHOUT
  adding ICE to condition 3 (confirming the analysis), or did it stall and
  require the `| (data == ICE)` extension? Quote the `ice_before`/`ice_after`
  counts from the integration test (the actual spread number).
- The `ICE_COLD_TARGET` value shipped (`-50`) and any tuning you applied to hit
  a satisfying spread rate; note it as a knob.
- Whether the `water -> ice` import introduced any cycle (it should not).
- The measured spread shape if you watched the SDL smoke (does the ice cube grow
  visibly in water? does the `H` overlay show ice cold?).
- Whether `docs/ARCHITECTURE.md` described ice's melt rule and was updated.
- Anything difficult/unexpected, deviations from this plan + why, and anything
  fun discovered.

Then make ONE atomic git commit covering all changes in this phase.

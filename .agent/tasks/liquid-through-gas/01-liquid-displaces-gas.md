# Phase 01: Liquid/powder displaces gas (the complement of buoyancy)

## Objective

Add one additive clause to `rules/_common.py::can_displace` so a **LIQUID or
POWDER** source may move into a **GAS** target (denser phase flows through
gas). Correct the `can_displace` docstring + module-docstring bullet (gases
are now displacable). Add three focused tests to the existing
`tests/test_gas_buoyancy.py` (reusing its `_warm_all` / `_WARM` helpers) and
repurpose one existing drift test whose water-flanks now shove the boxed
steam (the new correct behavior).

## Depends On

none — builds on the shipped buoyancy helper `is_riseable`
(`_common.py:55-63`), its `_LIQUID_IDS` frozenset (`_common.py:33-37`), the
gas rules (`steam.py` / `smoke.py`), `can_displace` itself
(`_common.py:40-52`), and `elements.py` `Phase` membership (GAS = EMPTY /
FIRE / SMOKE / STEAM; LIQUID = WATER / LAVA / ACID / BASE / OIL; POWDER =
SAND / GUNPOWDER). Scan order is bottom→top (`simulation.py:131`) with a
per-row randomized x-direction — the new tests are robust to both (see the
per-test traces below).

## Can Parallelize With

none — single-phase task.

## Recommended Agent

@implementer — small, well-specified edit: one `if … return True` clause and
a restructured final `return` in `can_displace`, two docstring touch-ups in
the same file, three new tests + one optional test appended to the existing
`test_gas_buoyancy.py`, and a repurpose of one existing drift test (change
its flank material from WATER to STONE so it no longer collides with the new
shove behavior). Read the overview's Decision #5 and Risks before editing the
drift test — its water-flanks shove the boxed steam once gases are
displacable (verified by trace), which is why it must be repurposed.

## Changes Required

- `src/sandfall/rules/_common.py` — insert one gas clause + restructure the
  final `return` in `can_displace` (`:48-52`); correct the `can_displace`
  docstring (`:41-46`); update the module-docstring bullet for
  `can_displace` (`:5-7`). No new import (`Phase` already at `:30`).
- `tests/test_gas_buoyancy.py` — append three new tests (water-through-steam
  sideways, water-through-steam down, sand-through-steam) + one optional
  fire-edge test; repurpose `test_drift_does_not_go_sideways_through_liquid`
  (`:172-202`) to flank with STONE (rename + docstring); extend the module
  docstring (`:1-22`) to mention the complement is also tested here.

> No changes to any rule file (`water.py` / `sand.py` / `lava.py` / `acid.py`
> / `base.py` / `oil.py` / `gunpowder.py` / `steam.py` / `smoke.py` /
> `fire.py`), `simulation.py`, `grid.py`, `config.py`, `elements.py`, or the
> renderer. Every liquid/powder rule already routes its movement through
> `can_displace`, so fixing the predicate fixes them all at once. No
> dormancy change (a liquid/powder-into-gas move is a swap → existing
> `moved` / `id_changed` wake fires).

## Implementation Instructions

### 1. `src/sandfall/rules/_common.py` — the `can_displace` clause

**1a. Insert the gas clause and restructure the final return** (`:48-52`).
The current body is:

```python
    if target_id == ElementId.EMPTY:
        return True
    src = ELEMENTS[src_id]
    target = ELEMENTS[ElementId(target_id)]
    return target.phase == Phase.LIQUID and target.density < src.density
```

Replace the final one-line `return` with a two-clause block (keep the EMPTY
and `src` / `target` lines byte-identical):

```python
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
```

> `Phase` is already imported (`:30`), so no import change. The
> `src.phase in (Phase.LIQUID, Phase.POWDER)` guard is what excludes gas-gas
> and (notionally) solid sources — see overview Decision #2.

**1b. Correct the `can_displace` docstring** (`:41-46`). It currently claims
*"Solids, gases, and same/higher-density liquids are not displacable"* —
gases now ARE displacable by liquids/powders. Before:

```python
    """True if an element ``src_id`` may move into a cell holding ``target_id``.

    A cell is displacable if it is EMPTY, or if it holds a strictly
    lower-density LIQUID (so denser powders/liquids sink through lighter
    liquids). Solids, gases, and same/higher-density liquids are not
    displacable.
    """
```

After:

```python
    """True if an element ``src_id`` may move into a cell holding ``target_id``.

    A cell is displacable if it is EMPTY; or if it holds a strictly
    lower-density LIQUID (so denser powders/liquids sink through lighter
    liquids); or if it holds a GAS and ``src_id`` is a LIQUID or POWDER -- the
    complement of :func:`is_riseable` (a denser phase flows through a gas:
    water flows through a steam wall, sand falls through steam). Solids and
    same/higher-density liquids are not displacable; gas-gas and solid sources
    never displace (the gas clause's ``src.phase in (LIQUID, POWDER)`` guard).
    """
```

**1c. Update the module-docstring bullet for `can_displace`** (`:5-7`).
Before:

```text
* :func:`can_displace` — the density/phase swap test (sand sinks in water;
  water itself only displaces EMPTY in v1 since no lower-density liquid
  exists yet).
```

After:

```text
* :func:`can_displace` — the density/phase swap test (sand sinks in water;
  water itself only displaces EMPTY in v1 since no lower-density liquid
  exists yet, but every liquid/powder also displaces any GAS -- the
  complement of :func:`is_riseable`: a denser phase flows through a gas, e.g.
  water through a steam wall, sand through steam).
```

### 2. `tests/test_gas_buoyancy.py` — new tests + one repurpose

The file already covers the gas↔liquid interaction and exposes the `_warm_all`
helper (`:37-46`) and the `_WARM = 80` constant (`:34`) — 60 <
`STEAM.condense_point` reversed... i.e. 80 > 60 (no condense) and 80 ≤ 100
=`WATER.boil_point` (no boil, since the water rule boils at strictly `>`
100). Reuse both for the new steam tests so the swap is the only thing under
test.

**2a. Extend the module docstring** (`:1-22`). Append one paragraph after the
existing "Temp choice for steam tests" block noting the complement is tested
here too:

```text
This file also tests the COMPLEMENT of buoyancy -- a denser phase flowing
THROUGH a gas (can_displace's gas clause): WATER flows sideways through a
steam wall, WATER sinks through STEAM, and SAND falls through STEAM. The two
directions are symmetric (denser phase down/in, lighter phase up) and must
coexist: a steam wall no longer dams flowing water, while steam still rises
through water (test_steam_rises_through_water). One legacy drift test was
repurposed to flank with STONE instead of WATER: once gases became
displacable the water-flanks shove the boxed steam (the new correct
liquid-through-gas behavior), which would confound the drift-is-air-only
assertion -- drift rejects any non-EMPTY cell identically, so stone flanks
preserve that lock.
```

**2b. Repurpose `test_drift_does_not_go_sideways_through_liquid`**
(`:172-202`). It currently flanks the boxed steam with WATER; under the fix
the water shoves the steam (verified by trace against the bottom→top scan),
so `g.get(1,1) == STEAM` no longer holds. Change the flank material to STONE
(drift is EMPTY-only for any non-EMPTY target, liquid or solid) and rename +
redoc. New version:

```python
def test_drift_does_not_go_sideways_into_non_empty() -> None:
    """Buoyancy is UPWARD only and DRIFT is EMPTY-only. A steam cell blocked
    above by STONE and flanked left/right by STONE cannot rise (stone is not
    riseable) and must NOT drift sideways into the stone (drift is EMPTY-only).
    The steam stays put.

    Flanks are STONE (not WATER) because, post gas-displacement fix, a WATER
    flank would shove the boxed steam sideways (the new correct
    liquid-through-gas behavior -- see test_water_flows_through_steam_sideways),
    which would confound this drift-is-air-only assertion. Drift rejects any
    non-EMPTY cell identically, so stone flanks lock the invariant without
    collision.
    """
    random.seed(0)
    g = Grid(3, 3)
    # Stone border on all four sides (top row, bottom row, left/right cols).
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    for x in range(g.width):
        g.set(x, 0, ElementId.STONE)
        g.set(x, 2, ElementId.STONE)
    # Steam in the middle; STONE on both sides (drift targets, but not EMPTY).
    g.set(1, 1, ElementId.STEAM)
    g.set_life(1, 1, 200)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 1) == ElementId.STEAM  # did not drift into the stone
```

> The previous version asserted `g.get(0,1)` / `g.get(2,1)` were WATER; with
> stone flanks those cells are STONE by construction (no need to re-assert,
> but you may add `assert g.get(0,1) == ElementId.STONE` for symmetry).

**2c. Water flows through a steam wall (sideways)** — the headline
complement proof. Boxed row so neither cell can fall; the only displacable
neighbor of the water is the steam.

```python
def test_water_flows_through_steam_sideways() -> None:
    """Complement of buoyancy: a denser phase flows THROUGH a gas. WATER beside
    a STEAM wall (both on a stone floor, stone bookends boxing the row) swaps
    sideways -- the water enters the steam's old cell and the steam is pushed
    to the water's old cell (then it would continue rising via is_riseable
    next step). Uniform warm temp (> STEAM.condense_point 60, <= WATER.boil_point
    100) keeps the steam gaseous so it isn't lost to condensation.

    Robust to scan order and the per-row x-randomization: if the steam is
    visited first it cannot rise (y-1 out of bounds) nor drift (both neighbors
    non-EMPTY), so it stays; the water then shoves it. If the water is visited
    first it shoves the steam directly. Either order yields the same swap.
    """
    random.seed(0)
    g = Grid(4, 2)
    # Row 1 (floor): all stone so neither cell can fall.
    for x in range(g.width):
        g.set(x, 1, ElementId.STONE)
    # Row 0: stone | WATER | STEAM | stone  (water boxed left by stone).
    g.set(0, 0, ElementId.STONE)
    g.set(1, 0, ElementId.WATER)
    g.set(2, 0, ElementId.STEAM)
    g.set_life(2, 0, 200)
    g.set(3, 0, ElementId.STONE)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(2, 0) == ElementId.WATER  # water flowed into the steam's cell
    assert g.get(1, 0) == ElementId.STEAM  # steam shoved to the water's old cell
```

**2d. Water falls through steam (down)** — the vertical complement. Stone
walls box the column so no sideways escape.

```python
def test_water_falls_through_steam() -> None:
    """Complement of buoyancy: WATER directly above STEAM sinks THROUGH it.
    After one step the water is below (in the steam's old cell) and the steam
    is above (in the water's old cell); the steam then continues rising via
    is_riseable. Stone walls box the column; warm temp keeps the steam gaseous.

    Robust to scan order: bottom->top visits the steam first -- it rises into
    the water above via is_riseable (the buoyancy path). Top->down would let
    the water sink via can_displace. Both yield the identical swap, so the
    assertions hold unseeded.
    """
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)  # floor
    g.set(1, 1, ElementId.WATER)  # water above...
    g.set(1, 2, ElementId.STEAM)  # ...steam below
    g.set_life(1, 2, 200)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 2) == ElementId.WATER  # water sank through the steam
    assert g.get(1, 1) == ElementId.STEAM  # steam bubbled up
```

**2e. Sand falls through steam** — proves the clause covers POWDER, not just
LIQUID. Sand has no temp interaction with steam at 80C (melt_point 1700), so
it stays sand; the steam stays gaseous (warm).

```python
def test_sand_falls_through_steam() -> None:
    """Complement of buoyancy extends to POWDERs too: SAND directly above STEAM
    sinks through it. After one step the sand is below and the steam above.

    Robust to scan order: if the steam is visited first it tries to rise into
    the sand -- is_riseable(SAND) is False (sand is POWDER, not EMPTY/LIQUID)
    -- so it stays; the sand then sinks via can_displace. The warm temp keeps
    the steam gaseous; sand does not melt at 80C (melt_point 1700).
    """
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)  # floor
    g.set(1, 1, ElementId.SAND)   # sand above...
    g.set(1, 2, ElementId.STEAM)  # ...steam below
    g.set_life(1, 2, 200)
    _warm_all(g)
    Simulation(g).step()
    assert g.get(1, 2) == ElementId.SAND   # sand sank through the steam
    assert g.get(1, 1) == ElementId.STEAM  # steam bubbled up
```

**2f. (OPTIONAL) Water displaces fire — current-behavior lock.** The same
clause lets water shove FIRE aside (no extinguish yet). This test is OPTIONAL:
FIRE's temp_spawn (800) is far above WATER.boil_point (100), and the
heat-diffusion pre-pass runs before movement, so the water cell adjacent to
fire may boil to STEAM mid-step and never shove the fire — making the
assertion fragile. Only include it if you can isolate the temp cleanly (e.g.
force the water cell cold via `grid.set_temp` AND confirm it does not boil on
this step); otherwise drop it and rely on the reflection note. If included:

```python
def test_water_displaces_fire_edge() -> None:
    """EDGE (current behavior, not a feature): the gas clause also lets WATER
    displace FIRE (a GAS) -- water shoves fire aside rather than dousing it,
    because there is no fire+water extinguish mechanic yet. The fire is pushed
    to the water's old cell and keeps its life; a proper extinguish is tracked
    as future work. Locked here so a later extinguish feature changes this test
    deliberately.

    NOTE: FIRE.temp_spawn is 800C (>> WATER.boil_point 100). The heat-diffusion
    pre-pass can boil the water cell before it moves, so this test forces the
    water cell cold and asserts the shove on step 1. If the boil path still
    wins on your seed, drop this test (it is optional) and record the edge in
    the reflection instead.
    """
    random.seed(0)
    g = Grid(3, 4)
    for y in range(g.height):
        g.set(0, y, ElementId.STONE)
        g.set(2, y, ElementId.STONE)
    g.set(1, 3, ElementId.STONE)  # floor
    g.set(1, 1, ElementId.WATER)
    grid_water_cold = 20  # AMBIENT; keep the water from boiling this step
    g.set_temp(1, 1, grid_water_cold)
    g.set(1, 2, ElementId.FIRE)
    g.set_life(1, 2, 30)
    Simulation(g).step()
    assert g.get(1, 2) == ElementId.WATER  # water shoved the fire
    assert g.get(1, 1) == ElementId.FIRE   # fire pushed to the water's old cell
```

> Do NOT make this optional test an acceptance criterion. If it is flaky,
> delete it; the fire-displacement edge is documented in the overview
> regardless.

## Acceptance Criteria

- [ ] `can_displace` in `rules/_common.py` returns True for a LIQUID or
      POWDER source moving into a GAS target (`can_displace(WATER, STEAM)`,
      `can_displace(SAND, SMOKE)`, `can_displace(LAVA, FIRE)` all True) and
      still returns True for EMPTY and strictly-lighter-liquid targets.
- [ ] `can_displace` returns False for gas-into-gas
      (`can_displace(SMOKE, STEAM)`), (notionally) solid-into-gas, solid
      targets, and same/higher-density-liquid targets — unchanged.
- [ ] **Water flows through a steam wall sideways** —
      `test_water_flows_through_steam_sideways` passes (water in the steam's
      old cell, steam in the water's old cell).
- [ ] **Water falls through steam** — `test_water_falls_through_steam`
      passes (water below, steam above after one step).
- [ ] **Sand falls through steam** — `test_sand_falls_through_steam`
      passes (sand below, steam above).
- [ ] **Buoyancy preserved (regression)** — `test_steam_rises_through_water`,
      `test_smoke_rises_through_water`, `test_steam_rises_through_oil`, and
      `test_steam_rises_to_surface_of_water_pool` pass UNCHANGED.
- [ ] **Drift stays EMPTY-only** — the repurposed
      `test_drift_does_not_go_sideways_into_non_empty` (stone flanks) passes;
      the steam does not drift into stone.
- [ ] **Gas-gas excluded** — `test_steam_does_not_rise_through_solid_or_gas`
      still passes (smoke above steam does not get shoved by the steam, and
      the smoke does not shove the steam — gas sources are excluded by the
      `src.phase in (LIQUID, POWDER)` guard).
- [ ] The `can_displace` docstring and module-docstring bullet no longer claim
      gases are not displacable; both mention the gas clause and its
      complement-of-`is_riseable` framing.
- [ ] No rule file, `simulation.py`, `grid.py`, `config.py`, `elements.py`,
      or renderer file is modified (only `_common.py` + the test file).
- [ ] Existing displacement tests stay green (`tests/test_water.py`,
      `tests/test_solids.py`, `tests/test_simulation.py`).
- [ ] Full suite stays green.
- [ ] All verification gates exit zero.

## Verification Commands

```bash
# Phase-focused tests (the gas<->liquid interaction file -- new + repurposed):
uv run pytest tests/test_gas_buoyancy.py -v

# Existing displacement suites stay green (no gas-blocking invariant relied on):
uv run pytest tests/test_water.py tests/test_solids.py tests/test_simulation.py -v

# Import sanity + the clause is wired:
uv run python -c "import sandfall; from sandfall.rules._common import can_displace; from sandfall.elements import ElementId; assert can_displace(ElementId.WATER, int(ElementId.STEAM)) and can_displace(ElementId.SAND, int(ElementId.STEAM)) and not can_displace(ElementId.SMOKE, int(ElementId.STEAM)) and can_displace(ElementId.WATER, int(ElementId.EMPTY)); print('liquid-through-gas OK')"

# FULL suite -- regression guard (nothing else broke):
uv run pytest

# Lint + format + types:
uv run ruff check . && uv run ruff format --check . && uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
#   Manual check: build a STEAM wall across a channel and pour WATER beside /
#   above it. Expect the water to flow THROUGH the steam (steam shoved aside /
#   bubbling up) instead of piling up against the wall as before. Drop SAND
#   onto steam -- expect it to fall through. Steam under a water pool should
#   still bubble up to the surface (buoyancy preserved).
```

All commands must exit zero. Do not proceed to the reflection/commit until
all six pass.

## Documentation Updates

- None required beyond the in-code docstrings. The `can_displace` docstring
  and the `_common.py` module-docstring bullet are updated in-place (steps
  1b / 1c) — that is the only doc surface this change touches.
- No `AGENTS.md`, README, or `BACKLOG.md` change (liquid-through-gas is a
  standalone physics fix; it is not a tracked deferred item).

## Reflection & Commit

After implementation, write `01-liquid-displaces-gas-reflection.md`. Include:
- whether the **three single-step swap tests** held as written (seed 0,
  `_WARM = 80`) or needed seed/temp tuning — in particular confirm
  `test_water_falls_through_steam` resolves via the buoyancy path (steam
  visited first, rises into the water) and still produces the asserted
  water-below / steam-above state;
- whether **`test_steam_rises_to_surface_of_water_pool`** stayed green
  unchanged over its 200-step run (the fix lets water shove steam, but the
  bottom→top scan visits the lower steam first each frame, so it should still
  climb — confirm);
- confirmation that **`test_drift_does_not_go_sideways_through_liquid`** was
  the ONLY existing test that needed repurposing (flanks stone, renamed), and
  that no other suite test relied on gases being impassable;
- whether the **optional fire-edge test** was included or dropped, and why
  (did the FIRE 800C diffusion pre-pass boil the adjacent water on step 1?);
- confirmation that **no rule file / `simulation.py` / `elements.py`** was
  touched and the gas clause's `src.phase in (LIQUID, POWDER)` guard correctly
  excludes gas-gas and solid sources.

Then make ONE atomic git commit covering `src/sandfall/rules/_common.py` and
`tests/test_gas_buoyancy.py`.

# Phase 02: Thermal combustion (fire = heat source; reactive ignition)

## Objective

**Replace** the probabilistic fire spread with temperature-driven combustion.
Fire no longer ignites its neighbors by chance; instead it **holds a burn-temp
(~800)** and lets the Phase 01 diffusion pass warm them. `WOOD` and `PLANT`
become **reactive rules**: each checks its OWN temperature, and if it exceeds the
element's `flashpoint`, the cell becomes `FIRE` (seeds life + sets burn-temp) and
returns `None`. Concretely: delete `SPREAD_FACTOR` and the neighbor-ignition loop
in `fire.py`; keep `SMOKE_CHANCE`, the smoke spawn, and fire's rise behavior.

## Depends On

01 (Thermal data model) — must have passed all its gates.

## Can Parallelize With

none — Phase 03's reactive transitions build on the contract this phase
formalizes.

## Recommended Agent

@implementer — behavior-changing refactor of the most complex existing rule
plus converting two static no-op rules into reactive ones. Tuning
(burn-temp vs flashpoint) matters; the deterministic test seeds make the tuning
verifiable.

## Changes Required

- `src/sandfall/rules/fire.py` — set/maintain `burn_temp` on the cell; **remove**
  `SPREAD_FACTOR` and the `_NEIGHBORS_8` ignition loop (`fire.py:59-72`); keep
  smoke + rise; update the docstring.
- `src/sandfall/rules/wood.py` — reactive: ignite to FIRE when `get_temp >
  flashpoint`.
- `src/sandfall/rules/plant.py` — reactive: ignite to FIRE when `get_temp >
  flashpoint`, in addition to its existing grow-near-water behavior.
- `tests/test_fire.py` — replace the probabilistic spread assertions with
  deterministic thermal ones (fire heats neighbors; wood ignites above
  flashpoint; stone never ignites).
- `tests/test_thermal_combustion.py` (NEW, optional split) or extend
  `test_fire.py` — the reactive wood/plant ignition tests.

## Implementation Instructions

> Re-read `fire.py`, `wood.py`, `plant.py`, `_common.py` before editing. The
> reactive-rule contract relaxation is documented in the overview Decision #7
> and mirrors the side-effect exception `fire.py:14-19` already acknowledges.

### 1. `src/sandfall/rules/fire.py`

**1a. Maintain burn-temp.** A fire cell must keep radiating heat each step, so at
the top of `update_fire` (after aging, `fire.py:51-57`) clamp the cell's temp to
at least the FIRE element's `burn_temp`. This re-asserts heat every step so
diffusion doesn't cool the fire below its source temperature while it still has
life:

```python
from ..elements import ELEMENTS, ElementId
...
_BURN_TEMP = ELEMENTS[ElementId.FIRE].burn_temp  # ~800, module-level constant

def update_fire(grid, x, y):
    # 1. Age; expire to EMPTY when life is exhausted.
    life = grid.get_life(x, y) - 1
    if life <= 0:
        grid.set(x, y, ElementId.EMPTY)
        grid.set_life(x, y, 0)
        grid.set_temp(x, y, AMBIENT_TEMP)   # expire cool
        return None
    grid.set_life(x, y, life)

    # 2. Maintain burn-temp: a living fire is a heat source. Re-assert >=
    #    burn_temp each step so diffusion carries heat outward but cannot
    #    quench the source while it still has life.
    if grid.get_temp(x, y) < _BURN_TEMP:
        grid.set_temp(x, y, _BURN_TEMP)
    ...
```

(Import `AMBIENT_TEMP` from wherever Phase 01 settled it.)

**1b. Remove the probabilistic spread.** Delete `SPREAD_FACTOR` (`fire.py:31`)
and the entire "Ignite flammable neighbors" block (`fire.py:59-72`), including
the `_NEIGHBORS_8` constant if it is now unused (it is — grep to confirm nothing
else reads it; smoke uses `_ABOVE`). Ignition is no longer fire's job: a
flammable neighbor ignites itself when diffusion raises ITS temp above its own
`flashpoint` (see steps 2/3 below).

**1c. Keep smoke + rise unchanged.** The `SMOKE_CHANCE` smoke spawn
(`fire.py:74-85`) and the rise logic (`fire.py:87-97`) stay exactly as they are.
Both already go through `swap` (which now carries temp from Phase 01) and
`set_life`; no further edits.

**1d. Update the docstring** (`fire.py:1-20`) to describe the new model:
"Fire is a heat SOURCE, not a spreader. It holds burn_temp (~800) each step while
it has life; the Simulation's diffusion pre-pass carries that heat to neighbors;
a flammable neighbor ignites ITSELF (via its own WOOD/PLANT rule) when its temp
exceeds its flashpoint. Smoke spawn and rise are unchanged." Remove the paragraph
about `SPREAD_FACTOR` and the per-neighbor probability formula.

### 2. `src/sandfall/rules/wood.py`

**2a. Make wood reactive.** Replace the pure no-op (`wood.py:14-16`) with a rule
that ignites when the cell's own temp exceeds the wood `flashpoint`. This is the
formal use of the reactive-rule relaxation (transform own cell in place, return
`None`):

```python
from __future__ import annotations

from ..elements import ELEMENTS, ElementId
from ..grid import Grid
from ._common import seed_fire_life

_ELM = ELEMENTS[ElementId.WOOD]


def update_wood(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Wood is static unless its own temperature exceeds its flashpoint.

    Thermal ignition (Phase 02): when ``get_temp(x,y) > flashpoint`` the cell
    becomes FIRE (seeds life, sets burn_temp) and returns None. The cell does
    not MOVE, so the moved-this-frame guard is unaffected (see the reactive-rule
    contract relaxation in the master plan). ``flashpoint == 0`` means never
    ignites; wood's flashpoint is set in ELEMENTS.
    """
    if _ELM.flashpoint > 0 and grid.get_temp(x, y) > _ELM.flashpoint:
        grid.set(x, y, ElementId.FIRE)
        grid.set_life(x, y, seed_fire_life())
        grid.set_temp(x, y, ELEMENTS[ElementId.FIRE].burn_temp)
    return None
```

### 3. `src/sandfall/rules/plant.py`

**3a. Add ignition to the existing grow rule.** Plant already grows near water
(`plant.py:35-56`); prepend a thermal-ignition check (same shape as wood) before
the growth logic. A burning plant neither grows nor needs water:

```python
_ELM = ELEMENTS[ElementId.PLANT]
_FIRE = ELEMENTS[ElementId.FIRE]


def update_plant(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Grow near water, OR ignite when hot (Phase 02)."""
    # Thermal ignition takes priority: a hot plant catches fire and stops growing.
    if _ELM.flashpoint > 0 and grid.get_temp(x, y) > _ELM.flashpoint:
        grid.set(x, y, ElementId.FIRE)
        grid.set_life(x, y, seed_fire_life())
        grid.set_temp(x, y, _FIRE.burn_temp)
        return None
    # ... existing grow-near-water logic unchanged ...
```

(Import `seed_fire_life` from `._common` and `ELEMENTS`/`ElementId` — plant.py
currently imports only `ElementId` and `Grid`; add the two imports.)

### 4. Tuning check (burn-temp vs flashpoint)

Combustion must actually **chain**: a single fire cell next to wood must, within
a bounded number of steps, raise the wood's temp above its flashpoint through
diffusion. Sanity-check the numbers Phase 01 set:

- `FIRE.burn_temp = 800`, `WOOD.flashpoint = 300`, `PLANT.flashpoint = 250`.
- One step of diffusion moves `rate * cond * (neighbor_sum - 4*temp)` per cell.
  With `rate=0.20`, `COND_EMPTY=0.10`, a wood cell adjacent (through air) to an
  800° fire gains on the order of `0.20 * 0.10 * (800 - 4*20) ≈ 15°/step` early
  on — so wood reaches 300° in well under 100 steps. Direct-adjacent (no air
  gap) is faster.

If the deterministic test in 5b shows wood NOT igniting within the step budget,
either raise `burn_temp`, lower `flashpoint`, or raise `COND_EMPTY`/`rate` —
tuning is an accepted part of this phase. **Pin the final values in the
reflection** so Phase 03's lava/water transitions inherit a known-good thermal
baseline.

### 5. Tests

The old `test_fire.py` probabilistic spread tests (`test_fire_ignites_wood_neighbor`,
`test_fire_ignites_plant_neighbor`) asserted *eventual* consumption under random
spread. Those are now DETERMINISTIC (heat-driven) and should assert the new
mechanism directly. Replace/augment:

**5a. Fire is a heat source.**

```python
def test_fire_heats_neighbors_deterministically():
    """A fire cell raises the temp of its orthogonal neighbors within a few
    steps (no randomness — pure diffusion)."""
    grid = Grid(width=5, height=5)
    # Floor + ring of EMPTY so the fire sits at (2,2) surrounded by air.
    for x in range(grid.width):
        grid.set(x, grid.height - 1, ElementId.STONE)
    grid.set(2, 2, ElementId.FIRE)
    grid.set_life(2, 2, 200)            # long-lived source
    grid.set_temp(2, 2, 800)            # burn_temp
    sim = Simulation(grid)
    before = grid.get_temp(2, 1)        # cell directly above the fire
    for _ in range(5):
        sim.step()
    assert grid.get_temp(2, 1) > before + 20   # warmed noticeably
    assert grid.get_temp(2, 1) < 800           # but not hotter than the source
```

**5b. Wood ignites when its OWN temp exceeds flashpoint (deterministic).**

```python
def test_wood_ignites_above_flashpoint():
    """A wood cell hotter than its flashpoint becomes FIRE on its next step."""
    from sandfall.elements import ELEMENTS
    grid = Grid(width=3, height=3)
    grid.set(1, 1, ElementId.WOOD)
    grid.set_temp(1, 1, ELEMENTS[ElementId.WOOD].flashpoint + 50)
    sim = Simulation(grid)
    sim.step()
    assert grid.get(1, 1) == ElementId.FIRE
    assert grid.get_life(1, 1) > 0
    assert grid.get_temp(1, 1) == ELEMENTS[ElementId.FIRE].burn_temp

def test_wood_below_flashpoint_does_not_ignite():
    from sandfall.elements import ELEMENTS
    grid = Grid(width=3, height=3)
    grid.set(1, 1, ElementId.WOOD)
    grid.set_temp(1, 1, ELEMENTS[ElementId.WOOD].flashpoint - 1)
    Simulation(grid).step()
    assert grid.get(1, 1) == ElementId.WOOD

def test_fire_next_to_wood_eventually_ignites_it():
    """End-to-end: a long-lived fire warms adjacent wood until it ignites.
    Deterministic (diffusion only); bounded step budget."""
    grid = Grid(width=5, height=5)
    for x in range(grid.width):
        grid.set(x, grid.height - 1, ElementId.STONE)
    grid.set(2, 3, ElementId.FIRE)
    grid.set_life(2, 3, 300)
    grid.set_temp(2, 3, 800)
    grid.set(2, 2, ElementId.WOOD)      # directly above the fire
    sim = Simulation(grid)
    ignited = False
    for _ in range(400):
        sim.step()
        if grid.get(2, 2) == ElementId.FIRE:
            ignited = True
            break
    assert ignited
```

**5c. Non-flammable material never ignites.** Replace the old
`test_fire_does_not_ignite_stone`: stone's `flashpoint == 0` (default, "never"),
so even at very high temp it stays stone.

```python
def test_stone_never_ignites_even_when_hot():
    """flashpoint == 0 means never; a hot stone stays stone."""
    grid = Grid(width=3, height=3)
    grid.set(1, 1, ElementId.STONE)
    grid.set_temp(1, 1, 2000)           # far above any flashpoint
    Simulation(grid).step()
    assert grid.get(1, 1) == ElementId.STONE
```

**5d. Keep the smoke + expiry tests.** `test_fire_emits_smoke`
(`test_fire.py:81-103`) and `test_isolated_fire_expires_to_empty`
(`test_fire.py:28-40`) still hold — smoke spawn and the age/expire path are
unchanged. Re-run them; they should pass as-is (the smoke test monkeypatches
`SMOKE_CHANCE`, which still exists).

### 6. Remove the now-dead `SPREAD_FACTOR` references

After deleting the spread loop, grep for `SPREAD_FACTOR` across `src/` and
`tests/` — it should have zero references. Any test that monkeypatched
`fire_mod.SPREAD_FACTOR` (none currently do, but verify) must be removed.

## Acceptance Criteria

- [ ] `SPREAD_FACTOR` no longer exists; `fire.py` has no neighbor-ignition loop
      (grep confirms zero references in `src/` and `tests/`).
- [ ] A living FIRE cell re-asserts `>= burn_temp` each step (it is a heat
      source); an expired fire resets to `AMBIENT_TEMP`.
- [ ] Fire's smoke spawn (`SMOKE_CHANCE`) and rise behavior are unchanged
      (existing smoke/expiry tests pass).
- [ ] `WOOD` and `PLANT` ignite to `FIRE` (seeded life + burn-temp) when their
      own temp exceeds their `flashpoint`; below it they do not (deterministic
      tests pass).
- [ ] A long-lived fire next to wood ignites the wood within a bounded step
      budget (combustion chains — the Phase 02 tuning gate).
- [ ] `STONE` (`flashpoint == 0`) never ignites however hot (test passes).
- [ ] `SMOKE_CHANCE` smoke test and the isolated-fire-expiry test still pass
      unchanged.
- [ ] All six gates exit zero.

## Verification Commands

```bash
# Phase-specific:
uv run pytest tests/test_fire.py -v
# Confirm SPREAD_FACTOR is fully gone:
rg -n 'SPREAD_FACTOR' src tests && echo 'STALE REFERENCE — fix before proceeding' || echo 'spread factor removed cleanly'

# The six gates (all must exit zero):
uv run python -c "import sandfall"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
#   Manual check on DISPLAY=:1: paint FIRE next to WOOD and watch the wood
#   ignite from heat (no longer instant probabilistic spread).
```

All commands must exit zero. Do NOT proceed to Phase 03 until all pass.

## Documentation Updates

- `docs/ARCHITECTURE.md` — Phase 04 writes the combustion section; this phase
  only needs the code + the docstring update in `fire.py`. Pin the final tuned
  burn-temp/flashpoint values in the reflection so Phase 03 and the Phase 04
  docs inherit them.

## Reflection & Commit

After implementation, write `02-thermal-combustion-reflection.md`. Include the
**final tuned values** (`FIRE.burn_temp`, `WOOD.flashpoint`, `PLANT.flashpoint`,
`DIFFUSION_RATE`, `COND_EMPTY`) and the measured step-count for the
fire-next-to-wood ignition (the combustion-chain latency). Then make ONE atomic
git commit covering all changes in this phase.

# Phase 03: Minimal Element Set (water, stone, wood, fire, smoke, plant)

## Objective

Implement the remaining 6 elements' physics as pure rule functions, register them in `RULES`, tune the `ELEMENTS` registry colors/properties, and add per-element tests. After this phase the simulation has all 7 elements interacting (fire ignites wood → smoke rises; plant grows near water; water flows; powders sink in liquids).

## Depends On

Phase 02 (Grid, Simulation, `RULES`, `ELEMENTS`, and the rule-signature convention `-> tuple[int,int] | None`).

## Can Parallelize With

Phase 04 (rendering & game loop). Phase 04 touches `renderer.py` + `game.py` + `__main__.py`; this phase touches `rules/*.py` + `elements.py` + tests. **Disjoint files** — safe to run concurrently. Coordinate only on the rule-signature convention (already fixed in Phase 02).

## Recommended Agent

@implementer

## Changes Required

- `src/sandfall/elements.py` — EDIT: tune colors/properties for WATER, STONE, WOOD, FIRE, SMOKE, PLANT (Phase 02 left placeholders; verify values are sensible). No enum changes.
- `src/sandfall/rules/water.py` — NEW.
- `src/sandfall/rules/stone.py` — NEW (also used as the basis for wood/plant "static" behavior).
- `src/sandfall/rules/wood.py` — NEW (static; flammability handled by fire).
- `src/sandfall/rules/fire.py` — NEW (gas-like, finite life, spreads).
- `src/sandfall/rules/smoke.py` — NEW (gas, rises, dissipates).
- `src/sandfall/rules/plant.py` — NEW (static; grows near water).
- `src/sandfall/rules/__init__.py` — EDIT: register all six new rules.
- `src/sandfall/state.py` — NEW (optional; see "Per-cell state" below).
- `tests/test_water.py`, `tests/test_fire.py`, `tests/test_smoke.py`, `tests/test_plant.py` — NEW.
- `tests/test_solids.py` — NEW (stone/wood static).
- `src/sandfall/grid.py` — likely NO change; if per-cell state is needed, see below.

## Implementation Instructions

### Rule signature (binding — set in Phase 02)

Every rule: `update_X(grid: Grid, x: int, y: int) -> tuple[int, int] | None`. Returns the destination cell the element moved into, or `None` if it did not move. (Solids return `None`; they don't move but may have side effects — see fire/plant.)

### Per-cell state: how to handle FIRE life & SMOKE life

Fire and smoke need a per-cell "life" counter. The grid only stores a `uint8` element ID — no room for life. **Three options; pick ONE and document in the reflection:**

- **Option A (recommended for v1):** A parallel `numpy.uint8` "life" array carried on the `Simulation` (or `Grid`) keyed by `(y, x)`. When fire is spawned, set life; each step decrement; on zero, clear the cell to EMPTY (and the life array entry). Simple, fast, vectorizable later.
- **Option B:** Encode life in the high bits of the cell (e.g. fire id + 4 bits of life). Clever but fragile — rejected for v1.
- **Option C:** A `dict[tuple[int,int], int]` of only-active cells. Slower but trivially correct; fine at our grid sizes.

**Decision: Option A.** Add to `Simulation` (or to `Grid` as an optional second array) a `life: np.ndarray` of shape `(height, width)`, dtype `uint8`, default 0. Spawners (fire rule, smoke rule) set `life[y, x] = <value>` when they create a FIRE/SMOKE cell. The rule for FIRE/SMOKE decrements `life[y, x]` each step; when it hits 0 the cell becomes EMPTY. Update Phase 02's `Simulation` to own this array and pass `life` into rules (extend rule signature to accept it, OR attach to Grid — pick a clean seam and be consistent). 

> If extending the rule signature would break Phase 02 tests, prefer attaching `life` as a `Grid.life` numpy array (defaulting to zeros) so Phase 02 code keeps working unchanged. Document the choice.

### `src/sandfall/rules/water.py` (LIQUID)

```python
def update_water(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    # 1. Down
    # 2. Down-left / down-right (randomized order)
    # 3. Left / right (randomized order) — flow horizontally into EMPTY.
    #    Optional: flow up to N cells sideways per step for snappier spread
    #    (keep N small, e.g. 2-3, to stay stable). v1: one cell sideways is fine.
    ...
```

Rules:
- Water only moves into EMPTY (no sinking other elements in v1).
- Returns destination `(nx, ny)` or `None`.
- Density-based swap with sand is handled by `sand.py` (Phase 02 already allows sand to displace liquids); water itself does not push sand.

### `src/sandfall/rules/stone.py` & `wood.py` & `plant.py` (SOLIDS — static movement)

A shared helper `update_static(grid, x, y)` returning `None`. Stone uses it directly. Wood uses it (flammability is a *property*; the FIRE rule reads it). Plant uses it as its *base* but then runs its growth check (below).

```python
# stone.py
from ..grid import Grid

def update_stone(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    return None
```

`wood.py` identical body (returns None). `plant.py` adds growth.

### `src/sandfall/rules/plant.py` (SOLID, grows near water)

**Rule (binding — documented in decision log):** plant grows by checking its 4-neighborhood (or 8) for a WATER cell; if found, with a small probability (e.g. 2% per step) it converts one EMPTY neighbor into a new PLANT cell. **Water is NOT consumed** (proximity-only requirement).

```python
import random
from ..elements import ElementId
from ..grid import Grid

GROW_CHANCE = 0.02
NEIGHBORS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1))

def update_plant(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    has_water = any(
        grid.in_bounds(x + dx, y + dy) and grid.get(x + dx, y + dy) == ElementId.WATER
        for dx, dy in NEIGHBORS
    )
    if not has_water:
        return None
    if random.random() < GROW_CHANCE:
        empty = [(x + dx, y + dy) for dx, dy in NEIGHBORS
                 if grid.in_bounds(x + dx, y + dy) and grid.get(x + dx, y + dy) == ElementId.EMPTY]
        if empty:
            nx, ny = random.choice(empty)
            grid.set(nx, ny, ElementId.PLANT)
            return (nx, ny)  # the newly grown cell — mark it moved so it won't grow again this frame
    return None
```

### `src/sandfall/rules/fire.py` (GAS-like, finite life)

Behavior each step:
1. Decrement `life[y, x]`. If `life <= 0`: set cell to EMPTY, return `None` (it died).
2. For each flammable neighbor (WOOD/PLANT with `flammability > 0`), with probability `min(1.0, target.flammability * SPREAD_FACTOR)`, convert it to FIRE and seed its life (e.g. `life = randrange(20, 40)`).
3. With small probability (e.g. 5%), spawn a SMOKE cell in an EMPTY neighbor above; seed its life.
4. Try to rise: move up `(x, y-1)` into EMPTY; else up-left/up-right (randomized); else stay. Return destination or `None`.

`SPREAD_FACTOR` ≈ 0.3 (tunable). Initial fire life ≈ `random.randint(20, 40)` frames.

### `src/sandfall/rules/smoke.py` (GAS, rises, dissipates)

Behavior:
1. Decrement `life[y, x]`. If `<= 0`: set EMPTY, return None.
2. Rise: up `(x, y-1)` into EMPTY; else up-left/up-right randomized; else drift left/right into EMPTY with small chance; else stay. Return destination or None.
3. Initial smoke life ≈ `random.randint(60, 120)` frames.

### `src/sandfall/rules/__init__.py` — register all

After Phase 02 registered SAND, Phase 03 adds:

```python
RULES[ElementId.WATER] = update_water
RULES[ElementId.STONE] = update_stone
RULES[ElementId.WOOD] = update_wood
RULES[ElementId.PLANT] = update_plant
RULES[ElementId.FIRE] = update_fire
RULES[ElementId.SMOKE] = update_smoke
```

(EMPTY has no rule; `Simulation.step` already skips it.)

### `src/sandfall/elements.py` — tune values

Verify (and adjust if needed) the placeholder values from Phase 02:
- WATER color `(40, 80, 200)`, density `1.0`.
- STONE `(120, 120, 120)`, density `10.0`.
- WOOD `(120, 72, 32)`, density `8.0`, `flammability=0.25`.
- FIRE `(255, 120, 20)`, density `0.1`.
- SMOKE `(90, 90, 90)`, density `0.05`.
- PLANT `(40, 160, 60)`, density `8.0`, `flammability=0.4`.

These are aesthetic/feel knobs — keep them but feel free to nudge for visual clarity.

### Tests (seed `random` for determinism; assert within bounds / eventually, NOT exact positions)

`tests/test_water.py`:
- Water placed mid-air falls one row per step until it hits a floor.
- A blob of water on a flat floor spreads out (after N steps, the water occupies a wider, shorter region — assert the bounding-box width increased and max height decreased).

`tests/test_solids.py`:
- Stone and wood never move across `step()` (place each alone; assert position unchanged over 10 steps).

`tests/test_fire.py`:
- Place a single FIRE next to a WOOD block; seed RNG; step many times (e.g. 200); assert at least one WOOD cell became FIRE or EMPTY (ignited/consumed), and at least one SMOKE cell appeared at some point.
- FIRE expires: isolated FIRE with no fuel becomes EMPTY after life exhausted (set life explicitly; step until gone).

`tests/test_smoke.py`:
- SMOKE rises (its y decreases over steps) and eventually dissipates to EMPTY.

`tests/test_plant.py`:
- PLANT adjacent to WATER grows: after enough steps (seed RNG, run ~500 steps with GROW_CHANCE), the plant count increases. (Use a high GROW_CHANCE via monkeypatch or set a tiny grid so the assertion is reliable.)
- PLANT with no nearby WATER does not grow.

For probabilistic tests, monkeypatch `random.random` / use `random.seed` and/or temporarily raise probabilities via module-level constants to make them deterministic. Document the technique in the reflection.

## Acceptance Criteria

- [ ] All six new rule files exist and follow the `-> tuple[int,int] | None` signature.
- [ ] `RULES` registry has entries for SAND, WATER, STONE, WOOD, FIRE, SMOKE, PLANT (7 total).
- [ ] FIRE and SMOKE use a per-cell life array (Option A) and expire to EMPTY when life hits 0.
- [ ] FIRE spreads to flammable neighbors (WOOD, PLANT) and can spawn SMOKE.
- [ ] WATER falls and spreads horizontally on a flat surface.
- [ ] PLANT grows only when adjacent to WATER; water is NOT consumed.
- [ ] STONE and WOOD are completely static.
- [ ] Sand displaces water (sinks) — covered by `sand.py` from Phase 02; add one test in `test_water.py` or `test_simulation.py` asserting SAND ends up below WATER when both are stacked.
- [ ] All tests pass; all five verification gates exit zero.

## Verification Commands

```bash
uv run python -c "import sandfall; from sandfall.rules import RULES; from sandfall.elements import ElementId; assert len(RULES) >= 6; print('ok')"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Phase-specific extra:
```bash
uv run pytest tests/test_water.py tests/test_fire.py tests/test_smoke.py tests/test_plant.py tests/test_solids.py -v
```

ALL must exit zero.

## Documentation Updates

- Write `.agent/tasks/sandfall/03-element-set-reflection.md`. Document: the per-cell-state decision (Option A vs B vs C), how probabilistic tests were made deterministic, and any tuning of density/spread/life constants.
- Note any deviation from the rule-signature convention so Phase 04/05 expectations align.

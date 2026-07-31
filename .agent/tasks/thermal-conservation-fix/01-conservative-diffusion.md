# Phase 01: Conservative diffusion + heat capacity (the thermal fix)

## Objective

Rewrite `thermal.diffuse_temps` from the **non-conservative own-conductivity
stencil** to a **conservative face-flux discretization** with **per-cell heat
capacity** (thermal inertia) and **round-to-nearest** (not truncation) back to
`int16`. Add a per-material heat-capacity LUT that mirrors the existing
conductivity LUT, thread it through the one caller (`Simulation.step`), update
the existing diffusion-math tests for the new formula, and ADD the key
conservation regression guard. This single phase fixes all three bugs documented
in `00-overview.md` (non-conservation, truncation drain, no thermal inertia).

## Depends On

none — first and only phase.

## Can Parallelize With

none — single phase.

## Recommended Agent

@implementer — one numerically-careful kernel rewrite + a frozen-dataclass
field addition + a new config/LUT pair + a signature change rippling to the
caller and tests. The numerics are subtle (the conservation argument is the
whole point), so read `00-overview.md` first and re-read every cited file before
editing (line numbers below are current at planning time and may have drifted).

## Changes Required

- `src/sandfall/config.py` — add a `CP_*` per-material heat-capacity block
  mirroring the `COND_*` block (`config.py:96-113`); update the stale
  stability comment (`config.py:88-93`) to the new bound
  `rate * max(cond) / min(cp) <= 0.25`.
- `src/sandfall/elements.py` — add a defaulted `heat_capacity: float = 1.0`
  field to the `Element` dataclass (after `conductivity`, `elements.py:81`);
  set `heat_capacity=` on each `ELEMENTS` entry.
- `src/sandfall/thermal.py` — add `build_heat_capacity_lut()` mirroring
  `build_conductivity_lut()` (`thermal.py:39-62`); rewrite `diffuse_temps`
  (`thermal.py:65-101`) to the face-flux form and change its signature to
  `diffuse_temps(temp, ids, cond_lut, cp_lut, rate)`; import the `CP_*`
  constants.
- `src/sandfall/simulation.py` — cache `self._cp_lut = build_heat_capacity_lut()`
  in `__init__` (`simulation.py:32-35`); pass it to `diffuse_temps` in `step`
  (`simulation.py:48`).
- `tests/test_thermal.py` — update every `diffuse_temps(...)` call to pass a cp
  LUT (build via `build_heat_capacity_lut()`); REPLACE
  `test_no_overshoot_at_stability_bound` with the new bound; ADD
  `test_diffusion_conserves_total_heat` (the key regression guard) and
  `test_build_heat_capacity_lut_shape_and_values`.

## Implementation Instructions

> Re-read each file before editing — line numbers below are current as of the
> `sandfall-temperature`-complete source and may have drifted. The signature
> change (`+cp_lut`) and the formula change MUST land in one coherent edit —
> the build breaks otherwise.

### 1. `src/sandfall/config.py`

**1a. Update the stale stability comment** at `config.py:88-93`. The current
text says the stencil is `new = temp + rate*cond*(...)` stable when
`rate * max(cond) <= 0.25`. Replace with the face-flux form and the NEW bound
`rate * max(cond) / min(cp) <= 0.25`:

```python
# Diffusion pre-pass tunables. diffuse_temps now uses a CONSERVATIVE face-flux
# (finite-volume) discretization with per-cell heat capacity:
#     flux across each interior face = k_face * rate * (t_left - t_right)
#     k_face = (cond[left] + cond[right]) / 2      (arithmetic mean)
#     new_t  = t + (net signed face flux into the cell) / cp[cell]
# The signed face fluxes telescope to zero over the grid, so total heat
# sum(cp*temp) is CONSERVED up to rounding/clip. The form reduces to standard
# explicit diffusion with coefficient rate*k/cp, so the stability bound is
#     rate * max(cond) / min(cp) <= 0.25
# With the defaults below: 0.20 * 0.50 (FIRE) / 0.5 (FIRE/SMOKE/STEAM) = 0.20
# <= 0.25 — comfortable. diffuse_temps additionally clips to [TEMP_MIN, TEMP_MAX].
DIFFUSION_RATE = 0.20
```

**1b. Add the `CP_*` heat-capacity block** immediately AFTER the `COND_*` block
(`config.py:109-113`, after `COND_GLASS = 0.10`). Mirror the `COND_*` pattern
exactly (same elements, same order). Every value MUST be > 0 (diffusion divides
by cp — a zero would be a divide-by-zero):

```python
# Per-material heat capacity (thermal inertia / thermal mass). Divides the
# temperature change in diffuse_temps: high cp = changes slowly = thermally
# massive (water/stone/lava); low cp = changes fast (gases); EMPTY (air) is the
# 1.0 baseline. Indexed by element id via build_heat_capacity_lut(). Every
# value is > 0 (diffusion divides by cp).
CP_EMPTY = 1.0    # air = baseline thermal mass
CP_SAND = 1.5
CP_WATER = 4.0    # high thermal mass (water heats/cools slowly)
CP_STONE = 2.0
CP_WOOD = 1.5
CP_FIRE = 0.5     # low mass (gas-like; changes fast)
CP_SMOKE = 0.5
CP_PLANT = 1.5
# Phase 03 new materials.
CP_STEAM = 0.5
CP_ICE = 2.0
CP_LAVA = 5.0     # VERY high thermal mass — lava persists (solidifies ~step 27)
CP_GLASS = 1.5
```

### 2. `src/sandfall/elements.py`

**2a. Add the `heat_capacity` field** to the `Element` dataclass right after
`conductivity` (`elements.py:81`). It MUST have a default (1.0) so every
existing `ELEMENTS` entry still constructs without spelling it out, and it
MUST come after the already-defaulted `conductivity` field (dataclass ordering
rule — defaulted fields after non-defaulted):

```python
    # Heat conductivity scalar in [0.0, 1.0]; also stored in the conductivity
    # LUT (config.COND_*). Kept on Element too so ELEMENTS is the single
    # registry a contributor edits when adding a material.
    conductivity: float = 0.0
    # Heat capacity / thermal inertia scalar (> 0). Divides the temperature
    # change in diffuse_temps: high cp = thermally massive (changes slowly);
    # also stored in the heat-capacity LUT (config.CP_*). Default 1.0 so every
    # existing entry still constructs.
    heat_capacity: float = 1.0
```

**2b. Set `heat_capacity=` on each `ELEMENTS` entry** (`elements.py:95-222`).
Set it adjacent to each `conductivity=` line. The values mirror Decision Log #2
in `00-overview.md`:

```python
ElementId.EMPTY:  Element(..., conductivity=0.10, heat_capacity=1.0)
ElementId.SAND:   Element(..., conductivity=0.15, heat_capacity=1.5)
ElementId.WATER:  Element(..., conductivity=0.35, heat_capacity=4.0, ...)
ElementId.STONE:  Element(..., conductivity=0.08, heat_capacity=2.0)
ElementId.WOOD:   Element(..., conductivity=0.12, heat_capacity=1.5, ...)
ElementId.FIRE:   Element(..., conductivity=0.50, heat_capacity=0.5, ...)
ElementId.SMOKE:  Element(..., conductivity=0.20, heat_capacity=0.5)
ElementId.PLANT:  Element(..., conductivity=0.12, heat_capacity=1.5, ...)
ElementId.STEAM:  Element(..., conductivity=0.25, heat_capacity=0.5, ...)
ElementId.ICE:    Element(..., conductivity=0.18, heat_capacity=2.0, ...)
ElementId.LAVA:   Element(..., conductivity=0.45, heat_capacity=5.0, ...)
ElementId.GLASS:  Element(..., conductivity=0.10, heat_capacity=1.5)
```

(Leave all other fields on each entry exactly as they are; only `heat_capacity`
is new. The `...` above is a placeholder for the unchanged fields — do not
literally write `...`.)

### 3. `src/sandfall/thermal.py`

**3a. Import the `CP_*` constants** in the existing import block
(`thermal.py:17-35`). Add them alongside the `COND_*` imports, in the same
order:

```python
from .config import (
    COND_EMPTY,
    COND_FIRE,
    COND_GLASS,
    COND_ICE,
    COND_LAVA,
    COND_PLANT,
    COND_SAND,
    COND_SMOKE,
    COND_STEAM,
    COND_STONE,
    COND_WATER,
    COND_WOOD,
    CP_EMPTY,
    CP_FIRE,
    CP_GLASS,
    CP_ICE,
    CP_LAVA,
    CP_PLANT,
    CP_SAND,
    CP_SMOKE,
    CP_STEAM,
    CP_STONE,
    CP_WATER,
    CP_WOOD,
    DIFFUSION_RATE,
    HEAT_VIZ_COLD,
    HEAT_VIZ_HOT,
    TEMP_MAX,
    TEMP_MIN,
)
```

**3b. Add `build_heat_capacity_lut()`** immediately AFTER
`build_conductivity_lut()` (`thermal.py:39-62`). It is the exact mirror — same
shape `(len(ElementId),)` float64, same element-id indexing, same element
ordering:

```python
def build_heat_capacity_lut() -> npt.NDArray[np.float64]:
    """Build the element-id -> heat-capacity LUT (mirrors build_conductivity_lut).

    Shape ``(len(ElementId),)`` float64; row ``int(eid)`` is that material's
    heat capacity (thermal inertia). Indexed by the grid's id array to get a
    per-cell heat-capacity field for :func:`diffuse_temps` (which divides the
    temperature change by cp). Every value is > 0 (diffusion divides by cp).
    """
    lut = np.zeros(len(ElementId), dtype=np.float64)
    lut[int(ElementId.EMPTY)] = CP_EMPTY
    lut[int(ElementId.SAND)] = CP_SAND
    lut[int(ElementId.WATER)] = CP_WATER
    lut[int(ElementId.STONE)] = CP_STONE
    lut[int(ElementId.WOOD)] = CP_WOOD
    lut[int(ElementId.FIRE)] = CP_FIRE
    lut[int(ElementId.SMOKE)] = CP_SMOKE
    lut[int(ElementId.PLANT)] = CP_PLANT
    # Phase 03 new materials (rows 8..11).
    lut[int(ElementId.STEAM)] = CP_STEAM
    lut[int(ElementId.ICE)] = CP_ICE
    lut[int(ElementId.LAVA)] = CP_LAVA
    lut[int(ElementId.GLASS)] = CP_GLASS
    return lut
```

**3c. Rewrite `diffuse_temps`** (`thermal.py:65-101`). Replace the whole
function (signature, docstring, body) with the conservative face-flux form.
The signature gains a required `cp_lut` parameter (positional, before the
defaulted `rate`, so callers must pass it explicitly — there is only one caller
and it is being updated in step 4):

```python
def diffuse_temps(
    temp: npt.NDArray[np.int16],
    ids: npt.NDArray[np.uint8],
    cond_lut: npt.NDArray[np.float64],
    cp_lut: npt.NDArray[np.float64],
    rate: float = DIFFUSION_RATE,
) -> npt.NDArray[np.int16]:
    """Advance the temperature field one CONSERVATIVE diffusion step.

    Finite-volume / face-flux discretization with per-cell heat capacity::

        flux across each interior face = k_face * rate * (t_left - t_right)
        k_face = (cond[left] + cond[right]) / 2          (arithmetic mean)
        new_t  = t + (net signed face flux into the cell) / cp[cell]

    The signed face fluxes telescope to zero over the grid (every flux appears
    once negative and once positive), so total heat ``sum(cp*temp)`` is
    CONSERVED up to rounding/clip — this is the fix for the non-conservative
    own-conductivity stencil and the int16-truncation drain the model shipped
    with. Per-cell heat capacity ``cp`` gives thermal inertia: high-cp
    materials (lava, water) change slowly; low-cp gases change fast.

    Computation is float64 throughout; the result is rounded to nearest
    (``np.rint``, NOT truncated toward zero) and cast to int16. Truncation
    biased every cell toward 0 each step; round-to-nearest makes the rounding
    drain negligible. The explicit form reduces to standard diffusion with
    coefficient ``rate*k/cp``, stable when ``rate*max(cond)/min(cp) <= 0.25``
    (defaults: 0.20*0.50/0.5 == 0.20). Walls are insulators: only INTERIOR
    faces carry flux (edge cells have fewer faces), so no heat crosses the grid
    edge. Pure / pygame-free -> unit-tested headlessly. Does NOT mutate
    ``temp`` in place; the caller (:meth:`Simulation.step`) assigns the result
    back.
    """
    cond = cond_lut[ids].astype(np.float64)  # (H, W) per-cell conductivity
    cp = cp_lut[ids].astype(np.float64)      # (H, W) per-cell heat capacity
    t = temp.astype(np.float64)

    # Face conductivities: arithmetic mean of the two cells sharing each face.
    kx = (cond[:, :-1] + cond[:, 1:]) / 2.0   # (H, W-1) vertical faces
    ky = (cond[:-1, :] + cond[1:, :]) / 2.0   # (H-1, W) horizontal faces
    # Signed heat crossing each face (positive = left/up -> right/down).
    flux_x = kx * rate * (t[:, :-1] - t[:, 1:])   # (H, W-1)
    flux_y = ky * rate * (t[:-1, :] - t[1:, :])   # (H-1, W)

    # Net heat INTO each cell: left/up neighbor loses (subtract), this cell
    # gains (add). sum(div) == 0 exactly -> total heat conserved up to rounding.
    div = np.zeros_like(t)
    div[:, :-1] -= flux_x   # left cell of each vertical face loses the flux
    div[:, 1:] += flux_x    # right cell of each vertical face gains it
    div[:-1, :] -= flux_y   # top cell of each horizontal face loses
    div[1:, :] += flux_y    # bottom cell of each horizontal face gains

    new_t = t + div / cp    # heat capacity -> thermal inertia
    np.clip(new_t, TEMP_MIN, TEMP_MAX, out=new_t)
    return np.rint(new_t).astype(np.int16)   # round-to-nearest (NOT trunc)
```

Notes for the implementer:
- The old body padded with `np.pad(..., mode="edge")` for insulated walls; the
  new form needs NO padding — only interior faces exist, so edge cells simply
  have fewer faces and no heat crosses the boundary. Drop the pad entirely.
- `np.rint` rounds half-to-even (banker's rounding); for the magnitudes here
  the difference from half-up is in the noise and the conservation test
  tolerance (±2 over 60 steps) absorbs it.
- `div / cp` is safe: every `CP_*` is > 0 and the default is 1.0.

### 4. `src/sandfall/simulation.py`

**4a. Cache the cp LUT in `__init__`** (`simulation.py:32-35`, right after
`self._cond_lut = build_conductivity_lut()`):

```python
from .thermal import build_conductivity_lut, build_heat_capacity_lut, diffuse_temps
...
class Simulation:
    def __init__(self, grid: Grid) -> None:
        self._grid = grid
        # Static for the whole run: only depends on config.COND_* / CP_* / ELEMENTS.
        self._cond_lut = build_conductivity_lut()
        self._cp_lut = build_heat_capacity_lut()
```

**4b. Pass `self._cp_lut` to `diffuse_temps` in `step`** (`simulation.py:48`).
`cp_lut` is positional in the new signature (right after `cond_lut`):

```python
        grid._temp = diffuse_temps(grid._temp, grid._data, self._cond_lut, self._cp_lut)
```

Also update the `Simulation` class docstring at `simulation.py:25-30` to mention
that the heat-capacity LUT is also cached in `__init__` (one sentence — mirror
the existing mention of the conductivity LUT).

### 5. `tests/test_thermal.py`

**5a. Update the imports** (`tests/test_thermal.py:17`) to also import
`build_heat_capacity_lut`:

```python
from sandfall.thermal import (
    build_conductivity_lut,
    build_heat_capacity_lut,
    diffuse_temps,
    thermal_to_rgb,
)
```

**5b. Update EVERY `diffuse_temps(...)` call** to pass a cp LUT (built once via
`build_heat_capacity_lut()`). In each of the existing diffusion-math tests
(`test_heat_flows_hot_to_cold`, `test_low_conductivity_transfers_slowly`,
`test_uniform_field_is_equilibrium`, `test_clips_to_int16_band`,
`test_diffuse_returns_new_array_does_not_mutate_input`), add `cp_lut =
build_heat_capacity_lut()` and pass it positionally after the cond LUT. For
example, in `test_heat_flows_hot_to_cold` (`tests/test_thermal.py:20-33`):

```python
def test_heat_flows_hot_to_cold() -> None:
    temp = np.full((3, 3), AMBIENT_TEMP, dtype=np.int16)
    temp[1, 1] = 1000
    ids = np.full((3, 3), int(ElementId.EMPTY), dtype=np.uint8)  # COND_EMPTY
    lut = build_conductivity_lut()
    cp_lut = build_heat_capacity_lut()
    out = diffuse_temps(temp, ids, lut, cp_lut, rate=0.2)
    assert out[1, 1] < 1000
    for y, x in [(0, 1), (2, 1), (1, 0), (1, 2)]:
        assert out[y, x] > AMBIENT_TEMP, (y, x, out[y, x])
    for y, x in [(0, 0), (0, 2), (2, 0), (2, 2)]:
        assert out[y, x] == AMBIENT_TEMP, (y, x, out[y, x])
```

These five existing tests still hold under the new formula (heat still flows
hot→cold; low-conductivity still transfers slowly; uniform field is still
equilibrium; clip still clamps; input is still not mutated). They only need the
extra argument.

**5c. REPLACE `test_no_overshoot_at_stability_bound`**
(`tests/test_thermal.py:59-68`). The old form pinned the obsolete bound
`rate*cond == 0.25`. Replace with the NEW bound `rate*max(cond)/min(cp) == 0.25`
and a uniform-cp field so the test isolates the cond/cp ratio:

```python
def test_no_overshoot_at_stability_bound() -> None:
    # The NEW stability bound is rate*max(cond)/min(cp) <= 0.25. At the bound,
    # a 0/1000 pair cannot swing past [0, 1000]. Use uniform cp (air, CP_EMPTY)
    # so the test isolates the cond/cp ratio; drive rate so the bound is hit
    # exactly: rate = 0.25 * cp / cond.
    temp = np.zeros((1, 2), dtype=np.int16)
    temp[0, 1] = 1000
    ids = np.zeros((1, 2), dtype=np.uint8)  # EMPTY
    lut = build_conductivity_lut()
    cp_lut = build_heat_capacity_lut()
    cond = lut[int(ElementId.EMPTY)]
    cp = cp_lut[int(ElementId.EMPTY)]
    out = diffuse_temps(temp, ids, lut, cp_lut, rate=0.25 * cp / cond)
    assert int(out.min()) >= 0
    assert int(out.max()) <= 1000
```

**5d. ADD the key regression guard `test_diffusion_conserves_total_heat`.**
This is the test that would have caught the original non-conservation bug. A
mixed-material scenario (one hot FIRE cell + one cold ICE cell in ambient air)
must keep `sum(cp*temp)` within a small tolerance (±2 over 60 steps, allowing
only rounding). Assert the OLD formula's catastrophic drain does NOT happen:

```python
def test_diffusion_conserves_total_heat() -> None:
    # The regression guard for the whole fix: in a mixed-material field the
    # CONSERVATIVE face-flux form must keep total heat sum(cp*temp) nearly
    # constant (rounding only). The OLD own-conductivity stencil drained this
    # scenario to ~0; this test fails on the old formula and passes on the new.
    lut = build_conductivity_lut()
    cp_lut = build_heat_capacity_lut()
    # 1x25 row of air with one hot FIRE cell and one cold ICE cell.
    temp = np.full((1, 25), AMBIENT_TEMP, dtype=np.int16)
    ids = np.full((1, 25), int(ElementId.EMPTY), dtype=np.uint8)
    temp[0, 5] = 1000
    ids[0, 5] = int(ElementId.FIRE)
    temp[0, 19] = -5
    ids[0, 19] = int(ElementId.ICE)
    heat0 = float((cp_lut[ids] * temp.astype(np.float64)).sum())
    for _ in range(60):
        temp = diffuse_temps(temp, ids, lut, cp_lut)  # default rate
        heat = float((cp_lut[ids] * temp.astype(np.float64)).sum())
        # Total heat must stay within +/-2 of the initial heat (rounding only).
        # The OLD non-conservative formula drained this to ~0; the bound below
        # would fail loudly on it.
        assert abs(heat - heat0) <= 2.0, (heat0, heat)
```

(Tolerance rationale: 60 steps × at most a couple rounding units per step at
the mixing front. The prototype measured ~10/410 drain for the pure-ice case;
this mixed case is well inside ±2 over 60 steps with round-to-nearest. If the
implementer observes the assertion is tighter than reality, widen to a
documented value — but do NOT loosen past ±5 without flagging it; the whole
point is that the drain is tiny, not zero.)

**5e. ADD `test_build_heat_capacity_lut_shape_and_values`**, mirroring
`test_build_conductivity_lut_shape_and_values` (`tests/test_thermal.py:87-101`):

```python
def test_build_heat_capacity_lut_shape_and_values() -> None:
    # Mirrors the conductivity LUT test: shape (len(ElementId),) float64,
    # indexed by element id. Pin a few representative values incl. LAVA=5.0
    # (the high-thermal-mass case driving the "lava persists" behavior).
    from sandfall.config import CP_EMPTY, CP_FIRE, CP_LAVA, CP_STONE

    lut = build_heat_capacity_lut()
    assert lut.shape == (len(ElementId),)
    assert lut.dtype == np.float64
    assert lut[int(ElementId.EMPTY)] == CP_EMPTY
    assert lut[int(ElementId.FIRE)] == CP_FIRE
    assert lut[int(ElementId.STONE)] == CP_STONE
    assert lut[int(ElementId.LAVA)] == CP_LAVA
    # Every registered element has cp > 0 (diffusion divides by cp).
    for eid in ElementId:
        assert lut[int(eid)] > 0.0
```

**5f. Note: the 1×1 phase-transition tests in `tests/test_phase.py` are
unaffected.** On a 1×1 grid there are no interior faces, so `div == 0` and
`new_t == t` exactly — diffusion is a no-op. Do not touch those tests.

## Acceptance Criteria

- [ ] `config.py` has a `CP_*` block mirroring `COND_*` (same elements, same
      order); every `CP_*` value is > 0; the diffusion-tunables comment states
      the NEW bound `rate*max(cond)/min(cp) <= 0.25` with the default-walk
      `0.20*0.50/0.5 == 0.20`.
- [ ] `Element` has a defaulted `heat_capacity: float = 1.0` field (after
      `conductivity`); every existing `ELEMENTS` entry still constructs and
      each has its intended `heat_capacity` value (LAVA 5.0, WATER 4.0, etc.).
- [ ] `thermal.build_heat_capacity_lut()` returns a `(len(ElementId),)` float64
      array indexed by element id, all values > 0; LAVA row == 5.0 (test
      passes).
- [ ] `thermal.diffuse_temps(temp, ids, cond_lut, cp_lut, rate=...)` implements
      the conservative face-flux form, rounds to nearest (`np.rint`) to int16,
      is pure (returns a new array, does not mutate input), and walls are
      insulators (only interior faces carry flux).
- [ ] The five carry-over diffusion tests pass (hot→cold; low-cond slow;
      uniform equilibrium; clip band; no mutation) with the new signature.
- [ ] `test_no_overshoot_at_stability_bound` passes with the NEW bound.
- [ ] **`test_diffusion_conserves_total_heat` passes** — total heat
      `sum(cp*temp)` stays within ±2 of the initial value over 60 steps in the
      mixed FIRE+ICE scenario. (This is the test that would have caught the
      original bug; it is the headline acceptance criterion.)
- [ ] `Simulation.__init__` caches `self._cp_lut = build_heat_capacity_lut()`;
      `Simulation.step` passes it to `diffuse_temps`.
- [ ] **Re-verified, not pre-emptively changed:**
      `tests/test_fire.py::test_fire_next_to_wood_eventually_ignites_it` and
      `tests/test_phase.py::test_lava_water_reaction_is_deterministic_across_scan_orders`
      both still pass (record the actual outcome in the reflection; re-tune
      ONLY if a test fails, and document the re-tune).
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the new conservation test is the headline):
uv run pytest tests/test_thermal.py -v

# Import smoke:
uv run python -c "import sandfall"

# Full suite — re-verifies the fire/phase/lava ripple tests:
uv run pytest

# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
```

All commands must exit zero. If a ripple test (`test_fire...ignites` or
`test_lava_water_reaction...`) fails, re-tune the MINIMUM needed to make it
pass (do not widen budgets gratuitously) and document the re-tune in the
reflection. Do NOT touch the `lava.py` steam-acceptance workaround.

## Documentation Updates

- `docs/ARCHITECTURE.md` — if it describes the diffusion formula or the
  `rate*max(cond) <= 0.25` bound, update it to the face-flux form and the new
  `rate*max(cond)/min(cp) <= 0.25` bound, and mention per-material heat
  capacity. If it does not describe diffusion numerics, leave it (the
  `sandfall-temperature` Phase 04 doc pass is the canonical place and may not
  have covered the formula). Note whichever you find in the reflection.
- Inline docstrings in `thermal.py`, `config.py`, and `simulation.py` are
  updated as part of the code changes above (they are the source of truth).

## Reflection & Commit

After implementation, write `01-conservative-diffusion-reflection.md` in this
directory. **Specifically include:**
- The re-verification outcome of the two ripple tests
  (`test_fire_next_to_wood_eventually_ignites_it`,
  `test_lava_water_reaction_is_deterministic_across_scan_orders`) — did they
  pass as-is, or need a re-tune (to what)?
- Confirmation that `test_diffusion_conserves_total_heat` passes and the
  actual measured `|heat - heat0|` over 60 steps (the headline number).
- The status of the now-redundant `lava.py` steam-acceptance workaround
  (Decision Log #4 in `00-overview.md`) — confirm it was left in place and is
  now belt-and-suspenders.
- Anything difficult/unexpected, deviations from this plan + why, and anything
  fun discovered.

Then make ONE atomic git commit covering all changes in this phase.

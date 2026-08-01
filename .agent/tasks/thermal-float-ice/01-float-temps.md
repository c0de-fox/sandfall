# Phase 01: Float temps foundation (`_temp` → `float32`)

## Objective

Switch `Grid._temp` from `int16` to `float32` so heat diffusion reaches phase-
transition thresholds **precisely** (no rounding stall), and thread the dtype
change through the temperature accessors, the diffusion kernel's return type,
and the heat-overlay mapper. This removes root cause #1 of the freeze regression
(the `np.rint(...).astype(np.int16)` at `thermal.py:156` that rounds a water
cell's ~0.5°C/step cooling back up, sticking it at ~+6°C forever). This phase is
the **foundation**: it does not by itself fix the freeze (ice is still only −5°C
and still melts at `>0` — that is Phase 02), but it makes the diffusion precise
so Phase 02's cold source can actually drive water across the `<= 0` threshold.

## Depends On

none — first phase.

## Can Parallelize With

none — Phase 02 depends on this.

## Recommended Agent

@implementer — a dtype swap that is mechanically small but ripples through
several annotations and one test tolerance that MUST be re-measured (not
assumed). Read `00-overview.md` first (especially Decision Log #1, Risks #1-#2),
then re-read `src/sandfall/grid.py`, `src/sandfall/thermal.py`,
`src/sandfall/simulation.py`, `tests/test_thermal.py`, and `tests/test_grid.py`
before editing (line numbers below are current at planning time and may have
drifted). **Run the conservation-test re-measurement as a real experiment**
(step 5d) and report the actual drift number — do NOT keep the loose `±15`.

## Changes Required

- `src/sandfall/grid.py` — `_temp` dtype `int16` → `float32`: the class-level
  annotation (`:84`), the `__init__` allocation (`:94`), the `temp` property
  return type (`:123`), `get_temp -> float` (`:212-221`), and
  `set_temp(value: float)` (`:223-235`). `fill_circle` (`:300, :317`) and
  `migrate_grid` (`:363`) need no logic change (assigning `AMBIENT_TEMP` int
  into a float array and copying a float overlap are both fine) — just confirm.
- `src/sandfall/thermal.py` — `diffuse_temps` input/return type `int16` →
  `float32` (`:102-108, :156`): drop `np.rint(...).astype(np.int16)`, return
  `new_t.astype(np.float32)` after the clip (computation stays `float64`
  internally). `thermal_to_rgb` input type `int16` → `float32` (`:195`) — its
  body already upcasts via `temp.astype(np.float64)` (`:215`), so only the
  annotation + docstring need touching.
- `src/sandfall/simulation.py` — **no logic change.** `temp_before = grid._temp`
  (`:115`), the `diffuse_temps` reassign (`:116`), and the thermal-wake
  comparison `grid._temp != temp_before` (`:163`) all work identically on
  `float32` (the comparison is now *more* sensitive — a sub-degree cooling
  registers as a change and wakes the cell, which is exactly what lets the freeze
  front advance in Phase 02). Just re-read to confirm.
- `src/sandfall/brush.py`, `src/sandfall/elements.py`, `src/sandfall/config.py`
  — **no change.** `brush.py` assigns `temp_spawn` ints into the (now float)
  array (`:92`); the `temp_spawn`/`flashpoint`/threshold `Element` fields and the
  `AMBIENT_TEMP`/`TEMP_*`/`COND_*`/`CP_*` constants stay `int` (assigned into
  float arrays — fine). Listed so the implementer audits rather than assumes.
- `tests/test_thermal.py` — migrate the `diffuse_temps` test temp arrays from
  `dtype=np.int16` to `dtype=np.float32`; **re-measure** the conservation
  tolerance (was `±15`, should be `<< 1`); rename `test_clips_to_int16_band` →
  `test_clips_to_band` (no rounding now); add a precision test asserting a cell
  cooling toward 0 *crosses* 0 (the int16 model could not).
- `tests/test_grid.py` — update `assert grid.temp.dtype == np.int16` →
  `np.float32` (`:223`); `get_temp` now returns `float` so `== 1500` still holds
  (`1500.0 == 1500`) — audit for any `int`-annotated test locals mypy flags.

## Implementation Instructions

> Re-read each file before editing — line numbers below are current at the
> `thermal-conservation-fix`-complete source and may have drifted. The dtype
> change must land coherently: `grid._temp` (float32) ↔ `diffuse_temps` return
> (float32) ↔ the `temp` property (float32). A half-applied swap leaves a dtype
> mismatch.

### 1. `src/sandfall/grid.py`

**1a. Class-level annotation** (`grid.py:84`):

```python
    _temp: npt.NDArray[np.float32]
```

**1b. `__init__` allocation** (`grid.py:94`):

```python
        self._temp = np.full((height, width), AMBIENT_TEMP, dtype=np.float32)
```

**1c. `temp` property** (`grid.py:122-131`) — update the return type annotation
and the docstring's "int16 view" phrasing:

```python
    @property
    def temp(self) -> npt.NDArray[np.float32]:
        """Raw ``(height, width)`` float32 view of per-cell temperature.

        Intended read-only access (e.g. for the diffusion pass and the heat
        overlay); mutate via :meth:`set_temp` so clipping is applied
        consistently. The diffusion pre-pass assigns a freshly-computed array
        back to the grid's ``_temp`` directly (see :class:`Simulation.step`).
        Stored as float32 so diffusion reaches phase-transition thresholds
        precisely (no int16 rounding stall).
        """
        return self._temp
```

**1d. `get_temp`** (`grid.py:212-221`) — return `float` instead of `int`:

```python
    def get_temp(self, x: int, y: int) -> float:
        """Return the temperature at ``(x, y)`` as a plain ``float``.

        Raises ``IndexError`` if out of bounds.
        """
        if not self.in_bounds(x, y):
            raise IndexError(
                f"({x}, {y}) out of bounds for {self._width}x{self._height} grid"
            )
        return float(self._temp[y, x])
```

**1e. `set_temp`** (`grid.py:223-235`) — annotate `value: float` (the clip
math is unchanged; `float < int` comparisons work):

```python
    def set_temp(self, x: int, y: int, value: float) -> None:
        """Set the temperature at ``(x, y)`` (clipped to ``[TEMP_MIN, TEMP_MAX]``).

        Out-of-bounds writes are silently ignored to mirror :meth:`set` /
        :meth:`set_life`.
        """
        if not self.in_bounds(x, y):
            return
        if value < TEMP_MIN:
            value = TEMP_MIN
        elif value > TEMP_MAX:
            value = TEMP_MAX
        self._temp[y, x] = value
```

**1f. `fill_circle`** (`grid.py:300, :317`) — **no logic change.** The two
`self.set_temp(cx, cy, AMBIENT_TEMP)` and `self._temp[y, x] = AMBIENT_TEMP`
writes assign an `int` into a `float32` array (numpy upcasts silently). Confirm
by re-reading; do not edit unless something is off.

**1g. `migrate_grid`** (`grid.py:363`) — **no logic change.**
`new._temp[:h, :w] = old._temp[:h, :w]` copies float32 → float32 now (both grids
allocate float32). Confirm; do not edit.

Also update the module docstring at `grid.py:11` ("A third parallel ``int16``
array ``temp``") to say `float32`, and the line at `grid.py:17-18` referencing
the clip band to mention float storage. Keep it to the dtype wording; do not
rewrite the whole docstring.

### 2. `src/sandfall/thermal.py`

**2a. `diffuse_temps` signature + return** (`thermal.py:102-108, :156`). Change
the input and return annotations from `int16` to `float32`, and replace the
final `return np.rint(new_t).astype(np.int16)` with a plain float32 cast. The
function body between them is UNCHANGED (it already computes in float64 and
clips). The new tail:

```python
def diffuse_temps(
    temp: npt.NDArray[np.float32],
    ids: npt.NDArray[np.uint8],
    cond_lut: npt.NDArray[np.float64],
    cp_lut: npt.NDArray[np.float64],
    rate: float = DIFFUSION_RATE,
) -> npt.NDArray[np.float32]:
```

… and the final two lines become:

```python
    new_t = t + div / cp  # heat capacity -> thermal inertia
    np.clip(new_t, TEMP_MIN, TEMP_MAX, out=new_t)
    return new_t.astype(np.float32)  # float32 storage (no int16 rounding stall)
```

Update the docstring's last paragraph (`thermal.py:124-133`): remove the
"rounded to nearest (`np.rint`, NOT truncated) and cast to int16" sentence and
the truncation-drain rationale (that was the *old* bug; storage is now float32,
so there is no rounding at all). Replace with one sentence noting the result is
cast to `float32` (computation stays `float64`) so diffusion reaches thresholds
precisely. Keep the conservation argument, the stability bound, and the
"pure / pygame-free / does not mutate" sentences — they are all still true.

**2b. `thermal_to_rgb` signature** (`thermal.py:195`). Change the input
annotation from `int16` to `float32`:

```python
def thermal_to_rgb(temp: npt.NDArray[np.float32]) -> npt.NDArray[np.uint8]:
```

The body is UNCHANGED — `t = np.clip(temp.astype(np.float64), lo, hi)`
(`thermal.py:215`) already upcasts, so a float32 input maps identically. Just
verify the docstring (`thermal.py:196-210`) does not say "int16 temp field"
(any such phrase → "float32 temp field").

### 3. `src/sandfall/simulation.py` — NO edit (audit only)

Re-read `simulation.py:115-116, :163`. Confirm:
- `temp_before = grid._temp` is now float32 — fine.
- `grid._temp = diffuse_temps(...)` assigns float32 → float32 — fine.
- `active_next |= grid._temp != temp_before` compares float32 ≠ float32 — fine,
  and is now MORE sensitive (a sub-degree cooling wakes the cell). This is the
  mechanism Phase 02 relies on; do NOT change it.

If everything is as described, make NO edit to `simulation.py`. Record the
confirmed-no-edit in the reflection.

### 4. `tests/test_grid.py`

**4a. The dtype assertion** (`test_grid.py:223`):

```python
    assert grid.temp.dtype == np.float32
```

**4b. Audit the `get_temp` assertions.** `test_set_temp_get_temp_round_trip`
(`:229-233`) does `assert grid.get_temp(1, 1) == 1500` — this still passes
(`1500.0 == 1500` is `True`), no edit needed. `test_set_temp_clips_to_band`
(`:236-243`) compares against `TEMP_MIN`/`TEMP_MAX` (ints) — `float == int`
holds, no edit. If mypy flags any test local annotated `: int` that now receives
a `get_temp()` float, change the annotation to `float` (expected to be none, but
fix what mypy reports). The `test_migrate_grid_*` temp assertions
(`:332, :336, :419`) compare against ints and hold under float — no edit.

### 5. `tests/test_thermal.py`

**5a. Migrate `diffuse_temps` test temp arrays to float32.** In every test that
builds a `temp` array and calls `diffuse_temps`, change `dtype=np.int16` →
`dtype=np.float32`. The affected tests (re-read each before editing):
- `test_heat_flows_hot_to_cold` (`:28`)
- `test_low_conductivity_transfers_slowly` (`:45`)
- `test_uniform_field_is_equilibrium` (`:61`)
- `test_no_overshoot_at_stability_bound` (`:74`)
- `test_clips_to_int16_band` (`:87`) — also RENAME to `test_clips_to_band`
  (see 5c)
- `test_diffuse_returns_new_array_does_not_mutate_input` (`:96`)
- `test_diffusion_conserves_total_heat` (`:151`)

The math is identical (diffuse_temps upcasts to float64 internally); only the
storage dtype of the test fixtures changes to match real usage. The assertions
all still hold under float.

**5b. `test_no_overshoot_at_stability_bound`** (`:69-83`) — the bound
`rate*max(cond)/min(cp) <= 0.25` is UNCHANGED (float storage does not change the
stability argument). Migrate the temp array to float32 (5a). The assertions
`int(out.min()) >= 0` / `int(out.max()) <= 1000` still hold at the bound (no
overshoot); optionally tighten to `float(out.min()) >= 0.0` /
`float(out.max()) <= 1000.0` for dtype honesty — either is acceptable, pick
float for cleanliness.

**5c. RENAME `test_clips_to_int16_band` → `test_clips_to_band`** (`:86-92`).
Migrate the temp array to float32 (5a). Update the test to assert the clip band
`[TEMP_MIN, TEMP_MAX]` (NOT an int16 band — there is no int16 anymore). The
assertion `int(out.max()) <= TEMP_MAX` is the real check and still holds; the
rename just removes the now-misleading "int16" from the name.

**5d. RE-MEASURE the conservation tolerance in `test_diffusion_conserves_total_heat`**
(`:141-162`). This is the careful step. The current bound is `±15`
(`:162`), deliberately loose to absorb the int16 round-to-nearest drain
(~10/410). With float32 storage the face-flux telescopes to zero in float64
computation and the only residual is the per-step float32 cast (~1e-6 relative),
so the measured drift over 60 steps should be **<< 1**.

Steps:
1. First, migrate the temp array to float32 (5a).
2. Temporarily print the measured `abs(heat - heat0)` at the end of the 60-step
   loop (or assert against a very tight provisional bound like `0.5`) and RUN
   `uv run pytest tests/test_thermal.py::test_diffusion_conserves_total_heat -v -s`.
3. Read the actual measured number. Set the assertion bound to that real value
   rounded up with a small margin (e.g. if it measures `0.03`, use `0.5`; if it
   measures `0.0001`, use `0.01`).
4. Update the tolerance comment to quote the MEASURED number and explain it is
   float32 cast residual (not the old int16 drain). **If the measured drift
   exceeds `1.0`, STOP and flag it** — that would indicate an unexpected issue
   (do not silently widen past `1.0`).

Provisional bound to ship if re-measurement is inconclusive: `1.0`. The
headline point is that it is **far inside the old `±15`** — do NOT keep `±15`.

**5e. ADD `test_diffusion_reaches_threshold_precisely`** — the test that
demonstrates the whole point of this phase (a cell cooling toward 0 actually
crosses 0, which the int16 model could not). Append after
`test_diffusion_conserves_total_heat`:

```python
def test_diffusion_reaches_threshold_precisely() -> None:
    # The headline float-temps test: a warm cell next to a very cold FIXED cell
    # must cool ACROSS the 0 freeze threshold over enough steps. Under the old
    # int16 + np.rint storage, the ~0.5C/step cooling rounded back up and the
    # cell stuck at ~+6 forever (the freeze-regression root cause). With float32
    # storage the cell's temp drops monotonically past 0.
    lut = build_conductivity_lut()
    cp_lut = build_heat_capacity_lut()
    # 1x10 row of EMPTY air; cell 0 is a pinned cold source at -200, cell 9 is
    # a warm cell at 20 (AMBIENT). All EMPTY so conductivity/cp are uniform and
    # the cold propagates smoothly. (We do NOT call any rule here -- this tests
    # the diffusion kernel alone, so "pinned" just means we re-set cell 0 each
    # step to model a persistent source, exactly as ice will in Phase 02.)
    temp = np.full((1, 10), 20.0, dtype=np.float32)
    ids = np.full((1, 10), int(ElementId.EMPTY), dtype=np.uint8)
    temp[0, 0] = -200.0
    crossed = False
    for _ in range(200):
        temp = diffuse_temps(temp, ids, lut, cp_lut)
        temp[0, 0] = -200.0  # re-pin the cold source each step
        if temp[0, 9] <= 0.0:
            crossed = True
            break
    assert crossed, temp[0, 9]  # the far cell cooled below 0 -- int16 could not
```

(The far cell crossing 0 within 200 steps is the pass condition; the int16 model
could never get it below ~+6 because each step's cooling rounded away. This is
the regression guard for root cause #1.)

**5f. `thermal_to_rgb` tests** (`:173-219`) — these build `dtype=np.int16`
arrays. They still PASS (thermal_to_rgb upcasts to float64 internally), so they
are technically optional to migrate. For consistency, migrate their temp arrays
to `dtype=np.float32` too (the `np.full(..., 20, dtype=np.int16)` →
`np.float32`, the `HEAT_VIZ_HOT + 5000` arrays, the `np.arange` sweep). If you
prefer to leave them as int16 because the function is genuinely dtype-agnostic,
that is also acceptable — but note `thermal_to_rgb`'s signature is now annotated
`float32`, so mypy will flag an int16 argument. **Recommended: migrate them to
float32** to keep the annotations honest and the tests aligned with real input.

## Acceptance Criteria

- [ ] `Grid._temp` is `np.float32` (class annotation `:84`, `__init__` `:94`,
      `temp` property `:123`); `get_temp -> float` (`:212`); `set_temp(value:
      float)` (`:223`); module docstring (`:11`) says `float32`.
- [ ] `diffuse_temps` is annotated `temp: npt.NDArray[np.float32] -> npt.NDArray[
      np.float32]`; the `np.rint(...).astype(np.int16)` return is GONE, replaced
      by `new_t.astype(np.float32)`; computation still `float64`; clip still
      applies; the docstring's int16/truncation rationale is removed.
- [ ] `thermal_to_rgb` is annotated `temp: npt.NDArray[np.float32]`; body
      unchanged (upcasts to float64); docstring does not say "int16".
- [ ] `simulation.py` is **unchanged** (audit-only); recorded in reflection.
- [ ] `test_grid.py` `dtype` assertion is `np.float32`; all `get_temp`/temp
      assertions still pass under float; no mypy `int`-annotation errors.
- [ ] `test_thermal.py`: all `diffuse_temps` test arrays are `float32`;
      `test_clips_to_int16_band` renamed to `test_clips_to_band`;
      `test_diffusion_conserves_total_heat` tolerance **re-measured** to the
      real float drift (far inside the old `±15`; flag if `> 1.0`) with the
      measured number quoted in the comment.
- [ ] **`test_diffusion_reaches_threshold_precisely` passes** — a warm cell
      next to a pinned −200 source cools across 0 within 200 steps (the
      regression guard for root cause #1; fails on the int16 model).
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the new precision test + the re-measured conservation test):
uv run pytest tests/test_thermal.py tests/test_grid.py -v

# Import smoke:
uv run python -c "import sandfall"

# FULL suite -- regression guard (fire/phase/lava/brush tests exercise get_temp
# and the temp arrays under the new float dtype):
uv run pytest

# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
```

All commands must exit zero. Do NOT proceed to Phase 02 until the FULL suite is
green. If a ripple test fails (most likely a `dtype == np.int16` assertion or an
`int`-annotated test local flagged by mypy), fix the test/type — do NOT revert
the float change or weaken the precision test.

## Documentation Updates

- Inline docstrings in `grid.py` (`temp` property, module header) and
  `thermal.py` (`diffuse_temps`, `thermal_to_rgb`) are updated as part of the
  code changes above (they are the source of truth).
- `docs/ARCHITECTURE.md` — if it describes the temp field as `int16` or mentions
  the round-to-nearest/truncation behavior, update it to `float32` and note the
  rounding stall is gone. If it does not describe the storage dtype, leave it.
  Note whichever you find in the reflection.

## Reflection & Commit

After implementation, write `01-float-temps-reflection.md` in this directory.
**Specifically include:**
- The **measured** conservation drift `abs(heat - heat0)` over 60 steps (the
  headline number — it should be `<< 1`; quote the actual value and the bound
  you shipped).
- Confirmation that `simulation.py` needed NO edit (the audit result).
- The mypy audit result: were any `int`-annotated `get_temp` callers (rules or
  tests) flagged? If so, which and how fixed.
- Whether `docs/ARCHITECTURE.md` described the temp dtype and was updated.
- Whether the `thermal_to_rgb` tests were migrated to float32 or left as int16
  (and why mypy did/didn't flag them).
- Anything difficult/unexpected, deviations from this plan + why, and anything
  fun discovered.

Then make ONE atomic git commit covering all changes in this phase.

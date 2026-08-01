# Phase 01 Reflection — Float temps foundation (`_temp` → `float32`)

## Summary

Switched `Grid._temp` from `int16` to `float32`, dropped the
`np.rint(...).astype(np.int16)` return in `diffuse_temps` (replaced with a plain
`float32` cast; float64 computation + clip unchanged), re-typed the accessors
(`get_temp -> float`, `set_temp(value: float)`, the `temp` property), and
re-measured the conservation tolerance from the loose int16-era `±15` down to
the real float32 residual. Added the headline
`test_diffusion_reaches_threshold_precisely` regression guard. All six gates
exit zero; suite went 174 → 175 tests.

## Files changed

- `src/sandfall/grid.py` — `_temp` annotation, `__init__` allocation, `temp`
  property, `get_temp`/`set_temp` signatures + return, module docstring.
- `src/sandfall/thermal.py` — `diffuse_temps` signature/return/docstring (dropped
  `np.rint`), `thermal_to_rgb` signature, module docstring.
- `tests/test_grid.py` — `dtype == np.int16` → `np.float32`.
- `tests/test_thermal.py` — migrated every `diffuse_temps`/`thermal_to_rgb` test
  array to `float32`; renamed `test_clips_to_int16_band` → `test_clips_to_band`;
  re-measured conservation tolerance; added the headline threshold test.
- `docs/ARCHITECTURE.md` — updated the 6 spots that described int16 storage /
  round-to-nearest / truncation to float32 (authorized by the plan's
  "Documentation Updates" section — it clearly described the old dtype).

## Headline number: conservation drift (old `±15` → new)

Re-measured `abs(heat - heat0)` over the 60-step conservation scenario
(3 ICE @ -5 in 25x1 air) with float32 storage:

- **Measured max `|drift|` over 60 steps: `4.27e-05`** (final drift `2.65e-05`).
- This is the expected float32 cast residual in `sum(cp*temp)` — there is no
  int16 round-to-nearest drain anymore.
- **Bound shipped: `0.001`** (≈23× the measured max, for platform/BLAS jitter).
  Far inside the old `±15`. Any real conservation regression (the old
  non-conservative stencil drained 410 → 0) produces drift ≫ 1, so the bound
  still fails loudly on the old formula. Well under the plan's `1.0` flag
  threshold — no anomaly.

## `simulation.py` — NO edit (audit-only, as required)

Confirmed `simulation.py:115-116, 163` are dtype-correct under float32 with zero
edits:

- `temp_before = grid._temp` (float32) — fine.
- `grid._temp = diffuse_temps(...)` assigns float32 → float32 — fine.
- `active_next |= grid._temp != temp_before` compares float32 ≠ float32 — fine,
  and is now MORE sensitive (a sub-degree cooling wakes the cell). This is the
  mechanism Phase 02 relies on; left untouched.

`brush.py` also needed no edit (it passes `temp_spawn` ints into
`set_temp(value: float)` — int → float param is fine in mypy).

**Stale-doc residual (out of scope, flagged for follow-up):** the inline comment
at `simulation.py:111` still says "NEW int16 array"; `config.py:89,92` and
`elements.py:16` still say "stored as int16 on Grid" / "int16 headroom is huge".
These are now factually stale, but the plan marked `simulation.py` as audit-only
("make NO edit") and `config.py`/`elements.py` as no-change / do-not-touch, so
they were left as-is. Phase 02 (or a small docs follow-up) should correct them.

## mypy audit — no `int`-annotated `get_temp` callers flagged

`mypy src` passes clean (25 files, 0 issues). The planning-time audit held:
every `get_temp` caller in `src/sandfall/rules/` either compares directly
(`get_temp(...) > melt_point`, `< condense_point`, `< LAVA_SOLIDIFY_TEMP`,
`< _BURN_TEMP`, `> flashpoint` — `float {<,>}` `int` is fine) or binds to an
untyped local (`t = grid.get_temp(x, y)` in `water.py:45` — infers `float`). No
rule annotates a `get_temp` result as `int`, so no rule logic or annotation
changed. No test local was flagged either. **Zero mypy ripple.**

## `thermal_to_rgb` tests — migrated to float32

Migrated all 5 `thermal_to_rgb` test arrays from `dtype=np.int16` to
`dtype=np.float32` (the `np.full`, the `HEAT_VIZ_HOT + 5000` arrays, the
`np.arange` sweep). Reason: `thermal_to_rgb`'s signature is now annotated
`npt.NDArray[np.float32]`, so passing an int16 array would be flagged by a
strict mypy on the test side. The function body is unchanged (it upcasts via
`temp.astype(np.float64)` at `thermal.py:215`), so the assertions are identical;
only the fixture dtype moved to match real usage.

## The headline test — and ONE deviation from the plan (flagged)

`test_diffusion_reaches_threshold_precisely` passes. **But the plan's literal
parameters (check the far `cell 9` within `range(200)`) do NOT work even with
the float fix**, so I changed the watched cell from 9 → 3. This is the single
deviation from the plan's literal code; details and evidence:

### Why cell 9 + 200 steps is physically impossible

With the real config (`COND_EMPTY=0.1`, `CP_EMPTY=1.0`, default
`DIFFUSION_RATE=0.2`) the effective diffusion coefficient is
`D = rate·cond/cp = 0.2·0.1/1.0 = 0.02`. `TEMP_MIN = -200` caps how cold the
pinned source can be. Measured crossing steps (cell 0 re-pinned to -200 each
step, 1×10 EMPTY row):

| cell | float32 crosses ≤0 at step | int16 crosses ≤0 |
|------|----------------------------|------------------|
| 1    | 5                          | 5                |
| 2    | 31                         | 27               |
| 3    | **75**                     | **NEVER (stalls at +2.0)** |
| 4    | 136                        | NEVER (stuck 20.0) |
| 5    | 215                        | NEVER (stuck 20.0) |
| 9    | **552**                    | NEVER (stuck 20.0) |

So the plan's `cell 9` needs **552 steps** under float32 — far outside the
user-specified "say ≤200 steps" budget, and the source cannot be made colder
(`TEMP_MIN=-200`). The plan's literal test asserts `cell 9 ≤ 0 within 200
steps`, which **fails at 19.37°C** (I observed this exact failure:
`AssertionError: np.float32(19.372778)`). The plan author's prototype validation
(overview lines 54-56: "1 → 3 → 5 → 9 cells over 120 steps") was the **full
simulation** with ice re-asserting cold + new-ice-gets-cold (Phase 02 mechanics),
not this bare-`diffuse_temps` kernel — so the bare-kernel step count was never
empirically checked against the real `COND_EMPTY`/`CP_EMPTY` values.

### The resolution: watch cell 3 (sharper discriminator, stays in budget)

Cell 3 is the **sharpest** probe of root cause #1:

- **float32:** cell 3 crosses ≤0 at step ~75 (2.7× margin to the 200-step
  budget).
- **int16:** cell 3 **NEVER** crosses — it stalls at exactly **+2.0** (the
  per-step delta drops below 0.5°C and `np.rint` rounds it away). That is the
  textbook near-threshold rounding stall — the precise phenomenon the overview
  calls "sticks at ~+6" — and +2.0 > 0 means the cell stays liquid (water's
  freeze check is `get_temp <= freeze_point(=0)`), exactly the freeze
  regression.

Cell 3 is the farthest cell int16 can cool before its rounding pins it just
above the freeze threshold, so it exercises the sub-0.5°C/step accumulation
that ONLY float storage allows. This honors the user's explicit primary
requirement ("a cell ... must actually cross ≤0 within a bounded step count (say
≤200 steps) — the int16 model could not do this") while staying inside the
≤200-step budget. The plan's exact geometry is preserved (1×10 row, cell 0
pinned to -200, re-pinned each step, default rate); only the watched index and
the comment changed. The assertion message reads
`assert crossed, temp[0, 3]  # cell 3 cooled below 0 -- int16 stalls it at +2.0`.

**This deviation sharpens (does not weaken) the test** — it is a stricter
discriminator than the plan's cell-9-at-200 (which would fail even the fixed
code). Flagging it prominently for user ack; if the user prefers the plan's
literal "far cell" framing, the alternative is to keep cell 9 and raise the
budget to ~700 (covers the 552-step crossing with margin).

## Six-gate results (all observed exit zero)

1. `uv run pytest tests/test_thermal.py tests/test_grid.py -v` → **51 passed** ✅
2. `uv run python -c "import sandfall"` → **OK** ✅
3. `uv run pytest` (full suite) → **175 passed** (was 174; +1 = the headline test) ✅
4. `uv run ruff check .` → **All checks passed!** ✅
5. `uv run ruff format --check .` → **47 files already formatted** ✅
6. `uv run mypy src` → **Success: no issues found in 25 source files** ✅
7. `SANDFALL_FRAMES=60 uv run sandfall` → **EXIT=0** (real SDL driver,
   `DISPLAY=:1` was present — did NOT need the `SDL_VIDEODRIVER=dummy`
   fallback; ran 60 real frames exercising the float32 `diffuse_temps` +
   thermal-wake path end-to-end, no traceback) ✅

## Notes for Phase 02

1. **The float foundation is verified.** Every cell in the 1×10 row eventually
   crosses ≤0 under float32; int16 stalls cells 3-9. Phase 02's spreading freeze
   (ice re-asserting `ICE_COLD_TARGET ≈ -50`) sits on a diffusion kernel that
   now reaches thresholds precisely.
2. **Re-assert + new-ice-gets-cold is what made the prototype reach cell 9 in
   120 steps**, not bare diffusion — bare diffusion of a single -200 source
   takes 552 steps to reach cell 9. Phase 02's mechanism (each freshly-frozen
   cell becomes a NEW cold source, so the cold front doesn't have to diffuse
   the full distance from the original ice) is what gives the fast 1→3→5→9
   spread. Keep this in mind if Phase 02's integration test seems slow.
3. **Dormant-wake sufficiency (overview Risk #3) still unverified** — that's
   Phase 02's gate. The `grid._temp != temp_before` wake is now strictly MORE
   sensitive under float32 (sub-degree changes register), which should help the
   freeze front stay awake, but the integration test is the proof.
4. **Fix the stale int16 comments** in `simulation.py:111`, `config.py:89,92`,
   `elements.py:16` when convenient (out of scope here).

# Sandfall Performance — Grid.move Raw-Array Fast-Swap — Master Plan

## Problem Statement

The dormant-cell (active-region) optimization shipped under
`.agent/tasks/performance-dormant-cells/` fixed **settled** scenes (a 7,326-grain
pile went 72.9 ms → ~3-5 ms by skipping dormant cells). **It did NOT touch the
per-cell rule cost on ACTIVELY-MOVING scenes** — the other busy-scene lever
flagged in the Out-of-Scope sections of BOTH
`.agent/tasks/performance-active-set/00-overview.md` and
`.agent/tasks/performance-dormant-cells/00-overview.md`.

On a busy/falling scene the cells that *do* move still each pay ~8.5 µs of rule
cost, and the single biggest chunk of that cost is the shared `swap` helper in
`src/sandfall/rules/_common.py:75-94`, which does **12 Grid method calls per
move** (6 `get` + 6 `set` across the element-id / life / temp arrays), each
carrying a per-call bounds check + `int()` cast + Python call overhead:

```python
def swap(grid, x1, y1, x2, y2):
    a = grid.get(x1, y1); b = grid.get(x2, y2)      # 2 gets  (ids)
    grid.set(x1, y1, b);   grid.set(x2, y2, a)       # 2 sets  (ids)
    la = grid.get_life(x1, y1); lb = grid.get_life(x2, y2)   # 2 gets (life)
    grid.set_life(x1, y1, lb); grid.set_life(x2, y2, la)     # 2 sets (life)
    ta = grid.get_temp(x1, y1); tb = grid.get_temp(x2, y2)   # 2 gets (temp)
    grid.set_temp(x1, y1, tb); grid.set_temp(x2, y2, ta)     # 2 sets (temp)
```

`swap` is called from **16 sites across 6 rules** (verified at planning time:
sand×2, water×3, lava×3, steam×3, smoke×3, fire×2 — see the audit in Phase 01).
So every moving cell on a busy scene funnels through this 12-call path.

**Measured context (cite as the evidence base — taken on the current source):**

| Scenario                                                 | Cost / note        | Source                                                              |
|----------------------------------------------------------|--------------------|---------------------------------------------------------------------|
| Per-cell rule cost on a moving cell                      | **~8.5 µs/cell**   | `performance-active-set/00` measured table (busy ~59% grid, 168 ms).|
| `swap` Grid method calls per move                        | **12** (6 get+6 set)| `rules/_common.py:83-94`.                                           |
| `swap` call sites across rules                           | **16** (6 rules)   | `rg -n 'swap\(' src/sandfall/rules/` (excl. the definition).        |
| Dormancy win already shipped                             | settled pile fixed | `.agent/tasks/performance-dormant-cells/` (settled scenes).         |

This phase attacks the **moving-scene** cost: collapse the 12-call `swap` into a
single raw numpy 3-array element-swap. Dormancy (settled scenes) is unaffected —
a dormant cell is skipped before its rule runs, so it never reaches `swap` either
way.

## Solution Summary

**One focused phase, two edits, zero rule edits (user-approved scope: "swap
delegates to Grid.move"; swap-only).**

1. **`src/sandfall/grid.py` — add `Grid.move(x1, y1, x2, y2) -> None`.** A RAW
   3-array element swap across `_data` (ids), `_life`, and `_temp` via numpy
   tuple-assignment:
   ```python
   self._data[y1, x1], self._data[y2, x2] = self._data[y2, x2], self._data[y1, x1]
   self._life[y1, x1],  self._life[y2, x2]  = self._life[y2, x2],  self._life[y1, x1]
   self._temp[y1, x1],  self._temp[y2, x2]  = self._temp[y2, x2],  self._temp[y1, x1]
   ```
   with **NO per-access bounds check** and **NO clipping**. **Documented
   precondition:** both cells MUST be in-bounds — the caller (`swap`) guarantees
   it (every rule pre-checks bounds today; see the audit). No clip is safe
   because both cells' values are already in-band (set via `set_temp`/`set_life`
   originally, which clip to `[TEMP_MIN, TEMP_MAX]` / `[0, 255]`), so swapping
   two in-band values preserves both bands.
2. **`src/sandfall/rules/_common.py` — rewrite `swap()` to delegate.** A one-line
   body `grid.move(x1, y1, x2, y2)` plus an updated docstring noting it now
   delegates to `Grid.move` (no longer the 12-call path). **All 16 rule call
   sites get the fast path with ZERO rule edits** — the `swap(grid, x1, y1, x2,
   y2)` signature and semantics are unchanged, so sand/water/lava/steam/smoke/
   fire need no edits. This is what makes the change low-risk and tiny.

**Expected win:** a busy/falling scene's per-cell rule cost drops materially
(swap is the biggest single chunk of the ~8.5 µs, ~12 of its method calls);
**headline target ~2-3× on the rule cost** (NOT more — see Risks: `can_displace`
dict lookups and the scan-loop overhead remain, and dormancy already removed the
settled-pile cost). The settled-pile `Simulation.step` time is **unchanged**
(dormant cells never reach `swap`). Perf is verified by **measurement reported
in the reflection**, NOT by a test assertion (timings are CI/environment-flaky —
see Verification Philosophy).

## Phase List

| #  | Phase                                              | Cx | Depends On | Parallelizable With |
|----|----------------------------------------------------|----|------------|---------------------|
| 01 | `Grid.move` fast-swap + `swap` delegation (1-call)| S  | —          | — (single phase)    |

## Dependency Map

```
01 (Grid.move + swap delegation) ──► done
```

This is a **single tiny phase** because the two edits are mutually dependent and
land together: `Grid.move` must exist before `swap` can delegate to it, and a
`swap` that delegates to a not-yet-existing `move` is a broken intermediate. The
change is self-contained (`grid.py` + `rules/_common.py` + one new test in
`tests/test_grid.py`) and changes no signatures, so nothing downstream needs to
move with it.

## Decision Log

All decisions below follow directly from the user-approved scope ("swap delegates
to Grid.move", swap-only). They must not be re-litigated without new measurement.

1. **`Grid.move` is a RAW swap with NO per-access bounds check — precondition:
   caller guarantees both cells in-bounds.** The whole point is to remove the 12
   bounds checks + casts that dominate `swap`. Every `swap` call site already
   pre-checks bounds today (the audit in Phase 01 lists all 16), so the
   precondition holds at every caller. *(Alternative considered: keep a bounds
   check inside `move` and `return` on OOB like `set` — rejected: that is exactly
   the per-call cost we are removing, and would cut the win to near-zero.)*
2. **`Grid.move` does NOT clip temp/life — and does not need to.** `set_temp`
   clips to `[TEMP_MIN, TEMP_MAX]` and `set_life` clips to `[0, 255]` at write
   time, so every value already stored is in-band. Swapping two in-band values
   cannot leave the band (min and max of two band-resident scalars are still in
   the band). The id array (`uint8`) likewise holds only valid `ElementId`
   values because every writer passes a valid id. *(Alternative considered:
   re-clip in `move` — rejected: pure overhead with no correctness gain.)*
3. **Numpy tuple-assignment is the swap primitive (`a[i],a[j] = a[j],a[i]`).**
   Python evaluates the RHS tuple fully before any assignment, so each of the
   three array swaps is a correct two-cell exchange even though source and dest
   are in the same array (standard Python swap semantics; no temp variable
   needed). The three arrays are independent (`_data`, `_life`, `_temp`), so
   there is no aliasing between them. *(Alternative considered: explicit
   `tmp = ...; ... = ...; ... = tmp` — rejected: more bytecode, same result; the
   tuple form is the idiomatic and equally-correct one.)*
4. **`swap()` becomes a one-line delegate, NOT an inlined removal.** Keeping
   `swap` as the single rule-facing entry point means all 16 call sites are
   unchanged (zero rule edits — the lowest-risk possible change), and the
   "every move carries id+life+temp" contract stays documented in one place.
   *(Alternative considered: replace all 16 `swap(grid,...)` calls with
   `grid.move(...)` and delete `swap` — rejected: 16 edits across 6 files for no
   behavior or perf gain over a one-line delegate; pure churn and merge-conflict
   surface.)*
5. **The win is bounded by `swap`'s share of the per-cell cost (~2-3×, NOT more).**
   `swap` is the biggest chunk of the ~8.5 µs (~12 of the method calls), but
   `can_displace` (two `ELEMENTS` dict lookups per candidate neighbor) and the
   Python scan-loop overhead (the `for x in xs` dispatch in `Simulation.step`)
   remain. So expect ~2-3× on the rule cost, not a 10× order-of-magnitude. The
   next lever after this is a `can_displace` phase/density LUT (deferred — see
   Out of Scope).
6. **Dormancy is unaffected, and that is a guard, not a gap.** A dormant cell is
   skipped in `Simulation.step` before its rule (and thus before `swap`) ever
   runs, so this change cannot help or hurt a settled pile. The reflection MUST
   confirm the settled-pile step time is unchanged (it isolates "did we touch
   dormancy? no" from "did we speed up moving cells? yes").
7. **No timing assertions in the test suite.** Timings are CI- and
   environment-dependent and would be flaky. Perf is verified by **measurement
   reported in the Phase 01 reflection** (before/after `Simulation.step` time on
   a busy/falling scene + a settled pile), NOT by an assertion. The one new test
   (`test_grid_move_swaps_id_life_and_temp`) is a deterministic correctness
   check (it asserts the swap carried id+life+temp), NOT a timing check.
8. **The entire existing suite (173 tests) is the headline correctness guard and
   MUST stay green.** In particular every temp/life-carrying test (e.g.
   `test_swap_carries_temp` at `tests/test_grid.py:261`, the fire/lava/steam
   lifetime + thermal-physics tests) pins that delegation did not drop a field
   or invert a swap. Any failure means a field was missed — **fix `move`/`swap`,
   do NOT weaken the tests.**

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | S  | Two small edits: one new ~6-line method on `Grid` (raw 3-array tuple-swap, no bounds/clip, with a precondition docstring) and a one-line rewrite of `swap`'s body (+ docstring). Plus one focused headless test pinning the id+life+temp carry. No signature changes, no rule edits, no new deps. The risk is logical (the bounds precondition + the tuple-swap correctness), not volumetric — and both are pinned by the audit + the new test + the full suite. |

## Risks & Unknowns

1. **The no-bounds-check precondition is the headline risk.** If some `swap`
   caller did NOT pre-check bounds, dropping the per-access check would let a raw
   numpy index go OOB — which raises `IndexError` (loudly), unlike the current
   `set()`/`set_temp()` silent no-op on OOB. **Mitigation:** the audit (Phase 01)
   confirms all 16 sites pre-check; a miss crashes loudly in the suite or the
   `SANDFALL_FRAMES` smoke — catchable, not silent. The full suite (173 tests) +
   the SDL smoke are the guard.
2. **Numpy scalar tuple-swap correctness.** `d[y1,x1], d[y2,x2] = d[y2,x2],
   d[y1,x1]` evaluates the RHS tuple first (two numpy scalar copies), then
   assigns — standard Python swap semantics. Verify with the new
   `test_grid_move_swaps_id_life_and_temp` (it swaps two cells with distinct
   id+life+temp and asserts each landed at the other cell). Trivially correct,
   but it is the one new code path, so it gets its own test.
3. **The win is bounded (Decision Log #5).** `swap` is the biggest chunk but not
   all of the ~8.5 µs/cell; `can_displace` and the scan loop remain. Do NOT
   promise more than ~2-3× on rule cost. (The deferred `can_displace` LUT is the
   next lever.)
4. **`mypy` strictness on the raw array writes.** `self._data[y1, x1],
   self._data[y2, x2] = ...` assigns into typed `npt.NDArray[np.uint8]` /
   `np.uint8` / `np.int16` arrays; numpy tuple-assignment type-checks cleanly.
   Parameters are plain `int` (callers already pass `int`). Verify
   `uv run mypy src` exits 0.
5. **Line numbers in this plan are current as of the post-dormant-cells source**
   (verified at planning time by reading every cited file). The implementer must
   re-read each file before editing rather than blind-applying line numbers.

## Verification Philosophy

The phase's `Verification Commands` block includes these six gates, and ALL must
exit zero before the phase is considered done:

```bash
uv run pytest tests/test_grid.py -v      # phase-focused (new Grid.move test + existing swap/grid tests)
uv run python -c "import sandfall"       # import smoke
uv run pytest                            # FULL suite -- regression guard (173 tests; temp/life-carry tests are the guard)
uv run ruff check .                      # lint
uv run ruff format --check .             # format
uv run mypy src                          # types
SANDFALL_FRAMES=60 uv run sandfall       # SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy)
```

**Perf is NOT a test gate** (timings are environment-dependent — Decision Log
#7). Instead, the Phase 01 implementer measures `Simulation.step` before and
after on (a) a busy/falling ~25%-fill scene (the headline: target ~2-3× on rule
cost), and (b) a settled pile (confirms dormancy is unaffected — should be
unchanged), and reports the numbers in `01-grid-move-reflection.md` as evidence.
The headline correctness gate is **the full suite staying green** plus the new
`test_grid_move_swaps_id_life_and_temp`.

## Out of Scope (Future Work — DO NOT plan now)

- **`can_displace` phase/density LUT** — the next busy-scene perf lever after
  this one. `can_displace` does two `ELEMENTS` dict lookups per candidate
  neighbor; a lookup table indexed by `(src_id, target_id)` would cut that to one
  array read. Deferred this pass (swap was the bigger chunk).
- **Numba JIT** of the scan + a unified rule-dispatch table (10-50×). Deferred —
  heavy dependency, restructures the rule registry.
- **Multithreading** (GIL; the scan is intrinsically sequential — a cell's move
  depends on cells scanned before it in the same frame) and **GPU offloading**
  (the bottleneck is the sequential Python CA, not rendering at ~1 ms or
  diffusion at ~2.5 ms). Analyzed and **REJECTED** in the prior perf plans — do
  not plan.
- **Inlining `swap` away** (replacing all 16 call sites with `grid.move`).
  Churn for no gain; `swap` stays as the one-line delegate (Decision Log #4).
- **Incremental active-set tracking / sub-frame wake.** Dormancy already
  recomputes the wake set cheaply (~0.6 ms); revisit only on much larger grids.

## Foundation Reference

This plan is the deferred "faster rule execution" lever flagged in BOTH
`.agent/tasks/performance-active-set/00-overview.md` and
`.agent/tasks/performance-dormant-cells/00-overview.md` Out-of-Scope sections.
Dormancy shipped first (settled scenes); this ships the moving-scene half. For
architecture context, read (re-read before editing — line numbers drift):
- `src/sandfall/rules/_common.py` — the `swap` function being rewritten
  (`_common.py:75-94`, the 12-call hot path).
- `src/sandfall/grid.py` — the `_data`/`_life`/`_temp` arrays `move` indexes
  directly (`grid.py:82-84` declarations, `grid.py:92-94` allocation), and the
  `set`/`get`/`set_life`/`get_life`/`set_temp`/`get_temp`/`in_bounds` accessors
  (`grid.py:147-235`) whose bounds+clip overhead `move` drops.
- `src/sandfall/rules/{sand,water,lava,steam,smoke,fire}.py` — the 16 `swap`
  call sites (all pre-check bounds; see the Phase 01 audit). NO edits needed
  here — listed so the implementer verifies the audit rather than assumes it.

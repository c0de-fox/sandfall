# Sandfall Performance — Active-Set (Sparse) Scan + Particle-Count HUD — Master Plan

## Problem Statement

The bottleneck is the **Python movement scan in `Simulation.step`**
(`src/sandfall/simulation.py:42-71`), which visits **every cell every frame** —
including all the empty ones. Empty cells are a hard no-op (the `if eid ==
ElementId.EMPTY: continue` at `simulation.py:63-64` fires), but Python still
pays for the loop iteration, the `grid.get(x, y)` call, and the comparison.
On a 200×140 grid that is 28,000 cells/frame of pure overhead.

**Measured (cite these as the evidence base — they were taken on the current
source before this fix):**

| Scenario                         | Time          | Notes                                                    |
|----------------------------------|---------------|----------------------------------------------------------|
| `step`, empty grid               | **27.6 ms**   | ~36-40 fps. Pure overhead of scanning 28,000 empty cells.|
| `step`, ~59% busy grid           | **168 ms**    | ~6 fps. Per non-empty cell ~8.5 µs (rule execution).     |
| `diffuse_temps` (vectorized heat)| **2.5 ms**    | Negligible — whole-grid numpy, already cheap.            |
| render (`Renderer.render`)       | **1.1 ms**    | Negligible.                                              |
| Prototype: iterate non-empty only| **~0.15 ms**  | Empty-grid scan 27.6 ms → ~0.15 ms (**185×**).           |
| `np.nonzero` per row (×140)      | **<0.15 ms**  | Cheap.                                                   |
| `(ids != 0).sum()` (particle ct) | **<0.15 ms**  | Cheap; full-grid count is ~0.04 ms.                      |

**Therefore the right lever is sparsifying the movement scan** (skip empty
cells). The two obvious-sounding alternatives were analyzed and **rejected**:

- **GPU offloading** of rendering/diffusion — rejected: render is 1.1 ms and
  diffusion is 2.5 ms; neither is the bottleneck. The bottleneck is the
  sequential cellular-automaton scan in Python.
- **Multithreading** — rejected: the scan is CPU-bound Python; the GIL blocks
  real parallelism, and the scan is intrinsically sequential (a cell's move
  depends on the cells scanned before it in the same frame).

**User-visible symptoms:** empty scene ~40-45 fps; busy scene ~15 fps. The
user asked point-blank: *"Do we check every cell all the time, or only the
living cells?"* — answer: every cell. The fix is to scan only the non-empty
(living) cells. The user also asked for a **live particle/element count near
the FPS counter**.

## Solution Summary

**Two phases (user-approved scope: "Phase 1+2 only").**

- **Phase 01 — Sparse per-row scan (the headline perf fix).** Sparsify
  `Simulation.step`'s movement scan so the inner loop only visits **non-empty**
  cells, while preserving the **EXACT** scan semantics that the simulation's
  correctness depends on: `y` descending (bottom→top, so columns settle one
  cell/step and don't teleport), per-row randomized `x` direction (so piling
  and liquid flow have no horizontal bias), and the `moved`-this-frame guard
  (so a cell moved *into* earlier in the scan is not re-dispatched). The
  implementation: keep the `for y in range(grid.height - 1, -1, -1)` loop and
  the per-row `random.random() < 0.5` flip, but replace the inner
  `xs = range(grid.width)` / `reversed(...)` with the **non-empty x indices of
  that row** via `np.nonzero(data[y])[0]`. Empty rows are skipped in one numpy
  call. Empty cells were no-ops before, so skipping them changes nothing about
  the result — the **entire existing test suite is the regression guard** and
  MUST stay green. The diffusion pre-pass (`diffuse_temps`) is UNCHANGED — it is
  already whole-grid vectorized and cheap.
- **Phase 02 — Particle-count HUD.** Add a live count of non-empty cells next
  to the FPS/brush readout. Compute once per frame in `Game._draw`
  (`count = int((self._grid.array != int(ElementId.EMPTY)).sum())`, ~0.04 ms —
  free), thread it through `UI.draw`'s signature, and render it in the existing
  top-left HUD line (`ui.py:180`). To keep the HUD format **headlessly
  testable** (matching the codebase's existing pure-layout / pygame-draw split),
  extract a pure module-level `format_hud(fps, brush_radius, count) -> str`
  helper that `UI.draw` calls — then unit-test the helper directly.

**Expected win:** empty-grid `step` ~27.6 ms → ~1-2 ms (limited by the 140
`np.nonzero` calls + the unchanged ~2.5 ms diffusion); busy scenes skip their
empty cells (~11-21 ms saved depending on fill). Perf is verified by
**measurement reported in the reflection**, NOT by a test assertion (timings
are CI/environment-dependent and flaky — see Verification Philosophy).

## Phase List

| #  | Phase                                     | Cx | Depends On | Parallelizable With        |
|----|-------------------------------------------|----|------------|----------------------------|
| 01 | Sparse per-row scan (the headline fix)    | M  | —          | Phase 02 (disjoint files)  |
| 02 | Particle-count HUD + pure `format_hud`    | S  | —          | Phase 01 (disjoint files)  |

## Dependency Map

```
01 (sparse scan) ──► done     02 (particle-count HUD) ──► done
```

**The two phases touch completely disjoint files** (Phase 01: `simulation.py`
+ `tests/test_simulation.py`; Phase 02: `ui.py` + `game.py` +
`tests/test_ui.py`), so they **can** run in parallel without merge conflict.
They are presented as 01 → 02 only for a cleaner serial commit history and so
the headline perf fix lands first. If executed in parallel, each branch must
still pass the FULL suite on its own (the full suite is each phase's
correctness guard).

## Decision Log

All decisions below are **user-approved** ("Phase 1+2 only") and must not be
re-litigated.

1. **Phase 1+2 ONLY — defer faster rule execution and Numba JIT.** The user
   was offered three levers and approved only the sparse scan + the HUD.
   *(Deferred — see Out of Scope: faster rule execution via a `Grid.move`
   raw-array fast-swap; Numba JIT of the scan + unified rule dispatch.)*
2. **Sparsify per-row (`np.nonzero(data[y])[0]`), NOT via a single 2D
   `np.argwhere`.** A single `np.argwhere` over the 2D array is ~0.13 ms but
   **loses the per-row grouping** required to preserve the per-row random
   `x`-direction flip (the flip is what keeps piling/flow horizontally
   unbiased). The per-row `np.nonzero` form (140 calls/frame, ~1 ms total) is
   chosen for **fidelity to the existing semantics** — the ~1 ms is negligible
   vs the ~26 ms saved on an empty grid, and is the price of not changing
   behavior. *(Alternative considered: one 2D nonzero + accept a single
   global direction — rejected: introduces horizontal bias, a behavior
   change.)*
3. **Read the raw array (`grid.array`), NOT `grid.get(x, y)` per cell.**
   `grid.get` (`grid.py:97-106`) does a bounds check + `int()` cast per call;
   reading `data[y, x]` directly avoids that overhead in the hot inner loop.
   Use the **public `grid.array` property** (`grid.py:66-71`, returns the same
   underlying `_data` array, documented as "Intended read-only access") rather
   than reaching into `grid._data` — the scan only READS the array (mutation
   happens via rule functions through `grid.set` / `swap`), so `array` is the
   clean, intended read path. *(Consistency note: `Simulation.step` already
   reads/writes `grid._temp` directly at `simulation.py:49` because there is
   no public setter equivalent; for the id array, `array` IS the public read
   accessor and is preferred.)*
4. **Keep the `moved` bool guard unchanged.** It still marks movement
   *destinations* (`moved[dy, dx] = True`) so a cell moved *into* during the
   scan is not re-dispatched in the same frame. This is still needed because
   a destination cell is, by definition, non-empty after the move — it IS in
   the active set and could be visited later in the same row scan (e.g. sand
   displacing water swaps into a water cell that has not yet been scanned).
5. **Keep the mid-scan empty re-check (`if eid == EMPTY: continue` AFTER
   reading `data[y, x]`).** A cell that was non-empty at nonzero-time but
   became empty during the scan (fire expired, erased, displaced by an
   earlier move in this same frame) must be skipped. Cheap (one int compare)
   and correct; dropping it would re-dispatch a now-empty cell.
6. **Accept 1-frame spawn latency for cells born mid-step.** Cells that
   become non-empty MID-step (plant grows into an empty neighbor, fire spawns
   smoke, lava flashes water to steam) are picked up NEXT frame, not this
   one — `np.nonzero` for row `y` is computed when the scan reaches row `y`,
   so a cell filled after that point by a row scanned later is not in this
   frame's active set. Imperceptible at 60 fps; documented as a known,
   accepted consequence of the sparse approach. *(Alternative considered:
   recompute nonzero after every move — rejected: defeats the whole point of
   sparsifying.)*
7. **Diffusion pass stays whole-grid.** `diffuse_temps` is one vectorized
   numpy op (~2.5 ms) and benefits from staying whole-grid (no per-row Python
   loop, no active-set bookkeeping). Only the movement scan is sparsified.
8. **No timing assertions in the test suite.** Timings are CI- and
   environment-dependent and would be flaky. Perf is verified by
   **measurement reported in the Phase 01 reflection** (before/after `step`
   time on an empty grid and a busy grid), NOT by an assertion. See
   Verification Philosophy.
9. **Pure `format_hud(...)` helper for the HUD string (Phase 02).** The HUD
   format `f"{int(fps)} FPS  r={brush_radius}  n={count}"` is extracted into a
   module-level pure function in `ui.py` (mirroring `palette_layout`, the pure
   counterpart to `UI.draw`'s swatch rendering). `UI.draw` calls it and
   renders the result with the existing font/`FPS_COLOR`. This makes the HUD
   format **headlessly unit-testable** (no pygame in the test), matching the
   codebase's established pure/draw split. *(See the prompt-discrepancy flag
   below.)*
10. **Particle count is a full-grid sum each frame, NOT incremental
    active-set tracking.** `(ids != 0).sum()` is ~0.04 ms — free at the
    current grid sizes. Incremental tracking (maintaining a running count as
    cells are painted/erased/moved) is complexity for no measurable gain at
    this scale; deferred (see Out of Scope).

**Prompt-discrepancy flag (important):** the planning prompt asserted there
is *"the one existing UI test that asserts the HUD string format"* in
`tests/test_ui.py` and asked to update it. **There is no such test.**
`tests/test_ui.py`'s module docstring (`tests/test_ui.py:1-12`) explicitly
states that `UI.draw` pixel rendering is *"intentionally not asserted
pixel-by-pixel"* and is verified manually via the `SANDFALL_FRAMES` seam; a
grep for `FPS`/`hud`/`brush_radius`/`FPS_COLOR` across `tests/` returns no
HUD-string assertion (only an unrelated `brush_radius` reference in
`tests/test_brush.py:108`). **Phase 02 therefore ADDS a new test for the pure
`format_hud` helper rather than updating an existing one.** This is a
deviation from the prompt's literal wording, taken to keep the plan faithful
to runtime truth; the acceptance criterion ("the HUD shows `n=<count>`") is
unchanged.

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | M  | One careful hot-loop rewrite where behavior preservation is the whole risk — keep y-descending + per-row random direction + moved guard + mid-scan empty re-check EXACTLY, only swap the x-index source from `range(width)` to `np.nonzero(data[y])[0]`. Plus two focused regression tests pinning sand-piles and water-levels on a mostly-empty grid (exercising the nonzero skip at scale). Small surface, but the correctness argument is subtle. |
| 02    | S  | One pure helper extraction + a signature thread (`UI.draw` ← `Game._draw`, the single caller) + one format-string change + one new headless test. Mechanical. |

## Risks & Unknowns

1. **Behavior preservation is the whole risk.** The sparse scan MUST produce
   results identical to the old full scan for the existing deterministic
   scenarios. **Mitigation:** keep y-descending order, the per-row random
   direction, the `moved` guard, and the mid-scan empty re-check EXACTLY as
   they are — only the source of `x` indices changes (full row → non-empty
   subset). Empty cells were no-ops before; skipping them changes nothing.
   **The full existing test suite is the guard** and MUST stay green. The two
   new Phase 01 tests additionally pin sand-piling and water-leveling on a
   wide mostly-empty grid (where the nonzero skip is actually exercised).
2. **`np.nonzero` per row (140 calls/frame) adds ~1 ms of Python/numpy
   overhead.** Negligible vs the ~26 ms saved on an empty grid. It is the
   price of preserving the exact per-row direction semantics (Decision Log
   #2). Note the tradeoff; do not "optimize" it into a 2D `np.argwhere` —
   that loses per-row grouping and changes behavior.
3. **mypy strictness on numpy index types.** `np.nonzero(data[y])[0]` returns
   an `intp` array; iterating yields numpy scalars. Cast `x = int(x)` at the
   top of the loop body (also satisfies `ElementId(eid)` / `moved[y, x]` /
   rule-function argument typing). `eid = int(data[y, x])` for the same
   reason. Verify `uv run mypy src` exits 0.
4. **No timing assertions in tests.** Do NOT add a `step < N ms` assertion —
   it will be flaky across CI/hosts. Perf is verified by MEASUREMENT reported
   in the Phase 01 reflection (cite the before/after numbers). See
   Verification Philosophy.
5. **The water-leveling test has a randomized-flow component.** Water's rule
   shuffles; the test seeds `random.seed(0)` and asserts a physical invariant
   ("no water suspended above an empty cell") after a generous step budget.
   If it proves flaky on a given host, widen the step budget (document the
   re-tune) — do NOT loosen the physical invariant.
6. **Phase 02 `UI.draw` signature change ripples to the single caller**
   (`Game._draw`, `game.py:281-287`) and to any test that constructs/calls
   `UI.draw`. The only caller is `Game._draw`; `tests/test_ui.py` does NOT
   call `UI.draw` (it tests pure helpers only), so the only ripple is the one
   caller. Verify with `uv run pytest` + `uv run mypy src`.
7. **Line numbers in this plan are current as of the
   `thermal-conservation-fix`-complete source** (verified at planning time by
   reading every cited file). The implementer must re-read each file before
   editing rather than blind-applying line numbers.

## Verification Philosophy (applies to both phases)

Each phase's `Verification Commands` block includes these six gates, and ALL
must exit zero before the phase is considered done:

```bash
uv run pytest tests/test_simulation.py tests/test_ui.py -v   # phase-focused
uv run python -c "import sandfall"                            # import smoke
uv run pytest                                                 # FULL suite — the regression guard
uv run ruff check .                                           # lint
uv run ruff format --check .                                  # format
uv run mypy src                                               # types
SANDFALL_FRAMES=60 uv run sandfall                            # SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy)
```

**Perf is NOT a test gate** (timings are environment-dependent). Instead, the
Phase 01 implementer measures `Simulation.step` before and after on (a) an
empty 200×140 grid and (b) a ~59%-busy grid, and reports the numbers in
`01-sparse-scan-reflection.md` as evidence. The headline correctness gate is
**the full suite staying green** plus the two new physical regression tests.

## Out of Scope (Future Work — DO NOT plan now)

- **Faster rule execution** (`Grid.move` raw-array fast-swap cutting the
  ~12-call `swap` to 1; ~2-3× on the ~8.5 µs/cell busy-scene cost). Deferred
  — this pass targets the empty/light-scene floor + the HUD, not the busy-scene
  per-cell rule cost.
- **Numba JIT** of the scan + a unified rule-dispatch table (10-50×). Deferred
  — heavy dependency, restructures the rule registry.
- **Multithreading** (GIL; scan is sequential) and **GPU offloading**
  (bottleneck is the sequential CA in Python, not rendering at 1.1 ms or
  diffusion at 2.5 ms). Analyzed and **REJECTED** — do not plan.
- **Throttling the particle count** (every N frames) or **incremental
  active-set tracking** (maintain a running count / a dirty-cell set instead
  of recomputing). At ~0.04 ms/frame the full-grid sum is free; revisit only
  if a much larger grid makes it non-negligible.
- **A 2D `np.argwhere` single-pass active set.** Loses the per-row grouping
  needed for the per-row random direction (Decision Log #2) — a behavior
  change, not an optimization.

## Foundation Reference

This plan targets the movement scan introduced under `.agent/tasks/sandfall/`
and refined through `.agent/tasks/sandfall-temperature/` (which added the
`diffuse_temps` pre-pass at `simulation.py:49` — UNCHANGED by this plan). For
architecture context, read:
- `src/sandfall/simulation.py` — the `step` scan loop being sparsified
  (`simulation.py:42-71`).
- `src/sandfall/grid.py` — the `array` property (`grid.py:66-71`) and `get`
  (`grid.py:97-106`) the scan reads through.
- `src/sandfall/ui.py` — `palette_layout` (`ui.py:61-86`, the pure/draw split
  pattern Phase 02's `format_hud` mirrors) and `UI.draw` (`ui.py:154-213`).
- `src/sandfall/game.py` — `Game._draw` (`game.py:263-287`, the single
  `UI.draw` caller Phase 02 threads the count through).
- Re-read each before editing; line numbers shift.

# Phase 01 Reflection — Sparse per-row scan

## Summary

Sparsified `Simulation.step`'s movement scan so the inner loop visits only the
non-empty x indices of each row (`np.nonzero(data[y])[0]`) instead of the full
`range(grid.width)`. The y-descending outer loop, the per-row
`random.random() < 0.5` direction flip, the `moved`-this-frame guard, and the
diffusion pre-pass are all byte-for-byte preserved. A new mid-scan empty
re-check (`eid = int(data[y, x]); if eid == EMPTY: continue`) guards against a
cell that emptied/transformed earlier in the same scan (now reachable because
the scan reads the raw `grid.array` directly). The `Simulation` class docstring
and `docs/ARCHITECTURE.md` were updated to describe the sparse scan.

## Measured performance (NOT a test gate — evidence only)

Method: `timeit.Timer(...).repeat(5, N)`, min reported, on a 200×140 grid.
Script: `/tmp/opencode/bench_step.py`. The "scan-only" rows exclude the
unchanged diffusion pre-pass; "full step" is the real `Simulation.step`
(diffusion + sparse scan). Host: the dev box this ran on.

### Empty 200×140 grid (the headline)

| Variant                                   | Time          |
|-------------------------------------------|---------------|
| OLD scan-only (movement, no diffusion)    | **22.76 ms**  |
| NEW scan-only (movement, no diffusion)    | **0.26 ms**   | ← **~88× faster** |
| NEW full `Simulation.step` (diff + scan)  | **2.21 ms**   |
| `diffuse_temps` alone (unchanged context) | 2.51 ms       |

The movement scan itself dropped 22.76 ms → 0.26 ms (~88×). End-to-end
`Simulation.step` is now **~25 ms → ~2.2 ms** — the residual is the unchanged
whole-grid diffusion pass (~2.5 ms), which is now the floor on a fully empty
grid. (Baseline overview cited 27.6 ms for the empty full step; my local OLD
number is 22.8 + 2.5 ≈ 25.3 ms — same machine-class, same conclusion.) Matches
the overview's prediction ("empty-grid step ~27.6 ms → ~1-2 ms").

### ~20% fill 200×140 grid (5558 non-empty cells; "25% fill" target ended up 19.9% because the random element mix includes EMPTY)

| Variant                                   | Time          |
|-------------------------------------------|---------------|
| OLD scan-only (movement, no diffusion)    | **62.6 ms**   |
| NEW scan-only (movement, no diffusion)    | **46.0 ms**   | ← ~16.6 ms saved (empty cells skipped) |
| NEW full `Simulation.step` (diff + scan)  | **47.0 ms**   |

On a ~20% fill grid the sparse scan saves ~16 ms/step by skipping the ~22k
empty cells; the remaining ~46 ms is the per-cell rule cost on 5558 non-empty
cells (~8.3 µs/cell — matches the overview's ~8.5 µs/cell busy-scene estimate;
this is the Phase-1-deferred "faster rule execution" lever). The per-row
`np.nonzero` overhead (140 calls/frame) is in the noise — well under 1 ms,
folded into the 0.26 ms empty-scan number.

## Correctness — the headline guard

- **Full suite stayed green: 156 → 158** (the 156 existing tests unchanged and
  still passing; the +2 are the new sparse-scan regression tests).
- **NO existing test needed an RNG-stream re-tune.** The sparse scan skips the
  per-row `random.random()` direction draw on *empty* rows (they hit the
  `if xs.size == 0: continue` fast path before the draw), which technically
  shifts the global RNG stream vs the old full scan. This did **not** break any
  existing test because the existing tests assert physical invariants (counts,
  settle rows, supported-from-below) that hold for any valid RNG stream, and
  the cells that ARE dispatched are dispatched in the same order. Verified by
  running the OLD full-scan and NEW sparse-scan side by side on the new
  sand-pile scenario across seeds {0,1,2,42} — **byte-identical** final grids
  in every case (`/tmp/opencode/compare_scan.py`).
- The mid-scan empty re-check and the `moved` guard are both exercised by the
  fire/lava/phase-change tests (cells transform/expire mid-scan) — all green.

## Deviation from the spec (documented): the sand-pile test assertion

The spec's verbatim `test_sparse_scan_piles_sand_on_floor_in_mostly_empty_grid`
asserted `y == height - 2` for **all** sand grains (i.e. all 4 grains in a
single flat row directly above the floor). That assertion is **physically
incorrect and provably not a behavior change**: four grains of sand dropped in
a single column pile into a **pyramid** — base `(9,10), (10,10), (11,10)` plus
apex `(10,9)` resting on `(10,10)` — and the **OLD full-scan produces the exact
same pyramid** (confirmed by the comparison script: OLD final positions =
`((9,10),(10,9),(10,10),(11,10))` for every seed). The apex grain at `y=9` is
correctly supported and is the stable shape; it cannot flatten because both of
its down-diagonals are occupied.

Per the spec's own philosophy (assert physical invariants, not exact positions
— as the water test does), I corrected the assertion to the true physical
invariant: **(a)** count preserved (4), **(b)** every grain supported from
below (cell directly below is non-empty — no suspended sand), **(c)** the pile
reaches the floor (≥1 grain at `height-2`), **(d)** the floor intact. This is a
strictly more correct invariant than the spec's; it still pins that the sparse
scan settles sand correctly at scale. The test name and intent are unchanged.
The implementation was **not** weakened to satisfy a wrong assertion — the
implementation was already correct (proven OLD==NEW), so the *test* was fixed.

## The 1-frame spawn-latency note (known, accepted)

Cells that become non-empty **mid-step** (plant grows, fire spawns smoke, lava
flashes water to steam) are picked up **next frame**, not this one:
`np.nonzero` for row `y` is computed when the scan reaches row `y`, so a cell
filled *after* that point by a row scanned later (lower `y`) is not in this
frame's active set. Imperceptible at 60 fps. This is exactly Decision Log #6
in the overview — documented, accepted, the price of sparsifying. The
fire/plant/lava tests all stay green (their assertions tolerate 1-frame
latency).

## Documentation updates

- `docs/ARCHITECTURE.md` — the "The scan: `Simulation.step`" section *did*
  describe the scan as visiting every cell ("For each cell... 2. Skip EMPTY
  cells"). Updated it to note the sparse (non-empty-only) per-row scan, the
  empty-row fast path, and that the result is identical to the old full-row
  scan; kept the 4-step scan description (the mid-scan re-check is mentioned).
  The diffusion pre-pass note is unchanged.
- `Simulation` class docstring — added a paragraph noting the sparse scan and
  that the result is identical to the old full-row scan.

## Anything difficult / unexpected

- The spec's sand-pile test had a physically-wrong assertion (above). The
  investigation — building a side-by-side OLD-vs-NEW comparison script — was
  the key step that turned "a test failed" into "the test is wrong, the
  implementation is provably correct." Worth the 10 minutes; without it the
  temptation would be to either weaken the scan or fudge the test.
- The empty-row RNG-skip is a real (if benign here) property: the sparse scan
  draws one fewer `random.random()` per empty row than the old scan. Future
  phases adding RNG-sensitive physical tests on sparse grids should know this.
- The per-row `np.nonzero` overhead is genuinely negligible (<1 ms for 140
  calls) — the tradeoff in Decision Log #2 (per-row nonzero vs 2D argwhere)
  is clearly correct.
- `ruff` flagged one >88-char inline comment on the `data = grid.array` line;
  shortened the trailing comment. No logic change.

## Files changed

- `src/sandfall/simulation.py` — the sparse-scan rewrite + docstring (the
  headline change). Diffusion pre-pass and signatures untouched.
- `tests/test_simulation.py` — 2 new tests (`test_sparse_scan_piles_sand_on_floor_in_mostly_empty_grid`,
  `test_sparse_scan_water_finds_its_level`); the sand test's assertion
  corrected to the true physical invariant (deviation documented above). No
  existing test modified.
- `docs/ARCHITECTURE.md` — scan section updated to describe the sparse scan.

Not touched (per scope): `ui.py`, `game.py`, `rules/*`, `grid.py`,
`thermal.py`, `elements.py`. No git operations performed (changes left
unstaged, as instructed).

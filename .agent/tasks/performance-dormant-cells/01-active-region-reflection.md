# Phase 01 Reflection — Dormant-cell (active-region) tracking

## Summary

Implemented the dormant-cell optimization exactly per the spec: a persistent
`_active` bool array on `Grid`, a `Simulation.step` rewrite that scans only
`active & non-empty` cells and rebuilds `_active` each frame from the four
wake conditions, plus `fill_circle`/`migrate_grid` marks and five regression
tests. **The headline win is real and large; one decision (`Grid.set`
marking) was reversed by measurement.**

## Measured performance (200×140 grid)

Method: one-off scripts under `/tmp/opencode/` (`measure_dormant.py`,
`measure_dormant2.py`, `measure_setmark.py`) using `time.perf_counter`,
warmup-discarded, median of repeated runs. Numbers are noisy — this is a
shared/loaded host (p10/p90 spans were wide) — but the **directional
conclusions are stable across all runs**.

### (a) Settled ~7,300-sand pile — the headline (plan: was 72.9 ms → target ~3–5 ms)

| Scan              | ms/frame (median) | notes |
|-------------------|------------------|-------|
| OLD sparse (all non-empty) | **~72–83 ms** | matches the plan's 72.9 ms baseline |
| NEW dormant scan           | **~4.4–7.2 ms** | target was ~3–5 ms; landed ~5–7 ms |

**~11–19× speedup.** Final active-set size on the settled pile: **0**
(`final_active == 0`, exactly as the test asserts — uniform ambient, no heat
source, no movement). The remaining cost is the whole-grid diffusion pre-pass
(~2.5 ms) + the mask rebuild (~0.6 ms) + scanning the zero-cell movement front.

### (b) Busy/falling scene (~25% fill, mid-fall / continuously refilled)

| Scan              | ms/frame (median) |
|-------------------|------------------|
| OLD sparse        | ~82–89 ms |
| NEW dormant       | ~87–89 ms |

**Break-even (as expected).** On a maximally-busy scene nearly every non-empty
cell is active (the active set was ~14k cells vs ~7k sand grains — dilation
inflates it), so the scan visits the *same* cells either way; the NEW scan
just pays the mask-rebuild overhead with no skip benefit. This is precisely
what the plan's Out-of-Scope note predicted: "Dormancy helps settled scenes;
faster rules help actively-moving scenes." The busy-scene win is a separate,
explicitly-deferred lever (faster `Grid.move` / numba).

### (c) `Grid.set` active-marking decision — **DROPPED** (reversed the spec)

The spec said to mark `_active[y,x]=True` on non-empty `set` writes and to
drop it only if the busy-scene measurement exceeded ~5%. I implemented it as
specified, then measured:

| Busy-scene variant              | ms/frame |
|---------------------------------|----------|
| NEW **with** `set` active-mark  | ~89–120 ms |
| NEW **without** `set` mark      | ~78–84 ms |

On a **continuously-busy** scene (sand refilled at the top each frame so it
never settles — the rigorous test), the `set`-mark cost **+37.8 ms/frame
(+31.6%)**. On a settling-busy scene it showed +4.8% to +16.8% depending on
how far settling had progressed (fewer moves → fewer `swap` → fewer `set`
calls → less impact). The continuous-busy number is the honest one: `swap`
(`rules/_common.py:85-86`) calls `set` **twice per move**, so on a frame with
thousands of moves the extra `int(ElementId.EMPTY)` compare + numpy scalar
bool write per call dominates.

**Decision: DROP the `set`-mark.** Decisively above the 5% threshold. The full
164-test suite stayed green afterward — correctness is fully preserved by:
- `id_changed` (`data != data_before`, wake 1) — captures every cell `set`
  touched *during* a scan (rule transforms, moves via `swap`);
- the `Simulation.__init__` bootstrap (`grid._active[:] = data != EMPTY`) —
  covers the `Grid(); set(...); Simulation(g); step()` test pattern (set
  before init is overwritten by the seed, which marks the same non-empty
  cells);
- `fill_circle` (`_mark_active_disk`) — covers the brush path, the only
  between-step grid mutator in the real loop.

The only gap — `set` called *between* steps after a `Simulation` exists, on a
cell not otherwise woken — is not a real code path (between-step mutation in
`Game.run` goes through the brush via `fill_circle`). Documented in the
`Grid.set`, `Grid.active`, module, and `Simulation` docstrings.

## Verification — all six gates green

- `uv run pytest tests/test_simulation.py -v` → **14 passed** (9 existing + 5 new)
- `uv run python -c "import sandfall"` → **IMPORT_OK**
- `uv run pytest` → **164 passed** (was 159; +5). **No existing test needed an
  RNG-stream re-tune** — the scan dispatches the same cells in the same order
  among the active set; dormant cells drew no RNG and produced no move, so
  downstream cells see identical grid state.
- `uv run ruff check .` → **All checks passed**
- `uv run ruff format --check .` → **47 files already formatted**
- `uv run mypy src` → **Success: no issues found in 25 source files**
- `SANDFALL_FRAMES=60 uv run sandfall` → **EXIT=0** (real SDL driver; no dummy
  fallback needed)

## The four wake conditions (as implemented, in `Simulation.step`)

1. `_dilate(id_changed | moved)` — movement / identity-change + 1-cell
   4-neighborhood dilation. `id_changed = data != data_before` (cheap
   `data.copy()` snapshot at step start, ~0.05 ms). `moved` is the existing
   moved-this-frame guard.
2. `grid._temp != temp_before` — thermal change. `temp_before = grid._temp` is
   a **reference** captured before the diffusion reassignment (no copy —
   `diffuse_temps` returns a new array, so the old reference is intact).
3. `_dilate((data == FIRE) | (data == LAVA))` — persistent heat sources +
   neighborhood.
4. Brush-painted/erased cells — OR-marked into `grid._active` between steps by
   `Grid.fill_circle` (via the new module-level `_mark_active_disk` helper) and
   consumed by the scan; **not** carried into `active_next`.

Final line: `grid._active = active_next` (**OVERWRITE**, not `|=` — the
consumption semantics that let cells sleep).

**No wake condition beyond these four was needed.** The full suite (159
physics tests covering sand/water/fire/lava/steam/ice/glass/thermal) passed
unchanged on the first run, confirming the four are complete. The five new
tests pin each path directly (dormancy, erosion-wake, water+lava, wood+fire,
brush-paint-wake).

## Files changed

- `src/sandfall/grid.py` — `_active` array (decl + `__init__`), read-only
  `active` property, module-level `_mark_active_disk` helper, `fill_circle`
  marks in both branches, `migrate_grid` carries the `_active` overlap,
  module/class docstrings. (`Grid.set` does NOT mark active — dropped by
  measurement.)
- `src/sandfall/simulation.py` — module-level `_dilate` helper, `__init__`
  bootstrap, `step` rewrite (scan `active & non-empty` + four-wake rebuild),
  class docstring.
- `tests/test_simulation.py` — `from sandfall.brush import paint_brush` + five
  dormancy/wake regression tests.
- `docs/ARCHITECTURE.md` — the "scan" section was rewritten from "sparse
  (non-empty-only)" to "dormant-cell-aware (active-region)" with the four wake
  conditions, the diffusion-must-stay-whole-grid rationale, the `set`-mark
  decision, and the measured win.
- `src/sandfall/brush.py` — **unchanged** (verified: `paint_brush` routes only
  through `fill_circle` at `brush.py:48`).
- `src/sandfall/game.py` — **unchanged** (brush already runs before `step` at
  `game.py:140-143`).

## Difficult / unexpected

- **The `Grid.set`-mark cost was much larger than the plan's "~5%" hint.** The
  plan's Risk #5 estimated "a small per-moving-cell cost"; the continuous-busy
  measurement showed **+31.6%**. Root cause: `swap` calls `set` *twice* per
  move (`_common.py:85-86`), so the cost is 2× per moving cell per frame, and a
  busy frame has thousands of moves. The first (settling-busy) measurement
  showed only +4.8% because the scene was settling toward dormancy (fewer
  moves). The lesson: **measure the worst case (continuously busy), not the
  transient.** Dropped the mark; suite stayed green; docstrings updated to
  record why.
- **No wake condition beyond the spec's four was needed.** I had braced for a
  possible fifth (e.g. a rule side-effecting a non-adjacent neighbor), but the
  full 159-test suite passed on the first run after the rewrite. The lava
  reaction side-effects an *adjacent* water cell (within dilation range of the
  LAVA heat-source mask, wake 3), and fire's smoke spawn is within dilation
  range of the fire — both are covered.
- **Measurement noise** on this shared host was high (p10/p90 spans of ±15 ms
  on busy scenes). The settled-pile win and the set-mark delta were both
  directionally unambiguous across all runs despite the noise; the busy-scene
  break-even was the noisier comparison but never showed a regression after
  dropping the set-mark.

## Fun / notable

- The mask rebuild (one `data.copy()` + ~3 comparisons + 3 dilations) costs
  ~0.6 ms/frame — negligible vs the ~65–75 ms saved on a settled pile. The
  `_dilate` helper is 4 lines of shifted-OR slice math, no scipy.
- `final_active == 0` on a settled pile is a satisfyingly clean result: the
  wake set is *provably* empty when nothing moves, temp is uniform, and there
  are no heat sources. The dormancy guard test asserts exactly this.
- Did NOT commit (per the hard constraint). HEAD remains `b3fabbb`.

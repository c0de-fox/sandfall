# Sandfall Performance — Dormant-Cell (Active-Region) Tracking — Master Plan

## Problem Statement

The prior **sparse-scan** phase (`.agent/tasks/performance-active-set/`) made empty
grids fast (~27 ms → ~2.6 ms) by skipping empty cells: the scan in
`Simulation.step` now visits only the non-empty cells of each row
(`np.nonzero(data[y])[0]`, `simulation.py:65-87`). **But it still scans EVERY
NON-EMPTY cell every frame, even cells that cannot move.** A grain of sand at the
bottom of a settled pile runs the full `update_sand` rule (~8.5 µs: "can I fall?
check below, check diagonals") every frame, forever, despite being at rest.

**Measured (cite these as the evidence base — taken on the current source, a
200×140 grid with a SETTLED pile of 7,326 sand grains, neutral temperature,
nothing moving):**

| Scenario                                            | Time / count        | Notes                                                                   |
|-----------------------------------------------------|---------------------|-------------------------------------------------------------------------|
| `Simulation.step`, settled 7,326-grain pile         | **72.9 ms/frame**   | ~14 fps. Matches the user's report of ~15 fps at ~7,500 particles.      |
| Grains that actually move/change per frame          | **66 of 7,326**     | The movement front.                                                     |
| Grains re-evaluated but dormant (do nothing)        | **7,260 (99%)**     | Each pays ~8.5 µs for a rule that returns "no move".                    |
| `diffuse_temps` (whole-grid, unchanged)             | ~2.5 ms             | Stays whole-grid (must — see Decision Log #12).                         |
| Prior sparse-scan win (empty grid)                  | ~27 ms → ~2.6 ms    | Already shipped; this plan extends "skip empty" to "skip dormant".      |

**User observation (the ask):** *"I expected performance to increase once the sand
settled, but it stayed low even though nothing was moving. For neutral-temperature
things that aren't moving, can they be ignored?"* — **Answer: YES.** Track which
cells are *dormant* (cannot move or react next frame because nothing in their
world changed) and skip them. The sparse scan already proved the mechanism
(skipping no-op cells is behavior-preserving); this plan applies the same idea one
level deeper — skip cells that are non-empty *but quiescent*.

## Solution Summary

**Maintain a persistent boolean `_active` array on `Grid`** (same shape as
`_data`, sibling to `_life` / `_temp`). Each frame, `Simulation.step` scans ONLY
cells where `_active[y, x]` is True AND non-empty — replacing the current
`np.nonzero(data[y])[0]` with `np.nonzero(active[y] & (data[y] != 0))[0]`. After
the scan, `_active` is **rebuilt from scratch** for the NEXT frame as the union of
four **wake conditions**. A cell that fires none of them goes dormant (skipped next
frame). One phase; touches `grid.py` + `simulation.py` + `brush.py` (trivially) +
`tests/test_simulation.py`.

### The four wake conditions (the correctness-critical part — each is necessary)

A cell is active next frame if ANY of:

1. **It moved, changed identity, or is orthogonally adjacent to a cell that did.**
   Captured by `id_changed = (data != data_before)` (a cheap `data.copy()`
   snapshot at step start, ~0.05 ms) OR'd with the existing `moved` guard, then
   **dilated one cell** (4-neighborhood) so that when support erodes or a hole
   opens, the cells above/beside wake and fall/flow. Dilation is a vectorized
   shift+OR via a small module-level `_dilate(mask)` helper.
2. **Its temperature changed this frame.** `temp_changed = (grid._temp !=
   temp_before)` where `temp_before` is the **pre-diffusion** temp reference. No
   copy is needed: `diffuse_temps` returns a NEW array (`simulation.py:52-54`),
   so `temp_before = grid._temp` captured before the reassignment still points at
   the old array. Rationale: a dormant water cell must still boil/freeze when heat
   reaches it; a dormant wood cell must ignite when its temp crosses flashpoint.
   Diffusion changing its temp wakes it. (For a uniform-ambient settled pile, temp
   does not change → no wake → dormant. Exactly the goal.)
3. **It is FIRE or LAVA, or is orthogonally adjacent to FIRE/LAVA.**
   `_dilate((data == FIRE) | (data == LAVA))`. Rationale: a *clinging* fire
   re-asserts its `burn_temp` and ages its life each step but does NOT move or
   change identity (`fire.py:77-126`), and if it is already at `burn_temp` its temp
   doesn't change either — so without this rule, fire and its fuel neighbor would
   go dormant and the fire would never ignite the wood (`wood.py:26` checks the
   wood cell's OWN temp, so the wood MUST be scanned). Persistent heat sources (and
   their neighborhood) must stay awake. LAVA is the same (hot reactor, `lava.py`).
4. **It was just painted/erased by the brush** (between steps). The brush OR-marks
   touched cells + orthogonal neighbors into `grid._active` (see the handshake).

### The brush/scan handshake (correctness-critical — encode clearly)

The brush runs **between** steps (`Game.run` at `game.py:140-143`:
`_paint_if_dragging` → `_erase_if_dragging` → `step()`), and both paint paths route
through `Grid.fill_circle` (`game.py:241`, `game.py:261`). `fill_circle` must
**OR its marks into `grid._active`** (each painted cell + its 4-neighbors) so the
next scan sees them — covering both painting new cells AND erasing (which opens
space and must wake the cells beside/above the hole). `Simulation.step` then
**READS** `grid._active` for the scan and **OVERWRITES**
`grid._active = active_next` at the end.

**Consequence (the trap to avoid):** brush marks survive exactly until the next
scan (consumed by it). A painted cell that then does something stays active via
`id_changed`; a painted *static* cell (stone) correctly goes dormant after one
scan. **Do NOT do `active_next |= grid._active`** — that would let cells marked
once stay active forever (they would never sleep, defeating the whole optimization).

**Expected win:** settled 7,326-sand pile `Simulation.step` **72.9 ms → ~3-5 ms**
(diffusion ~2.5 ms + mask rebuild ~0.6 ms + scanning only the ~66-cell movement
front). Empty grid unchanged (~2.6 ms — it pays only the new ~0.6 ms mask rebuild,
still ~3 ms). Perf is verified by **measurement reported in the reflection**, NOT by
a test assertion (timings are CI/environment-flaky — see Verification Philosophy).

## Phase List

| #  | Phase                                       | Cx | Depends On | Parallelizable With |
|----|---------------------------------------------|----|------------|---------------------|
| 01 | Dormant-cell tracking (`_active` + wake set)| M  | —          | — (single phase)    |

## Dependency Map

```
01 (dormant-cell tracking) ──► done
```

This is a **single coherent phase** because the four pieces are mutually dependent
and cannot be split without an intermediate broken state: the `_active` array on
`Grid` (1), the `Simulation.step` rewrite that reads+rebuilds it (2), the
brush/migrate changes that feed it (3), and the regression tests that pin it (4)
all land together. Splitting would leave the sim scanning an all-False `_active`
(no movement) or an all-True one (no dormancy) between commits — neither is a
useful checkpoint.

## Decision Log

All decisions below follow directly from the user's ask ("ignore non-moving
neutral-temp things") and the measured evidence. They must not be re-litigated
without new measurement.

1. **Persistent `_active` bool array, rebuilt from scratch each frame — NOT
   incremental dirty-cell tracking.** A recomputed wake set is simple, fully
   vectorized (a handful of numpy boolean ops + one cheap `data.copy()`), and
   obviously correct (the four conditions are independently auditable). Incremental
   maintenance (mutating a running set on every move/transform) is complex,
   bug-prone (easy to miss a writer), and pays Python-level overhead per cell
   touched — the opposite of what we want on busy frames. *(Deferred — see Out of
   Scope.)*
2. **`_active` lives on `Grid` as a sibling to `_data` / `_life` / `_temp`, and
   `Simulation` writes it directly.** This mirrors the established pattern:
   `Simulation.step` already assigns `grid._temp = diffuse_temps(...)` directly
   (`simulation.py:55`), and the rule helpers already reach into `grid._life` /
   `grid._temp` via `set_life` / `set_temp`. A read-only `active` property
   (`grid.py`, mirroring `temp` at `grid.py:82-91` / `life` at `grid.py:73-80`)
   exposes it for tests and diagnostics. *(Alternative considered: a separate
   `ActiveSet` object owned by `Simulation` — rejected: adds a new type threaded
   through the sim for no benefit, and breaks the "all per-cell state lives on
   Grid" invariant that `migrate_grid` relies on.)*
3. **The four wake conditions are each necessary (the correctness argument):**
   - **(1) Movement / id-changed + dilation** — when a cell moves or transforms,
     the cell above it (which was supported by it) may now be unsupported and must
     wake to fall; the cell beside a vacated hole must wake to flow. Dilation by
     one cell propagates the wake to exactly the cells whose support/neighbors
     changed.
   - **(2) Thermal** — phase transitions are driven by a cell's OWN temperature
     (`water.py:50` boil, `water.py:57` freeze, `wood.py:26` ignite). A dormant
     cell whose temp changed (via diffusion from a heat source, or a rule) MUST be
     rescanned or it will never react.
   - **(3) FIRE/LAVA persistent sources** — a clinging fire re-asserts `burn_temp`
     and ages life but neither moves nor changes identity nor (if already at
     `burn_temp`) changes temp (`fire.py:89-93`). Without this rule, fire + its
     fuel neighbor would go dormant and combustion would never chain. Same for lava.
   - **(4) Brush** — painting/erasing between steps changes the world; the touched
     cells + neighbors must be scanned. (Erasing opens space → neighbors must wake
     to fall/flow into it.)
4. **Brush OR-marks `_active` between steps; the scan OVERWRITES `_active` at end
   (consumes the marks). Do NOT `active_next |= grid._active`.** Carrying the old
   active set forward would let any cell marked once stay active forever — it would
   never go dormant, and the optimization would do nothing. The overwrite is what
   lets a painted static cell (stone) correctly sleep after one scan. The brush's
   marks survive exactly one scan.
5. **`data_before = data.copy()` snapshot (~0.05 ms) for `id_changed`.** A full
   uint8 copy of a 200×140 grid is ~0.05 ms — negligible vs the ~69 ms saved on a
   settled pile. Cheap, obvious, allocation-only. *(Alternative considered: a
   per-cell "dirty" flag set by `Grid.set` — rejected: instruments the hottest
   function with state, and `data != data_before` already captures it perfectly.)*
6. **`temp_before = grid._temp` is a REFERENCE, not a copy.** `diffuse_temps`
   returns a NEW int16 array (documented at `simulation.py:52-54`, "does not mutate
   `grid._temp` in place"), so after `grid._temp = diffuse_temps(...)`, the
   `temp_before` reference still points at the unchanged pre-diffusion array. No
   allocation. The comparison `grid._temp != temp_before` then catches BOTH
   diffusion-driven temp changes AND rule-driven temp changes (rules write
   `grid._temp` via `set_temp`, e.g. fire re-asserting `burn_temp` at
   `fire.py:92-93`) — either means the cell's thermal state is in flux and it
   should wake. Correct, and free.
7. **`_dilate(mask)` via four zero-padded shifted ORs against the ORIGINAL mask
   (no scipy).** Reading from the original `mask` and accumulating into `out` for
   all four shifts avoids compounding into a 2-cell dilation. O(H·W), one
   allocation, no new dependency. At 200×140 it is ~0.1 ms per call (~0.3 ms total
   for the two dilations + the heat-source one). *(Alternative considered:
   `scipy.ndimage.binary_dilation` — rejected: adds a heavy dependency for a
   4-line helper.)*
8. **Bootstrap `grid._active[:] = (grid._data != EMPTY)` in `Simulation.__init__`.**
   The first step has no prior `active` set to read, so seed it with "all non-empty
   cells active". This covers the common test pattern `Grid(); set(...);
   Simulation(g); step()` and the initial frame of a real game. Combined with
   `Grid.set` marking active on non-empty writes, mid-sim placement via `set` also
   works. (Resize re-runs `Simulation(new_grid)` at `game.py:219`, which re-seeds
   the bootstrap — conservative-correct; the migrated `_active` overlap from
   `migrate_grid` is a subset and is harmlessly overwritten.)
9. **`Grid.set` marks `_active[y, x] = True` on non-empty writes.** Needed so that
   cells placed via `set` between steps (test code; hypothetical external callers)
   are scanned next frame; `fill_circle`'s own calls delegate through `set`.
   **Flag (see Risks #5):** rule transforms also call `set` *during* the scan,
   where the mark is redundant (`id_changed` already captures it) AND discarded
   (`active_next` overwrites `grid._active` at end of step). It is harmless to
   correctness but adds a branch + a numpy scalar write to the hottest function,
   so it carries a small busy-scene perf cost on *moving* cells. Encode as
   specified; if the reflection's busy-scene measurement shows a regression,
   dropping the `set` mark is safe (id_changed + bootstrap + fill_circle fully
   cover correctness) — re-run the full suite to confirm.
10. **`fill_circle` marks each painted cell AND its 4-neighbors active** (both the
    `radius == 0` branch at `grid.py:186-190` and the disk loop at
    `grid.py:197-204`). The +neighbors is what makes **erasing** wake the cells
    beside/above the opened hole (erasing writes EMPTY, which `set` does NOT mark
    active — condition #9 is non-empty-only — so `fill_circle` must mark the
    neighborhood itself). This is the single source of between-step wake for the
    brush path.
11. **`migrate_grid` carries the `_active` overlap** (alongside `_data` / `_life` /
    `_temp`, `grid.py:222-225`). Newly-exposed cells in the grown region default to
    inactive (they are EMPTY). Consistent with how temp/life are migrated.
12. **The diffusion pre-pass stays whole-grid (UNCHANGED).** It is one vectorized
    op (~2.5 ms) and **must** stay whole-grid: dormant cells' temps still propagate
    (so a heat source reaching a dormant cell raises its temp → condition #2 wakes
    it). Sparsifying diffusion would break thermal wake.
13. **1-frame wake latency for rule-driven support erosion is accepted.** A cell
    whose support is eroded *by a rule during a step* (not by the brush) falls next
    frame, not the same frame: the erosion is captured in `id_changed` at end of
    step, dilation wakes the neighbor, and it falls on the following step.
    Imperceptible at 60 fps. (Brush-driven erosion has NO latency — the brush marks
    the neighbor active between steps, so it falls the same next step.)
14. **No timing assertions in the test suite.** Timings are CI- and
    environment-dependent and would be flaky. Perf is verified by **measurement
    reported in the Phase 01 reflection** (before/after `Simulation.step` time on a
    settled 7,326-sand pile, plus an empty grid and a busy grid), NOT by an
    assertion. See Verification Philosophy. (The active-set COUNT assertions in the
    new tests are deterministic given the seed — those ARE allowed, and are the
    dormancy guard.)
15. **The entire existing test suite is the headline correctness guard, and MUST
    stay green.** 159 tests cover sand/water/fire/lava/steam/ice/glass/thermal
    physics. Any failure means a wake condition was missed — **fix the wake logic,
    do NOT weaken the tests.** Five new focused tests pin the dormancy/wake
    behavior directly (settled pile goes dormant; erosion wakes it; dormant
    water+lava → steam; dormant wood+fire → ignites; painting into a dormant region
    wakes it).

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | M  | One coherent change across `grid.py` (new `_active` array + property + `set`/`fill_circle`/`migrate_grid` marks), `simulation.py` (the `step` rewrite + `_dilate` helper + bootstrap), and `brush.py` (no change — it already routes through `fill_circle`, which now marks active). The individual edits are small and mechanical, but the correctness argument is subtle (the four wake conditions must be complete) — so the risk is logical, not volumetric. Five new regression tests pin the wake paths. |

## Risks & Unknowns

1. **A missed wake condition = a dormant bug** (the headline risk). If some cell
   that needs to act is not woken, it freezes in place / never reacts — a visible
   correctness regression. **Mitigation:** the four conditions are reasoned
   complete (Decision Log #3); the **full existing suite (159 tests) is the guard**
   and MUST stay green; five new tests target each wake path explicitly (erosion,
   thermal via lava, thermal via fire, brush). If a test fails, add/fix the wake
   condition — do NOT weaken the test.
2. **Mask-rebuild overhead (~0.6 ms/frame) is paid every frame, even on empty
   grids** (`data.copy()` + 3 comparisons + 2-3 dilations). Acceptable: an empty
   grid is still ~3 ms total; a settled pile drops from 72.9 ms to ~3-5 ms. The
   rebuild cost scales with grid area, not activity — fine at 200×140; revisit only
   if grid sizes grow dramatically.
3. **1-frame wake latency** for rule-driven support erosion (Decision Log #13).
   Imperceptible at 60 fps; documented and accepted.
4. **`_dilate` cost scales with grid size, not activity.** At 200×140 each
   dilation is ~0.1 ms; ~0.3 ms total for the ~3 dilations per frame. Negligible
   vs the win. Would matter only on very large grids (deferred concern).
5. **`Grid.set` active-marking instruments the hottest function (Decision Log #9).**
   During the scan, rule transforms call `set`, which now does an extra int
   compare + numpy scalar bool write per non-empty write. This is redundant there
   (id_changed captures it; active is overwritten at end of step) and adds a small
   per-moving-cell cost on busy scenes. Encode as specified; the reflection MUST
   measure a busy scene (e.g. ~59% busy) before/after to confirm no regression. If
   it regresses measurably, dropping the `set` mark is safe and full-suite-green
   (id_changed + bootstrap + fill_circle cover correctness) — re-run the suite.
6. **mypy strictness on numpy boolean array ops.** `np.nonzero(active[y] &
   (data[y] != 0))[0]` and the `_dilate` shifted-OR slices must type-check. Keep
   `_active: npt.NDArray[np.bool_]`; the `&` operand promotes cleanly
   (bool & bool). Cast `x = int(x)` in the loop (already present). Verify
   `uv run mypy src` exits 0.
7. **Diffusion MUST stay whole-grid** (Decision Log #12). Sparsifying it would
   break thermal wake (condition #2). Do not be tempted.
8. **Line numbers in this plan are current as of the post-sparse-scan source**
   (verified at planning time by reading every cited file). The implementer must
   re-read each file before editing rather than blind-applying line numbers.

## Verification Philosophy

The phase's `Verification Commands` block includes these six gates, and ALL must
exit zero before the phase is considered done:

```bash
uv run pytest tests/test_simulation.py -v   # phase-focused (new dormancy/wake tests + existing physics)
uv run python -c "import sandfall"          # import smoke
uv run pytest                                # FULL suite — the headline regression guard (159 tests)
uv run ruff check .                          # lint
uv run ruff format --check .                 # format
uv run mypy src                              # types
SANDFALL_FRAMES=60 uv run sandfall           # SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy)
```

**Perf is NOT a test gate** (timings are environment-dependent — Decision Log #14).
Instead, the Phase 01 implementer measures `Simulation.step` before and after on
(a) the settled 7,326-sand pile (the headline: 72.9 ms → expected ~3-5 ms),
(b) an empty 200×140 grid (should stay ~2.6-3 ms), and (c) a ~59%-busy grid
(confirms no regression from the `set` active-mark — Risk #5), and reports the
numbers in `01-active-region-reflection.md` as evidence. The headline correctness
gate is **the full suite staying green** plus the five new dormancy/wake tests.

## Out of Scope (Future Work — DO NOT plan now)

- **Faster rule execution** (`Grid.move` raw-array fast-swap, cutting the ~12-call
  `swap` to 1; ~2-3× on the ~8.5 µs/cell busy-scene cost). Deferred — this is the
  OTHER busy-scene lever, orthogonal to dormancy. Dormancy helps settled scenes;
  faster rules help actively-moving scenes. Both are wanted eventually; this plan
  does dormancy only.
- **Numba JIT** of the scan + a unified rule-dispatch table (10-50×). Deferred —
  heavy dependency, restructures the rule registry.
- **Multithreading** (GIL; scan is sequential) and **GPU offloading**
  (bottleneck is the sequential CA in Python). Analyzed and **REJECTED** in the
  prior perf plan — do not plan.
- **Incremental (non-recomputed) active-set maintenance** and **sub-frame wake**.
  The recomputed wake set is simple, correct, and fast enough (~0.6 ms). Revisit
  only if a much larger grid makes the per-frame rebuild non-negligible.

## Foundation Reference

This plan extends the movement scan shipped under
`.agent/tasks/performance-active-set/01-sparse-scan.md` (which introduced the
per-row `np.nonzero(data[y])[0]` sparse scan this plan narrows further). For
architecture context, read (re-read before editing — line numbers drift):
- `src/sandfall/simulation.py` — the `step` scan to extend (`simulation.py:48-87`),
  the diffusion pre-pass (`simulation.py:55`, UNCHANGED), and `__init__`
  (`simulation.py:38-42`, gets the bootstrap).
- `src/sandfall/grid.py` — the arrays (`grid.py:42-55`), the `temp`/`life`
  properties this mirrors (`grid.py:73-91`), `set` (`grid.py:108-119`),
  `fill_circle` (`grid.py:171-204`), and `migrate_grid` (`grid.py:207-225`).
- `src/sandfall/brush.py` — `paint_brush` (`brush.py:27-76`) routes through
  `fill_circle` (`brush.py:48`); NO change needed here.
- `src/sandfall/game.py` — the brush→step ordering (`game.py:140-143`) and resize
  re-Simulation (`game.py:219`).
- `src/sandfall/rules/fire.py`, `rules/lava.py`, `rules/wood.py`,
  `rules/water.py` — the reactive rules that motivate wake conditions 2 and 3.

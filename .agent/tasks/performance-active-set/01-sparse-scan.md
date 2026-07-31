# Phase 01: Sparse per-row scan (the headline perf fix)

## Objective

Sparsify `Simulation.step`'s movement scan so the inner loop only visits
**non-empty** cells, while preserving the **EXACT** scan semantics the
simulation's correctness depends on (`y` descending so columns settle; per-row
randomized `x` direction so piling/flow has no horizontal bias; the
`moved`-this-frame guard). The empty cells that are now skipped were no-ops
before, so the result is identical — **the entire existing test suite is the
regression guard** and MUST stay green. Add two focused physical regression
tests pinning sand-piling and water-leveling on a wide mostly-empty grid
(where the `np.nonzero` skip is actually exercised at scale).

## Depends On

none — first phase (Phase 02 is independent and touches disjoint files).

## Can Parallelize With

Phase 02 (disjoint files: this phase touches `simulation.py` +
`tests/test_simulation.py`; Phase 02 touches `ui.py` + `game.py` +
`tests/test_ui.py`). Presented first for a cleaner serial commit history and
so the headline perf fix lands first.

## Recommended Agent

@implementer — one careful hot-loop rewrite where behavior preservation is the
whole point. Read `00-overview.md` (especially Decision Log #2-#6 and Risks)
and re-read `src/sandfall/simulation.py` and `src/sandfall/grid.py` before
editing. Do NOT be tempted to "optimize" the per-row `np.nonzero` into a
single 2D `np.argwhere` — that loses per-row grouping and changes behavior
(Decision Log #2).

## Changes Required

- `src/sandfall/simulation.py` — rewrite the movement scan in `step`
  (`simulation.py:53-71`) so the inner `x` loop iterates the **non-empty** x
  indices of each row (`np.nonzero(data[y])[0]`) instead of the full
  `range(grid.width)`. Keep the y-descending outer loop, the per-row random
  direction flip, the `moved` guard, and add the mid-scan empty re-check.
  Diffusion pre-pass (`simulation.py:49`) is UNCHANGED. Update the `Simulation`
  class docstring (`simulation.py:16-30`) to note the scan now visits only
  non-empty cells.
- `tests/test_simulation.py` — ADD two focused regression tests that pin the
  sparse path on a wide mostly-empty grid: sand piles on a floor, and water
  finds its level. (The existing physical-outcome tests — `test_sand_falls_*`,
  `test_sand_piles_on_floor_without_sinking`, `test_sand_sinks_through_water`,
  `test_empty_grid_steps_without_error` — are the headline regression guard
  and MUST stay green unchanged.)

## Implementation Instructions

> Re-read `src/sandfall/simulation.py` and `src/sandfall/grid.py` before
> editing — line numbers below are current at planning time and may have
> drifted. This is a single coherent edit to one method; no signature changes,
> no data-model changes, no new dependencies.

### 1. `src/sandfall/simulation.py` — rewrite the movement scan

The current scan (`simulation.py:53-71`) is:

```python
        for y in range(grid.height - 1, -1, -1):
            xs = (
                range(grid.width)
                if random.random() < 0.5
                else range(grid.width - 1, -1, -1)
            )
            for x in xs:
                if moved[y, x]:
                    continue
                eid = grid.get(x, y)
                if eid == ElementId.EMPTY:
                    continue
                fn = RULES.get(ElementId(eid))
                if fn is None:
                    continue
                dest = fn(grid, x, y)
                if dest is not None:
                    dx, dy = dest
                    moved[dy, dx] = True
```

Replace it (and ONLY it — leave `simulation.py:42-52` and the diffusion call
at `simulation.py:49` untouched) with:

```python
        # Movement scan: y-descending (bottom -> top) so a single grain falls
        # at most one cell per step (no teleporting through the grid). The x
        # direction is randomized per row to avoid left bias. SPARSE: only
        # non-empty cells of each row are visited (np.nonzero on the row),
        # skipping the (frequently many) empty cells that were no-ops before.
        data = grid.array  # raw (H, W) uint8; read directly (no per-cell get() overhead)
        for y in range(grid.height - 1, -1, -1):           # y-descending — UNCHANGED
            xs = np.nonzero(data[y])[0]                    # non-empty x's this row (ascending)
            if xs.size == 0:
                continue                                   # empty row -> skipped in one numpy call
            if random.random() < 0.5:                      # per-row random direction — UNCHANGED
                xs = xs[::-1]
            for x in xs:
                x = int(x)                                 # numpy intp -> plain int (mypy + rule args)
                if moved[y, x]:
                    continue
                # Mid-scan re-check: a cell non-empty at nonzero-time may have
                # emptied/transformed earlier in this scan (fire expired,
                # erased, displaced). Re-read the raw array and skip if now empty.
                eid = int(data[y, x])
                if eid == int(ElementId.EMPTY):
                    continue
                fn = RULES.get(ElementId(eid))
                if fn is None:
                    continue
                dest = fn(grid, x, y)
                if dest is not None:
                    dx, dy = dest
                    moved[dy, dx] = True
```

**Properties the implementer MUST verify are preserved (the whole correctness
argument):**

- **y-descending outer loop** — `range(grid.height - 1, -1, -1)` is byte-for-byte
  unchanged. Columns still settle one cell per step.
- **Per-row random direction** — `if random.random() < 0.5: xs = xs[::-1]` is
  unchanged in spirit and in RNG draw count: exactly one `random.random()`
  call per row, same as before. The only difference is `xs` starts as the
  non-empty subset (ascending from `np.nonzero`) instead of `range(width)`;
  reversing it gives the descending non-empty subset. Horizontal bias is
  unchanged.
- **`moved` guard unchanged** — still marks movement *destinations*
  (`moved[dy, dx] = True`), still checked at loop top (`if moved[y, x]:
  continue`). Still required: a destination cell is non-empty after the move,
  so it IS in the active set and could be visited later in the same row scan
  (e.g. sand displacing water swaps into a water cell not yet scanned).
- **Mid-scan empty re-check** — `eid = int(data[y, x]); if eid ==
  int(ElementId.EMPTY): continue`. NEW but only because we now read the raw
  array: a cell non-empty at nonzero-time may have emptied during the scan.
  Cheap (one int compare) and correct.
- **Reading `data[y, x]` is in-bounds without `grid.get`'s bounds check** —
  `x` comes from `np.nonzero(data[y])[0]`, which is guaranteed in `[0,
  width)` for row `y`. The per-cell `grid.get` bounds check + `int()` cast
  overhead is eliminated.
- **RNG sequence is unchanged** — the only `random.*` call is still the one
  `random.random()` per row for the direction flip. (Sand/water rules draw
  their own RNG internally; those calls are unaffected because the same cells
  are dispatched in the same order. If a re-verification shows a previously-
  passing randomized test now draws a different RNG stream, that is a bug —
  investigate before "fixing" the test.)

### 2. `src/sandfall/simulation.py` — update the class docstring

The `Simulation` class docstring (`simulation.py:16-30`) describes the scan
order. Add one sentence noting the scan is now sparse (visits only non-empty
cells per row), and that empty rows are skipped in one numpy call. Keep the
existing sentences about y-descending, per-row random direction, the moved
guard, and the diffusion pre-pass — they are all still true. Example
insertion (after the existing "randomized per row" sentence):

```python
    The x scan is SPARSE: only the non-empty cells of each row are visited
    (``np.nonzero`` on the row), so empty rows and empty cells are skipped
    cheaply instead of being iterated as no-ops. This is a performance
    optimization only -- empty cells were no-ops before, so the result is
    identical to the old full-row scan.
```

### 3. `tests/test_simulation.py` — ADD two focused regression tests

These pin the sparse path on a wide, mostly-empty grid (so the `np.nonzero`
skip is actually exercised at scale, not just on a tiny grid where empty
cells are few). Append after the existing tests.

```python
def test_sparse_scan_piles_sand_on_floor_in_mostly_empty_grid() -> None:
    """Regression guard for the sparse (non-empty-only) scan path.

    A wide, mostly-empty grid with a full floor and a column of sand well
    above it: the sparse scan must still settle every grain directly onto the
    floor. The empty cells that are now skipped were no-ops before, so the
    result is identical to the old full-row scan. Pins that sparsifying the
    scan did not break movement at scale.
    """
    _seed()
    width, height = 20, 12
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    # A column of sand in the upper-middle, surrounded by air on all sides.
    for y in range(0, 4):
        grid.set(width // 2, y, ElementId.SAND)
    sim = Simulation(grid)

    for _ in range(60):
        sim.step()

    sand_mask = grid.array == int(ElementId.SAND)
    assert int(sand_mask.sum()) == 4  # no sand lost
    # Every grain rests directly on the floor row (height - 2).
    for y in range(height):
        for x in range(width):
            if sand_mask[y, x]:
                assert y == height - 2, (x, y)
    # The floor is entirely intact.
    for x in range(width):
        assert grid.get(x, height - 1) == ElementId.STONE


def test_sparse_scan_water_finds_its_level() -> None:
    """Water in a mostly-empty grid settles so no grain is suspended over air.

    Liquid flow is randomized; the test seeds the RNG and asserts the settled
    physical invariant (no water cell with an empty cell directly below it)
    after a generous step budget. Pins that liquid flow still works under the
    sparse scan (empty cells skipped were no-ops before).
    """
    _seed()
    width, height = 12, 10
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)
    # A blob of water in the upper-left, surrounded by air.
    for y in range(0, 3):
        for x in range(0, 4):
            grid.set(x, y, ElementId.WATER)
    sim = Simulation(grid)

    for _ in range(120):
        sim.step()

    water_mask = grid.array == int(ElementId.WATER)
    assert int(water_mask.sum()) == 12  # no water lost
    # Settled invariant: no water cell has an empty cell directly below it
    # (every water cell rests on the floor or on another water cell).
    for y in range(height - 1):
        for x in range(width):
            if water_mask[y, x]:
                assert grid.get(x, y + 1) != int(ElementId.EMPTY), (x, y)
```

Notes for the implementer:
- Both tests seed `random.seed(0)` via `_seed()` (the existing helper at
  `tests/test_simulation.py:18-20`) for determinism, matching the file's
  convention.
- The sand-piles test is fully deterministic given the seed (sand's rule is a
  deterministic down/down-diagonal fall modulo the per-row direction flip,
  which the seed fixes).
- The water-levels test asserts a physical invariant (no suspended water),
  not exact positions — robust to water's randomized sideways flow. If the
  120-step budget proves insufficient on a slow host, WIDEN THE BUDGET
  (document the re-tune in the reflection); do NOT loosen the invariant.

## Acceptance Criteria

- [ ] `Simulation.step`'s movement scan iterates `np.nonzero(data[y])[0]` per
      row (NOT `range(grid.width)`); empty rows hit the `if xs.size == 0:
      continue` fast path; the y-descending outer loop, the per-row
      `random.random() < 0.5` direction flip, and the `moved` guard are all
      byte-for-byte preserved.
- [ ] The scan reads the raw array via the public `grid.array` property (not
      `grid.get(x, y)` per cell); `x = int(x)` and `eid = int(data[y, x])`
      casts are present; the mid-scan `if eid == int(ElementId.EMPTY):
      continue` re-check is present.
- [ ] The diffusion pre-pass (`diffuse_temps` call at `simulation.py:49`) is
      UNCHANGED.
- [ ] The `Simulation` class docstring notes the scan is sparse and that the
      result is identical to the old full-row scan.
- [ ] **The entire existing test suite stays green** — this is the headline
      correctness guard. In particular: `test_sand_falls_one_row_per_step`,
      `test_sand_falls_multiple_rows_over_multiple_steps`,
      `test_sand_does_not_fall_through_floor`,
      `test_sand_piles_on_floor_without_sinking`,
      `test_sand_does_not_move_when_fully_supported`,
      `test_empty_grid_steps_without_error`, `test_sand_sinks_through_water`,
      and all fire/phase/lava/thermal tests.
- [ ] `test_sparse_scan_piles_sand_on_floor_in_mostly_empty_grid` passes.
- [ ] `test_sparse_scan_water_finds_its_level` passes (re-tune the step budget
      ONLY if flaky, and document it).
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the two new sparse-scan tests + the existing physical tests):
uv run pytest tests/test_simulation.py -v

# Import smoke:
uv run python -c "import sandfall"

# FULL suite — the headline regression guard (fire/phase/lava/thermal ripples):
uv run pytest

# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
```

All commands must exit zero. If a previously-passing randomized test fails,
investigate the RNG stream before re-tuning (the sparse scan must NOT change
the number/order of `random.*` draws — only one `random.random()` per row for
the direction flip, same as before).

## Documentation Updates

- The `Simulation` class docstring is updated as part of the code change above
  (it is the source of truth for scan semantics).
- `docs/ARCHITECTURE.md` — if it describes the movement scan as visiting every
  cell, update it to note the sparse (non-empty-only) per-row scan and that
  the result is identical to the old full scan. If it does not describe the
  scan at that level, leave it. Note whichever you find in the reflection.

## Reflection & Commit

After implementation, write `01-sparse-scan-reflection.md` in this directory.
**Specifically include:**

- The measured before/after `Simulation.step` time on (a) an empty 200×140
  grid and (b) a ~59%-busy grid (the headline perf evidence — NOT a test gate,
  but report the numbers). Cite the measurement method (e.g. `timeit` over N
  frames, or a one-off script under `/tmp/opencode/`).
- Confirmation that the full suite stayed green and that NO existing test
  needed an RNG-stream re-tune (if one did, explain why and what was changed).
- Whether `docs/ARCHITECTURE.md` described the scan and was updated.
- Anything difficult/unexpected, deviations from this plan + why, and
  anything fun discovered (e.g. the measured per-row `np.nonzero` overhead vs
  the ~26 ms saved).

Then make ONE atomic git commit covering all changes in this phase.

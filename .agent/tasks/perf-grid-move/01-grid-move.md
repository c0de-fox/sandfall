# Phase 01: Grid.move raw-array fast-swap + swap delegation

## Objective

Add `Grid.move(x1, y1, x2, y2) -> None` — a raw 3-array element swap across
`_data` (ids), `_life`, and `_temp` via numpy tuple-assignment, with **NO
per-access bounds check** and **NO clipping** (documented precondition: both
cells in-bounds, caller-guaranteed) — and rewrite `swap()` in
`rules/_common.py` to delegate to it as a one-liner. This collapses the per-move
cost from 12 Grid method calls (6 get + 6 set) to 1, with **zero rule edits**
(all 16 `swap` call sites across sand/water/lava/steam/smoke/fire are
unchanged). The headline regression guard is **the full existing suite (173
tests) staying green**; one new focused test pins the id+life+temp carry.

## Depends On

none — single phase (the `Grid.move` method and the `swap` delegation are
mutually dependent and land together; see the overview's Dependency Map).

## Can Parallelize With

nothing — single phase.

## Recommended Agent

@implementer — two small, behavior-preserving edits (`grid.py` adds a method;
`rules/_common.py` rewrites a function body) plus one headless test. Read
`00-overview.md` first (especially Decision Log #1-#4 and Risks #1-#2), then
re-read `src/sandfall/grid.py`, `src/sandfall/rules/_common.py`, and the six
rule files before editing. **Run the bounds-safety audit first** (step 0 below)
and record its result — it is the evidence that dropping the per-access bounds
check is safe. Do NOT be tempted to add a bounds check or clip inside `move`
(Decision Log #1, #2) — that is exactly the cost being removed.

## Changes Required

- `src/sandfall/grid.py` — ADD `Grid.move(x1, y1, x2, y2) -> None`: a raw
  3-array element swap (numpy tuple-assignment) with no bounds check and no
  clip, plus a docstring stating the in-bounds precondition and why no clip is
  safe.
- `src/sandfall/rules/_common.py` — REWRITE `swap()` body to a one-line delegate
  `grid.move(x1, y1, x2, y2)`; update its docstring (it now delegates to
  `Grid.move`; no longer the 12-call path). Signature unchanged.
- `tests/test_grid.py` — ADD `test_grid_move_swaps_id_life_and_temp` (focused
  correctness test pinning all three arrays carry on the swap).
- The six rule files — **NO change.** All 16 `swap(grid, x1, y1, x2, y2)` call
  sites are unchanged (the signature/semantics are identical; they just run
  faster). Listed so the implementer runs the audit (step 0) rather than assumes
  this.

## Implementation Instructions

> Re-read `src/sandfall/grid.py` and `src/sandfall/rules/_common.py` before
> editing — line numbers below are current at planning time and may have drifted.
> This is two small edits + one test; no new dependencies, no signature changes
> to any public method (only a new `Grid.move` and a rewritten `swap` body).

### 0. Bounds-safety audit (RUN FIRST — encode the result in the reflection)

`Grid.move` drops the per-access bounds check, so a raw numpy index on an OOB
cell would raise `IndexError` (loud) instead of `set()`'s silent no-op. Confirm
EVERY `swap` call site pre-checks bounds before calling `swap`, so no caller can
hand OOB coordinates to `Grid.move`. The audit was performed at planning time and
is clean — re-verify by re-reading each rule; the expected pre-check per call
site is:

| Rule      | swap site          | Pre-check (must hold before the swap)                          |
|-----------|--------------------|----------------------------------------------------------------|
| sand.py   | `:46` straight-down| `y + 1 < grid.height` (`:45`)                                  |
| sand.py   | `:56` down-diag    | `grid.in_bounds(nx, ny)`, ny=y+1 (`:55`)                       |
| water.py  | `:63` straight-down| `y + 1 < grid.height` (`:62`)                                  |
| water.py  | `:73` down-diag    | `grid.in_bounds(nx, ny)`, ny=y+1 (`:72`)                       |
| water.py  | `:83` sideways     | `grid.in_bounds(nx, ny)`, ny=y (`:82`)                         |
| lava.py   | `:85` straight-down| `y + 1 < grid.height` (`:84`)                                  |
| lava.py   | `:95` down-diag    | `grid.in_bounds(nx, ny)`, ny=y+1 (`:94`)                       |
| lava.py   | `:105` sideways    | `grid.in_bounds(nx, ny)`, ny=y (`:104`)                        |
| steam.py  | `:54` straight-up  | `y - 1 >= 0` (`:53`)                                           |
| steam.py  | `:61` up-diag      | `grid.in_bounds(nx, ny)`, ny=y-1 (`:60`)                       |
| steam.py  | `:71` sideways     | `grid.in_bounds(nx, ny)`, ny=y (`:70`)                         |
| smoke.py  | `:37` straight-up  | `y - 1 >= 0` (`:36`)                                           |
| smoke.py  | `:44` up-diag      | `grid.in_bounds(nx, ny)`, ny=y-1 (`:43`)                       |
| smoke.py  | `:54` sideways     | `grid.in_bounds(nx, ny)`, ny=y (`:53`)                         |
| fire.py   | `:116` straight-up | `y - 1 >= 0` (`:115`)                                          |
| fire.py   | `:123` up-diag     | `grid.in_bounds(nx, ny)`, ny=y-1 (`:122`)                      |

For the straight-down/up sites, `y ± 1` is checked and `x` is unchanged (and `x`
was valid — the cell is being scanned, so it is in-bounds), so both cells are
in-bounds. For every diagonal/sideways site, `grid.in_bounds(nx, ny)` confirms
the destination; the source `(x, y)` is in-bounds because it is being scanned.
**Result expected: all 16 sites pre-check — the precondition holds at every
caller.** If any site does NOT pre-check, STOP and flag it (do not proceed until
the rule is fixed or the plan is revised) — a missed pre-check would crash
loudly under `Grid.move`. Record the confirmed-clean audit in the reflection.

### 1. `src/sandfall/grid.py` — ADD `Grid.move`

Place the new method after `set_temp` (currently ends at `grid.py:235`) and
before `fill_circle` (currently starts at `grid.py:237`) — it groups naturally
with the other indexed accessors (`get`/`set`/`get_life`/`set_life`/`get_temp`/
`set_temp`/`move`). Exact code:

```python
    def move(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Swap the contents (element id AND life AND temp) of two cells, raw.

        This is the fast path used by :func:`sandfall.rules._common.swap`: it
        exchanges all three parallel arrays (``_data``, ``_life``, ``_temp``)
        at ``(x1, y1)`` and ``(x2, y2)`` in a single numpy tuple-assignment per
        array, with **no per-access bounds check** and **no clipping**.

        Precondition (the caller MUST guarantee): both ``(x1, y1)`` and
        ``(x2, y2)`` are in bounds. Every ``swap`` call site pre-checks bounds
        today (see the audit in ``.agent/tasks/perf-grid-move/01-grid-move.md``),
        so this holds at every caller. A raw numpy index on an out-of-bounds
        cell raises ``IndexError`` (loudly) rather than the silent no-op that
        :meth:`set` / :meth:`set_temp` perform — so a missed pre-check fails
        loudly in the suite, not silently.

        No clip is needed (and none is applied): every stored value is already
        in-band because the only writers (:meth:`set_temp` clips to
        ``[TEMP_MIN, TEMP_MAX]``, :meth:`set_life` clips to ``[0, 255]``, and
        :meth:`set` for ids) clip at write time, so swapping two in-band values
        cannot leave the band. The three arrays are independent (no aliasing
        between them); the tuple-assignment evaluates each RHS fully before
        assigning, so it is a correct two-cell exchange even though source and
        destination share one array.
        """
        d = self._data
        d[y1, x1], d[y2, x2] = d[y2, x2], d[y1, x1]
        life = self._life
        life[y1, x1], life[y2, x2] = life[y2, x2], life[y1, x1]
        temp = self._temp
        temp[y1, x1], temp[y2, x2] = temp[y2, x2], temp[y1, x1]
```

Notes for the implementer:
- Binding each array to a local (`d`/`life`/`temp`) is a micro-opt that avoids
  three `self.` attribute lookups per line on the hot path; keep it. mypy is
  happy (the locals are the typed NDArray attributes).
- Do NOT add an `in_bounds` guard, a `return`-on-OOB, or any `int()` cast —
  that is the overhead being removed (Decision Log #1). Callers pass plain
  `int`s already.

### 2. `src/sandfall/rules/_common.py` — rewrite `swap` to delegate

Replace the entire `swap` body (`_common.py:83-94`, the 12 lines of
get/set/get_life/set_life/get_temp/set_temp) with a one-line delegate. The
function signature and docstring header stay; update the docstring to note the
delegation. Replace:

```python
def swap(grid: Grid, x1: int, y1: int, x2: int, y2: int) -> None:
    """Swap the contents (element id AND life AND temp) of two in-bounds cells.

    Both cells must be in bounds. Carrying life and temp along on every move
    is what keeps FIRE/SMOKE lifetimes and per-cell temperatures correct when
    those cells get pushed around (e.g. fire rising, sand displacing a cell
    that later becomes fire).
    """
    a = grid.get(x1, y1)
    b = grid.get(x2, y2)
    grid.set(x1, y1, b)
    grid.set(x2, y2, a)
    la = grid.get_life(x1, y1)
    lb = grid.get_life(x2, y2)
    grid.set_life(x1, y1, lb)
    grid.set_life(x2, y2, la)
    ta = grid.get_temp(x1, y1)
    tb = grid.get_temp(x2, y2)
    grid.set_temp(x1, y1, tb)
    grid.set_temp(x2, y2, ta)
```

with:

```python
def swap(grid: Grid, x1: int, y1: int, x2: int, y2: int) -> None:
    """Swap the contents (element id AND life AND temp) of two in-bounds cells.

    Delegates to :meth:`sandfall.grid.Grid.move`, the raw 3-array element swap
    (one numpy tuple-assignment per array, no per-access bounds check, no
    clipping) -- the fast path that replaced the old 12-call get/set sequence.
    Carrying life and temp along on every move is what keeps FIRE/SMOKE
    lifetimes and per-cell temperatures correct when those cells get pushed
    around (e.g. fire rising, sand displacing a cell that later becomes fire).

    Precondition (inherited from ``Grid.move``): both cells must be in bounds.
    Every caller pre-checks bounds today (see the audit in
    ``.agent/tasks/perf-grid-move/01-grid-move.md``); a raw index on an OOB
    cell raises ``IndexError`` rather than failing silently.
    """
    grid.move(x1, y1, x2, y2)
```

The signature `(grid, x1, y1, x2, y2) -> None` is byte-for-byte unchanged, so all
16 rule call sites compile and behave identically (only faster). No rule file is
edited.

### 3. `tests/test_grid.py` — ADD `test_grid_move_swaps_id_life_and_temp`

Append after the existing `test_swap_carries_temp` (`tests/test_grid.py:261`),
mirroring its setup (two cells with distinct id + temp) but ALSO exercising
life, and asserting all three arrays carried. This pins both the tuple-swap
correctness and the id+life+temp carry directly against `Grid.move`:

```python
def test_grid_move_swaps_id_life_and_temp() -> None:
    """Grid.move exchanges id AND life AND temp across the two cells (raw swap).

    Pins the fast-path used by rules._common.swap: a single numpy
    tuple-assignment per array with no bounds check and no clip. Verifies the
    tuple-swap evaluates the RHS before assigning (so each cell ends up with the
    OTHER cell's value, not its own) and that all three parallel arrays carry.
    """
    grid = Grid(width=3, height=3)
    # Cell A: SAND, life 12, hot.
    grid.set(0, 0, ElementId.SAND)
    grid.set_life(0, 0, 12)
    grid.set_temp(0, 0, 900)
    # Cell B: WATER, life 0, cold.
    grid.set(1, 1, ElementId.WATER)
    grid.set_life(1, 1, 0)
    grid.set_temp(1, 1, 10)

    grid.move(0, 0, 1, 1)

    # All three arrays swapped: A took B's values, B took A's values.
    assert grid.get(0, 0) == ElementId.WATER
    assert grid.get_life(0, 0) == 0
    assert grid.get_temp(0, 0) == 10
    assert grid.get(1, 1) == ElementId.SAND
    assert grid.get_life(1, 1) == 12
    assert grid.get_temp(1, 1) == 900
```

Notes for the implementer:
- `ElementId` and `Grid` are already imported at the top of `test_grid.py`
  (`:8-9`); no new top-level import needed. (`set_temp`/`set_life`/`get_temp`/
  `get_life` are `Grid` methods, no import.)
- This is a deterministic state check, NOT a timing assertion (Decision Log #7).
  Do not add any perf/timing assertion anywhere.

### 4. Verify the six rule files are unchanged

Confirm the audit (step 0) found all 16 sites pre-check bounds, and that NO rule
file was edited. Run `git diff --stat src/sandfall/rules/{sand,water,lava,steam,
smoke,fire}.py` — it must show no changes. (If a rule needed an edit, that is a
deviation: explain why in the reflection and confirm the full suite still
passes.)

## Acceptance Criteria

- [ ] `Grid.move(x1, y1, x2, y2) -> None` exists; it swaps all three arrays
      (`_data` id + `_life` + `_temp`) via numpy tuple-assignment; it performs
      NO per-access bounds check and NO clipping; its docstring states the
      in-bounds precondition and why no clip is safe.
- [ ] `swap()` in `rules/_common.py` delegates to `grid.move(x1, y1, x2, y2)` as
      a one-line body; its docstring is updated to note the delegation + the
      inherited precondition; its signature `(grid, x1, y1, x2, y2)` is
      unchanged.
- [ ] **All 16 rule call sites are unchanged** — zero edits to
      `sand.py`/`water.py`/`lava.py`/`steam.py`/`smoke.py`/`fire.py`.
- [ ] **Bounds audit complete**: all 16 sites pre-check bounds before calling
      `swap` (the step-0 table confirmed clean); the result is recorded in the
      reflection.
- [ ] **Behavior identical** — the full existing suite (173 tests) stays green.
      In particular `test_swap_carries_temp` (`test_grid.py:261`) and every
      fire/lava/steam lifetime + thermal-physics test pass unchanged.
- [ ] `test_grid_move_swaps_id_life_and_temp` passes (id + life + temp all carry;
      tuple-swap puts each cell's values at the other cell).
- [ ] **No timing assertions** are added anywhere; perf is MEASURED and reported
      in the reflection.
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the new Grid.move test + existing swap/grid tests):
uv run pytest tests/test_grid.py -v

# Import smoke:
uv run python -c "import sandfall"

# FULL suite -- the headline regression guard (173 tests; temp/life-carry
# tests + fire/lava/steam lifetime + thermal physics all exercise swap):
uv run pytest

# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
```

All commands must exit zero. Do NOT proceed until the FULL suite is green. If a
previously-passing test fails (especially a temp/life-carry test), a field was
dropped or a swap inverted in `Grid.move` — fix `move`/`swap`, do NOT weaken the
test.

## Documentation Updates

- The `Grid.move` docstring (step 1) is the source of truth for the raw-swap
  semantics + the precondition; the rewritten `swap` docstring (step 2) points
  to it. No external doc change is required for this perf-only, behavior-
  preserving change.
- `docs/ARCHITECTURE.md` — if it describes `swap` as doing "12 Grid method
  calls" or enumerates the get/set sequence, update it to note `swap` now
  delegates to `Grid.move` (raw 3-array element swap). If it does not describe
  `swap` at that level of detail, leave it. Note whichever you find in the
  reflection.

## Reflection & Commit

After implementation, write `01-grid-move-reflection.md` in this directory.
**Specifically include:**

- The bounds-safety audit result (the step-0 table, confirmed clean) — the
  evidence that dropping the per-access bounds check is safe.
- The measured before/after `Simulation.step` time on (a) a busy/falling ~25%-
  fill scene (the headline: target ~2-3× on rule cost — report actual), and
  (b) a settled pile (confirms dormancy is unaffected — should be unchanged;
  report actual before/after). Cite the measurement method (e.g. `timeit` over
  N frames via a one-off script under `/tmp/opencode/`).
- Confirmation that the full suite (173 tests) stayed green and that NO rule
  file was edited (`git diff --stat src/sandfall/rules/*.py` empty for the six
  movement rules).
- Whether `docs/ARCHITECTURE.md` described `swap` at the call-count level and
  was updated.
- Anything difficult/unexpected, deviations from this plan + why, and anything
  fun discovered (e.g. how close the actual win came to the ~2-3× target, and
  what share of the residual per-cell cost `can_displace` now represents — the
  next deferred lever).

Then make ONE atomic git commit covering all changes in this phase.

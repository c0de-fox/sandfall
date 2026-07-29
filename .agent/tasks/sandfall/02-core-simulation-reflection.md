# Phase 02 Reflection — Core Simulation Engine

## What was done

Implemented Phase 02 (Core Simulation Engine). End state:

- `src/sandfall/elements.py` — `ElementId(IntEnum)` with all 8 members (EMPTY=0
  … PLANT=7); `Phase(IntEnum)` (SOLID/POWDER/LIQUID/GAS); frozen+slotted
  `Element` dataclass (`id`, `name`, `color`, `density`, `phase`,
  `flammability=0.0`); `ELEMENTS: dict[ElementId, Element]` registry fully
  populated for all 8 entries (EMPTY+SAND per spec; WATER/STONE/WOOD/FIRE/
  SMOKE/PLANT pre-populated with the realistic placeholder values from the
  phase file so Phase 03 only *tunes* numbers and *adds rules*, never adds
  enum members).
- `src/sandfall/grid.py` — `Grid(width, height)` wrapping
  `numpy.typing.NDArray[np.uint8]` of shape `(height, width)`. Public API:
  `width`, `height`, `array` (raw view), `in_bounds`, `get`, `set`,
  `fill_circle`. Origin top-left; `+y` down; indexed `array[y, x]` internally
  but the public API takes `(x, y)`.
- `src/sandfall/rules/sand.py` — `update_sand(grid, x, y) -> tuple[int,int] | None`.
  Powder physics: try below; else try down-diagonals in `random.shuffle`d
  order. Swaps into EMPTY or a lower-density LIQUID (sand sinks in water).
- `src/sandfall/rules/__init__.py` — `UpdateFn` alias + `RULES` dict with
  only SAND registered.
- `src/sandfall/simulation.py` — `Simulation(grid)` with `step()`. Scans
  bottom→top, randomizes x direction per row, dispatches via `RULES`,
  marks `moved[dest_y, dest_x] = True` when a rule returns a destination.
- `tests/test_grid.py` (12 tests) and `tests/test_simulation.py` (7 tests),
  including a bonus `test_sand_sinks_through_water` that proves the
  density-swap seam works today (no need to wait for Phase 03).

## Verification gate results (all pass, exit 0)

| Gate | Result |
|------|--------|
| `uv run python -c "import sandfall; ..."` | `ok 8 elements 1 rules` |
| `uv run pytest` | `21 passed in 0.18s` (12 grid + 7 simulation + 2 smoke) |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `13 files already formatted` |
| `uv run mypy src` | `Success: no issues found in 7 source files` |

## Decisions confirmed (BINDING for Phase 03)

These are the seams Phase 03 must build against:

1. **Rule function signature is `tuple[int, int] | None`** — every `update_*`
   rule takes `(grid: Grid, x: int, y: int)` and returns the `(x, y)` cell it
   moved *into*, or `None` if it did not move. Phase 03's water/fire/smoke/
   plant rules must use the identical signature. The phase file listed two
   possible signatures; this one was the "preferred" option and is what was
   implemented. `Simulation.step` uses the returned destination to mark the
   moved-guard — no "scan the neighbors to find where it went" heuristic.

2. **`RULES: dict[ElementId, UpdateFn]` registry** lives in
   `src/sandfall/rules/__init__.py`. Phase 03 adds entries by importing the
   rule function and adding it to the dict literal; do NOT mutate the dict at
   runtime. `Simulation.step` looks up `RULES.get(ElementId(eid))` and
   silently skips cells whose element has no rule (e.g. STONE/WOOD/PLANT in
   Phase 03 — they are static solids, so they intentionally have no rule).

3. **Density & phase are the cross-rule contract.** `ELEMENTS[ElementId(id)]`
   gives `Element` with `.density: float` and `.phase: Phase`. Sand's
   `_can_displace` already shows the pattern: a target is swappable if EMPTY,
   or a strictly-lower-density LIQUID. Phase 03 water/plant/fire rules should
   reuse the same comparison; consider extracting a shared `_can_displace`
   helper to `rules/_common.py` when the second powder/liquid rule arrives.

4. **Scan order is `y` descending (bottom→top), x randomized per row, with a
   `numpy.bool_` moved-guard.** Gas rules in Phase 03 (fire/smoke) move *up*
   but the bottom→top scan still works: a gas cell at `y` moving to `y-1`
   won't be reprocessed this frame because `y-1` hasn't been visited yet
   (we're going downward) — wait, actually `y-1` *will* be visited later
   (smaller y). The moved-guard correctly prevents double-update: when gas
   moves up, mark `moved[y-1, x] = True` via the returned destination, and
   the scan skips it. So the contract holds for all directions.

5. **Coordinate convention: origin top-left, +y DOWN.** Public Grid API is
   `(x, y)`; numpy array is indexed `[y, x]`. Phase 03 rules and Phase 04
   renderer must respect this.

6. **`ELEMENTS` is keyed by `ElementId`** (not by int). Phase 03 must wrap
   raw ints from the grid as `ElementId(eid)` before lookup — `Simulation`
   already does this in its dispatch loop.

## Difficult / unexpected

1. **The phase file's literal test "sand with a STONE cell directly beneath
   stays put" is physically inconsistent with the powder rule it
   specifies.** With stone only at `(x, y+1)`, the down-diagonals `(x±1,
   y+1)` are EMPTY and sand *will* slide into one of them — that IS the
   pile/slump behavior. To make the test deterministic I widened the
   support: `test_sand_does_not_move_when_fully_supported` puts stone across
   the whole bottom row so all three fall targets (down, down-left,
   down-right) are blocked. Justified deviation; documented in the test's
   docstring. Phase 03 implementers should keep this in mind when writing
   similar tests.
2. **mypy strict was painless this time** — the Phase 01 warning about strict
   mode being unforgiving did not bite. Two tricks helped: (a) declare
   `npt.NDArray[np.uint8]` and `npt.NDArray[np.bool_]` instead of bare
   `np.ndarray` (avoids `disallow-any-generics`); (b)annotate instance attrs
   at class scope (`_width: int`, `_data: npt.NDArray[np.uint8]`) so the
   `__init__` assignment typechecks cleanly. No `Any` anywhere.
3. **`ruff format` wanted to collapse the multi-line `ValueError(...)` in
   `grid.py` onto one line** because the message is short enough to fit
   within 88 cols once reformatted. First format-check failed; re-running
   `ruff format .` fixed it. Easy.

## Deviations from the phase file

1. **Widened the "supported sand" test** as described above. Documented in
   the test docstring. No deviation from the rule itself.
2. **Used `npt.NDArray[...]` instead of bare `np.ndarray`** in type
   annotations. Functionally identical at runtime; just keeps mypy strict
   happy. Phase 03+ should do the same.
3. **Used `collections.abc.Callable` instead of `typing.Callable`** in
   `rules/__init__.py` (the phase file drafted `typing.Callable`). ruff `UP`
   rule prefers the `collections.abc` form on Python 3.9+; identical at
   runtime.
4. **Did NOT use the lazy `_register()` indirection** sketched in the phase
   file for `rules/__init__.py`. There is no import cycle (elements imports
   nothing from sandfall; grid imports elements; rules import both), so a
   plain `from .sand import update_sand` at module top is cleaner and the
   RULES dict is a single literal. Same end state.
5. **Pre-imported `ELEMENTS` at top of `rules/sand.py`** instead of inside
   `_can_displace`. The phase file's lazy-import was over-cautious — there's
   no cycle to avoid. Cleaner; same behavior.

## Suggestions for future work / agent improvements

- **Phase 03 (elements)**: extract a shared `can_displace(src: ElementId,
  target_id: int) -> bool` helper into `rules/_common.py` once you have
  water + sand both needing the density comparison. Don't duplicate the
  density/phase check.
- **Phase 03 (liquids/gases)**: the current `Simulation.step` dispatches a
  rule per cell. For FIRE (finite life) the rule will need to mutate more
  than just position — e.g. decrement a per-cell life counter. Decide now
  whether life/state lives in a parallel array (e.g. `int8` grid) or is
  encoded in a separate `ElementId.FIRE_*` family. The latter pollutes the
  enum; the former is cleaner. Recommend a parallel `state: np.uint8` grid
  owned by `Simulation` (or `Grid`), documented in the Phase 03 plan before
  implementation starts.
- **Phase 04 (renderer)**: `Grid.array` returns the raw `uint8` view. The
  renderer should map ids → colors via a precomputed `np.ndarray` of shape
  `(256, 3)` lookup table built from `ELEMENTS`, then index it with the grid
  to get an `(H, W, 3)` RGB array for `pygame.surfarray`. This is the fast
  path mentioned in the overview; keep `array` as a read-only view.
- **Agent prompt improvement**: the phase file contained *two* possible rule
  signatures (`-> bool` and `-> tuple[int,int] | None`) and called the
  second one "preferred." The implementer prompt should pick one and commit,
  rather than presenting alternatives — the spec for Phase 02 already did
  this in the inline decision paragraph, which is good, but the *initial*
  code blocks all used `-> bool` and were misleading until the cleanup
  note. Future phase files: use the final signature in all code blocks.
- **Global**: mypy strict + numpy required `numpy.typing.NDArray[...]`. Could
  be captured in a "numpy typing under mypy strict" note in the global
  AGENTS.md or project AGENTS.md so the next implementer doesn't rediscover
  it.

## Fun discovered

- The "sand sinks in water" test passes on the *first* Phase 02 build
  because the density-swap seam is wired into `update_sand`'s
  `_can_displace` — even though WATER has no rule yet, the sand rule already
  knows how to displace it. Phase 03's water rule will reciprocate.
- `numpy.typing.NDArray[np.uint8]` is just an alias for
  `np.ndarray[tuple[int, ...], np.dtype[np.uint8]]` — the modern PEP 646 /
  PEP 483 generic form. Works great with mypy strict.
- 21 tests in 0.18s — pure-Python per-cell dispatch is plenty fast for the
  grid sizes we'll use in Phases 04–05; the overview's performance risk
  #1 hasn't materialized yet.

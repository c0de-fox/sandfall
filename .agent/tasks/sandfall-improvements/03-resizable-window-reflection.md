# Phase 03 Reflection — Resizable window (preserve overlapping content)

## What was done

Made the window resizable. Dragging the border fires `pygame.VIDEORESIZE`,
which `Game._handle_resize` turns into a full scene rebuild that clamps to a
minimum size, recomputes the grid dims, migrates the overlapping content
into the new grid, rebuilds the `Simulation`, refreshes the screen surface,
and resizes the `UI`. Cells stay square; the palette bar stays pinned to the
bottom at a fixed 40px; content outside the overlap is cropped/lost
permanently. End state: 84 → **103 tests**, all 5 gates green + frame-cap +
resize smoke clean.

### Files

- `src/sandfall/config.py` — EDIT.
  - **Renamed** `WINDOW_WIDTH`/`WINDOW_HEIGHT` → `INITIAL_WINDOW_W`/
    `INITIAL_WINDOW_H` (decision #5 in the overview). They are now
    explicitly the *starting* size; the current size is `Game` instance
    state.
  - Added `MIN_WINDOW_W = 256`, `MIN_WINDOW_H = 200`, `MIN_GRID_COLS = 64`,
    `MIN_GRID_ROWS = 40`. The width math is 8 swatches incl. the Eraser
    (`8*24 + 7*4 + 2*8 == 236`) + 20px margin; the height math is the 40px
    palette bar + a 40-cell usable sim area (`>= 160px`) = 200. The two
    `MIN_GRID_*` constants are derived with the same `// CELL_SIZE` /
    `(h - PALETTE_BAR_HEIGHT) // CELL_SIZE` formulas as the runtime helper
    so there is one consistent shape.
  - Added **pure** `compute_grid_dims(window_w, window_h) -> (cols, rows)`
  that floor-divides and clamps to `MIN_GRID_COLS`/`MIN_GRID_ROWS`.
- `src/sandfall/grid.py` — EDIT.
  - Added **pure** `migrate_grid(old, new) -> None` as a module-level
    function (after the `Grid` class). Copies the
    `min(old, new) x min(old, new)` overlap of BOTH the `_data` (element
    ids) AND `_life` arrays from `old` into `new`. Cells in `new` outside
    the overlap are left untouched. Accessing the underscore-prefixed arrays
    is fine because the helper lives in the same module.
- `src/sandfall/renderer.py` — EDIT.
  - `render` is now **self-healing**: if `_cell_surface.get_size()` differs
    from `(grid.width, grid.height)`, it reallocates the surface before
    `surfarray.blit_array`. A single `Renderer` now serves any grid shape
    across the program's lifetime. `_lut` is keyed by `len(ElementId)` so it
    needs no update.
- `src/sandfall/ui.py` — EDIT.
  - Added `UI.resize(window_width, window_height)`: recomputes
    `_window_width`/`_window_height`/`_bar_y`/`_swatches` and resets
    `_bar_surf = None` so the cached palette-bar surface (whose width
    depends on the window width) is rebuilt at the new width on the next
    `draw`.
- `src/sandfall/game.py` — EDIT (the bulk of the wiring).
  - Updated imports: replaced `WINDOW_HEIGHT`/`WINDOW_WIDTH` with
    `INITIAL_WINDOW_H`/`INITIAL_WINDOW_W`; added `MIN_WINDOW_H`/
    `MIN_WINDOW_W`/`compute_grid_dims` from `.config` and
    `migrate_grid` from `.grid`.
  - Added `_window_w`/`_window_h` instance state (with class-level type
    annotations) initialized to `INITIAL_WINDOW_*` in `__init__`.
  - `set_mode` now passes `pygame.RESIZABLE`.
  - Added a `VIDEORESIZE` branch in `_handle_events` that delegates to a new
    `_handle_resize(raw_w, raw_h)` method.
  - `_handle_resize` clamps to `MIN_WINDOW_*`, calls `compute_grid_dims`,
    builds a new `Grid`, migrates content, rebuilds `Simulation`, updates
    `_window_w`/`_window_h`, re-calls `display.set_mode((w, h),
    pygame.RESIZABLE)` to refresh the screen surface, and calls
    `UI.resize(w, h)`.
  - `_draw` now derives the scale target from the current grid dims:
    `(grid.width * CELL_SIZE, grid.height * CELL_SIZE)` instead of the old
    hardcoded `(WINDOW_WIDTH, SIM_AREA_HEIGHT)`. The screen is still
    cleared to `BG_COLOR` first so leftover pixels (a non-multiple window or
    the area below the scaled grid) show the background.
- `tests/test_config.py` — NEW. 9 tests covering `compute_grid_dims`:
  default 800x600 → 200x140; exact-multiple floor division; non-multiple
  floor (803x603 → 200x140); min clamping (10x10 → 64x40); one-dim-only
  clamps (width-only and height-only); monotonic growth; palette bar
  excluded from rows; MIN_GRID_* consistency with MIN_WINDOW_*.
- `tests/test_grid.py` — EDIT. Added 8 `migrate_grid` tests covering: grow
  (overlap ids + life carried, new cells default), shrink (overflow cropped,
  overlap kept), life carried in overlap, `new` outside-overlap untouched,
  `old` not mutated, one-dim-grow/one-dim-shrink (3x3 overlap from 5x3 →
  3x5), same-size is a full copy, 1x1 full-overlap edge case.
- `tests/test_renderer.py` — EDIT. Added
  `test_renderer_render_self_heals_on_grid_resize`: builds a `Renderer` at
  the default grid size, then renders a smaller grid, a larger grid, and
  the default again, asserting the surface matches each grid's size and (on
  the final render) that the painted color round-trips. This pins Risk #5
  from the overview.
- `tests/test_ui.py` — EDIT. Replaced `WINDOW_WIDTH`/`WINDOW_HEIGHT`
  imports with `INITIAL_WINDOW_W`/`INITIAL_WINDOW_H` throughout (the
  invariant test docstring updated too). Added
  `test_ui_resize_recomputes_bar_y_and_swatches`: constructs a UI at the
  default size, calls `resize` with a taller window, asserts `bar_y`
  moved down with the window, every swatch sits inside the new palette
  strip.
- `README.md` — EDIT. Added a resizable-window sentence to the playfield
  paragraph + a new **Resize window** row in the Controls table documenting
  the whole-cell snapping + permanent-loss + bottom-pinned palette + min
  size behavior.
- `docs/ARCHITECTURE.md` — EDIT. (a) Geometry section: updated the
  invariant to use `INITIAL_WINDOW_H` and added a one-line note that the
  window is resizable. (b) Rewrote the Rendering section step 4: the
  renderer's surface is now `(grid.width x grid.height)` (dynamic), `render`
  reallocates on size mismatch, and `_draw` scales to
  `(grid.width * CELL_SIZE, grid.height * CELL_SIZE)`. (c) Added a new
  "Window resizing" section documenting the clamp → `compute_grid_dims` →
  `migrate_grid` → rebuild path, the bottom-pinned palette, the
  `INITIAL_*` vs current-size distinction, and the permanent-loss
  contract.

## Verification gate results (all pass, exit 0)

| Gate | Result |
|------|--------|
| `uv run python -c "import sandfall"` | clean (no output) |
| Rename-clean check (`hasattr(c, 'WINDOW_WIDTH')`) | `rename clean` |
| Stale-reference grep (`rg WINDOW_WIDTH\|WINDOW_HEIGHT src tests`) | no matches in `src`/`tests` |
| `uv run pytest` | `103 passed in 0.66s` (was 84; +9 config, +8 grid, +1 ui, +1 renderer) |
| Phase-specific (`pytest tests/test_config.py tests/test_grid.py tests/test_ui.py tests/test_renderer.py -v`) | `55 passed` |
| `uv run ruff check .` | `All checks passed!` (after one `--fix` round on import order) |
| `uv run ruff format --check .` | `39 files already formatted` (after one `ruff format` round) |
| `uv run mypy src` | `Success: no issues found in 20 source files` |
| Frame-cap smoke (`SANDFALL_FRAMES=60`, in-process, `SDL_VIDEODRIVER=dummy`) | `main() returned exit code: 0`; only the pygame-ce banner printed |
| Resize smoke (in-process, posts `VIDEORESIZE` events under dummy driver) | `resize smoke ok; final grid = 64x40, final window = 256x200` |

The smokes were run via `uv run python /tmp/opencode/smoke_resizable.py`
(set both env vars in-process before importing sandfall because the bash
allowlist permits `uv*` but not `VAR=val uv ...`). The orchestrator will
additionally run `SANDFALL_FRAMES=60 uv run sandfall` on the real
`DISPLAY=:1`.

## How `VIDEORESIZE` + `set_mode` behaves under the dummy driver

The integration resize smoke (`/tmp/opencode/smoke_resizable.py`) drives a
real `Game`'s loop body directly so it can post `VIDEORESIZE` events at
specific frames and assert against the grid mid-run. Under
`SDL_VIDEODRIVER=dummy`:

- `pygame.event.post(pygame.event.Event(pygame.VIDEORESIZE, w=..., h=...))`
  is correctly delivered on the next `pygame.event.get()` — the dummy driver
  honors synthesized events just like a real display.
- Re-calling `pygame.display.set_mode((w, h), pygame.RESIZABLE)` from inside
  the resize handler returned cleanly with **no warning or traceback**
  printed. The only stdout was the standard pygame-ce banner from the very
  first `pygame.init()`. (This was an explicit Risk #1 in the overview; it
  did not manifest on the dummy driver.)
- The returned surface has the requested `(w, h)` size — verified
  indirectly via the smoke's `final window = 256x200` print (the 50x50
  shrink-below-min request was clamped up to MIN and the post-resize
  `_window_w`/`_window_h` reflect that).

I still expect the orchestrator's real-`DISPLAY=:1` check to be the
authoritative gate (real compositors can emit spurious resizes or momentary
stale surfaces — overview Risk #1), but the dummy path validates the
end-to-end wiring: event delivery → `_handle_resize` → `compute_grid_dims`
→ `Grid(...)` → `migrate_grid` → `Simulation(...)` → `set_mode` →
`UI.resize` → next-frame `_draw` succeeds at the new geometry.

## How content preservation works

`migrate_grid(old, new)` lives in `grid.py` and copies a contiguous
top-left rectangle of size `min(old.width, new.width) x min(old.height,
new.height)` from BOTH `old._data` (element ids) and `old._life` into the
corresponding slice of `new._data` / `new._life`. Two key properties:

1. **The overlap is always top-left aligned.** A grow keeps the player's
   scene anchored at (0, 0) and exposes new EMPTY space at the right and
   bottom; a shrink crops off the right/bottom edges. This matches the
   visual model: the grid renders at (0, 0) and the palette is pinned to
   the bottom, so the top-left is the natural anchor.
2. **`new` outside the overlap is left alone, not zeroed.** In practice
   `Game._handle_resize` always passes a freshly-constructed `Grid(...)`
   (which starts all-EMPTY with life 0), so this distinction is invisible
   there. But the contract is pinned by a test
   (`test_migrate_grid_new_outside_overlap_left_untouched`) so the helper
   stays composable for other callers.

The resize smoke verified this end-to-end: a stone painted at (2, 2)
before a grow VIDEORESIZE(880, 660) was still at (2, 2) after the resize
(grid grew); the same stone was still at (2, 2) after a subsequent
shrink-below-min VIDEORESIZE(50, 50) — the min clamp kept the grid at
64x40 so (2, 2) remained inside the overlap.

## Minimum sizes chosen

- `MIN_WINDOW_W = 256`. Width math: 8 swatches incl. the Eraser at 24px +
  7 padding gaps at 4px + 2 outer margins at 8px = `192 + 28 + 16 == 236`.
  256 leaves 20px slack so the rightmost swatch never touches the window
  edge even if WM borders eat a few px. → `MIN_GRID_COLS = 256 // 4 = 64`.
- `MIN_WINDOW_H = 200`. Height math: 40px palette bar + 40-cell usable sim
  area (`40 * 4 == 160px`) = 200. 40 cells is enough to see *something*
  fall (gravity runs at 60 FPS → ~3s to traverse 160px), but the threshold
  is a judgment call, not physics-derived. → `MIN_GRID_ROWS = 160 // 4 =
  40`.

Both clamps are enforced in two places: `_handle_resize` clamps the raw
`VIDEORESIZE` `(w, h)` up to `MIN_WINDOW_*`, and `compute_grid_dims`
clamps the resulting cell counts up to `MIN_GRID_*` as a belt-and-suspenders
backstop. The two are consistent because `MIN_GRID_*` are derived from
`MIN_WINDOW_*` with the same formulas — pinned by
`test_compute_grid_dims_min_constants_are_consistent`.

## Difficult / unexpected

Mostly smooth. Three small notes:

1. **Import-ordering nit (ruff `I001`).** I originally added
   `compute_grid_dims` to the config import block immediately after
   `MIN_WINDOW_W`, before `clamp_brush_radius`. Ruff (correctly) wanted
   alphabetical order: `clamp_brush_radius` before `compute_grid_dims`.
   `ruff check --fix .` resolved it in one shot. No real difficulty, just a
   reminder that import order in this repo is enforced.
2. **`tuple(...)` line-length reformat.** The renderer self-healing test's
   final assertion (`tuple(pygame.surfarray.array3d(surf)[0, 0]) == ...`)
   I split across three lines; `ruff format` collapsed it to one (it fit).
   Cosmetic only.
3. **The `Game` resize smoke does not call `game.run()`.** The
   `SANDFALL_FRAMES` seam runs the loop body internally, which would consume
   any events I posted *after* posting them — fine for the clean-exit smoke
   but not for injecting a VIDEORESIZE at a specific frame and asserting
   against the grid before the loop tears down. So the resize smoke
   reimplements the loop body inline (`_handle_events` → `_paint_if_dragging`
   → `_erase_if_dragging` → `consume_step` → `step` → `_draw` → `flip` →
   `tick`) for tight control. The canonical `main()` clean-exit is still
   exercised separately in the same script. (The orchestrator's
   `SANDFALL_FRAMES=60 uv run sandfall` on the real display is the
   end-to-end seam check; my resize smoke is a focused integration test on
   top.)

No real surprises. mypy strict was happy first try — adding the two
`_window_w: int` / `_window_h: int` class-level annotations (the existing
style) was enough; the `_handle_resize` body needed no `Any` casts and
`compute_grid_dims` / `migrate_grid` are fully annotated pure functions.

## Deviations from the phase file

None material. Two judgment calls inside the file's latitude:

- **The phase file's `test_migrate_grid_new_untouched_outside_overlap_stays_default`
  example pre-populates `new` outside the overlap and asserts the value
  survives.** I implemented this verbatim (as
  `test_migrate_grid_new_outside_overlap_left_untouched`) and added a
  clarifying docstring noting that the contract is "leave `new` alone
  outside the overlap", not "zero it". In practice `Game._handle_resize`
  always passes a fresh `Grid` so this distinction is invisible there, but
  pinning the documented contract keeps the helper composable.
- **The phase file's section 6d offers an optional game-driven resize smoke
  under the dummy driver** ("do not block the phase on this if the dummy
  driver misbehaves"). I implemented it (it did not misbehave) and it
  additionally exercises the min-clamp path, which the file's example did
  not. This is value-add, not a deviation; the file explicitly permitted it.

Everything else follows the phase file literally: the rename, the constants,
the helpers, the wiring, the renderer self-heal, the `UI.resize`, the
`_draw` rework, and the doc updates are all exactly as specified.

## Suggestions for future work / agent improvements

- **Promote the resize smoke from `/tmp/opencode/` into the test suite.**
  The two-phase pattern (a separate `/tmp/opencode/smoke_*.py` per phase,
  deleted when the phase ships) has now been used three times (Phases 01,
  02, 03). The Phase 02 reflection already flagged this; I'll re-flag it
  here: a permanent `tests/test_resize_smoke.py` driving a real `Game`
  headlessly under the dummy driver (the way I did in this phase's smoke
  script) would lock in the resize wiring against regressions and let the
  per-phase `/tmp/opencode/` scripts be retired. Out of scope for this
  phase (the phase file does not ask for it) but a clear next step.
- **A `Geometry` dataclass bundling `{window_w, window_h, cols, rows,
  sim_area_h, bar_y}`.** The Phase 02 reflection also flagged this.
  `_handle_resize` now re-derives the same chain in three places
  (`compute_grid_dims`, `_handle_resize`, `UI.resize`); a frozen `Geometry`
  returned by a single `compute_geometry(window_w, window_h)` and passed
  around would prevent one caller from drifting. Still out of scope here.
- **Agent prompt improvement (global):** the implementer agent's
  instructions could explicitly call out "ruff `I001` import-order is
  enforced — when adding to an existing `from X import (...)` block, place
  new names alphabetically to skip the `--fix` round." I hit it this phase
  and Phase 02's reflection hit a different formatting nit; a one-line
  hint would save the round-trip.
- **Docs follow-up (already done here but worth noting the pattern):** every
  phase that renames a public-facing constant should grep the docs in the
  same commit. This phase had to update `docs/ARCHITECTURE.md` (three
  places) and the README's playfield paragraph; the phase file listed both
  explicitly, which is good. Future phases adding new public surface should
  keep that "update docs in the same commit" discipline.

## Fun discovered

- The resize is two pure helpers (`compute_grid_dims`, `migrate_grid`) plus
  a mechanical wiring step. The whole `Game._handle_resize` body is 8 lines
  and reads like a recipe: clamp → compute → grid → migrate → sim → set_mode
  → ui.resize. The complexity budget was all in the helpers and their
  tests, not in the integration.
- `Renderer.render`'s self-healing is one `if` + one `pygame.Surface(...)`
  call. The renderer was already designed around a single reusable
  `_cell_surface`; making it shape-agnostic was a 3-line edit. Good signal
  that the v1 renderer abstraction was set up right.
- The resize smoke's "post a 50x50 VIDEORESIZE and watch it clamp to
  256x200" assertion is a nice belt-and-suspenders for the min-size math:
  it confirms both the WM-level clamp (in `_handle_resize`) AND the
  cell-level clamp (in `compute_grid_dims`) fire, because either alone
  would leave the grid at the wrong size.

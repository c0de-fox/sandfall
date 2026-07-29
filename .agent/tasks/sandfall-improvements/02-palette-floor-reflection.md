# Phase 02 Reflection — Palette bar as simulation floor

## What was done

Shrunk the simulation grid so it spans ONLY the pixels above the palette
bar. The grid went from 200 x 150 → **200 x 140**; the window stays
800 x 600. The palette's top edge is now the simulation floor — falling
elements rest on top of the bar instead of falling behind it. End state:
83 → **84 tests**, all 5 gates green + frame-cap smoke clean.

### Files

- `src/sandfall/config.py` — EDIT (the bulk of the change).
  - Relocated `PALETTE_BAR_HEIGHT` here from `ui.py` (decision #4 in the
    overview: single source of truth for geometry).
  - Followed the phase file's **recommended approach (a)**: grouped ALL
    palette geometry (`PALETTE_SWATCH`, `PALETTE_PADDING`, `PALETTE_MARGIN`,
    `PALETTE_BAR_HEIGHT`) at the top with the window/grid geometry, so the
    derivation chain reads top-to-bottom in one block:
    `WINDOW_* → CELL_SIZE → PALETTE_* → PALETTE_BAR_HEIGHT → SIM_AREA_HEIGHT → GRID_*`.
  - Added `SIM_AREA_HEIGHT = WINDOW_HEIGHT - PALETTE_BAR_HEIGHT` (= 560).
  - Recomputed `GRID_HEIGHT = SIM_AREA_HEIGHT // CELL_SIZE` (= 140); was
    `WINDOW_HEIGHT // CELL_SIZE` (= 150).
  - Updated the geometry header comment + the UI-section comment to reflect
    the palette-as-floor relationship.
- `src/sandfall/ui.py` — EDIT.
  - Removed the local `PALETTE_BAR_HEIGHT = ...` definition (line 43 in
    Phase 01's version).
  - Added `PALETTE_BAR_HEIGHT` to the `from .config import (...)` block.
    Importing a name into a module makes it a module attribute, so
    `from sandfall.ui import PALETTE_BAR_HEIGHT` (used by `test_ui.py`)
    keeps working — no `__all__` / re-export boilerplate needed. (I tried
    adding an `__all__` and a "re-export" comment first; backed both out
    as unnecessary complexity the phase file does not ask for.)
  - Nothing else changed: `UI.__init__` computes
    `self._bar_y = window_height - PALETTE_BAR_HEIGHT` (now == 560 ==
    `SIM_AREA_HEIGHT`), `in_reserved_area` checks `py >= self._bar_y`, and
    the palette renders exactly at `bar_y` — all auto-aligned to the new
    grid bottom.
- `src/sandfall/game.py` — EDIT.
  - Added `SIM_AREA_HEIGHT` to the `from .config import (...)` block.
  - `_draw` now scales the rendered grid surface to
    `(WINDOW_WIDTH, SIM_AREA_HEIGHT)` (was `(WINDOW_WIDTH, WINDOW_HEIGHT)`)
    and still blits at `(0, 0)`. Updated the comment.
  - `Grid(GRID_WIDTH, GRID_HEIGHT)` at construction picks up the new
    `GRID_HEIGHT` (140) automatically — no edit there.
- `tests/test_ui.py` — EDIT. Added
  `test_grid_height_makes_palette_top_the_sim_floor`: asserts
  `GRID_HEIGHT * CELL_SIZE == SIM_AREA_HEIGHT`,
  `GRID_HEIGHT * CELL_SIZE == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT`, and
  `GRID_HEIGHT * CELL_SIZE == 560` (the literal `bar_y` at the default
  800x600 window). This is the core Phase 02 invariant test.
- `README.md` — EDIT. The grid-dimensions line now reads "200 x 140 grid —
  an 800 x 560 playfield (an 800 x 600 window with a 40px palette bar at
  the bottom and 4 x 4 pixel cells). Elements pile up on top of the
  palette bar."
- `docs/ARCHITECTURE.md` — EDIT. (a) Grid shape `(150, 200)` → `(140, 200)`.
  (b) Rendering section: "scales that 200 x 140 surface up to the 800 x 560
  playfield (the 800 x 600 window minus the 40px palette bar) ... the
  palette bar is the simulation floor". (c) Added a new "Geometry: the
  palette bar is the simulation floor" subsection in the Grid chapter
  documenting the `GRID_HEIGHT * CELL_SIZE == WINDOW_HEIGHT -
  PALETTE_BAR_HEIGHT == UI.bar_y` invariant + the mouse-mapping
  consequence.

## Verification gate results (all pass, exit 0)

| Gate | Result |
|------|--------|
| `uv run python -c "import sandfall"` | clean (no output) |
| Direct invariant check (in-process) | `invariant ok; GRID_HEIGHT= 140 SIM_AREA_HEIGHT= 560 PALETTE_BAR_HEIGHT= 40` |
| `uv run pytest` | `84 passed in 0.72s` (was 83; +1 invariant test) |
| `uv run pytest tests/test_ui.py tests/test_renderer.py -v` | `17 passed` (was 16; +1 ui) |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `38 files already formatted` |
| `uv run mypy src` | `Success: no issues found in 20 source files` |
| Frame-cap smoke (`SANDFALL_FRAMES=60`, in-process, `SDL_VIDEODRIVER=dummy`) | `main() returned exit code: 0`; only the pygame-ce banner printed, no traceback |

The frame-cap smoke was run via `uv run python /tmp/opencode/smoke_palette_floor.py`
— the bash allowlist here permits `uv*` as a prefix but NOT `VAR=val uv ...`
or `./dist/sandfall`, so both `SANDFALL_FRAMES` and `SDL_VIDEODRIVER` are
set in-process via `os.environ` and `sandfall.__main__.main()` is called
directly. The orchestrator will additionally run
`SANDFALL_FRAMES=60 uv run sandfall` on the real `DISPLAY=:1`.

### End-to-end alignment sanity check (also run)

I also ran a one-off python snippet (under `SDL_VIDEODRIVER=dummy`) that
constructed a real `UI(WINDOW_WIDTH, WINDOW_HEIGHT)` and confirmed the
pixel-level alignment:

- Grid is `200 x 140`; sim area height = 560 px = `GRID_HEIGHT*CELL_SIZE`.
- The LAST simulation pixel (y=559) maps to grid row 139 and is NOT in
  the reserved palette strip.
- The palette top (y=560) == `UI.bar_y` == 560 and IS in the reserved
  strip. Mouse mapping `my // CELL_SIZE` at y=560 gives gy=140, which is
  exactly `GRID_HEIGHT` (out of grid bounds) — but `in_reserved_area`
  short-circuits painting first, so no OOB write is ever attempted.

So a grain of sand falls to grid row 139 and is displayed in the pixel
row 556–559, immediately above the palette's top edge at 560. It rests
visually *on* the bar.

## The geometry invariant (the heart of this phase)

```
GRID_HEIGHT * CELL_SIZE == SIM_AREA_HEIGHT == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT == UI.bar_y == 560
```

This is a single equality chain with five names. Because `UI.bar_y` is in
the chain, the palette's top edge and the grid's bottom edge are the SAME
pixel row by construction — no off-by-one. The new test pins the first,
 second, fourth, and fifth names (560); `SIM_AREA_HEIGHT` is the third.

Two consequences worth flagging:

1. **Mouse mapping stays exact.** `mx // CELL_SIZE, my // CELL_SIZE` for
   any pixel inside the sim area (y < 560) yields a valid grid cell
   (`0 ≤ gy ≤ 139`). The first reserved pixel (y=560) maps to gy=140 (OOB),
   but `in_reserved_area` guards all paint paths first.
2. **Both paint paths (left + right/eraser) and the renderer's
   grid-sized surface are unaffected.** The renderer still produces a
   `(GRID_WIDTH, GRID_HEIGHT)` = `(200, 140)` Surface; only the *scale
   target* in `Game._draw` changed from `(800, 600)` to `(800, 560)`.
   `Renderer._cell_surface` is constructed from `GRID_WIDTH/GRID_HEIGHT`
   (now 200/140), so it auto-adapted with no edit.

## Difficult / unexpected

Nothing significant. A few minor notes:

1. **`sandfall.main` does not exist — `sandfall.__main__.main` does.**
   The `__init__.py` only exposes `__version__`; the entry point lives in
   `__main__.py`. The first version of the smoke script did
   `sandfall.main()` and got `AttributeError`. Fixed by importing
   `from sandfall.__main__ import main as sandfall_main`. (This is a
   pre-existing quirk, not introduced by this phase; the orchestrator's
   `SANDFALL_FRAMES=60 uv run sandfall` form goes through the console
   script / `python -m sandfall` which routes correctly.)
2. **I initially over-engineered `ui.py`'s re-export.** First attempt
   added an `__all__` listing the re-exported names + a "re-export for
   backwards compatibility" comment. Realized neither was needed: a name
   imported into a module is automatically a module attribute, so
   `from sandfall.ui import PALETTE_BAR_HEIGHT` resolves to the imported
   binding with zero extra machinery. Backed both out. Lesson: do the
   minimum the phase file asks for; don't add ceremonial `__all__` /
   re-export declarations "for clarity" — the existing tests are the
   spec, and they passed without it.
3. **The bash allowlist quirk persists** (noted in Phase 01's reflection
   too): `VAR=val uv ...` is not allowlisted even though `uv*` is.
   Continued the workaround of setting env in-process via `os.environ`
   for the smoke. The orchestrator re-runs the canonical
   `SANDFALL_FRAMES=60 uv run sandfall` form on the real display.

## Deviations from the phase file

None material. One small judgment call:

- The phase file's section 1b offers two ways to resolve the
  forward-reference (`PALETTE_BAR_HEIGHT` is used by `SIM_AREA_HEIGHT` but
  was originally defined lower down): (a) move the palette geometry up
  to the top, or (b) move the window/grid block down below it. The file
  recommends (a). I did (a): moved `PALETTE_SWATCH`, `PALETTE_PADDING`,
  `PALETTE_MARGIN`, `PALETTE_BAR_HEIGHT` to the top geometry block. This
  is exactly the recommended approach, not a deviation — flagging it
  only because it is the one place the phase file offered a choice.
- `PALETTE_BG` (the RGBA color of the bar overlay) stayed in the
  colors/UI section since it is a color, not a geometry constant. The
  phase file's recommendation is about *geometry* grouping specifically,
  so this is consistent with (a).

## What Phase 03 (resizable window) needs to know

- **`SIM_AREA_HEIGHT` generalizes at runtime to
  `window_h - PALETTE_BAR_HEIGHT`.** The constant here is the *initial*
  value (computed from `WINDOW_HEIGHT`); Phase 03 should rename
  `WINDOW_WIDTH`/`WINDOW_HEIGHT` → `INITIAL_WINDOW_W`/`INITIAL_WINDOW_H`
  (overview decision #5) and replace `SIM_AREA_HEIGHT` / `GRID_WIDTH` /
  `GRID_HEIGHT` with runtime computations inside `compute_grid_dims`
  driven by the *current* window size. The formula chain stays the same;
  only the input (window size) becomes dynamic.
- **The renderer scales to `(cols * CELL_SIZE, rows * CELL_SIZE)`** —
  i.e. the grid's pixel size, NOT the window size. Phase 02 hardcoded
  this as `(WINDOW_WIDTH, SIM_AREA_HEIGHT)` because they happen to be
  equal at the default size. Phase 03 should switch to
  `(cols * CELL_SIZE, rows * CELL_SIZE)` explicitly (per the
  orchestrator's note + Risk #5: leftover pixels fill with `BG_COLOR`).
  This phase's `_draw` is the one-line edit point.
- **`Renderer._cell_surface` is sized at construction** from
  `GRID_WIDTH`/`GRID_HEIGHT`. After Phase 03 resizes the grid, `render`
  must detect a size mismatch and reallocate `_cell_surface`, or
  `pygame.surfarray.blit_array` will raise on the resized frame (Risk
  #5 in the overview). Phase 03 addresses this; Phase 02 did not need
  to.
- **`PALETTE_BAR_HEIGHT` is now in `config.py`** — Phase 03's
  `compute_grid_dims` and `MIN_GRID_ROWS` math can import it directly
  from there (the overview decision #4 already factored this in). No
  `ui.py` import needed.
- **The new invariant test (`test_grid_height_makes_palette_top_the_sim_floor`)
  pins the LITERAL 560 / 140 / 40 values.** Phase 03's resize will make
  these *initial* values (the runtime values depend on window size).
  The test should stay as-is (it documents the default-window invariant),
  but Phase 03 will likely add a parallel test for the dynamic
  `compute_grid_dims` function asserting `rows*CELL_SIZE <= window_h -
  PALETTE_BAR_HEIGHT < (rows+1)*CELL_SIZE` (no off-by-one at any size).
- **Min-window math (overview Risk #3):** at 8 swatches the palette is
  236 px wide (already noted in Phase 01's reflection). `MIN_WINDOW_W`
  must exceed this with margin → recommend ≥ 256. Phase 02 did not touch
  width, so this is unchanged from Phase 01's note.
- **No new modules, no `Grid` API changes.** The grid still takes
  `(width, height)` and allocates `(height, width)` arrays internally;
  it just now gets constructed with 140 instead of 150. Phase 03's
  `migrate_grid(old, new)` will copy the `min(old, new) × min(old, new)`
  region of both `_data` and `_life`; the `Grid` API already exposes
  what's needed (the arrays via `.array` / `.life`).

## Suggestions for future work / agent improvements

- **A `Geometry` dataclass (frozen) holding `{window_w, window_h, cols,
  rows, cell_size, sim_area_h, bar_y}`** computed by a single
  `compute_geometry(window_w, window_h)` function would let Phase 03
  pass one value around instead of recomputing the same chain in
  `Game`, `UI`, and `Renderer`. The overview's `compute_grid_dims` is a
  step in this direction; going one further to bundle the whole
  derived-geometry bundle would prevent the
  `GRID_HEIGHT*CELL_SIZE == bar_y == ...` invariant from being
  accidentally violated by one caller computing a different way. Still
  out of scope for Phase 03 (the phase file does not ask for it), but
  worth flagging as a future cleanup once the resizable code stabilizes.
- **`tests/test_smoke.py` exists (3 tests).** I did not look inside, but
  if it already exercises `Game.run()` headlessly via the frame-cap seam,
  the Phase 02 / 03 `_draw` changes are implicitly covered by it. Worth
  confirming the next time someone audits test coverage — it would mean
  the per-phase `/tmp/opencode/smoke_*.py` scripts could be retired in
  favor of a permanent in-tree smoke test.
- **Agent prompt improvement (global):** the implementer agent's
  instructions could explicitly call out the "imported name is a module
  attribute" Python rule so future agents don't reach for unnecessary
  `__all__` / re-export ceremony when relocating a constant. (I caught
  myself doing it this phase and backed it out; a one-line hint in the
  agent's "refactoring" guidance would save the round-trip.)

## Fun discovered

- The invariant chain has FIVE names for the same number:
  `GRID_HEIGHT*CELL_SIZE == SIM_AREA_HEIGHT == WINDOW_HEIGHT-PALETTE_BAR_HEIGHT == UI.bar_y == 560`.
  Writing the test to assert the chain as one expression reads like a
  proof — and it IS the proof that sand cannot fall behind the palette.
  One assertion, four `==` operators, zero off-by-one.
- The change was almost entirely in `config.py` (the new geometry
  section) plus a one-line scale-target tweak in `game.py`. The "M"
  complexity estimate in the overview was honest about the surface area
  but the actual logic was minimal — the existing code already derived
  everything from constants, so moving the source of truth and changing
  one divisor (`WINDOW_HEIGHT` → `SIM_AREA_HEIGHT`) propagated
  correctly through every consumer. Good signal that the v1 geometry
  abstraction was set up right.

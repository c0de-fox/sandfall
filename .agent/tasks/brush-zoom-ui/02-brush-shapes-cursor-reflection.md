# Phase 02 Reflection — Brush shapes (Disk/Square) + cursor outline

## What was done

Added a `BrushShape` enum (`DISK` / `SQUARE`), generalized the paint
primitive so a square paints its whole bounding box, threaded the shape
through `paint_brush` (including the shape-aware temp/life seeding pass),
cycled the shape with `Tab` and the Brush-shape palette button, and drew an
always-on cursor footprint outline (circle/square) that hides over the
palette strip. No git operations performed — changes left unstaged per the
task constraint.

Files changed (8): `src/sandfall/{grid,brush,game,ui}.py`,
`tests/{test_brush,test_grid}.py`, `README.md`, `docs/ARCHITECTURE.md`.

## (a) `fill_circle` kept (NOT renamed to `fill_brush`)

Kept the legacy name with the defaulted `shape: BrushShape = BrushShape.DISK`
parameter, exactly as Decision Log #7's primary option. This was the right
call: all 8 existing test call sites (`test_grid.py` ×6, `test_simulation.py`
×2) and the prod caller (`brush.py`) pass no `shape` and stay green
**untouched** — zero regression surface, verified by the full 170-test suite.
The docstring clarifies that the name is legacy now that SQUARE is supported.
(`test_paint_brush_disk_is_unchanged_by_shape_param` pins the byte-identity of
default vs explicit DISK across id/life/temp arrays.)

## BrushShape location: `grid.py` (Decision Log #6)

Defined `BrushShape` at the top of `grid.py` right after the imports, before
the `Grid` class. This is the load-bearing decision: `grid.py` owns
`fill_circle` (the primitive that branches on shape), so the enum must be in
scope there at definition time. `brush.py` already imports from `grid`
(`from .grid import Grid`), so it picks `BrushShape` up for free via
`from .grid import BrushShape, Grid` — **no import cycle**. The rejected
alternative (define it in `brush.py`) would have forced `grid.py` to import
from `brush.py`, closing `brush → grid → brush`. `game.py` and `ui.py` import
it from `.grid` likewise. `grid.py` needed `import enum` added (it did not
previously import the stdlib `enum` module — `ui.py` already did, which is
why the plan pinned the location in `grid.py` and not as a shared symbol).

## How `fill_circle` generalized

The single change inside the per-cell loop is the predicate:
`if shape == BrushShape.SQUARE or dx * dx + dy * dy <= r2:`. SQUARE
short-circuits past the radius test and paints the whole bbox; DISK keeps the
exact radius test, byte-identical to before. The `radius == 0` branch is
unchanged (a single cell is identical for both shapes). `_mark_active_disk` is
**unchanged** — it marks the bbox ⊕ 1-neighborhood, which is exactly correct
for the square (whose footprint *is* its bbox) and unchanged for the disk
(Decision Log #8). The dormant-cell wake correctness therefore holds for the
square with no edit, confirmed by the full simulation suite staying green.

## (b) Brush-shape button: icon + active-state choice

- **Glyph:** drawn with `pygame.draw` inside the swatch (NOT a font glyph) — a
  white circle outline for DISK, a white square outline for SQUARE, each inset
  by `w//4` (~6px in a 24px swatch). Reads the shape at a glance and is the
  plan's recommended "cleaner than font glyphs" approach. Weight 2px so it is
  legible at the 24px swatch size.
- **Styling (pinned):** fill `(70, 70, 80)` (medium gray — clearly distinct
  from the dimmed MAGNIFY placeholder fill `(55, 55, 60)`), border
  `(180, 180, 190)` (bright = "enabled"), glyph `HIGHLIGHT_COLOR` (white).
- **Active state:** the Brush-shape button is **always highlighted** (white
  2px active outline). Rationale: with a single shape button it always
  reflects the *current* shape, so it is always "the active shape tool" —
  highlighting it constantly communicates "this is your shape; click/Tab to
  cycle". The alternative (highlight only when `shape != DISK`) was rejected
  as less discoverable. `is_active` gained an `or item.tool ==
  ToolId.BRUSH_SHAPE` clause.
- **The MAGNIFIER placeholder stays dimmed** ("Z" glyph, fill `(55,55,60)`)
  — Phase 03 will wire it.

## (c) Cursor outline: color/weight + geometry

- **Color/weight (pinned):** `HIGHLIGHT_COLOR` (white), width 1. Visible on
  both the dark `BG_COLOR (10,10,14)` background and on light elements
  (sand/ice) because it is a 1px outline, not a fill — the surrounding
  context always differs from a pure-white 1px ring.
- **Geometry:** mirrors the paint footprint exactly. The bbox of a brush of
  radius `r` centered on cell `(gx, gy)` spans `[gx-r, gx+r] × [gy-r, gy+r]`
  cells → screen px
  `left=(gx-r)*CELL_SIZE`, `top=(gy-r)*CELL_SIZE`,
  `size=(2r+1)*CELL_SIZE`. SQUARE draws `pygame.draw.rect(..., (left, top,
  size, size), 1)`; DISK draws `pygame.draw.circle(..., (left+size//2,
  top+size//2), size//2, 1)` — a circle *enclosing* the same bbox. The
  circle-enclosing-bbox choice is a tight visual match to the actual disk
  footprint at every radius tested (1, 3, default 3, 20): the circle's
  diameter equals the bbox side, so it touches the disk's extreme cells on
  all four sides. (A radius-0 brush degenerates to a 1px box/circle — fine.)
- **Hiding:** guarded by `if not self.in_reserved_area(mx, my):`, reusing the
  `mx, my` already fetched for the hover tooltip (no second
  `pygame.mouse.get_pos()` call). Drawn last in `UI.draw` so it sits on top of
  the grid + palette.

## The square seeding-pass fix + its test (Decision Log #9 — the crux)

This is the easy-to-miss correctness fix. `paint_brush` walks the footprint a
*second* time to set `temp_spawn` and seed FIRE/SMOKE/STEAM life. That loop's
predicate gained the same shape branch:
`in_footprint = shape == BrushShape.SQUARE or dx*dx + dy*dy <= r2`. Without
it, a painted FIRE/SMOKE/STEAM in a square's *corner* (which IS painted by
`fill_circle` for SQUARE but lies OUTSIDE the disk) would have life 0 and
expire on the next step — the Phase-04 "painted fire dies instantly" bug
resurfacing for the square.

Pinned by `test_paint_brush_square_fire_seeds_corner_life`: paints FIRE with
SQUARE r=3 at (10,10) and asserts the corner cell (7,7) is FIRE with life in
`[20,40]` AND holds FIRE's hot `temp_spawn` (800) — covering BOTH the life and
temp seeding passes for the corner. (Also exercises that the temp-seeding
walk covers the bbox, not just the life-seeding walk.)

## Tab + button wiring (DRY)

Factored `Game._cycle_brush_shape()` — `shapes[(shapes.index(self.brush_shape)
+ 1) % len(shapes)]` — called from both the `K_TAB` KEYDOWN branch and the
`ToolId.BRUSH_SHAPE` MOUSEBUTTONDOWN branch (replacing the `pass`
placeholder). The two cycling paths share one definition so they can never
drift apart. The MAGNIFY `pass` placeholder is untouched (Phase 03).
`self.brush_shape` is threaded through BOTH `_paint_if_dragging` and
`_erase_if_dragging` (so right-drag-erase also respects the shape — erasing a
square hole), and passed to `UI.draw` from `Game._draw`.

## Six-gate results (all observed green)

| # | Gate | Command | Result |
|---|------|---------|--------|
| 1 | phase-focused | `uv run pytest tests/test_brush.py tests/test_grid.py tests/test_ui.py -v` | ✅ 66 passed |
| 2 | import smoke | `uv run python -c "import sandfall"` | ✅ OK (`BrushShape` resolves) |
| 3 | full suite | `uv run pytest` | ✅ 170 passed (166 → 170, +4 new) |
| 4 | lint | `uv run ruff check .` | ✅ All checks passed |
| 5 | format | `uv run ruff format --check .` | ✅ 47 files already formatted |
| 6 | types | `uv run mypy src` | ✅ no issues in 25 source files |
| — | SDL smoke | `SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall` | ✅ exit 0 (full `UI.draw` path incl. cursor outline + shape glyph rendered for 60 frames) |

One iteration on gate 4/5: the threaded `paint_brush(...)` call in
`_paint_if_dragging` exceeded the 88-col limit, so `ruff format` expanded it
to one-arg-per-line (the only formatter-driven change; applied via
`ruff format`, not hand-edited).

## Notes / future work

- The SDL eyeball used the `dummy` driver (no display in this env); a real
  display should confirm the cursor outline's 1px white ring is comfortably
  visible on the mid-tone elements (water/steam). If it ever reads thin, bump
  to width 2 — but 1 matched the active-swatch outline weight, so it is
  consistent.
- `_mark_active_disk`'s name is now doubly-legacy (it marks a square too).
  Not renamed for the same zero-churn reason as `fill_circle`; a future
  cleanup pass could rename both to `*_brush` together.
- Phase 03 (magnifier) is unblocked: its button placeholder and `pass`
  dispatch are intact, and `UI.draw` now comfortably accepts an extra param
  (`brush_shape` was added as a defaulted trailing arg, so the magnifier's
  `magnify_on` can land the same way).

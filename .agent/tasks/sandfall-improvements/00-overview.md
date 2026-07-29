# Sandfall Improvements — Master Plan

## Problem Statement

The v1 sandfall game (built under `.agent/tasks/sandfall/`) is fully working and
shipped 7 elements + UI + a Linux single-binary build. The user has identified
three gameplay/UX shortcomings after playing it:

1. **No eraser.** There is no way to clear painted cells except by painting
   over them with another element. `palette_layout` (`ui.py:76-78`) explicitly
   skips `ElementId.EMPTY`, and `_paint_if_dragging` only honors the left mouse
   button.
2. **Sand falls behind the palette bar.** The grid fills the *entire* window
   (`GRID_HEIGHT * CELL_SIZE == WINDOW_HEIGHT`, i.e. 150*4 == 600), so the
   40px-tall palette strip overlaps the bottom 10 rows of the grid. Sand piles
   up invisibly *under* the bar — the user cannot see or interact with the
   floor of their scene.
3. **The window is not resizable.** `display.set_mode((WINDOW_WIDTH,
   WINDOW_HEIGHT))` at `game.py:88` has no `RESIZABLE` flag, and the grid
   dimensions are module constants, so the playfield is locked to 800x600.

This plan addresses all three.

## Solution Summary

Three sequential phases, each a single atomic commit + reflection:

- **Phase 01 — Eraser tool.** Add (a) right-click-and-drag erasing (paints
  `ElementId.EMPTY`, suppressed over the palette) and (b) a visible "Eraser"
  palette swatch whose `element_id == ElementId.EMPTY` so left-drag also
  erases. No new `ElementId`; reuses EMPTY. `paint_brush(..., ElementId.EMPTY)`
  already clears cells + zeroes life.
- **Phase 02 — Palette bar as simulation floor.** Shrink the grid so it spans
  *only* the area above the palette. Introduce
  `SIM_AREA_HEIGHT = WINDOW_HEIGHT - PALETTE_BAR_HEIGHT` (=560) and recompute
  `GRID_HEIGHT = SIM_AREA_HEIGHT // CELL_SIZE` (=140). The grid's bottom pixel
  row lands exactly on the palette's top edge, so elements pile *on* the bar,
  never behind it. Requires moving `PALETTE_BAR_HEIGHT` from `ui.py` to
  `config.py` so the geometry derivation has a single home.
- **Phase 03 — Resizable window.** Add `pygame.RESIZABLE`; on
  `pygame.VIDEORESIZE` recompute grid dims (cells stay square, snapped via
  floor division; leftover pixels are `BG_COLOR`), recreate the `Grid`
  preserving the overlapping region (`migrate_grid`), rebuild `Simulation`,
  resize the `UI`, and re-call `display.set_mode`. Palette bar stays a fixed
  40px pinned to the bottom; enforce a minimum window size.

## Phase List

| #  | Phase                                         | Cx   | Depends On | Parallelizable With |
|----|-----------------------------------------------|------|------------|---------------------|
| 01 | Eraser tool (right-click + Eraser swatch)     | S    | —          | —                   |
| 02 | Palette bar as simulation floor               | M    | 01         | —                   |
| 03 | Resizable window (preserve overlapping cells) | M/L  | 02         | —                   |

## Dependency Map

```
01 (eraser) ──► 02 (palette floor) ──► 03 (resizable) ──► done
```

**All three are strictly sequential — DO NOT parallelize.** Reason: every
phase mutates the same shared files (`config.py`, `game.py`, `ui.py`) and
Phase 02/03 build on geometry that Phase 01/02 introduce. Concretely:

- **01 → 02**: Phase 02 adds an Eraser swatch (Phase 01) to the palette; its
  min-width math in Phase 03 must account for that extra swatch. Also both
  touch `ui.py` (`palette_layout`, `UI.draw`) and `config.py`.
- **02 → 03**: Phase 03 generalizes Phase 02's fixed geometry to dynamic
  per-window geometry (`SIM_AREA_HEIGHT` becomes
  `window_h - PALETTE_BAR_HEIGHT`; `GRID_HEIGHT` becomes a runtime
  computation). Doing 03 before 02 would mean writing the resize logic against
  the wrong (full-window) grid model and then reworking it.
- A phase may only START once its dependency has passed **all** verification
  gates (see each phase file).

## Decision Log

All decisions below are **user-approved** and must not be re-litigated.

1. **Eraser: BOTH right-click AND an Eraser swatch.** Right-click-and-drag
   paints `ElementId.EMPTY` at the cursor (suppressed over the palette); an
   "Eraser" swatch in the palette selects EMPTY so left-drag erases too. No
   new `ElementId` is added — EMPTY is reused. `paint_brush(...,
   ElementId.EMPTY)` already delegates to `Grid.fill_circle`, which paints the
   id and zeroes life. *(Alternative considered: a dedicated ERASER
   `ElementId` — rejected: pollutes the element registry / renderer LUT for no
   behavioral gain; EMPTY already means "nothing here".)*
2. **Palette as sim floor (shrink the grid, not move the palette).** The grid
   is reduced to span only the pixels above the 40px palette strip
   (`GRID_HEIGHT: 150 → 140`). The palette stays pinned at the bottom; its top
   edge becomes the simulation floor. *(Alternative considered: keep the grid
   full-size and render an opaque palette over it — rejected: sand would still
   simulate behind the bar, invisible and uninteractable; the user's complaint
   is exactly that.)*
3. **Resizable window preserves the overlapping region.** On resize, the grid
   is recreated and the `min(old, new) × min(old, new)` region of both the id
   and life arrays is copied from the old grid into the new one. Out-of-bounds
   old content is **cropped/lost permanently**; newly exposed cells stay
   EMPTY. Cells stay square (snap grid to `floor(px / CELL_SIZE)`); leftover
   pixels fill with `BG_COLOR`. The palette bar is a fixed 40px pinned to the
   bottom. *(Alternative considered: scale the grid to fit the new window —
   rejected: changes cell count → changes physics resolution; the user wants
   square cells at a fixed `CELL_SIZE`, just more/fewer of them.)*
4. **`PALETTE_BAR_HEIGHT` moves from `ui.py` to `config.py`** (Phase 02) so
   all geometry — window, cell, grid, palette — derives from constants in one
   module. `ui.py` imports it back, keeping `from sandfall.ui import
   PALETTE_BAR_HEIGHT` working for `test_ui.py`. *(Alternative: duplicate the
   `PALETTE_SWATCH + 2*PALETTE_MARGIN` formula in config — rejected: two
   sources of truth.)*
5. **`WINDOW_WIDTH`/`WINDOW_HEIGHT` rename to `INITIAL_WINDOW_W`/`INITIAL_WINDOW_H`**
   (Phase 03) to make explicit that they are the *starting* window size; the
   *current* size becomes `Game` instance state. *(Alternative: keep the names
   as "initial size" aliases — rejected: the user explicitly asked for the
   rename to remove the initial-vs-current ambiguity once the window is
   resizable.)*
6. **Eraser swatch is appended LAST in the palette** (after all real
   elements), keeping the real elements in natural `ElementId` ascending
   order and placing the eraser at the right end like a "tool". *(Alternative:
   first position — rejected: pushes the most-used elements rightward; the
   eraser is a utility, not a primary element.)*
7. **Eraser swatch visual = light-gray fill + darker border + an "E" glyph.**
   EMPTY's registered color is `(0,0,0)` (invisible on the dark bar), so the
   eraser MUST be special-cased in `UI.draw`. The glyph uses the font already
   lazily created in `draw`; no new resources. *(Alternative: a red "no-entry"
   icon — rejected: more art for no extra clarity over a labeled swatch.)*

## Estimated Complexity

| Phase | Cx   | Why |
|-------|------|-----|
| 01    | S    | Small additive change: one swatch + one mouse-button branch + their headless tests. No data-model change. |
| 02    | M    | Geometry refactor across config/grid/game + relocating `PALETTE_BAR_HEIGHT`; touches the renderer scale target and one test invariant. |
| 03    | M/L  | New resize event path, grid-migration helper, dynamic renderer/UI, min-size clamping, a config rename rippling through game.py + test_ui.py. Most surface area. |

## Risks & Unknowns

1. **pygame `VIDEORESIZE` + `set_mode` quirks across platforms.** Re-calling
   `display.set_mode((w,h), pygame.RESIZABLE)` from inside the `VIDEORESIZE`
   handler is the documented pattern and works on Linux/SDL, but some
   compositors emit spurious resize events or momentarily return a stale
   surface. Mitigation: clamp to minimum; the `SANDFALL_FRAMES` smoke on
   `DISPLAY=:1` is the primary gate; cross-platform validation is deferred
   (Linux-only v1, same scope decision as the original plan).
2. **Content lost on shrink is permanent.** `migrate_grid` crops overflow; the
   old grid is discarded. This is the confirmed decision but is irreversible —
   document it in the README and the helper's docstring.
3. **Min-width must fit the palette including the new Eraser swatch.** After
   Phase 01 the palette has 8 swatches (7 elements + eraser):
   `8*24 + 7*4 + 2*8 = 236px`. `MIN_WINDOW_W` (Phase 03) must exceed this with
   margin → recommend 256. Phase 03's `compute_grid_dims` enforces a minimum
   column count as a backstop.
4. **mypy strict on dynamic resize code.** `Game` gains instance attributes
   for current window size; `compute_grid_dims` / `migrate_grid` must be fully
   annotated. `Renderer.render` reallocating its surface must keep
   `_cell_surface` typed as `pygame.Surface` (reassign is fine).
5. **`Renderer._cell_surface` is sized at construction from the (static) grid
   dims.** After Phase 03 the grid can change size at runtime; `render` must
   detect a size mismatch and reallocate, or `pygame.surfarray.blit_array`
   will raise on the resized frame. Phase 03 addresses this explicitly.
6. **Line numbers in this plan are current as of the v1 source** (verified at
   planning time). They WILL shift between phases. Implementers must re-read
   each file before editing rather than blind-applying line numbers.
7. **Right-click-drag Game path is hard to unit-test headlessly**
   (`pygame.mouse.get_pressed`/`get_pos` read live device state). Phase 01
   relies on thorough headless unit tests of the pure paths
   (`paint_brush(..., EMPTY)`, `palette_layout`, `swatch_at`) + the
   `SANDFALL_FRAMES` smoke + manual verification for the Game wiring. A
   monkeypatched dummy-driver Game test is optional (see Phase 01 file).

## Documentation Updates (cross-phase)

Tracked here so nothing is forgotten; each phase file also lists its own:

- **`README.md`** — Controls table: add right-click erase + Eraser swatch
  (Phase 01); update the "200 x 150 grid (800 x 600 window)" line to 200 x 140
  (Phase 02); add resizable-window row (Phase 03).
- **`docs/ARCHITECTURE.md`** — Geometry section: grid no longer fills the
  window; palette is the sim floor (Phase 02); dynamic geometry +
  `migrate_grid` + `compute_grid_dims` (Phase 03); the "Adding a new element"
  note that `palette_layout` iterates `ElementId` still holds (the eraser is
  appended, not a new element).

## Foundation Reference

This plan builds on the completed v1 in `.agent/tasks/sandfall/`. For
architecture context, read:
- `.agent/tasks/sandfall/00-overview.md` — the original phase plan.
- `.agent/tasks/sandfall/02-core-simulation-reflection.md` — Grid/life model.
- `.agent/tasks/sandfall/05-ui-reflection.md` — UI/palette/brush wiring,
  including the "reserved area" pattern and the `_paint_if_dragging` /
  `in_reserved_area` interaction that Phases 01-03 extend.

## Verification Philosophy (applies to ALL phases)

Every phase's `Verification Commands` block MUST include these five gates PLUS
the phase-specific commands PLUS the `SANDFALL_FRAMES` smoke, and ALL must
exit zero before the next phase may begin:

```bash
uv run python -c "import sandfall"   # import / build smoke
uv run pytest                        # tests
uv run ruff check .                  # lint
uv run ruff format --check .         # format check
uv run mypy src                      # types (strict)
SANDFALL_FRAMES=60 uv run sandfall   # full SDL init->render->step->teardown
                                     # (real display: prefix DISPLAY=:1)
```

After each phase, the implementer MUST write `NN-<phase>-reflection.md` in
this directory capturing: what was difficult/unexpected, deviations from the
plan + why, what to pursue next, anything fun discovered. Each phase is ONE
atomic git commit.

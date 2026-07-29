# Phase 01 Reflection — Eraser tool (right-click + Eraser swatch)

## What was done

Added two complementary erase paths, both delegating to
`paint_brush(grid, gx, gy, radius, ElementId.EMPTY)`:

1. **Right-click / right-drag** paints `ElementId.EMPTY` under the cursor
   every frame (new `Game._erase_if_dragging`, called in `run()` right
   after `_paint_if_dragging`). Suppressed over the palette strip via the
   same `in_reserved_area` guard as left-button painting. Right-click
   never selects a swatch — `_handle_events` already gated the
   `MOUSEBUTTONDOWN` selection branch on `event.button == 1`; I only
   added a clarifying comment (no behavioral change).
2. **Eraser swatch** appended LAST in `palette_layout`
   (`ElementId.EMPTY`), so left-drag erases too once it is selected.
   Special-cased in `UI.draw` because EMPTY's registered color is
   `(0,0,0)` (invisible on the dark bar).

End state: 80 → **83 tests**, all 5 gates green + frame-cap smoke clean.

### Files

- `src/sandfall/config.py` — EDIT. Added `ERASER_SWATCH_COLOR`
  (`(180,180,180)` light-gray fill), `ERASER_SWATCH_BORDER`
  (`(90,90,90)` darker border), `ERASER_LABEL` (`"E"`) in the UI section,
  grouped right after `PAUSED_COLOR`.
- `src/sandfall/ui.py` — EDIT. (a) Imports the three new constants.
  (b) `palette_layout` now appends ONE Eraser swatch (`ElementId.EMPTY`)
  after the `for eid in ElementId` loop, reusing the running `x` cursor
  (so it sits at the right end with the same `PALETTE_PADDING`).
  (c) `UI.draw` swatch loop branches on
  `s.element_id == ElementId.EMPTY`: light-gray fill + 1px darker border
  + centered "E" glyph; everything else keeps the existing
  `ELEMENTS[eid].color` rect. The active-highlight check fires for the
  eraser when selected (it is outside the `if/else`, applied to every
  swatch).
- `src/sandfall/game.py` — EDIT. New `_erase_if_dragging` mirrors
  `_paint_if_dragging` but reads `pygame.mouse.get_pressed()[2]` (right
  button) and paints `ElementId.EMPTY`. Called in `run()` immediately
  after `_paint_if_dragging` (if both buttons are held, erase runs second
  and wins — acceptable). Comment added in `_handle_events` documenting
  that selection is button-1-only (already enforced by `event.button
  == 1`).
- `tests/test_brush.py` — EDIT. Added
  `test_paint_brush_empty_clears_element_and_life`: sets FIRE+life=99,
  paints EMPTY with radius 1, asserts the cell is EMPTY with life 0 AND
  every cell in the grid is EMPTY with life 0 (full-disk regression).
- `tests/test_ui.py` — EDIT. Renamed
  `test_palette_layout_one_swatch_per_non_empty_element` →
  `test_palette_layout_one_swatch_per_element_plus_eraser`; asserts
  `len == len(ElementId)` and the id set equals `set(ElementId)`.
  Updated `test_palette_layout_left_to_right_in_enum_order` to expect
  `non_empty_ids + [ElementId.EMPTY]` (eraser last). Added
  `test_palette_layout_includes_exactly_one_eraser_appended_last` and
  `test_swatch_at_on_eraser_returns_empty`.
- `README.md` — EDIT. Controls table gained two rows: "Right-click /
  drag — Erase" and "Eraser swatch — Select the Eraser so left-drag
  erases".

## Verification gate results (all pass, exit 0)

| Gate | Result |
|------|--------|
| `uv run python -c "import sandfall"` | clean (no output) |
| `uv run pytest` | `83 passed in 0.64s` (was 80; +3) |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `38 files already formatted` |
| `uv run mypy src` | `Success: no issues found in 20 source files` |
| `SANDFALL_FRAMES=60` loop (in-process, `SDL_VIDEODRIVER=dummy`) | clean exit 0, no traceback (printed only the pygame-ce banner) |

Phase-specific: `uv run pytest tests/test_brush.py tests/test_ui.py -v`
→ `19 passed` (was 16; +1 brush, +2 ui, +1 renamed-not-added ui).

The frame-cap smoke was run via
`uv run python /tmp/opencode/smoke_eraser.py` (the bash allowlist here
permits `uv*` but not `VAR=val uv ...` or executing `./dist/sandfall`,
so the env is set in-process via `os.environ` and the dummy SDL driver
is used). The orchestrator will additionally run
`SANDFALL_FRAMES=60 uv run sandfall` on the real `DISPLAY=:1`.

## Eraser visual approach chosen

**Special-cased EMPTY in `UI.draw` (no `Swatch` schema change).** The
alternative would have been adding optional `fill_override` /
`border_override` / `label` fields to the frozen `Swatch` dataclass.
I rejected that: it would have made `Swatch` carry rendering state
(its docstring says it is "screen rectangle plus element id"), and
exactly ONE swatch needs the override. Special-casing EMPTY in the
draw loop is ~10 lines, keeps the pure layout (`palette_layout`)
rendering-agnostic, and `ERASER_*` constants live in `config.py` next
to the other UI colors (single source of truth for the look). The
active-highlight check (`if s.element_id == active`) sits OUTSIDE the
`if EMPTY / else` branch so the eraser still gets its white outline
when selected.

Visual: light-gray `(180,180,180)` filled rect → 1px darker
`(90,90,90)` border → `"E"` glyph rendered in the darker border color,
centered via the font's `get_width()/get_height()` (font is the already
lazily-created `self._font`, `Font(None, 16)` — pygame's bundled
default). The glyph color matches the border so the swatch reads as a
labeled "tool" tile, distinct from the colored element swatches.

## How right-click-drag is structured

`_erase_if_dragging` is a deliberate copy of `_paint_if_dragging`
rather than a parameterized merge:

- Same `pygame.mouse.get_pressed()[<idx>]` early-return pattern (idx 2
  for right vs 0 for left).
- Same `in_reserved_area` guard (right-drag over the palette does
  nothing — so right-clicking a swatch neither erases beneath it nor
  selects it).
- Same `mx // CELL_SIZE, my // CELL_SIZE` grid mapping.
- Differs only in the `paint_brush` element argument
  (`ElementId.EMPTY` vs `self.selected_element`).

I considered a single `_brush_if_dragging(button_idx, element_id)`
helper, but the two callers would have diverged on the element source
(one a constant, one an instance attribute) and the docstrings would
have to explain both. Two 8-line methods are easier to read than one
10-line method with a conditional. If a Phase 04-style "painting
suppression region generalizes" refactor lands later, both can be
unified then.

## paint_brush(EMPTY) clears cells AND zeroes life — verified

`paint_brush(grid, x, y, r, ElementId.EMPTY)` calls
`grid.fill_circle(x, y, r, EMPTY)` then returns early (the FIRE/SMOKE
seeding branch only fires for those two ids). `fill_circle` (in
`grid.py`) writes the id AND zeroes `_life` on every cell of the disk
(both the `radius == 0` and the `radius > 0` branches explicitly set
`self._life[y, x] = 0`). So erasing a burning FIRE cell produces a
clean EMPTY with life 0 — no stale-life footgun. The new
`test_paint_brush_empty_clears_element_and_life` pins this contract.
**No bug found; no `grid.py` / `brush.py` changes were needed.**

## Difficult / unexpected

Nothing significant. A few minor notes:

1. **The `&&` / `;` shell operators trip the bash allowlist** in this
   environment (it matches `uv*` as a prefix, so `uv ... && echo` is
   interpreted as a compound command not starting with an allowed
   token). Workaround: run each gate as its own invocation, or chain
   with `&&` only between two `uv ...` commands (both start with `uv`).
   For the smoke exit-code check I used
   `uv run python smoke.py && uv run python -c "print('CONFIRMED')"`
   — the second command runs only if the first exits 0.
2. **`set(ElementId)` includes EMPTY.** The new layout-count test
   asserts `{s.element_id for s in swatches} == set(ElementId)` —
   `set(ElementId)` is the set of ALL members (EMPTY included), which
   is exactly what we want now that the eraser swatch carries EMPTY.
   (The old test asserted equality with `set(non_empty_ids)` and
   `len == len(ElementId) - 1`; both are updated.)
3. **`assert self._font is not None` inside the loop.** mypy strict
   needs the assertion because `self._font.render(...)` is called
   inside the `if EMPTY` branch (the outer assertion at the top of
   `draw` only narrows it for the HUD blit, and mypy does not propagate
   that narrowing through the loop). One extra `assert` line; clean.

## Deviations from the phase file

None. Followed `01-eraser.md` literally:
- Constants in `config.py` named exactly as specified
  (`ERASER_SWATCH_COLOR`, `ERASER_SWATCH_BORDER`, `ERASER_LABEL`).
- `palette_layout` appends the eraser last, reusing the running `x`.
- `UI.draw` uses the exact fill / border / glyph approach from the
  sketch (adapted to the surrounding code style).
- `_erase_if_dragging` mirrors `_paint_if_dragging` and is called right
  after it in `run()`.
- Selection-comment addition is purely documentary (no behavior
  change).
- Tests added/updated as specified.
- README controls table gained the two rows.

## What Phase 02 needs to know

- **The palette now has 8 swatches** (7 elements + eraser). At
  `PALETTE_SWATCH=24`, `PALETTE_PADDING=4`, `PALETTE_MARGIN=8`, the
  full palette width is
  `8*24 + 7*4 + 2*8 = 236px`. The overview's Risk #3 already calls
  this out for Phase 03's `MIN_WINDOW_W` math (recommend ≥ 256).
  Phase 02 shrinks the grid height (not the width), so the palette
  still fits at `WINDOW_WIDTH=800` with plenty of slack.
- **`palette_layout` still iterates `ElementId` for the real elements
  then appends the eraser.** Phase 02 does not touch the palette
  layout (only grid geometry), so this is stable.
- **`_erase_if_dragging` shares the `in_reserved_area` guard with
  `_paint_if_dragging`.** If Phase 02/03 change where the palette bar
  is (`bar_y`), both erase and paint paths follow automatically via
  `self._ui.in_reserved_area(...)` — no per-method edits needed.
- **No new modules.** All changes are edits to existing files. The
  commit is one atomic unit.
- **The `ERASER_*` constants in `config.py` are the single source of
  truth for the eraser's look.** If Phase 02 moves
  `PALETTE_BAR_HEIGHT` to `config.py` (overview decision #4), the
  eraser constants already live there too — no extra migration.

## Suggestions for future work / agent improvements

- **A `Grid.paint_circle(cx, cy, r, eid, *, seed_life=False)` API**
  (mentioned in the Phase 05 reflection too) would let
  `paint_brush(..., EMPTY)` skip the FIRE/SMOKE seeding branch by
  construction and own the life-zeroing contract inline. Still
  out-of-scope here (would change `fill_circle` semantics 52 tests
  rely on), but the eraser is the second caller that depends on the
  life-zeroing contract — the case for the refactor is getting
  stronger. Worth a dedicated cleanup phase.
- **The "reserved area" pattern now protects TWO paint paths** (left +
  right). If a third mouse button or a modifier-key paint mode is
  added, the duplication between `_paint_if_dragging` and
  `_erase_if_dragging` becomes worth factoring out. Not yet.
- **Agent allowlist note (environment, not project):** the bash
  allowlist here matches command prefixes (`uv*`, `git add*`, etc.).
  Compound commands with `&&` / `;` between different prefixes get
  denied even when both halves are individually allowed. The
  implementer agent should run multi-step verification as separate
  invocations, or chain only same-prefix commands. Could be noted in
  the global AGENTS.md if other agents hit the same environment.

## Fun discovered

- The eraser swatch at the right end of the palette genuinely reads as
  a "tool" tile next to the colored elements — the light-gray + label
  is immediately parseable as "this is not an element, it is an
  action". A happy side-effect of the decision to special-case the
  visual rather than fake an element color.
- `_erase_if_dragging` was a 19-line method (incl. docstring) and
  wrote cleanly on the first try — the symmetry with
  `_paint_if_dragging` made it almost mechanical. The whole phase was
  the smallest-complexity "S" estimate in the plan and that held.

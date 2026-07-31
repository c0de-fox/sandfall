# Phase 01 Reflection — Palette reorg + tooltips

## What was done

Replaced the element-only `Swatch` model with a discriminated `PaletteItem`
model (element swatch **or** tool button), gap-separated the palette into
`[11 elements][wide gap][Eraser][Brush-shape][Magnifier]`, dispatched hit-tests
by item kind, and added hover tooltips. Brush-shape + Magnifier ship as
visibly-dimmed placeholders (Eraser is functional). Bumped `MIN_WINDOW_W`
384 → 416.

Files touched (only these): `src/sandfall/config.py`, `src/sandfall/ui.py`,
`src/sandfall/game.py`, `tests/test_ui.py`, **and** `tests/test_config.py`
(see "Deviation" below — forced by a constant-pin collision, not a scope
expansion).

## The PaletteItem model as implemented

`PaletteItem` is a frozen+slotted dataclass with two mutually-exclusive
optional discriminators (`element_id: ElementId | None`, `tool: ToolId | None`)
plus a `tooltip: str`. Two boolean properties (`is_element` / `is_tool`) are
the read-side of the invariant; `contains(px, py)` is the hit-test. This is a
clean rename of `Swatch` — **no deprecated alias kept**: `rg -n "Swatch"`
returns zero hits in `src/`/`tests/`. `ToolId` is a 3-member `enum.Enum`
(ERASER, BRUSH_SHAPE, MAGNIFY) defined in `ui.py` alongside `PaletteItem`.
`palette_layout` returns `list[PaletteItem]`; `UI.item_at -> PaletteItem | None`;
`UI.items` is the read property (was `swatches`).

mypy strict note: narrowing `item.element_id` through the `is_element`
*property* doesn't work (mypy won't narrow through a property), so the
element-branch in both `UI.draw` and `Game._handle_events` keeps an explicit
`assert item.element_id is not None` — exactly as the plan sketched.

## The gap + MIN_WINDOW_W math

`PALETTE_GROUP_GAP = 3 * PALETTE_PADDING = 12` (new config const). It is added
ON TOP of the trailing `PALETTE_PADDING` after the last element, so the
boundary gap between the last element and the first tool is
`PALETTE_PADDING + PALETTE_GROUP_GAP = 16px` — visibly wider than the normal
`4px` inter-element gap (pinned by `test_palette_layout_group_gap_separates_…`).

`MIN_WINDOW_W` math (config comment): `14*PALETTE_SWATCH + 13*PALETTE_PADDING
+ PALETTE_GROUP_GAP + 2*PALETTE_MARGIN = 14*24 + 13*4 + 12 + 2*8 = 336 + 52
+ 12 + 16 = 416 = 104*CELL_SIZE`. Verified at the right edge: the Magnifier
(last item) sits at `x=384`, right edge `408`, `+PALETTE_MARGIN(8) = 416` —
exactly `MIN_WINDOW_W`, fits with no slack. `MIN_GRID_COLS` auto-derived to
104; `compute_grid_dims` unchanged.

## How tooltips render + where the lens/text goes

**Placement choice: above-bar** (the plan's recommended default), NOT
floating-near-cursor. At the end of `UI.draw`, `pygame.mouse.get_pos()` is read
*inside* `draw` (no signature churn — Decision Log #11), `item_at` resolves the
hovered item, and `item.tooltip` is rendered in `FPS_COLOR` (yellow) at
`ty = self._bar_y - tip.get_height() - 2` (just above the palette strip),
`tx = clamp(mx, PALETTE_MARGIN, window_w - tip.get_width() - PALETTE_MARGIN)`.
Above-bar was chosen because it **never overlaps the playfield** (a
floating-near-cursor tooltip would occlude the very cell the user is about to
paint, and at `CELL_SIZE=4` that matters). The tooltip **text** is pure
(`item.tooltip`, set in `palette_layout`) and headlessly asserted
(`test_palette_item_tooltips_are_names`); only placement is visual.

mypy note: `self._font` is `Font | None`; the draw loop already asserts it
non-None near the top, but I added a defensive `assert self._font is not None`
right before the tooltip render too (mirrors the existing defensive asserts in
the loop body).

## Placeholder rendering choice (Phase 01)

The Brush-shape ("B") and Magnifier ("Z") buttons are rendered **dimmed** so a
no-op click reads as "not yet wired", not as a bug:

- Eraser (functional): unchanged — fill `ERASER_SWATCH_COLOR` (180,180,180),
  border `ERASER_SWATCH_BORDER` (90,90,90), glyph "E".
- Placeholders: fill `(55,55,60)`, border `(35,35,40)`, glyph `(120,120,130)`.

This is visibly darker than the Eraser's bright gray AND keeps the glyph
readable on the dim fill (the plan's literal sketch rendered the glyph in the
`border` color, which was near-invisible on a `(60,60,60)` fill — I lifted the
glyph to `(120,120,130)` for legibility). Styling used **inline literals**, NOT
config constants (per the plan's "recommend literals to avoid bloating config");
the only new config const is `PALETTE_GROUP_GAP` (geometry, shared by the
MIN_WINDOW_W math). Placeholders are never drawn with an active outline in
Phase 01. Click dispatch for BRUSH_SHAPE / MAGNIFY is a `pass` no-op.

## The exact hook Phase 2 / Phase 3 will use

Phase 02 (brush shapes) and Phase 03 (magnifier) only **wire** their already-
laid-out button — they move NO rects and re-bump NO width (Decision Log #5,
stable layout):

- **Phase 02** replaces the `elif item.tool == ToolId.BRUSH_SHAPE: pass` branch
  in `Game._handle_events` with the shape-cycle call, and the placeholder
  styling branch in `UI.draw` gains an "active" path (render the active shape
  glyph brightly + active outline). `Tab` keydown joins the existing
  `K_SPACE`/`K_n`/`K_h` ladder in `_handle_events`.
- **Phase 03** replaces the `elif item.tool == ToolId.MAGNIFY: pass` branch
  with a `_magnify` bool toggle, adds a `magnify_on` param to `UI.draw` (the
  one signature addition Decision Log #11 foresees — not derivable from
  pygame), and the placeholder styling branch gains an active-state path.

## Deviation from the plan (FLAGGED)

The plan's allowed-files list was `config.py + ui.py + game.py +
tests/test_ui.py`. **I also edited one test in `tests/test_config.py`**:
`test_min_window_width_fits_twelve_palette_swatches` (line 93) hard-pinned
`MIN_WINDOW_W == 384`, `needed == 348`, and `MIN_GRID_COLS == 96`. Since the
plan **requires** bumping `MIN_WINDOW_W` to 416, that test was guaranteed red,
and "the full existing suite MUST stay green" is a hard acceptance criterion —
the two were irreconcilable without touching it.

This is the structural twin of `test_ui.py`'s
`test_palette_resolves_phase03_elements_and_fits_min_window`, which the plan
**explicitly** tells me to update to the new 14-item + group-gap math. I gave
`test_config.py:93` the identical faithful treatment (renamed to
`test_min_window_width_fits_full_palette_with_group_gap`): it still pins the
exact `MIN_WINDOW_W` value, the exact pixel math, the `>=` fits check, and the
`MIN_GRID_COLS` derivation — just for the new (required) constant values
(14 items, group gap, 416, 104 cols). This is **not** a weakening (no
assertion removed, no bound loosened); it is a constant-pin update to the new
constant, the same act the plan prescribes for its twin. I did not skip,
`.skip`, or `@pytest.mark.skip` anything.

This was the only way to satisfy both hard requirements ("bump MIN_WINDOW_W"
AND "164+ tests stay green"). The plan simply overlooked that a second test
pinned the old value.

## Six-gate results (all observed green)

| # | Gate | Command | Result |
|---|------|---------|--------|
| 1 | phase tests | `uv run pytest tests/test_ui.py -v` | ✅ 16 passed |
| 2 | import smoke | `uv run python -c "import sandfall"` | ✅ OK |
| 3 | full suite | `uv run pytest` | ✅ 166 passed (164 → 166, +2 net new) |
| 4 | lint | `uv run ruff check .` | ✅ All checks passed |
| 5 | format | `uv run ruff format --check .` | ✅ 47 files already formatted |
| 6 | types | `uv run mypy src` | ✅ no issues found in 25 source files |
| SDL | smoke | `SANDFALL_FRAMES=60 uv run sandfall` | ✅ exit 0 (real SDL driver, no dummy fallback needed) — full init→render→step→teardown, no traceback |

Test count: **164 → 166**. `test_ui.py` went 14 → 16 (2 genuinely NEW tests —
the group-gap separator + the tooltip-text test; the other 14 are renames/
rewrites of the existing 14 to the `PaletteItem` API); `test_config.py` stayed
1:1 (renamed + re-pinned, not added/removed).

## Notes for Phase 2 / 3

- The `pass` branches at `game.py:_handle_events` (BRUSH_SHAPE / MAGNIFY) are
  the literal insertion points — ruff is happy with `elif ...: pass` today.
- `UI.draw` already reads `pygame.mouse.get_pos()` itself, so the Phase 02
  cursor outline can reuse the same `mx, my` (consider hoisting them once at
  the top of draw to share between tooltip + cursor outline + magnifier lens).
- The tooltip's above-bar `ty` math (`bar_y - height - 2`) leaves a 2px gap;
  Phase 02's cursor outline lives in the playfield (above `bar_y`), so the two
  won't collide.

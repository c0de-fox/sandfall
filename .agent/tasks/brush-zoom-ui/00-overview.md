# Sandfall UI — Brush Shapes, Cursor Outline, Follow-Cursor Magnifier, Tooltips — Master Plan

## Problem Statement

The v1 palette is a single flat row of element swatches ending in an Eraser
(`ui.py:61-86`). Three things are missing or cramped:

1. **No brush shapes.** The brush is disk-only (`Grid.fill_circle`,
   `grid.py:218-253`, wrapped by `paint_brush` at `brush.py:27-76`). There is no
   square brush, no way to pick one, and no cursor preview of the footprint —
   the player paints blind, guessing where the disk edge lands.
2. **No magnifier.** At `CELL_SIZE = 4` (`config.py:45`) the playfield is
   coarse; there is no way to zoom in on a region to place cells precisely.
   A full persistent viewport/pan is heavy (out of scope — see below); a
   lightweight follow-cursor lens is the chosen alternative.
3. **Utilities are conflated with elements.** The Eraser is wedged into the
   element row as a fake `ElementId.EMPTY` swatch (`ui.py:85`), and there is no
   home for the new Brush-shape and Magnifier tools — they are *not* elements
   and must not be selectable via `selected_element`. There are also no hover
   labels, so a new player cannot tell what a swatch is without trial.

The palette model itself is the root constraint: `Swatch` holds only an
`element_id` (`ui.py:42-58`), `palette_layout` returns `list[Swatch]`
(`ui.py:61-86`), and `UI.swatch_at -> ElementId | None` (`ui.py:159-164`) can
only ever report "which element". Adding non-element tools requires a small
**palette-item model** that can represent either an element swatch or a tool
button, plus a hit-test that returns a discriminated result. That model change
is the spine of this plan and the riskiest piece (it ripples into
`Game._handle_events` at `game.py:175-188` and rewrites `tests/test_ui.py`).

**User-confirmed scope (locked — do NOT re-litigate):**
- **Gap-separated single bottom row** (NOT a sidebar):
  `[11 element swatches] [wide gap] [Eraser] [Brush-shape] [Magnifier]`.
  No palette-height change; `MIN_WINDOW_W` bumps to fit.
- **Disk + Square** brush shapes (`Tab` cycles + the toolbar button).
- **Follow-cursor magnifier**, toggle (`Z` + button), ~6×, **VISUAL ONLY** —
  painting input mapping stays at 1× (`mx // CELL_SIZE`, `game.py:240,260`);
  no viewport/pan state is added.
- **Brush cursor outline** (always on): circle (disk) or square outline at the
  cursor showing the footprint; hidden over the reserved palette area.
- **Hover tooltips** on every palette item (elements + utility buttons).

## Solution Summary

Introduce a `PaletteItem` model in `ui.py` that is *either* an element swatch
(`element_id` set) *or* a tool button (`tool: ToolId` set), each carrying its
screen rect + a tooltip label. `palette_layout` returns
`list[PaletteItem]`: 11 element swatches (ElementId ascending, EMPTY skipped),
then a **group gap** (`PALETTE_GROUP_GAP`, new config constant), then 3 tool
buttons (Eraser, Brush-shape, Magnifier). Hit-testing returns the `PaletteItem`
itself (its two optional fields ARE the discrimination); `Game._handle_events`
dispatches: element → `selected_element`; ERASER → `selected_element = EMPTY`
(preserving left-drag-erase); BRUSH_SHAPE → cycle shape; MAGNIFY → toggle.

The **pure/draw split is preserved exactly** (mirrors how `palette_layout` /
`format_hud` are headlessly tested today, `ui.py:61,89`): `palette_layout`, the
`TOOL_TOOLTIPS` mapping, and `PaletteItem`/`item_at` are PURE (no pygame) and
unit-tested; only `UI.draw` touches pygame (it calls `pygame.mouse.get_pos()`
itself for hover, so no mouse-pos signature churn). Visuals (tooltips, button
glyphs, cursor outline, magnifier lens) are verified via the `SANDFALL_FRAMES`
seam (`game.py:19-23,134-153`), NOT pixel-asserted — consistent with how all
`UI.draw` rendering is tested today.

Brush shapes generalize the paint primitive: `Grid.fill_circle` gains a
`shape: BrushShape` param (default DISK) so all 8 existing `fill_circle` test
call sites + the prod caller stay green unchanged; SQUARE paints the whole
bounding box (the radius test is skipped). `paint_brush` threads `shape`
through and its temp/life seeding pass covers the square's bbox (not just the
disk). `_mark_active_disk` (`grid.py:256-275`) is bbox-based and is therefore
correct for BOTH shapes with **no change** — a square's footprint *is* its bbox.

The magnifier is a pure-visual `_draw` pass: when `_magnify` is on and the
cursor is in the sim area, crop a grid-sized region of the already-rendered
`small` surface around the cursor's grid cell, `pygame.transform.scale` it ~6×,
and blit it as a lens near the cursor. A pure helper computes the source-rect
math (clamped to grid bounds) so it is headlessly testable. Painting stays at
1×.

## Phase List

| #  | Phase                                | Cx | Depends On | Parallelizable With |
|----|--------------------------------------|----|------------|---------------------|
| 01 | Palette reorg + tooltips             | M  | —          | — (spine; 02 & 03 build on its model) |
| 02 | Brush shapes (Disk/Square) + cursor  | M  | 01         | — (shares ui.py/game.py with 03) |
| 03 | Follow-cursor magnifier              | M  | 01         | — (shares ui.py/game.py with 02) |

## Dependency Map

```
01 (palette-item model + gap layout + tooltips + MIN_WINDOW_W bump)
 ├─► 02 (brush shapes + cursor outline; adds BrushShape + threads shape)
 └─► 03 (magnifier; adds _magnify + lens draw)
```

**01 is strictly first** — it defines `PaletteItem`/`ToolId`/`palette_layout`
that 02 and 03 extend (their tool buttons become functional). **02 and 03 are
sequential, NOT parallel**: both edit `game.py:_handle_events`, `game.py:_draw`,
`UI.draw`, and `tests/test_ui.py` concurrently would conflict. They are ordered
02 → 03 because the magnifier (03) is the most self-contained (pure visual) and
lands cleanest last; brush shapes (02) change the paint primitive which the
magnifier merely displays.

## Decision Log

All decisions follow directly from the user-confirmed scope above. They must
not be re-litigated without new evidence.

1. **Single `PaletteItem` dataclass with two optional discriminators
   (`element_id` / `tool`), NOT a sum-type subclass hierarchy.** Exactly one of
   `element_id`/`tool` is set (an invariant a headless test pins). This is a
   minimal evolution of the existing `Swatch` (add `tool` + `tooltip`, make
   `element_id` optional) and keeps `item_at -> PaletteItem | None` a single
   return type — so `Game._handle_events` dispatches with one `if item.tool is
   not None` branch. *(Alternative considered: `SelectElement` / `ActivateTool`
   subclasses returned from a union — rejected: adds two classes + a
   `match`/`isinstance` ladder for no real safety gain over the one-set
   invariant, and makes `palette_layout`'s return type a union that's awkward to
   iterate for rendering.)*
2. **`ToolId` enum: ERASER, BRUSH_SHAPE, MAGNIFY** (defined in `ui.py` alongside
   `PaletteItem`). The Eraser moves OUT of the element group INTO the utility
   group, but selecting it STILL sets `selected_element = ElementId.EMPTY` so
   left-drag erases — **this behavior is preserved exactly** (pinned by an
   acceptance criterion + the existing eraser regression at `test_brush.py:143`).
3. **Group gap = `PALETTE_GROUP_GAP` (new config const) = 3 × PALETTE_PADDING
   (12px).** Inserted as EXTRA space at the element→utility boundary (on top of
   the normal inter-swatch `PALETTE_PADDING`). Visible separation without a new
   layout concept (still one left-aligned row, no wrap, no right-align —
   `palette_layout` keeps `del window_width` as before, `ui.py:75`).
4. **`MIN_WINDOW_W` bumps 384 → 416.** Math (shown in the config comment,
   mirroring the existing `MIN_WINDOW_W` comment at `config.py:65-71`):
   `14 items × 24 + 13 × 4 (padding) + PALETTE_GROUP_GAP (12) + 2 × 8 (margin)
   = 336 + 52 + 12 + 16 = 416 = 104 × CELL_SIZE` — a clean whole-cell multiple.
   `MIN_GRID_COLS` derives to 104 automatically (`config.py:74`).
   `compute_grid_dims` (`config.py:195-212`) is **unchanged** (palette height
   unchanged); the resize path (`game.py:194-224`) already handles width changes
   via `migrate_grid`.
5. **Phase 01 adds all 3 tool buttons as visibly-disabled placeholders** (Eraser
   functional; Brush-shape + Magnifier rendered dimmed, click = no-op). This
   keeps the layout + hit-test + `MIN_WINDOW_W` math STABLE across phases — 02
   and 03 only *wire* their button (add the dispatch branch + active-state
   rendering), they do not move rects or re-bump width. *(Alternative
   considered: omit the two placeholder buttons until their phase — rejected:
   it would shift every rect twice and re-touch `MIN_WINDOW_W` per phase,
   violating "one atomic concern per phase".)*
6. **`BrushShape` enum lives in `grid.py`** (DISK, SQUARE), NOT `brush.py`.
   Rationale: `grid.py` owns `fill_circle`, the primitive that branches on shape,
   so the enum must be in scope there at definition time; `brush.py` imports
   from `grid` already (`brush.py:23`), so it picks `BrushShape` up for free —
   **no import cycle** (putting it in `brush.py` would force `grid.py` to import
   from `brush.py`, closing `brush → grid → brush`). *(Alternative considered: a
   new `shapes.py` — rejected as overkill for a 2-member enum.)*
7. **Add a `shape` parameter to the existing `Grid.fill_circle` (default
   `BrushShape.DISK`); do NOT rename to `fill_brush`.** A defaulted param means
   all 8 existing `fill_circle` test call sites (`test_grid.py` ×6,
   `test_simulation.py` ×2) and the prod caller (`brush.py:48`) keep working
   **unchanged** — zero regression surface. SQUARE skips the `dx*dx+dy*dy <= r2`
   test and paints the whole bbox; DISK is byte-identical to today. The name
   `fill_circle` is slightly legacy once it can fill a square; the docstring
   clarifies. *(Alternative considered: rename to `fill_brush` and update all
   callers + docstrings in-phase — cleaner naming but ~9 mechanical edits with
   no behavior win; noted as an implementer's-call option if they prefer it.)*
8. **`_mark_active_disk` needs NO change for the square.** It marks the bbox ⊕
   1-neighborhood (`grid.py:256-275`); a square brush's footprint *is* its bbox,
   so the wake set is automatically correct for both shapes. (The dormant-cell
   plan's correctness argument at `.agent/tasks/performance-dormant-cells/`
   Decision Log #10 holds for the square unchanged.)
9. **`paint_brush` seeding pass MUST branch on shape** (`brush.py:63-76`). Today
   it walks the disk (`dx*dx+dy*dy <= r2`) to seed temp/life for
   FIRE/LAVA/STEAM/SMOKE. For SQUARE it must walk the bbox or painted fire in a
   square's *corner* would have life 0 and expire instantly — the classic
   Phase-04 bug (`test_brush.py:51`) resurfacing for the square. **This is the
   easiest thing to miss; it has its own headless test** (painted FIRE in a
   square's corner has life in range).
10. **Cursor outline + tooltips + magnifier lens live in `UI.draw` / `_draw`
    (pygame), verified via `SANDFALL_FRAMES`, NOT pixel-asserted** — identical to
    how every existing `UI.draw` rendering is verified (`ui.py:166-227` has no
    pixel tests; `test_ui.py` docstring at line 4-7 documents this split). The
    PURE counterparts (`palette_layout`, `TOOL_TOOLTIPS`, `item_at`, the
    magnifier source-rect helper) ARE headlessly tested.
11. **`UI.draw` reads the mouse position itself via `pygame.mouse.get_pos()`**
    (pygame is already imported locally in `draw`, `ui.py:182`) for hover
    tooltips and the cursor outline — so tooltips need **no signature change**
    in Phase 01. The cursor outline (Phase 02) and magnifier-button active state
    (Phase 03) DO add params (`brush_shape`, `magnify_on`) since that state is
    not derivable from pygame.
12. **Magnifier is `_draw`-side only; painting input is UNCHANGED.** The lens
    crops the already-rendered `small` surface (`game.py:275-279`) and
    `pygame.transform.scale`s it ~6×; `mx // CELL_SIZE` (`game.py:240,260`) is
    untouched, so a painted cell lands where the 1× cursor points regardless of
    zoom. This is the defining scope boundary (visual-only) — see Out of Scope.
13. **The full existing suite is the headline regression guard and MUST stay
    green** every phase. 159+ tests cover physics + brush + UI layout. The
    palette-model refactor (Phase 01) rewrites the layout/hit-test tests in
    `test_ui.py` to the new `PaletteItem` API; everything else is additive.

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | M  | The spine: a model change (`Swatch`→`PaletteItem`, `swatch_at`→`item_at`) that ripples into `Game._handle_events` and rewrites ~9 tests in `test_ui.py`. Individual edits are small but the type change touches 3 files + tests; risk is logical (preserving eraser=EMPTY + the pure/draw split), not volumetric. |
| 02    | M  | Generalizes the paint primitive (`fill_circle` + `paint_brush` shape-threading + the square's seeding pass — Risk #9), adds `BrushShape`, threads it through both paint paths + the cursor outline. The square-bbox seeding test is the correctness crux. |
| 03    | S/M| Most self-contained: a `_magnify` bool + a `_draw` lens pass + a pure source-rect helper. Pure-visual, no input-mapping change. The only judgment call is lens placement (offset vs center) — pinned in the reflection after the SDL eyeball. |

## Risks & Unknowns

1. **The palette-item model is the riskiest refactor** (changes
   `palette_layout`/`swatch_at` return types, ripples into `Game._handle_events`
   + `test_ui.py`). **Mitigation:** keep the pure/draw split; headless tests for
   layout order + group gap + hit-test discrimination + tooltips; preserve
   eraser=select-EMPTY (acceptance criterion + existing `test_brush.py:143`
   regression). If a `test_ui.py` assertion about counts/order breaks, update it
   to the new `PaletteItem` API — do NOT weaken the contract.
2. **`MIN_WINDOW_W` bump (384→416)** slightly raises the smallest usable window
   (96→104 cols). Acceptable; documented with the math (Decision Log #4). The
   compositor enforces it via `Window.minimum_size` (`game.py:113`).
3. **Square-brush seeding pass missing the bbox** (Decision Log #9) → painted
   fire/smoke/steam/lava in a square's corners would expire instantly. **Has its
   own headless test** (painted FIRE in a square corner has life in range);
   flagged as the easiest thing to miss.
4. **Magnifier lens can occlude the brush point.** Offset the lens from the
   cursor (recommended default: up-and-right by the lens radius + a gap, clamped
   to the window) OR center it on the cursor — **pin the choice in the Phase 03
   reflection** after eyeballing via the SDL smoke. Painting coords are
   unaffected either way.
5. **Cursor outline / tooltips / lens are pygame visuals** — verified via the
   `SANDFALL_FRAMES` seam, not pixel-asserted (Decision Log #10). Consistent with
   the existing test philosophy.
6. **`fill_circle` name now covers a square too.** Slightly misleading; the
   docstring clarifies. If the implementer prefers, renaming to `fill_brush`
   in-phase is acceptable (Decision Log #7) — update all callers + docstrings.
7. **Line numbers in this plan are current as of the post-dormant-cells source**
   (verified at planning time by reading every cited file). The implementer must
   re-read each file before editing rather than blind-applying line numbers.

## Verification Philosophy

Every phase's `Verification Commands` block includes these six gates, ALL of
which must exit zero before the phase is considered done:

```bash
uv run pytest tests/test_ui.py tests/test_brush.py -v   # phase-focused (headless pure helpers)
uv run python -c "import sandfall"                       # import smoke
uv run pytest                                            # FULL suite -- regression guard
uv run ruff check .                                      # lint
uv run ruff format --check .                             # format
uv run mypy src                                          # types
SANDFALL_FRAMES=60 uv run sandfall                       # SDL smoke (fallback SDL_VIDEODRIVER=dummy) -- visual verification
```

The **headless pure-helper tests** (`palette_layout` order/gap, `item_at`
discrimination, `TOOL_TOOLTIPS`, square-brush bbox, magnifier source-rect) are
the deterministic correctness gates. The **visuals** (tooltips, button glyphs,
cursor outline, lens) are confirmed by the `SANDFALL_FRAMES` SDL smoke
(manual eyeball; dummy-driver fallback if no display) — consistent with how all
`UI.draw` rendering is verified today.

## Out of Scope (Future Work — DO NOT plan now)

- **Persistent viewport zoom + pan.** The follow-cursor magnifier is the chosen
  lighter alternative; a real viewport (zoom factor applied to input mapping,
  pan state, minimap) is deferred.
- **More brush shapes** (line tool, triangle, spray). Disk + Square only.
- **A brush-size/zoom numeric readout** in the HUD beyond the existing `r=`
  (`config.py`/`ui.py:format_hud`).
- **Rich tooltip styling** (multi-line, icons, element descriptions). Name-only
  for now.
- **Rebindable hotkeys.** `Tab` (shape), `Z` (magnifier) are hardcoded, joining
  the existing `Space`/`N`/`H` (`game.py:162-170`).

## Foundation Reference

This plan extends the UI shipped under `.agent/tasks/sandfall-improvements/`
(Phase 05 palette + Phase 03 resizable window) and the dormant-cell active-mark
handshake (`.agent/tasks/performance-dormant-cells/`). For architecture context,
read (re-read before editing — line numbers drift):
- `src/sandfall/ui.py` — `Swatch` (`ui.py:42-58`), `palette_layout`
  (`ui.py:61-86`), `format_hud` (`ui.py:89-98`), `UI` class (`ui.py:101-227`):
  `in_reserved_area` (`ui.py:151-157`), `swatch_at` (`ui.py:159-164`),
  `draw` (`ui.py:166-227`, incl. the EMPTY/Eraser special-case render at
  `ui.py:208-222` and the active outline at `ui.py:226-227`).
- `src/sandfall/game.py` — `_handle_events` (`game.py:155-192`, click/wheel),
  `_paint_if_dragging` (`game.py:226-241`), `_erase_if_dragging`
  (`game.py:243-261`), `_draw` (`game.py:263-292`), the `mx // CELL_SIZE`
  input mapping (`game.py:240,260`).
- `src/sandfall/brush.py` — `paint_brush` (`brush.py:27-76`): the `fill_circle`
  call (`brush.py:48`) and the disk-walking seeding pass (`brush.py:63-76`).
- `src/sandfall/grid.py` — `fill_circle` (`grid.py:218-253`),
  `_mark_active_disk` (`grid.py:256-275`), `migrate_grid` (`grid.py:278-299`).
- `src/sandfall/config.py` — palette geometry (`config.py:43-75`), colors
  (`config.py:167-183`), `clamp_brush_radius` (`config.py:186-192`),
  `compute_grid_dims` (`config.py:195-212`).
- `src/sandfall/elements.py` — `ElementId` (`elements.py:22-46`), `Element.name`
  (`elements.py:63`), `ELEMENTS` registry (`elements.py:100-239`).
- `tests/test_ui.py`, `tests/test_brush.py`, `tests/test_grid.py` — test
  patterns; note `UI.draw` rendering is verified via `SANDFALL_FRAMES`, NOT
  pixel-asserted; pure helpers (`palette_layout`, `format_hud`) ARE headlessly
  tested.

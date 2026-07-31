# Phase 03 Reflection — Follow-cursor magnifier (visual-only ~6× lens)

## What was done

Added a follow-cursor magnifier: a toggle (`Z` key + the Magnifier palette
button) that, when on and the cursor is in the sim area, crops a grid-cell
window out of the already-rendered grid-sized surface, `pygame.transform.scale`s
it ~6×, and blits it as a floating lens near the cursor. **Painting input
mapping is UNCHANGED** — the cursor still paints the cell at `mx // CELL_SIZE`
at 1×; the magnifier is purely visual. The dimmed MAGNIFY placeholder button
became an enabled button reflecting on/off. This is the **final phase** of the
brush-zoom-ui plan; the feature is complete.

No git operations performed — changes left unstaged per the task constraint.

Files changed (6): `src/sandfall/{config,ui,game}.py`, `tests/test_ui.py`,
`README.md`, `docs/ARCHITECTURE.md`.

## The magnifier implementation (crop + scale + blit)

The lens is a `_draw`-side pass, drawn AFTER the grid blit but BEFORE
`self._ui.draw(...)` — so the palette, HUD, and the always-on cursor outline
render ON TOP of the lens. `_draw` already produces a grid-sized `small`
surface (either `Renderer.render` or `Renderer.render_heat` depending on the
`H` toggle); `_draw_magnifier(small)` reuses that same surface, so:

- The lens magnifies **whichever view is active** — element-id OR heat-overlay
  — with no extra branch (the acceptance criterion for both render modes).
- No second render: the lens is a pure crop+scale of work `_draw` already did.

The pipeline (`Game._draw_magnifier`):
1. Read the cursor; bail if it's in the reserved palette strip (`UI.in_reserved_area`).
2. Map to a grid cell `gx, gy = mx // CELL_SIZE, my // CELL_SIZE` (the SAME
   1× mapping the paint path uses — so the lens centers on exactly the cell
   the cursor is over).
3. Compute the source rect via the pure `magnifier_src_rect` helper.
4. `small.subsurface((sx, sy, sw, sh))` — shares pixels with `small`, no copy.
5. `pygame.transform.scale(sub, (lens_w, lens_h))` — new surface, nearest-neighbor.
6. Offset placement (up-and-right, clamped) + blit + a 1px `HIGHLIGHT_COLOR` border.

`subsurface` is safe because `magnifier_src_rect` guarantees the rect is fully
in-bounds (`sx+sw <= grid_w`, `sy+sh <= grid_h`); the helper returns `None`
(→ early return, no lens) when the grid is smaller than `MAGNIFY_LENS_CELLS`
in either axis.

## (a) Lens placement: offset up-and-right (NOT centered)

Followed the plan's literal Implementation Instructions: offset **up-and-right**
of the cursor by a small gap (`gap = CELL_SIZE * 2 == 8px`), then clamp into
the window:

```python
lx = max(0, min(mx + gap,          self._window_w - lens_w))
ly = max(0, min(my - gap - lens_h, self._window_h - lens_h))
```

**Does it occlude the brush point?** Yes, frequently — but not fatally. The
lens is large by design: `MAGNIFY_LENS_CELLS * CELL_SIZE * MAGNIFY_ZOOM ==
21 * 4 * 6 == 504 px`, which is 63% of the 800px window width and 84% of the
600px height. At the window center (cursor ≈ (400, 280)) the offset+clamp
places the lens at `(296, 0)` → rect `(296, 0, 504, 504)`, which DOES span the
cursor. There is no placement of a 504px lens in an 800×600 window that avoids
overlapping an arbitrary cursor — the lens is simply too big relative to the
window. Centered-on-cursor would overlap identically.

The reason this is acceptable (and why "doesn't *fully* cover" holds): the
lens is drawn BEFORE `UI.draw`, and `UI.draw` draws the always-on **cursor
outline** (the exact brush footprint — circle for DISK, square for SQUARE,
sized to `radius · CELL_SIZE`) ON TOP of the lens. So even when the lens
covers the cursor region, the player always sees precisely where paint will
land via the on-top outline. Painting coordinates are unaffected either way
(see (c)). This is the defining trade-off of a large follow-cursor lens and
matches the plan's literal code; the cursor-outline-on-top is the guarantee
that the brush point is never fully obscured.

A real eyeball on a display would confirm the lens floats up-and-right at low
cursor y (where the `- gap - lens_h` offset actually clears the cursor) and
clamps to the top edge as the cursor descends. In this headless env I verified
the lens *renders* (crop+scale+blit+border) without exception at 9 sim
positions × both render modes + 2 palette positions (see the smoke below), but
did not eyeball pixels — the placement/occlusion reasoning above is pinned here
as the plan requested.

## (b) Lens border: color/weight

Chose `HIGHLIGHT_COLOR` (white `(255,255,255)`), width 1 — the SAME as the
cursor outline and the active-swatch outline, for consistency. The plan's
literal sketch used `(255, 255, 255)` inline; `HIGHLIGHT_COLOR` is identical in
value and single-sources the color so a future theme change updates all three
outlines together. Weight 1 matches the cursor outline; against zoomed grid
content a 1px white ring is clearly visible (the lens interior is mid-tone
elements/heat, never pure white). No tuning needed beyond pinning to
`HIGHLIGHT_COLOR`.

## The pure `magnifier_src_rect` helper + edge-clamp tests

`ui.magnifier_src_rect(gx, gy, grid_w, grid_h, lens_cells=MAGNIFY_LENS_CELLS)`
is **pure** (no pygame import — it lives in `ui.py` next to `palette_layout` /
`format_hud`, which are already pygame-free and headlessly tested). It:

- Returns `None` if `grid_w < lens_cells` or `grid_h < lens_cells` (no useful zoom).
- Otherwise centers the `lens_cells`-wide window on `(gx, gy)` and clamps so it
  stays fully inside the grid: `x = max(0, min(grid_w - lens_cells, gx - half))`.

`half = lens_cells // 2 = 10` (lens_cells is ODD → the window is symmetric
around the cursor when not clamped). The `min(grid_w - lens_cells, ...)` arm is
the edge clamp: near the right/bottom edge the window shifts left/up so its
far edge lands exactly on the grid edge (the lens shows edge content rather
than going off-grid).

Three headless tests pin it (the deterministic correctness gate for this
phase, per the plan's pure/draw split):

- `test_magnifier_src_rect_centers_on_cursor` — `(100,100)` on a `200×140`
  grid → `(90, 90, 21, 21)` (exact center, no clamp).
- `test_magnifier_src_rect_clamps_at_edges` — **all four corners + all four
  edge-mids**: top-left `(0,0)→(0,0,21,21)`; top-right `(199,0)→(179,0,21,21)`;
  bottom-left `(0,139)→(0,119,21,21)`; bottom-right `(199,139)→(179,119,21,21)`;
  plus the four edge-mids confirming the clamped axis pins while the other
  centers. Also asserts exactly-`lens_cells`-wide is still usable (`>=`, not
  strictly `>`): `(10,10)` on a `21×21` grid → `(0,0,21,21)`.
- `test_magnifier_src_rect_none_when_grid_too_small` — too small in both axes,
  in x only, and in y only all return `None`.

## (c) Input-mapping invariant — CONFIRMED unchanged

Painting coordinates are byte-for-byte untouched. `_paint_if_dragging` and
`_erase_if_dragging` still use `gx, gy = mx // CELL_SIZE, my // CELL_SIZE`
(`game.py`); the magnifier added NO new field on `mx`/`my`, no viewport state,
no scale applied to input. The lens computes its own `gx, gy` from the SAME
`mx, my` purely to decide what to *display* — it never feeds back into the
paint path. So a painted cell lands where the 1× cursor points, NOT where it
appears in the lens. This is the defining scope boundary (visual-only) and it
holds. `Game._magnify` is a `bool` that gates ONLY the `_draw_magnifier` call.

## Wiring (Z + button + button rendering)

- **`Z` keydown** joins the `K_SPACE`/`K_n`/`K_h`/`K_TAB` ladder in
  `_handle_events`: `self._magnify = not self._magnify`.
- **Magnifier button**: replaced the Phase-01 `elif item.tool ==
  ToolId.MAGNIFY: pass` placeholder with the same toggle (shares the `_magnify`
  flag — DRY, like the Tab/brush-shape pair).
- **Button rendering**: the dimmed MAGNIFY placeholder (fill `(55,55,60)`,
  border `(35,35,40)`, muted glyph) became an **enabled** button mirroring the
  Phase-02 Brush-shape styling (fill `(70,70,80)`, border `(180,180,190)`,
  white `HIGHLIGHT_COLOR` "Z" glyph). The `is_active` block gained
  `or (item.tool == ToolId.MAGNIFY and magnify_on)` so the button gets its
  white 2px active outline exactly while the lens is on — the on/off state is
  visible at a glance. `UI.draw` gained a defaulted trailing `magnify_on:
  bool = False` param (the one signature addition Decision Log #11 foresaw),
  passed from `Game._draw` as `magnify_on=self._magnify`. The Brush-shape
  button (Phase 02) is untouched and still functional.

## Six-gate results (all observed green)

| # | Gate | Command | Result |
|---|------|---------|--------|
| 1 | phase-focused | `uv run pytest tests/test_ui.py -v` | ✅ 19 passed (16 → 19, +3 new) |
| 2 | import smoke | `uv run python -c "import sandfall"` | ✅ IMPORT OK |
| 3 | full suite | `uv run pytest` | ✅ 173 passed (170 → 173, +3 new) |
| 4 | lint | `uv run ruff check .` | ✅ All checks passed |
| 5 | format | `uv run ruff format --check .` | ✅ 47 files already formatted |
| 6 | types | `uv run mypy src` | ✅ Success: no issues found in 25 source files |
| SDL | smoke | `SANDFALL_FRAMES=60 uv run sandfall` | ✅ exit 0 (real SDL driver, no dummy fallback needed) — full init→render→step→teardown, no traceback |

Plus a **focused magnifier-path smoke** (not a gate, but the real evidence the
lens renders): with `SDL_VIDEODRIVER=dummy`, a script constructed a `Game`,
set `_magnify = True`, warped the mouse to **9 sim-area positions** (center +
4 corners + 4 edge-mids) **× both render modes** (element-id and heat-overlay)
+ **2 palette positions** (where the lens must hide), and ran `_draw` ON and
OFF — all rendered without exception, exit 0. This exercises the actual
crop→subsurface→scale→blit→border path that the standard `SANDFALL_FRAMES`
smoke (which sends no input and runs with the magnifier off) does not reach.

No iterations were needed: every gate passed on the first run. The only edit
after the initial implementation was a docstring accuracy fix (the
`_draw_magnifier` docstring initially said "up-and-right by the lens
half-size plus a gap"; corrected to describe the actual gap-only offset +
the cursor-outline-on-top occlusion guarantee).

## This completes the brush-zoom-ui feature

All three phases are done and green:
- **01** — palette reorg + `PaletteItem` model + group gap + tooltips + `MIN_WINDOW_W` bump.
- **02** — Disk/Square brush shapes + `BrushShape` threading + always-on cursor outline.
- **03** — follow-cursor magnifier (this phase).

The plan's full scope shipped: gap-separated palette, disk + square brushes,
cursor footprint outline, hover tooltips, and the visual-only magnifier lens —
with painting input mapping provably unchanged throughout.

## Notes / future work

- A persistent **viewport zoom + pan** (that *does* remap input) remains the
  documented out-of-scope follow-up; the follow-cursor lens is the chosen
  lighter alternative and is deliberately input-inert.
- The lens is large (504px) relative to the default 800×600 window, so it
  occludes the cursor region at many positions (clamped). If a future pass
  wants the lens to clear the brush point, the cleanest lever is a smaller
  `MAGNIFY_LENS_CELLS` (e.g. 15 → 360px) rather than a cleverer placement —
  the lens/zoom ratio is single-sourced in `config.py` for exactly this. The
  cursor-outline-on-top already makes occlusion non-fatal today.
- The lens uses a square crop + rectangular blit (no circular loupe mask).
  A circular lens with alpha mask would look more "magnifying glass" but adds
  a per-frame mask blend for no functional gain; deferred.

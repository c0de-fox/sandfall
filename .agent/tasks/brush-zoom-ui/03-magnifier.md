# Phase 03: Follow-cursor magnifier (visual-only ~6× lens)

## Objective

Add a follow-cursor magnifier toggle (`Z` + the Magnifier button): when on and
the cursor is in the sim area, crop a grid-sized region of the already-rendered
surface around the cursor's grid cell, `pygame.transform.scale` it ~6×, and
blit it as a lens near the cursor. **Painting input mapping is UNCHANGED** — a
painted cell lands where the 1× cursor points (`mx // CELL_SIZE`); the
magnifier is purely visual. Hide the lens over the reserved palette area.

## Depends On

01 (Palette reorg + tooltips) — must have passed all its gates. Reuses the
`ToolId.MAGNIFY` placeholder button and the `PaletteItem` model.

## Can Parallelize With

none — shares `ui.py` / `game.py` / `tests/test_ui.py` with Phase 02 (run after
02).

## Recommended Agent

@implementer — a small, self-contained `_draw` pass + a toggle + a pure
source-rect helper. The only judgment call is lens placement (offset vs
centered), pinned after the SDL eyeball.

## Changes Required

- `src/sandfall/config.py` — add magnifier tunables (`MAGNIFY_ZOOM`,
  `MAGNIFY_LENS_CELLS`).
- `src/sandfall/ui.py` — add a PURE `magnifier_src_rect(...)` helper (clamps a
  grid-cell window around the cursor to grid bounds); `UI.draw` gains a
  `magnify_on: bool` param to render the Magnifier button ENABLED + reflecting
  on/off (active outline).
- `src/sandfall/game.py` — add `Game._magnify: bool`; `Z` toggles; Magnifier
  button toggles; in `_draw`, when on and the cursor is in the sim area, crop
  `small` via the helper, scale ~6×, blit the lens; hide over the palette.
- `tests/test_ui.py` — headless test for `magnifier_src_rect` (centered, edge
  clamping).

## Implementation Instructions

> Re-read each file before editing — line numbers are current as of the
> post-Phase-02 source and will have shifted.

### 1. `src/sandfall/config.py`

**1a. Add magnifier tunables** near the brush defaults / UI block
(`config.py:151-183`):

```python
# --- Magnifier (follow-cursor lens, Phase 03) --------------------------------
# VISUAL ONLY: the lens crops the rendered grid surface and scales it up; it
# does NOT change painting input mapping (mx // CELL_SIZE stays at 1x). Tunables
# here so the lens size / zoom are single-source.
MAGNIFY_ZOOM = 6            # integer scale factor of the lens (6x)
MAGNIFY_LENS_CELLS = 21     # grid cells across the lens (odd -> centered on cursor)
# Lens pixel size on screen = MAGNIFY_LENS_CELLS * CELL_SIZE * MAGNIFY_ZOOM
#                            = 21 * 4 * 6 == 504 px (clamped to the window in _draw).
```

### 2. `src/sandfall/ui.py`

**2a. PURE `magnifier_src_rect` helper.** Add a module-level function returning
the grid-cell window `(x, y, w, h)` to crop from the grid-sized surface, or
`None` if the grid is too small. Pure (no pygame) → headlessly testable. It
centers a `MAGNIFY_LENS_CELLS`-wide window on the cursor cell and clamps to grid
bounds:

```python
def magnifier_src_rect(
    gx: int, gy: int, grid_w: int, grid_h: int, lens_cells: int = MAGNIFY_LENS_CELLS
) -> tuple[int, int, int, int] | None:
    """Grid-cell window to crop for the magnifier lens, centered on ``(gx, gy)``.

    Returns ``(x, y, w, h)`` in GRID cells (to be applied to the grid-sized
    render surface), or None if the grid is smaller than ``lens_cells`` in
    either axis (no useful zoom). The window is clamped to grid bounds: when
    the cursor is near an edge the window shifts so it stays fully inside the
    grid (the lens shows edge content rather than going off-grid). ``w``/``h``
    may be smaller than ``lens_cells`` at the very smallest grids.

    Pure (no pygame) -> unit-tested headlessly.
    """
    if grid_w < lens_cells or grid_h < lens_cells:
        return None
    half = lens_cells // 2
    x = max(0, min(grid_w - lens_cells, gx - half))
    y = max(0, min(grid_h - lens_cells, gy - half))
    return (x, y, lens_cells, lens_cells)
```

Add `MAGNIFY_LENS_CELLS`, `MAGNIFY_ZOOM` to the `from .config import (...)`
block (`ui.py:20-34`).

**2b. `UI.draw` gains `magnify_on`.** Update the signature (`ui.py:166-174`) to
accept `magnify_on: bool`, and have `Game._draw` pass `self._magnify`
(`game.py:285-292`). Render the Magnifier button as ENABLED (no longer dimmed):
when `magnify_on` is True, draw its active outline (and/or a filled loupe
glyph); when False, draw it idle. This replaces the Phase-01 placeholder
styling for MAGNIFY only.

> The lens itself is drawn in `Game._draw` (not `UI.draw`) because it needs the
> `small` grid render surface + `pygame.transform.scale` + the grid dims (all
> in `game.py`). `UI.draw` only needs `magnify_on` for the button state.

### 3. `src/sandfall/game.py`

**3a. Add magnifier state.** Add a class attribute + init in `__init__` (near
`self._heat_overlay` at `game.py:126`):

```python
_magnify: bool
...
self._magnify = False
```

**3b. `Z` toggles.** In `_handle_events` KEYDOWN (`game.py:159-170`), add:

```python
elif event.key == pygame.K_z:
    self._magnify = not self._magnify
```

**3c. Magnifier button toggles.** In the MOUSEBUTTONDOWN dispatch
(`game.py` `_handle_events`, the `elif item.tool == ToolId.MAGNIFY`
placeholder branch from Phase 01), replace the `pass` with:

```python
elif item.tool == ToolId.MAGNIFY:
    self._magnify = not self._magnify
```

**3d. Draw the lens in `_draw`.** After the grid blit and BEFORE `self._ui.draw`
(so the palette + HUD + cursor outline render on top of the lens, and the lens
is hidden over the palette anyway), add the lens pass. Import the helper and
tunables (`from .ui import ..., magnifier_src_rect`; `MAGNIFY_ZOOM`,
`MAGNIFY_LENS_CELLS` from config — `MAGNIFY_*` may be added to the existing
config import at `game.py:33-47`):

```python
def _draw(self) -> None:
    self._screen.fill(BG_COLOR)
    if self._heat_overlay:
        small = self._renderer.render_heat(self._grid)
    else:
        small = self._renderer.render(self._grid)
    target = (self._grid.width * CELL_SIZE, self._grid.height * CELL_SIZE)
    scaled = pygame.transform.scale(small, target)
    self._screen.blit(scaled, (0, 0))

    # Follow-cursor magnifier (visual only). Crop the grid-sized ``small``
    # surface around the cursor cell, scale up, blit as a lens. Painting input
    # mapping is UNCHANGED (mx // CELL_SIZE at 1x). Hidden over the palette.
    if self._magnify:
        self._draw_magnifier(small)

    count = int((self._grid.array != int(ElementId.EMPTY)).sum())
    self._ui.draw(
        self._screen,
        self.selected_element,
        self._clock.get_fps(),
        self.brush_radius,
        self._loop.paused,
        count,
        brush_shape=self.brush_shape,     # added in Phase 02
        magnify_on=self._magnify,         # added here
    )
```

Add the helper method:

```python
def _draw_magnifier(self, small: pygame.Surface) -> None:
    """Crop + scale a grid region around the cursor into a ~MAGNIFY_ZOOM lens.

    Visual only: does not affect painting coordinates. The lens is hidden when
    the cursor is over the reserved palette strip. Placement is offset from
    the cursor (up-and-right by the lens radius + a gap, clamped to the window)
    so it does not cover the brush point; pin the exact offset in the reflection.
    """
    mx, my = pygame.mouse.get_pos()
    if self._ui.in_reserved_area(mx, my):
        return
    gx, gy = mx // CELL_SIZE, my // CELL_SIZE
    src = magnifier_src_rect(gx, gy, self._grid.width, self._grid.height)
    if src is None:
        return
    sx, sy, sw, sh = src
    lens_w = sw * CELL_SIZE * MAGNIFY_ZOOM
    lens_h = sh * CELL_SIZE * MAGNIFY_ZOOM
    # Crop at grid resolution (surface is grid.width x grid.height) then scale.
    lens_surf = pygame.transform.scale(
        small.subsurface((sx, sy, sw, sh)), (lens_w, lens_h)
    )
    # Offset placement: up-and-right of the cursor, clamped to the window.
    gap = CELL_SIZE * 2
    lx = mx + gap
    ly = my - gap - lens_h
    lx = max(0, min(lx, self._window_w - lens_w))
    ly = max(0, min(ly, self._window_h - lens_h))
    self._screen.blit(lens_surf, (lx, ly))
    # A thin border so the lens edge is visible against the scene.
    pygame.draw.rect(self._screen, (255, 255, 255), (lx, ly, lens_w, lens_h), 1)
```

> `small.subsurface(...)` shares memory with `small` (no copy) and
> `pygame.transform.scale` returns a new surface — both are cheap. `sw`/`sh`
> equal `MAGNIFY_LENS_CELLS` (21) whenever the grid is large enough; the helper
> already guarantees `sx+sw <= grid_w` etc. so the subsurface rect is always
> valid. If `small` is the heat-overlay surface, the lens naturally shows
> zoomed heat too — no extra branch needed.
>
> **Input mapping is UNCHANGED**: `_paint_if_dragging` / `_erase_if_dragging`
> still use `mx // CELL_SIZE` (`game.py:240,260`). The lens is display-only; a
> painted cell lands where the 1× cursor points, NOT where it appears in the
> lens. This is the defining scope boundary (visual-only) — see Out of Scope.

### 4. `tests/test_ui.py`

Add a headless test for the pure helper:

```python
def test_magnifier_src_rect_centers_on_cursor() -> None:
    from sandfall.ui import magnifier_src_rect
    # On a large grid, centered on the cursor (21-cell window, odd -> exact center).
    assert magnifier_src_rect(100, 100, 200, 140) == (100 - 10, 100 - 10, 21, 21)


def test_magnifier_src_rect_clamps_at_edges() -> None:
    from sandfall.ui import magnifier_src_rect
    # Near the top-left edge the window shifts to stay inside the grid.
    assert magnifier_src_rect(0, 0, 200, 140) == (0, 0, 21, 21)
    # Near the bottom-right edge likewise.
    assert magnifier_src_rect(199, 139, 200, 140) == (200 - 21, 140 - 21, 21, 21)


def test_magnifier_src_rect_none_when_grid_too_small() -> None:
    from sandfall.ui import magnifier_src_rect
    # A grid smaller than the lens window in either axis -> no useful zoom.
    assert magnifier_src_rect(5, 5, 10, 10) is None
```

> The lens rendering itself is pygame (verified via SDL smoke, not asserted),
> consistent with how all `UI.draw` / `_draw` rendering is verified.

## Acceptance Criteria

- [ ] `Z` and the Magnifier button both toggle `_magnify` (visual via SDL
      smoke; the Magnifier button is no longer a dimmed placeholder and reflects
      on/off).
- [ ] When on and the cursor is in the sim area, a ~6× lens floats near the
      cursor showing zoomed grid content; it hides when the cursor is over the
      reserved palette area (visual via SDL smoke).
- [ ] **Painting coordinates are UNCHANGED**: with the magnifier on, a painted
      cell lands where the 1× cursor points (the grid cell at `mx // CELL_SIZE`),
      NOT where it appears in the lens. (Manual check via SDL smoke: toggle
      magnifier on, paint, confirm the cell appears at the 1× cursor location,
      not the lens location. Input mapping in `game.py:240,260` is untouched.)
- [ ] `magnifier_src_rect` centers on the cursor, clamps at edges, and returns
      `None` for too-small grids (headless test).
- [ ] The lens works in both render modes (element-id and heat-overlay) since
      it crops whatever `small` surface `_draw` produced (visual via SDL smoke
      with `H` toggled).
- [ ] The full existing suite stays green.

## Verification Commands

```bash
# Phase-focused (pure magnifier_src_rect helper):
uv run pytest tests/test_ui.py tests/test_brush.py -v
# Import smoke:
uv run python -c "import sandfall"
# FULL suite -- regression guard (must stay green):
uv run pytest
# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src
# SDL smoke -- visual: toggle Z, move the cursor, confirm the lens floats,
# hides over the palette, and painting lands at the 1x cursor (not the lens):
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
```

All commands must exit zero. The plan is complete when all pass.

## Documentation Updates

- `README.md` — Controls: add `Z` = toggle magnifier (follow-cursor ~6× lens,
  visual-only); note the lens hides over the palette and does not change where
  paint lands.
- `docs/ARCHITECTURE.md` — rendering section: the magnifier `_draw` pass
  (visual-only, input mapping unchanged), `magnifier_src_rect` (pure, edge
  clamping), and the `MAGNIFY_*` tunables.

Both done as part of this phase's commit.

## Reflection & Commit

After implementation, write `03-magnifier-reflection.md` in this directory.
Pin in it: (a) the chosen lens placement (offset up-and-right vs centered) and
whether it occluded the brush point in practice; (b) whether the lens border
color/weight needed tuning for visibility; (c) confirm the input-mapping
invariant held (paint landed at the 1× cursor, not the lens). Then make ONE
atomic git commit covering all changes in this phase. This is the final phase
of the brush-zoom-ui plan.

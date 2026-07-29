# Phase 01: Eraser tool (right-click + Eraser swatch)

## Objective

Add two complementary ways to erase painted cells: (a) right-click-and-drag
paints `ElementId.EMPTY` at the cursor (suppressed over the palette), and (b)
a visible "Eraser" palette swatch whose `element_id == ElementId.EMPTY` so
left-drag erases too. No new `ElementId` is introduced.

## Depends On

none

## Can Parallelize With

none — shares `config.py`, `game.py`, `ui.py` with Phases 02 and 03, which
must run strictly after this one.

## Recommended Agent

@implementer — additive, well-scoped code change with clear test surface.

## Changes Required

- `src/sandfall/config.py` — add eraser-swatch visual constants.
- `src/sandfall/ui.py` — `palette_layout` appends an Eraser swatch (EMPTY)
  last; `UI.draw` special-cases EMPTY so the swatch is visible.
- `src/sandfall/game.py` — add `_erase_if_dragging` (right button) and call it
  in `run()`; ensure right-click never selects a swatch.
- `tests/test_brush.py` — add a regression test that `paint_brush(..., EMPTY)`
  clears cells + zeroes life.
- `tests/test_ui.py` — update the layout-count/order assertions for the added
  Eraser swatch; add an eraser-rect `swatch_at` test.
- `README.md` — Controls table: add right-click erase + Eraser swatch rows.

## Implementation Instructions

> Re-read each file before editing — line numbers are current as of the v1
> source and will not have shifted yet at the start of Phase 01, but verify.

### 1. `src/sandfall/config.py`

Add the following constants in the UI section (after `HIGHLIGHT_COLOR` /
`PAUSED_COLOR`, near line 51-52):

```python
# Eraser swatch visual. EMPTY's registered color is (0,0,0) (invisible on the
# dark palette bar), so the Eraser swatch is rendered with a distinct fill +
# border + an "E" glyph (the font is already lazily created in UI.draw).
ERASER_SWATCH_COLOR: tuple[int, int, int] = (180, 180, 180)  # light-gray fill
ERASER_SWATCH_BORDER: tuple[int, int, int] = (90, 90, 90)  # darker border
ERASER_LABEL = "E"  # single-character glyph rendered centered in the swatch
```

### 2. `src/sandfall/ui.py`

**2a. Imports.** Add `ERASER_LABEL`, `ERASER_SWATCH_BORDER`, `ERASER_SWATCH_COLOR`
to the existing `from .config import (...)` block (lines 20-30).

**2b. `palette_layout` (lines 62-81).** After the `for eid in ElementId:`
loop that appends the real-element swatches, append ONE Eraser swatch whose
`element_id == ElementId.EMPTY`, reusing the running `x` cursor so it sits at
the right end with the same padding:

```python
def palette_layout(window_width: int, bar_y: int) -> list[Swatch]:
    """Compute the swatch rects: every non-EMPTY element left-to-right, then
    an Eraser swatch (ElementId.EMPTY) appended last.

    Pure: no pygame. Real elements are laid out in ElementId ascending order;
    the Eraser is appended at the right end as a utility tool. Selecting the
    Eraser sets selected_element = ElementId.EMPTY so left-drag erases too.
    """
    del window_width
    swatches: list[Swatch] = []
    x = PALETTE_MARGIN
    y = bar_y + PALETTE_MARGIN
    for eid in ElementId:
        if eid == ElementId.EMPTY:
            continue
        swatches.append(Swatch(eid, x, y, PALETTE_SWATCH, PALETTE_SWATCH))
        x += PALETTE_SWATCH + PALETTE_PADDING
    # Eraser tool appended last (reuses ElementId.EMPTY; left-drag erases).
    swatches.append(Swatch(ElementId.EMPTY, x, y, PALETTE_SWATCH, PALETTE_SWATCH))
    return swatches
```

**2c. `UI.draw` swatch loop (lines 172-176).** Special-case EMPTY so the
eraser swatch is visible (its `ELEMENTS[EMPTY].color` is black). Replace the
swatch-drawing block with a branch: for EMPTY, fill with
`ERASER_SWATCH_COLOR`, draw a 1px `ERASER_SWATCH_BORDER` outline, and render
the `ERASER_LABEL` glyph centered (font is already lazily created as
`self._font` earlier in `draw`, lines 150-151). For all other elements keep
the existing behavior. The active-highlight check (`s.element_id == active`)
must still fire for the eraser when it is selected.

Sketch (adapt to surrounding code; keep the `assert self._font is not None`
already present above):

```python
for s in self._swatches:
    rect = (s.x, s.y, s.w, s.h)
    if s.element_id == ElementId.EMPTY:
        pygame.draw.rect(screen, ERASER_SWATCH_COLOR, rect)
        pygame.draw.rect(screen, ERASER_SWATCH_BORDER, rect, 1)
        label = self._font.render(ERASER_LABEL, True, ERASER_SWATCH_BORDER)
        screen.blit(
            label,
            (s.x + (s.w - label.get_width()) // 2,
             s.y + (s.h - label.get_height()) // 2),
        )
    else:
        color = ELEMENTS[s.element_id].color
        pygame.draw.rect(screen, color, rect)
    if s.element_id == active:
        pygame.draw.rect(screen, HIGHLIGHT_COLOR, rect, 2)
```

### 3. `src/sandfall/game.py`

**3a. Add `_erase_if_dragging`.** Mirror `_paint_if_dragging` (lines 151-166)
but for the RIGHT mouse button (`pygame.mouse.get_pressed()[2]`) and always
painting `ElementId.EMPTY`. Reuse the same reserved-area guard so
right-clicking over the palette does nothing:

```python
def _erase_if_dragging(self) -> None:
    """Erase (paint EMPTY) under the cursor while the RIGHT button is held.

    Suppressed inside the palette strip, identical to left-button painting,
    so right-dragging over swatches does not erase beneath them. Right-click
    never selects a swatch (only button 1 does — see _handle_events).
    """
    if not pygame.mouse.get_pressed()[2]:
        return
    mx, my = pygame.mouse.get_pos()
    if self._ui.in_reserved_area(mx, my):
        return
    gx, gy = mx // CELL_SIZE, my // CELL_SIZE
    paint_brush(self._grid, gx, gy, self.brush_radius, ElementId.EMPTY)
```

**3b. Call it in `run()`.** In the frame loop (around line 112), add
`self._erase_if_dragging()` immediately after `self._paint_if_dragging()`.
(If both buttons are held, erase runs second and wins — acceptable edge case.)

**3c. Right-click must NOT select.** The existing `MOUSEBUTTONDOWN` branch
(line 140) already gates on `event.button == 1`, so button 3 (right-click)
does not select a swatch. Verify this and add a one-line comment making the
intent explicit, e.g. `# Only button 1 (left) selects; right-click erases
(see _erase_if_dragging) and must NOT select.` No behavioral change needed.

### 4. `tests/test_brush.py`

Add a regression test confirming `paint_brush(..., ElementId.EMPTY)` clears
both the element id and the life value:

```python
def test_paint_brush_empty_clears_element_and_life() -> None:
    """Erasing via paint_brush(..., EMPTY) clears the id AND zeroes life."""
    grid = Grid(10, 10)
    grid.set(5, 5, ElementId.FIRE)
    grid.set_life(5, 5, 99)
    assert grid.get(5, 5) == ElementId.FIRE
    assert grid.get_life(5, 5) == 99

    paint_brush(grid, 5, 5, 1, ElementId.EMPTY)

    assert grid.get(5, 5) == ElementId.EMPTY
    assert grid.get_life(5, 5) == 0
    # All cells in the disk are EMPTY with zero life.
    for y in range(grid.height):
        for x in range(grid.width):
            assert grid.get(x, y) == ElementId.EMPTY
            assert grid.get_life(x, y) == 0
```

### 5. `tests/test_ui.py`

**5a. Update `_non_empty_element_ids` usages / count assertions.** The palette
now has `len(ElementId)` swatches (7 elements + 1 eraser). Update:

- `test_palette_layout_one_swatch_per_non_empty_element` (lines 25-29): rename
  intent — now "one swatch per element plus an eraser". Assert
  `len(swatches) == len(ElementId)` and that the set of element ids equals
  `set(ElementId)` (EMPTY included, representing the eraser).
- `test_palette_layout_left_to_right_in_enum_order` (lines 32-43): the id list
  is now `non_empty_ids + [ElementId.EMPTY]` (eraser last). Update the
  assertion accordingly; the strictly-increasing-x and no-overlap checks still
  hold.

**5b. Add an eraser-specific test:**

```python
def test_palette_layout_includes_exactly_one_eraser_appended_last() -> None:
    swatches = palette_layout(WINDOW_WIDTH, WINDOW_HEIGHT - PALETTE_BAR_HEIGHT)
    erasers = [s for s in swatches if s.element_id == ElementId.EMPTY]
    assert len(erasers) == 1
    # The eraser is the last swatch.
    assert swatches[-1].element_id == ElementId.EMPTY


def test_swatch_at_on_eraser_returns_empty() -> None:
    ui = UI(WINDOW_WIDTH, WINDOW_HEIGHT)
    eraser = [s for s in ui.swatches if s.element_id == ElementId.EMPTY][0]
    cx = eraser.x + eraser.w // 2
    cy = eraser.y + eraser.h // 2
    assert ui.swatch_at(cx, cy) == ElementId.EMPTY
```

> The existing `test_palette_strip_lies_within_the_window` (lines 103-111)
> still holds — the eraser swatch is within the window at 800px wide (8
> swatches need 236px). No change required; leave it.

### 6. `README.md`

In the Controls table (lines 31-38), add two rows:

```
| **Right-click / drag** | Erase (paint EMPTY) under the cursor (ignored over the palette strip). |
| **Eraser swatch** | Select the Eraser (rightmost swatch) so left-drag erases instead of painting. |
```

## Acceptance Criteria

- [ ] `palette_layout` returns exactly one swatch with
      `element_id == ElementId.EMPTY`, appended last; all other elements
      remain in `ElementId` ascending order.
- [ ] `UI(WINDOW_WIDTH, WINDOW_HEIGHT).swatch_at(center_of_eraser)` returns
      `ElementId.EMPTY`.
- [ ] `paint_brush(grid, x, y, r, ElementId.EMPTY)` clears the element id AND
      zeroes life on every painted cell (regression test passes).
- [ ] Right mouse button held over the playfield erases each frame; right
      button held over the palette strip does nothing.
- [ ] Right-click (`MOUSEBUTTONDOWN` button 3) does NOT change
      `selected_element`; only left-click (button 1) selects.
- [ ] The Eraser swatch is visually distinct in `UI.draw` (light-gray fill +
      border + "E" glyph), not black/invisible.
- [ ] All existing UI tests updated and passing; new eraser tests passing.
- [ ] Five gates + `SANDFALL_FRAMES=60` smoke all exit zero.

## Verification Commands

```bash
# Phase-specific (pure-path eraser behavior, headless):
uv run pytest tests/test_brush.py tests/test_ui.py -v

# The five gates (all must exit zero):
uv run python -c "import sandfall"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# Full SDL loop smoke (real display available at DISPLAY=:1):
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback if no display:
#    SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
```

All commands must exit zero. Do NOT proceed to Phase 02 until all pass.

## Documentation Updates

- `README.md` Controls table — right-click erase + Eraser swatch rows (done as
  part of this phase's commit).

## Reflection & Commit

After implementation, write `01-eraser-reflection.md` in this directory
(difficulties, deviations, next steps, anything fun). Then make ONE atomic
git commit covering all changes in this phase.

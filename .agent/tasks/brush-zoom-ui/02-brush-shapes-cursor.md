# Phase 02: Brush shapes (Disk/Square) + cursor outline

## Objective

Add a `BrushShape` enum (DISK / SQUARE), generalize the paint primitive so a
square brush paints its whole bounding box, thread the shape through
`paint_brush` (including the temp/life seeding pass — which MUST cover the
square's bbox), cycle the shape with `Tab` and the Brush-shape button, and draw
an always-on cursor outline (circle for DISK, square for SQUARE) at the
footprint that hides over the reserved palette area.

## Depends On

01 (Palette reorg + tooltips) — must have passed all its gates. Reuses the
`ToolId.BRUSH_SHAPE` placeholder button and the `PaletteItem` model.

## Can Parallelize With

none — shares `ui.py` / `game.py` / `tests/test_ui.py` with Phase 03.

## Recommended Agent

@implementer — generalizes a core primitive (`Grid.fill_circle`) and threads a
new param through the brush + both paint paths in `game.py`, plus pygame cursor
rendering. The square-bbox seeding pass is the correctness crux; give it a
dedicated headless test.

## Changes Required

- `src/sandfall/grid.py` — add `BrushShape` enum (DISK, SQUARE); add a
  `shape: BrushShape = BrushShape.DISK` parameter to `fill_circle`; SQUARE
  paints the whole bbox (skip the radius test); `_mark_active_disk` UNCHANGED
  (already bbox-based).
- `src/sandfall/brush.py` — add `shape: BrushShape = BrushShape.DISK` to
  `paint_brush`; pass it to `fill_circle`; branch the temp/life seeding loop on
  shape (SQUARE → all bbox cells; DISK → radius test).
- `src/sandfall/game.py` — add `Game.brush_shape` state; `Tab` cycles it;
  Brush-shape button activates/cycles it; pass `self.brush_shape` through both
  `_paint_if_dragging` and `_erase_if_dragging`.
- `src/sandfall/ui.py` — `UI.draw` gains a `brush_shape` param; render the
  Brush-shape button as ENABLED (no longer dimmed) reflecting Disk/Square; draw
  the cursor outline (circle/square) at the footprint, hidden over the palette.
- `tests/test_brush.py` — square brush paints the bbox corners (unlike disk);
  painted FIRE in a square corner has life in range (the seeding-pass guard).
- `tests/test_grid.py` — `fill_circle(..., BrushShape.SQUARE)` fills the bbox;
  DISK unchanged (existing tests already cover it via the defaulted param).

## Implementation Instructions

> Re-read each file before editing — line numbers are current as of the
> post-Phase-01 source and will have shifted slightly.

### 1. `src/sandfall/grid.py`

**1a. Add `BrushShape`** near the top of `grid.py` (after the imports,
~`grid.py:46`). It lives here (not `brush.py`) to avoid an import cycle —
`brush.py` imports from `grid` already, so it picks `BrushShape` up for free;
`grid.py` never imports from `brush.py` (see Decision Log #6):

```python
class BrushShape(enum.Enum):
    """The footprint shape of a brush stroke.

    DISK paints every cell whose Euclidean distance from the center is <=
    radius (a filled circle). SQUARE paints the whole axis-aligned bounding
    box [cx-radius, cx+radius] x [cy-radius, cy+radius] (a filled square whose
    half-side is ``radius``). Defined here (not in brush.py) because
    ``Grid.fill_circle`` branches on it; brush.py imports from grid already.
    """

    DISK = enum.auto()
    SQUARE = enum.auto()
```

Add `import enum` to `grid.py`'s imports (near `import numpy as np`,
`grid.py:42`).

**1b. Add the `shape` parameter to `fill_circle`** (`grid.py:218-253`).
Default `BrushShape.DISK` so every existing caller (`brush.py:48` + 8 test
sites) is unchanged. For SQUARE, skip the `dx*dx + dy*dy <= r2` test and paint
the whole bbox. The `radius == 0` branch (`grid.py:233-238`) is unchanged (a
single cell is identical for both shapes). Update the docstring to mention the
shape:

```python
def fill_circle(
    self,
    cx: int,
    cy: int,
    radius: int,
    element_id: ElementId | int,
    shape: BrushShape = BrushShape.DISK,
) -> None:
    """Fill every cell within ``radius`` of ``(cx, cy)``.

    ``shape`` selects the footprint: DISK (default) paints the Euclidean disk;
    SQUARE paints the whole bounding box [cx-radius, cx+radius] x
    [cy-radius, cy+radius]. For ``radius == 0`` both shapes paint a single
    cell. Cells outside the grid are silently clipped. ``radius < 0`` raises
    ``ValueError``. Painted cells have their life reset to 0 and their
    temperature reset to ``AMBIENT_TEMP``; callers painting FIRE/SMOKE should
    seed life afterwards, and callers wanting a hot spawn-temp should set it
    afterwards, if they want either to persist.
    """
    if radius < 0:
        raise ValueError(f"radius must be non-negative ({radius=})")
    if radius == 0:
        self.set(cx, cy, element_id)
        self.set_life(cx, cy, 0)
        self.set_temp(cx, cy, AMBIENT_TEMP)
        _mark_active_disk(self, cx, cy, 0)
        return
    r2 = radius * radius
    x0 = max(0, cx - radius)
    x1 = min(self._width - 1, cx + radius)
    y0 = max(0, cy - radius)
    y1 = min(self._height - 1, cy + radius)
    eid = int(element_id)
    for y in range(y0, y1 + 1):
        dy = y - cy
        for x in range(x0, x1 + 1):
            dx = x - cx
            if shape == BrushShape.SQUARE or dx * dx + dy * dy <= r2:
                self._data[y, x] = eid
                self._life[y, x] = 0
                self._temp[y, x] = AMBIENT_TEMP
    _mark_active_disk(self, cx, cy, radius)
```

> `_mark_active_disk` (`grid.py:256-275`) is UNCHANGED — it marks the
> bbox ⊕ 1-neighborhood, which is exactly correct for the square (whose
> footprint IS its bbox) and unchanged for the disk. (Decision Log #8.)

> **Name note:** `fill_circle` now fills squares too. The docstring clarifies.
> If you prefer a clean rename to `fill_brush`, update `brush.py:48` + the 8
> test call sites + docstrings in this same commit (mechanical); the defaulted
> param keeps the rename optional (Decision Log #7). Pick one and pin it in the
> reflection.

### 2. `src/sandfall/brush.py`

**2a. Thread `shape` through `paint_brush`** (`brush.py:27-76`). Add the param
(default DISK), pass to `fill_circle`, and **branch the seeding loop on shape**
(`brush.py:63-76`). This is the correctness-critical edit: the seeding pass
walks the disk today (`dx*dx + dy*dy <= r2`); for SQUARE it must walk the whole
bbox or painted FIRE/LAVA/STEAM/SMOKE in a square's corners would have life 0
and expire instantly (the Phase-04 bug resurfacing for the square — Decision
Log #9):

```python
def paint_brush(
    grid: Grid,
    gx: int,
    gy: int,
    radius: int,
    element_id: ElementId,
    shape: BrushShape = BrushShape.DISK,
) -> None:
    """Paint a filled disk or square of ``element_id`` centered on ``(gx, gy)``.

    Wraps :meth:`Grid.fill_circle` (passing ``shape``) and then walks the same
    footprint once more setting each painted cell's temperature to its
    element's ``temp_spawn`` and, for FIRE/SMOKE/STEAM, seeding life. The
    footprint walk respects ``shape``: SQUARE walks the whole bounding box
    (corners included); DISK walks only the radius-tested disk. Out-of-bounds
    centers are clipped silently.
    """
    grid.fill_circle(gx, gy, radius, element_id, shape)

    spawn_temp = ELEMENTS[element_id].temp_spawn
    if element_id == ElementId.FIRE:
        seed: Callable[[], int] | None = seed_fire_life
    elif element_id == ElementId.SMOKE:
        seed = seed_smoke_life
    elif element_id == ElementId.STEAM:
        seed = seed_steam_life
    else:
        seed = None
    if spawn_temp == AMBIENT_TEMP and seed is None:
        return

    r2 = radius * radius
    x0 = max(0, gx - radius)
    x1 = min(grid.width - 1, gx + radius)
    y0 = max(0, gy - radius)
    y1 = min(grid.height - 1, gy + radius)
    for y in range(y0, y1 + 1):
        dy = y - gy
        for x in range(x0, x1 + 1):
            dx = x - gx
            in_footprint = shape == BrushShape.SQUARE or dx * dx + dy * dy <= r2
            if in_footprint and grid.get(x, y) == element_id:
                if spawn_temp != AMBIENT_TEMP:
                    grid.set_temp(x, y, spawn_temp)
                if seed is not None:
                    grid.set_life(x, y, seed())
```

Add `BrushShape` to `brush.py`'s `from .grid import Grid` import
(`brush.py:23`) → `from .grid import BrushShape, Grid`.

### 3. `src/sandfall/game.py`

**3a. Add brush-shape state.** Add a class attribute + init in `__init__`
(near `self.brush_radius` at `game.py:122`):

```python
brush_shape: BrushShape
...
self.brush_shape = BrushShape.DISK
```

Add `BrushShape` to the `from .grid import ...` import (`game.py:50`):
`from .grid import BrushShape, Grid, migrate_grid`.

**3b. `Tab` cycles shape.** In `_handle_events` KEYDOWN (`game.py:159-170`),
add:

```python
elif event.key == pygame.K_TAB:
    shapes = list(BrushShape)
    self.brush_shape = shapes[(shapes.index(self.brush_shape) + 1) % len(shapes)]
```

**3c. Brush-shape button cycles shape.** In the MOUSEBUTTONDOWN dispatch added
in Phase 01 (`game.py` `_handle_events`, the `elif item.tool == ToolId.BRUSH_SHAPE`
placeholder branch), replace the `pass` with the same cycle logic (factor a
tiny `_cycle_brush_shape(self)` helper and call it from both `Tab` and the
button — DRY):

```python
def _cycle_brush_shape(self) -> None:
    shapes = list(BrushShape)
    self.brush_shape = shapes[(shapes.index(self.brush_shape) + 1) % len(shapes)]
```

**3d. Thread shape through both paint paths.** In `_paint_if_dragging`
(`game.py:241`) and `_erase_if_dragging` (`game.py:261`), pass
`self.brush_shape`:

```python
paint_brush(self._grid, gx, gy, self.brush_radius, self.selected_element, self.brush_shape)
...
paint_brush(self._grid, gx, gy, self.brush_radius, ElementId.EMPTY, self.brush_shape)
```

> Input mapping (`mx // CELL_SIZE`, `game.py:240,260`) is UNCHANGED — the
> magnifier (Phase 03) is the only thing that will ever touch visual zoom; the
> shape changes only the footprint, not the coordinate mapping.

### 4. `src/sandfall/ui.py`

**4a. `UI.draw` gains `brush_shape`.** Update the signature
(`ui.py:166-174`) to accept `brush_shape: BrushShape`, and have `Game._draw`
pass `self.brush_shape` (`game.py:285-292`). Import `BrushShape` into `ui.py`
(`from .grid import BrushShape`).

**4b. Brush-shape button now ENABLED + reflects shape.** In the tool-rendering
block added in Phase 01, stop dimming BRUSH_SHAPE: render it with the normal
tool styling and an active outline when `brush_shape` is the shape it
represents. (A single button cycling Disk→Square should show the CURRENT shape:
e.g. draw a small circle outline when DISK, a small square outline when SQUARE,
via `pygame.draw` inside the button rect — cleaner than font glyphs. Pin the
exact icon in the reflection.) The button is active (highlighted) whenever it
is the selected shape family — since there's only one shape button, highlight
it whenever the shape != default, OR always; recommend highlighting it to
indicate "brush shape tool is the current shape". Pin in reflection.

**4c. Cursor outline (always on).** At the end of `UI.draw`, read the cursor
and draw the footprint outline in screen space. Hide it when the cursor is in
the reserved palette area (`in_reserved_area`). The footprint in screen pixels
for a brush of `radius` r centered on grid cell `(gx, gy)` spans
`[gx-r, gx+r] × [gy-r, gy+r]` cells → screen px
`[(gx-r)*CELL_SIZE, (gx+r+1)*CELL_SIZE)`. Recommended outline geometry:

```python
mx, my = pygame.mouse.get_pos()
if not self.in_reserved_area(mx, my):
    gx, gy = mx // CELL_SIZE, my // CELL_SIZE
    # Bounding box of the footprint in screen px (encloses the r-cell disk/square).
    left = (gx - brush_radius) * CELL_SIZE
    top = (gy - brush_radius) * CELL_SIZE
    size = (2 * brush_radius + 1) * CELL_SIZE
    if brush_shape == BrushShape.SQUARE:
        pygame.draw.rect(screen, HIGHLIGHT_COLOR, (left, top, size, size), 1)
    else:  # DISK — a circle enclosing the same bbox.
        pygame.draw.circle(screen, HIGHLIGHT_COLOR,
                           (left + size // 2, top + size // 2), size // 2, 1)
```

> Import `CELL_SIZE` into `ui.py` from config (add to the existing import
> block, `ui.py:20-34`). Pin the exact outline weight/color in the reflection
> (HIGHLIGHT_COLOR width-1 is the recommended default; ensure it's visible on
> both light and dark elements).

### 5. Tests

**5a. `tests/test_brush.py`** — add square-brush tests:

```python
def test_paint_brush_square_paints_bounding_box_corners() -> None:
    """SQUARE paints the whole bbox; DISK does not paint the corners."""
    from sandfall.grid import BrushShape
    grid = Grid(20, 20)
    paint_brush(grid, 10, 10, 3, ElementId.SAND, BrushShape.SQUARE)
    # The four bbox corners are painted for SQUARE...
    assert grid.get(10 - 3, 10 - 3) == ElementId.SAND
    assert grid.get(10 + 3, 10 + 3) == ElementId.SAND
    assert grid.get(10 - 3, 10 + 3) == ElementId.SAND
    assert grid.get(10 + 3, 10 - 3) == ElementId.SAND
    # ...but a DISK of the same radius does NOT paint the corners.
    grid2 = Grid(20, 20)
    paint_brush(grid2, 10, 10, 3, ElementId.SAND, BrushShape.DISK)
    assert grid2.get(10 - 3, 10 - 3) == ElementId.EMPTY


def test_paint_brush_square_fire_seeds_corner_life() -> None:
    """The seeding pass must cover the SQUARE bbox, not just the disk.

    Regression guard (Decision Log #9): without the shape-aware seeding walk,
    painted FIRE in a square's corner would have life 0 and expire on the next
    step. (Phase 04 fixed this for the disk; this test pins it for the square.)
    """
    from sandfall.grid import BrushShape
    grid = Grid(20, 20)
    paint_brush(grid, 10, 10, 3, ElementId.FIRE, BrushShape.SQUARE)
    # A bbox corner must be FIRE with seeded life in range.
    cx, cy = 10 - 3, 10 - 3
    assert grid.get(cx, cy) == ElementId.FIRE
    assert FIRE_LIFE_MIN <= grid.get_life(cx, cy) <= FIRE_LIFE_MAX


def test_paint_brush_disk_is_unchanged_by_shape_param() -> None:
    """The defaulted DISK shape is byte-identical to the pre-shape behavior."""
    from sandfall.grid import BrushShape
    g1 = Grid(20, 20)
    g2 = Grid(20, 20)
    paint_brush(g1, 10, 10, 3, ElementId.SAND)                      # default
    paint_brush(g2, 10, 10, 3, ElementId.SAND, BrushShape.DISK)     # explicit
    assert np.array_equal(g1.array, g2.array)
```

(add `import numpy as np` if not already imported in `test_brush.py`.)

**5b. `tests/test_grid.py`** — add a square `fill_circle` test (additive; the
existing disk tests at lines 79/87/109/117/174/245 are unchanged thanks to the
defaulted param):

```python
def test_fill_circle_square_paints_whole_bounding_box() -> None:
    from sandfall.grid import BrushShape
    grid = Grid(20, 20)
    grid.fill_circle(10, 10, 3, ElementId.SAND, BrushShape.SQUARE)
    # Every cell in the bbox is painted (corners included).
    for y in range(10 - 3, 10 + 4):
        for x in range(10 - 3, 10 + 4):
            assert grid.get(x, y) == ElementId.SAND
    # Life + temp reset on the whole square (mirrors disk contract).
    assert grid.get_life(10 - 3, 10 - 3) == 0
```

**5c. `tests/test_ui.py`** — the cursor outline is pygame (verified via SDL
smoke, not asserted). No new headless UI test is required for the outline; the
`brush_shape` param threading is exercised by the SDL smoke + the fact that
`UI.draw` accepts it without error.

## Acceptance Criteria

- [ ] `Grid.fill_circle(..., BrushShape.SQUARE)` paints the whole bbox
      (corners painted); DISK is unchanged (headless test; existing disk tests
      stay green via the defaulted param).
- [ ] `paint_brush(..., SQUARE)` paints the bbox corners AND seeds life/temp
      there for FIRE/LAVA/STEAM/SMOKE — a painted FIRE in a square corner has
      life in range (headless test; Decision Log #9).
- [ ] `Tab` and the Brush-shape button both cycle Disk ↔ Square (visual via SDL
      smoke; the cursor outline reflects the current shape + radius).
- [ ] The cursor outline is always on over the sim area, matches the shape
      (circle/square) and radius, and hides over the reserved palette area
      (visual via SDL smoke).
- [ ] The Brush-shape button is no longer a dimmed placeholder — it renders
      enabled and reflects the current shape (visual via SDL smoke).
- [ ] `_mark_active_disk` was NOT modified and dormant-cell wake correctness
      holds for the square (full simulation suite stays green).
- [ ] The full existing suite stays green.

## Verification Commands

```bash
# Phase-focused (square-bbox + seeding-pass guards; disk unchanged):
uv run pytest tests/test_brush.py tests/test_grid.py tests/test_ui.py -v
# Import smoke:
uv run python -c "import sandfall"
# FULL suite -- regression guard (incl. dormant-cell active-mark for the square):
uv run pytest
# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src
# SDL smoke -- visual: cycle Tab, paint with each shape, watch the cursor outline:
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
```

All commands must exit zero. Do NOT proceed to Phase 03 until all pass.

## Documentation Updates

- `README.md` — Controls: add `Tab` = cycle brush shape (Disk/Square); note the
  cursor outline shows the footprint.
- `docs/ARCHITECTURE.md` — brush section: `BrushShape`, the `shape` param on
  `fill_circle` / `paint_brush`, the square=bbox / disk=radius-test distinction,
  and the shape-aware seeding pass.

Both done as part of this phase's commit.

## Reflection & Commit

After implementation, write `02-brush-shapes-cursor-reflection.md` in this
directory. Pin in it: (a) whether you kept `fill_circle` or renamed to
`fill_brush`; (b) the Brush-shape button's icon/active-state choice; (c) the
cursor outline color/weight and whether the circle-enclosing-bbox geometry
looked right at several radii. Then make ONE atomic git commit covering all
changes in this phase.

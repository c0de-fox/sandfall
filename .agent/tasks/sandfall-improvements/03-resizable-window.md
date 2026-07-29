# Phase 03: Resizable window (preserve overlapping content)

## Objective

Make the window resizable. On `pygame.VIDEORESIZE`, recompute the grid
dimensions (cells stay square; snap via floor division), recreate the `Grid`
**preserving the overlapping region** of both the id and life arrays, rebuild
the `Simulation`, resize the `UI`, and refresh the display surface. The
palette bar stays a fixed 40px pinned to the bottom; enforce a minimum window
size. Also rename `WINDOW_WIDTH`/`WINDOW_HEIGHT` →
`INITIAL_WINDOW_W`/`INITIAL_WINDOW_H` since they now mean "starting size".

## Depends On

02 (Palette floor) — must have passed all its gates.

## Can Parallelize With

none — final phase; builds on Phase 02's geometry and Phase 01's palette
(which sets the min-width requirement).

## Recommended Agent

@implementer — largest surface area: new event path + helpers + a rename
ripple + dynamic renderer/UI. Read carefully; mypy strict throughout.

## Changes Required

- `src/sandfall/config.py` — rename `WINDOW_WIDTH`/`WINDOW_HEIGHT` to
  `INITIAL_WINDOW_W`/`INITIAL_WINDOW_H`; add `MIN_WINDOW_W`/`MIN_WINDOW_H`,
  `MIN_GRID_COLS`/`MIN_GRID_ROWS`; add pure `compute_grid_dims(w, h)`.
- `src/sandfall/grid.py` — add pure `migrate_grid(old, new) -> None`.
- `src/sandfall/renderer.py` — `render` reallocates `_cell_surface` if the
  grid size changed (self-healing against runtime resize).
- `src/sandfall/ui.py` — add `UI.resize(w, h)` that recomputes geometry and
  invalidates the cached `_bar_surf`.
- `src/sandfall/game.py` — `RESIZABLE` flag; store current window size as
  instance state; handle `VIDEORESIZE`; add `_handle_resize`; update `_draw`
  to derive the scale target from the current grid dims.
- `tests/test_config.py` (NEW) or extend an existing config test —
  `compute_grid_dims` floor-division + minimum-clamping.
- `tests/test_grid.py` — `migrate_grid` (grow, shrink, life carried, crop,
  disjoint).
- `tests/test_ui.py` — update `WINDOW_WIDTH`/`WINDOW_HEIGHT` imports to the
  new names; add a `UI.resize` test.
- `README.md` — Controls: add resizable-window row.
- `docs/ARCHITECTURE.md` — dynamic geometry, `migrate_grid`, `compute_grid_dims`.

## Implementation Instructions

> Re-read each file before editing — line numbers are current as of the v1
> source plus Phases 01-02 and will have shifted.

### 1. `src/sandfall/config.py`

**1a. Rename** `WINDOW_WIDTH` → `INITIAL_WINDOW_W` and `WINDOW_HEIGHT` →
`INITIAL_WINDOW_H` (lines 16-17). Update the comment. `GRID_WIDTH`/`GRID_HEIGHT`
now derive from the new names:

```python
INITIAL_WINDOW_W = 800  # starting window width (the window is resizable)
INITIAL_WINDOW_H = 600  # starting window height (the window is resizable)
CELL_SIZE = 4

SIM_AREA_HEIGHT = INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT  # 560
GRID_WIDTH = INITIAL_WINDOW_W // CELL_SIZE   # 200  (initial grid cols)
GRID_HEIGHT = SIM_AREA_HEIGHT // CELL_SIZE   # 140  (initial grid rows)
```

**1b. Add minimum-size constants** (placed near the geometry section):

```python
# Minimum resizable window size. Width must fit the whole palette (8 swatches
# incl. the Eraser: 8*24 + 7*4 + 2*8 == 236px) with margin -> 256. Height
# must fit the 40px palette + a usable sim area (>= 40 cells == 160px) -> 200.
MIN_WINDOW_W = 256
MIN_WINDOW_H = 200
MIN_GRID_COLS = MIN_WINDOW_W // CELL_SIZE                     # 64
MIN_GRID_ROWS = (MIN_WINDOW_H - PALETTE_BAR_HEIGHT) // CELL_SIZE  # 40
```

**1c. Add the pure `compute_grid_dims` helper** (place near
`clamp_brush_radius` at the bottom; it is a pure function so it is unit-tested
headlessly):

```python
def compute_grid_dims(window_w: int, window_h: int) -> tuple[int, int]:
    """Compute ``(cols, rows)`` for a window of the given pixel size.

    Cells stay square at ``CELL_SIZE``: cols/rows are floor-divided so the
    grid is the largest whole-cell multiple that fits; leftover pixels (when
    the window isn't an exact multiple) are filled with BG_COLOR by the
    renderer. Rows exclude the fixed palette bar pinned to the bottom.
    Both dimensions are clamped to a minimum cell count (MIN_GRID_COLS /
    MIN_GRID_ROWS) so an aggressively shrunk window still has a usable grid
    and the palette always fits.

    Pure / pygame-free -> unit-tested headlessly.
    """
    cols = max(MIN_GRID_COLS, window_w // CELL_SIZE)
    rows = max(MIN_GRID_ROWS, (window_h - PALETTE_BAR_HEIGHT) // CELL_SIZE)
    return cols, rows
```

### 2. `src/sandfall/grid.py`

**2a. Add `migrate_grid`** as a module-level function (after the `Grid`
class). It copies the overlapping region of BOTH arrays; out-of-bounds old
content is cropped/lost; new cells stay EMPTY/life 0. Accessing the
underscore-prefixed arrays is fine because this function lives in the same
module as `Grid`:

```python
def migrate_grid(old: Grid, new: Grid) -> None:
    """Copy the overlapping region of ``old`` into ``new`` (ids AND life).

    The copied region is ``min(old.width, new.width) x min(old.height,
    new.height)``. Old content outside the overlap is cropped and lost
    (permanent). Cells in ``new`` outside the overlap keep their defaults
    (EMPTY / life 0). ``old`` is read-only here; ``new`` is mutated in place.

    Pure / pygame-free -> unit-tested headlessly. Used by Game on window
    resize to preserve the player's scene.
    """
    w = min(old.width, new.width)
    h = min(old.height, new.height)
    if w > 0 and h > 0:
        new._data[:h, :w] = old._data[:h, :w]
        new._life[:h, :w] = old._life[:h, :w]
```

### 3. `src/sandfall/renderer.py`

**3a. Make `render` self-healing against grid resize.** Currently
`_cell_surface` is created once in `__init__` (line 68) from the static
`GRID_WIDTH`/`GRID_HEIGHT`. After resize the grid may be a different size and
`pygame.surfarray.blit_array` would raise on a size mismatch. At the top of
`render` (line 70), reallocate if the size differs:

```python
def render(self, grid: Grid) -> pygame.Surface:
    """Paint ``grid`` onto the grid-sized cell surface and return it."""
    # Reallocate if the grid size changed (e.g. after a window resize) so
    # blit_array never sees a size mismatch.
    if self._cell_surface.get_size() != (grid.width, grid.height):
        self._cell_surface = pygame.Surface((grid.width, grid.height))
    rgb = grid_to_rgb(grid, self._lut)
    rgb_t = np.transpose(rgb, (1, 0, 2))
    pygame.surfarray.blit_array(self._cell_surface, rgb_t)
    return self._cell_surface
```

> `_lut` is keyed by `ElementId` count, which is unchanged by resize, so the
> LUT needs no update.

### 4. `src/sandfall/ui.py`

**4a. Add `UI.resize`.** Insert after `__init__` (around line 107). It
re-runs the geometry computation and invalidates the cached `_bar_surf` (whose
width depends on the window width):

```python
def resize(self, window_width: int, window_height: int) -> None:
    """Recompute layout for a new window size (called on VIDEORESIZE).

    Resets the cached palette-bar surface so it is rebuilt at the new width
    on the next draw.
    """
    self._window_width = window_width
    self._window_height = window_height
    self._bar_y = window_height - PALETTE_BAR_HEIGHT
    self._swatches = palette_layout(window_width, self._bar_y)
    self._bar_surf = None
```

### 5. `src/sandfall/game.py`

**5a. Imports.** In the `from .config import (...)` block (lines 33-44):
- Replace `WINDOW_HEIGHT`, `WINDOW_WIDTH` with `INITIAL_WINDOW_H`,
  `INITIAL_WINDOW_W`.
- Add `MIN_WINDOW_H`, `MIN_WINDOW_W`, `compute_grid_dims`.
- Add `migrate_grid` to the `from .grid import Grid` import (line 47) →
  `from .grid import Grid, migrate_grid`.

**5b. Instance state for current size.** Add two attributes to the class
declaration (around lines 73-84) and initialize them in `__init__`:

```python
_window_w: int
_window_h: int
```

In `__init__`:
```python
self._screen = pygame.display.set_mode(
    (INITIAL_WINDOW_W, INITIAL_WINDOW_H), pygame.RESIZABLE
)
...
self._window_w = INITIAL_WINDOW_W
self._window_h = INITIAL_WINDOW_H
```

(The `RESIZABLE` flag is the only change to the `set_mode` call beyond the
rename.)

**5c. Handle `VIDEORESIZE`.** In `_handle_events` (lines 125-149), add a
branch (e.g. after the `MOUSEBUTTONDOWN` branch):

```python
elif event.type == pygame.VIDEORESIZE:
    self._handle_resize(event.w, event.h)
```

**5d. Add `_handle_resize`.** Clamp to minimum, recompute dims, migrate the
grid, rebuild the sim, refresh the screen surface, resize the UI:

```python
def _handle_resize(self, raw_w: int, raw_h: int) -> None:
    """Recompute grid + UI for a resized window, preserving the overlap.

    Cells stay square (floor snap); leftover pixels are BG_COLOR. The palette
    bar stays a fixed PALETTE_BAR_HEIGHT pinned to the bottom. Content
    outside the overlapping region is lost (see migrate_grid).
    """
    w = max(MIN_WINDOW_W, raw_w)
    h = max(MIN_WINDOW_H, raw_h)
    cols, rows = compute_grid_dims(w, h)
    new_grid = Grid(cols, rows)
    migrate_grid(self._grid, new_grid)
    self._grid = new_grid
    self._sim = Simulation(self._grid)
    self._window_w, self._window_h = w, h
    self._screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
    self._ui.resize(w, h)
```

**5e. `_draw` scale target (line 173).** Derive from the current grid dims
instead of the (now-renamed, initial-only) window constants. The grid surface
is `(grid.width, grid.height)`; scale to `(grid.width * CELL_SIZE,
grid.height * CELL_SIZE)` and blit at `(0, 0)`. Leftover window pixels (window
not a whole-cell multiple) keep the `BG_COLOR` from `self._screen.fill`:

```python
def _draw(self) -> None:
    self._screen.fill(BG_COLOR)
    small = self._renderer.render(self._grid)
    target = (self._grid.width * CELL_SIZE, self._grid.height * CELL_SIZE)
    scaled = pygame.transform.scale(small, target)
    self._screen.blit(scaled, (0, 0))
    self._ui.draw(
        self._screen,
        self.selected_element,
        self._clock.get_fps(),
        self.brush_radius,
        self._loop.paused,
    )
```

> `WINDOW_WIDTH`/`WINDOW_HEIGHT` should no longer be referenced anywhere in
> `game.py` after this — grep to confirm.

### 6. Tests

**6a. `tests/test_config.py` (NEW)** — or add to an existing config test file
if one exists; at planning time there is none, so create it. Cover
`compute_grid_dims`:

```python
def test_compute_grid_dims_floor_division_exact_multiple() -> None:
    from sandfall.config import CELL_SIZE, PALETTE_BAR_HEIGHT, compute_grid_dims
    cols, rows = compute_grid_dims(800, 600)
    assert cols == 800 // CELL_SIZE
    assert rows == (600 - PALETTE_BAR_HEIGHT) // CELL_SIZE


def test_compute_grid_dims_floors_non_multiple() -> None:
    # 803 // 4 == 200 (3 leftover px -> BG_COLOR); 603 -> (603-40)//4 == 140
    from sandfall.config import compute_grid_dims
    cols, rows = compute_grid_dims(803, 603)
    assert cols == 200
    assert rows == 140


def test_compute_grid_dims_clamps_to_minimum() -> None:
    from sandfall.config import MIN_GRID_COLS, MIN_GRID_ROWS, compute_grid_dims
    cols, rows = compute_grid_dims(10, 10)  # absurdly small
    assert cols == MIN_GRID_COLS
    assert rows == MIN_GRID_ROWS
```

**6b. `tests/test_grid.py`** — add `migrate_grid` tests:

```python
def test_migrate_grid_grow_preserves_overlap_ids_and_life() -> None:
    from sandfall.grid import migrate_grid
    old = Grid(3, 3)
    old.set(0, 0, ElementId.SAND)
    old.set(2, 2, ElementId.FIRE)
    old.set_life(2, 2, 77)
    new = Grid(5, 5)
    migrate_grid(old, new)
    assert new.get(0, 0) == ElementId.SAND
    assert new.get(2, 2) == ElementId.FIRE
    assert new.get_life(2, 2) == 77
    # Newly exposed cells are EMPTY / life 0.
    assert new.get(4, 4) == ElementId.EMPTY
    assert new.get_life(4, 4) == 0


def test_migrate_grid_shrink_crops_overflow() -> None:
    from sandfall.grid import migrate_grid
    old = Grid(5, 5)
    old.set(4, 4, ElementId.STONE)
    new = Grid(2, 2)
    migrate_grid(old, new)
    # The (4,4) stone is outside the 2x2 overlap -> lost.
    assert new.get(0, 0) == ElementId.EMPTY
    # Overlap preserved.
    old2 = Grid(5, 5)
    old2.set(1, 1, ElementId.WATER)
    new2 = Grid(2, 2)
    migrate_grid(old2, new2)
    assert new2.get(1, 1) == ElementId.WATER


def test_migrate_grid_new_untouched_outside_overlap_stays_default() -> None:
    from sandfall.grid import migrate_grid
    old = Grid(2, 2)
    new = Grid(4, 4)
    # Pre-populate new outside the overlap to prove it's NOT overwritten by
    # default values, but rather left alone outside the overlap region.
    new.set(3, 3, ElementId.PLANT)
    migrate_grid(old, new)
    assert new.get(3, 3) == ElementId.PLANT  # untouched (overlap is only 2x2)
    assert new.get_life(3, 3) == 0
```

(Adjust the last test's intent if clearer: the contract is "overlap copied,
non-overlap in `new` unchanged". The implementer may also assert `new` starts
all-zero and the non-overlap stays zero — either is fine; pin the documented
contract.)

**6c. `tests/test_ui.py`** — update the import (line 16)
`from sandfall.config import WINDOW_HEIGHT, WINDOW_WIDTH` →
`from sandfall.config import INITIAL_WINDOW_H, INITIAL_WINDOW_W` and replace
all usages in this file (lines 26, 33, 47, 65, 75, 85, 93, 97, 100, 104, 106,
109, 111). Add:

```python
def test_ui_resize_recomputes_bar_y_and_invalidates_bar_surf() -> None:
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)
    assert ui.bar_y == INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT
    ui.resize(INITIAL_WINDOW_W, INITIAL_WINDOW_H + 80)
    assert ui.bar_y == INITIAL_WINDOW_H + 80 - PALETTE_BAR_HEIGHT
    # Swatch y positions moved with the new bar.
    assert all(s.y >= ui.bar_y for s in ui.swatches)
```

**6d. (Optional, if feasible) Game-driven resize under the dummy driver.**
If `pygame.mouse`/event posting cooperates under `SDL_VIDEODRIVER=dummy`, post
a `pygame.event.Event(pygame.VIDEORESIZE, w=..., h=...)` into a short
`SANDFALL_FRAMES`-capped run and assert `game._grid.width/height` changed and
a cell painted before the resize is still present after (overlap preserved).
This is optional — the pure `migrate_grid` + `compute_grid_dims` tests are
the primary correctness gate; the smoke is the integration gate. Do not block
the phase on this if the dummy driver misbehaves.

### 7. `README.md`

In the Controls table (lines 31-38), add:

```
| **Resize window** | Drag the window border to resize the playfield. The grid grows/shrinks in whole 4px cells; content outside the new area is lost. The palette bar stays pinned to the bottom. |
```

### 8. `docs/ARCHITECTURE.md`

- Update the rendering section (lines 172-174): the grid surface is now
  `(grid.width, grid.height)` which can change at runtime; `render`
  reallocates its surface on size change; `_draw` scales to
  `(grid.width * CELL_SIZE, grid.height * CELL_SIZE)`.
- Add a short "Window resizing" subsection documenting `compute_grid_dims`,
  `migrate_grid` (overlap-preserving, overflow lost), the fixed palette bar,
  and the minimum window size.
- Update any reference to `WINDOW_WIDTH`/`WINDOW_HEIGHT` to
  `INITIAL_WINDOW_W`/`INITIAL_WINDOW_H`.

## Acceptance Criteria

- [ ] The window opens with `pygame.RESIZABLE`; dragging the border fires
      `VIDEORESIZE` and the playfield redraws at the new size.
- [ ] `compute_grid_dims` floor-divides and clamps to `MIN_GRID_COLS`/
      `MIN_GRID_ROWS` (tests pass).
- [ ] `migrate_grid` copies the overlapping region of both id and life
      arrays; crops overflow; leaves non-overlap in `new` untouched (tests
      pass).
- [ ] `Renderer.render` reallocates `_cell_surface` when the grid size
      differs (no `blit_array` size-mismatch error after a resize).
- [ ] `UI.resize` recomputes `bar_y`/`_swatches` and clears `_bar_surf`; the
      palette stays pinned to the bottom at the new width.
- [ ] `_handle_resize` clamps to `MIN_WINDOW_W`/`MIN_WINDOW_H`.
- [ ] `WINDOW_WIDTH`/`WINDOW_HEIGHT` no longer exist; all references use
      `INITIAL_WINDOW_W`/`INITIAL_WINDOW_H` (grep confirms zero stale uses).
- [ ] `_draw` derives the scale target from the current grid dims; leftover
      pixels are `BG_COLOR`.
- [ ] All existing tests pass; new tests pass.
- [ ] Five gates + `SANDFALL_FRAMES=60` smoke all exit zero.

## Verification Commands

```bash
# Phase-specific (pure helpers):
uv run pytest tests/test_config.py tests/test_grid.py tests/test_ui.py -v
# Confirm no stale old-name references:
uv run python -c "import sandfall.config as c; assert not hasattr(c, 'WINDOW_WIDTH'); assert not hasattr(c, 'WINDOW_HEIGHT'); print('rename clean')"
# (grep-level belt-and-suspenders:)
rg -n 'WINDOW_WIDTH|WINDOW_HEIGHT' src tests || echo 'no stale references'

# The five gates (all must exit zero):
uv run python -c "import sandfall"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# Full SDL loop smoke at the initial size:
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
# Manual resize check on DISPLAY=:1: launch the game, drag the window border,
# confirm sand piles on the palette and resizing preserves the top-left scene.
```

All commands must exit zero. The plan is complete when all pass.

## Documentation Updates

- `README.md` — Controls: resizable-window row.
- `docs/ARCHITECTURE.md` — dynamic rendering geometry, window-resizing
  subsection (`compute_grid_dims`, `migrate_grid`, fixed palette bar, min
  size), `INITIAL_WINDOW_*` rename.

Both done as part of this phase's commit.

## Reflection & Commit

After implementation, write `03-resizable-window-reflection.md` in this
directory. Then make ONE atomic git commit covering all changes in this phase.
This is the final phase of the improvements plan.

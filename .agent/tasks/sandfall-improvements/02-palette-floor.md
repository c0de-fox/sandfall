# Phase 02: Palette bar as simulation floor

## Objective

Shrink the grid so it spans ONLY the area above the palette bar. Elements now
pile ON the palette's top edge instead of falling behind it. The grid becomes
200 x 140 (was 200 x 150); the window stays 800 x 600.

## Depends On

01 (Eraser tool) — must have passed all its gates.

## Can Parallelize With

none — shares `config.py`/`game.py`/`ui.py` with Phases 01 and 03.

## Recommended Agent

@implementer — geometry refactor across config/grid/game + test invariant
updates.

## Changes Required

- `src/sandfall/config.py` — relocate `PALETTE_BAR_HEIGHT` here (from `ui.py`);
  add `SIM_AREA_HEIGHT`; recompute `GRID_HEIGHT` from it.
- `src/sandfall/ui.py` — import `PALETTE_BAR_HEIGHT` from `config` instead of
  defining it (re-export preserved so `test_ui.py` is unaffected).
- `src/sandfall/game.py` — `_draw` scales the grid surface to
  `(WINDOW_WIDTH, SIM_AREA_HEIGHT)` (was `(WINDOW_WIDTH, WINDOW_HEIGHT)`).
- `tests/test_ui.py` — add the geometry-invariant assertion; existing tests
  need no changes (they use the constants, which auto-adapt — verify).
- `README.md` — update the "200 x 150 grid (800 x 600 window)" line to 200 x 140.
- `docs/ARCHITECTURE.md` — geometry section: grid no longer fills the window;
  palette is the sim floor.

## Implementation Instructions

> Re-read each file before editing — line numbers are current as of the v1
> source plus Phase 01's additions and will have shifted.

### 1. `src/sandfall/config.py`

**1a. Relocate `PALETTE_BAR_HEIGHT`.** Currently defined in `ui.py:40` as
`PALETTE_BAR_HEIGHT = PALETTE_SWATCH + 2 * PALETTE_MARGIN`. Move that
definition into `config.py` (it depends only on `PALETTE_SWATCH` and
`PALETTE_MARGIN`, which already live in `config.py` lines 45-47). Place it in
the UI section, right after the `PALETTE_*` constants (around line 47):

```python
# Height of the reserved bottom palette strip. Derived from the swatch size +
# a margin top and bottom so swatches are visually centered. Lives in config
# (not ui.py) so the grid geometry below can derive from it in one place.
PALETTE_BAR_HEIGHT = PALETTE_SWATCH + 2 * PALETTE_MARGIN  # 24 + 16 == 40
```

**1b. Add `SIM_AREA_HEIGHT` and recompute `GRID_HEIGHT`.** In the Window/grid
geometry section (lines 16-21), change the grid derivation. The new block:

```python
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
CELL_SIZE = 4  # pixels per side of one simulation cell

# The simulation occupies only the pixels ABOVE the palette bar (the palette
# is the sim floor, not an overlay). The grid's bottom pixel row lands exactly
# on the palette's top edge so elements pile ON the bar, never behind it.
SIM_AREA_HEIGHT = WINDOW_HEIGHT - PALETTE_BAR_HEIGHT  # 600 - 40 == 560

GRID_WIDTH = WINDOW_WIDTH // CELL_SIZE   # 200
GRID_HEIGHT = SIM_AREA_HEIGHT // CELL_SIZE  # 560 // 4 == 140
```

Update the comment block at lines 11-15 that says "800 / 4 == 200, 600 / 4 ==
150" to reflect 140 and the palette-floor relationship.

> **Note on ordering:** `PALETTE_BAR_HEIGHT` is now used at line ~21
> (`SIM_AREA_HEIGHT`) but defined lower down in the UI section. Python module
> execution is top-to-bottom, so `PALETTE_BAR_HEIGHT` MUST be defined BEFORE
> `SIM_AREA_HEIGHT`. Simplest fix: move the `PALETTE_BAR_HEIGHT` definition
> UP into the geometry section (right after `CELL_SIZE`), since
> `PALETTE_SWATCH`/`PALETTE_MARGIN` must also then be defined before it. Either
> (a) move `PALETTE_SWATCH`, `PALETTE_PADDING`, `PALETTE_MARGIN`,
> `PALETTE_BAR_HEIGHT` all to the top geometry section, or (b) keep them in the
> UI section and move the `WINDOW_*`/`SIM_AREA_HEIGHT`/`GRID_*` block below
> them. Recommended: **(a)** — group ALL geometry constants together at the top
> (window, cell, palette bar, sim area, grid dims), then colors, then loop/brush
> constants. This keeps the derivation chain in reading order and is what Phase
> 03 (which adds `MIN_WINDOW_*` and `compute_grid_dims`) will expect.

### 2. `src/sandfall/ui.py`

**2a. Remove the local `PALETTE_BAR_HEIGHT` definition** (line 40) — it now
lives in `config.py`.

**2b. Import it back** from config by adding `PALETTE_BAR_HEIGHT` to the
existing `from .config import (...)` block (lines 20-30). This keeps
`sandfall.ui.PALETTE_BAR_HEIGHT` resolvable, so `test_ui.py`'s
`from sandfall.ui import PALETTE_BAR_HEIGHT, ...` (line 18) continues to work
unchanged.

> Nothing else in `ui.py` changes: `UI.__init__` computes
> `self._bar_y = window_height - PALETTE_BAR_HEIGHT` (line 104) — unchanged
> and still == 560. `in_reserved_area` (lines 119-125) — unchanged. The
> palette already renders exactly at `bar_y`, which now equals the grid's
> bottom edge.

### 3. `src/sandfall/game.py`

**3a. `_draw` scale target (line 173).** Change from scaling to the full
window to scaling to the sim-area height:

```python
# Before:
scaled = pygame.transform.scale(small, (WINDOW_WIDTH, WINDOW_HEIGHT))
# After:
scaled = pygame.transform.scale(small, (WINDOW_WIDTH, SIM_AREA_HEIGHT))
```

Add `SIM_AREA_HEIGHT` to the `from .config import (...)` block (lines 33-44).
The `self._screen.fill(BG_COLOR)` at line 171 still fills the whole 600px
window, so the 40px palette region gets `BG_COLOR` and is then overdrawn by
`UI.draw`'s semi-transparent bar — unchanged behavior, correct result. Blit
target stays `(0, 0)`.

> The `Grid(GRID_WIDTH, GRID_HEIGHT)` at line 91 picks up the new `GRID_HEIGHT`
  (140) automatically — no edit needed there.

### 4. `tests/test_ui.py`

**4a. Add the geometry-invariant test** (this is the core correctness
assertion for the phase):

```python
def test_grid_height_makes_palette_top_the_sim_floor() -> None:
    """The grid's bottom pixel row lands exactly on the palette's top edge.

    GRID_HEIGHT * CELL_SIZE == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT, so the
    grid spans only the area above the palette (elements pile ON the bar).
    """
    from sandfall.config import CELL_SIZE, GRID_HEIGHT

    assert GRID_HEIGHT * CELL_SIZE == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT
    assert GRID_HEIGHT * CELL_SIZE == 560  # == UI bar_y at 800x600
```

**4b. Verify existing tests still pass unchanged.** They reference
`WINDOW_WIDTH`/`WINDOW_HEIGHT`/`PALETTE_BAR_HEIGHT` (constants) and
`bar_y == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT` (still 560), so they should be
unaffected. If any test hardcoded `150`, update it — but per the grep at
planning time, none do. Run the suite and confirm.

### 5. `tests/test_renderer.py` (verify, likely no change)

The session fixture at line 36 calls
`pygame.display.set_mode((GRID_WIDTH, GRID_HEIGHT))` and the render-size test
(line 89-95) uses `GRID_WIDTH`/`GRID_HEIGHT`. Both auto-adapt to the new
`GRID_HEIGHT == 140`. No edit expected; confirm the suite is green.

### 6. `README.md`

Line 26-27 currently says "The simulation runs at a fixed 60 FPS over a 200 x
150 grid (an 800 x 600 window with 4 x 4 pixel cells)." Update to:

> The simulation runs at a fixed 60 FPS over a 200 x 140 grid — an 800 x 560
> playfield (an 800 x 600 window with a 40px palette bar at the bottom and
> 4 x 4 pixel cells). Elements pile up on top of the palette bar.

### 7. `docs/ARCHITECTURE.md`

**7a.** Line 49: "`array` — ... both shape `(height, width)` = `(150, 200)`"
→ change to `(140, 200)`.

**7b.** Lines 172-174 (the Rendering section): "`Game._draw` scales that
200 x 150 surface up to the 800 x 600 window" → update to "scales that
200 x 140 surface up to the 800 x 560 playfield (the 800 x 600 window minus
the 40px palette bar); the palette bar is then drawn over the bottom 40px."

**7c.** Add a short note in the geometry area that the palette bar is the
simulation floor (the grid spans only the area above it), replacing any
language implying the grid fills the whole window.

## Acceptance Criteria

- [ ] `GRID_HEIGHT == 140` and `SIM_AREA_HEIGHT == 560`.
- [ ] `GRID_HEIGHT * CELL_SIZE == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT == 560`
      (invariant test passes).
- [ ] `PALETTE_BAR_HEIGHT` is defined in `config.py` and re-exported from
      `ui.py` (so `from sandfall.ui import PALETTE_BAR_HEIGHT` still works).
- [ ] `Game._draw` scales the grid surface to `(WINDOW_WIDTH, SIM_AREA_HEIGHT)`
      and blits at `(0, 0)`; the palette renders exactly at the grid's bottom
      edge (sand piles on the bar, not behind it — verify in the smoke run).
- [ ] `UI.bar_y == 560 == GRID_HEIGHT * CELL_SIZE`.
- [ ] All existing tests pass (no regressions); the new invariant test passes.
- [ ] Five gates + `SANDFALL_FRAMES=60` smoke all exit zero.

## Verification Commands

```bash
# Phase-specific (geometry invariant):
uv run pytest tests/test_ui.py tests/test_renderer.py -v
# And assert the key invariant directly:
uv run python -c "from sandfall.config import GRID_HEIGHT, CELL_SIZE, WINDOW_HEIGHT; from sandfall.ui import PALETTE_BAR_HEIGHT; assert GRID_HEIGHT*CELL_SIZE == WINDOW_HEIGHT-PALETTE_BAR_HEIGHT == 560; print('invariant ok')"

# The five gates (all must exit zero):
uv run python -c "import sandfall"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# Full SDL loop smoke — visually confirm sand piles ON the palette bar:
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
```

All commands must exit zero. Do NOT proceed to Phase 03 until all pass.

## Documentation Updates

- `README.md` — grid-dimension line (200 x 140 + palette-floor wording).
- `docs/ARCHITECTURE.md` — grid shape `(140, 200)`, rendering scale target,
  palette-as-floor note.

Both done as part of this phase's commit.

## Reflection & Commit

After implementation, write `02-palette-floor-reflection.md` in this
directory. Then make ONE atomic git commit covering all changes in this phase.

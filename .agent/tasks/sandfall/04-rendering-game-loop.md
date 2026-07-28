# Phase 04: Rendering & Game Loop (pygame-ce window)

## Objective

Bring the simulation on screen: a pygame-ce window that renders the grid to a `Surface` each frame (scaled by `CELL_SIZE`), lets the user paint the selected element with the mouse (left-click drag with a circular brush), runs the simulation at 60 FPS, and exits cleanly on window-close or ESC. This is the first phase where the game is *playable*.

## Depends On

Phase 02 (Grid, Simulation, ELEMENTS). Does NOT require Phase 03's full element set to render — but the window is only "fun" once Phase 03 lands. They are parallelizable because this phase touches entirely different files.

## Can Parallelize With

Phase 03 (element rules). Disjoint files: this phase = `renderer.py`, `game.py`, `__main__.py`, `config.py`; Phase 03 = `rules/*.py`, `elements.py`, tests. Merge conflict risk is essentially zero.

## Recommended Agent

@implementer

## Changes Required

- `src/sandfall/config.py` — NEW. Central tunables (window size, cell size, FPS, default element/brush).
- `src/sandfall/renderer.py` — NEW. `Renderer` converting `Grid` → `pygame.Surface`.
- `src/sandfall/game.py` — NEW. `Game` class with init + `run()` loop.
- `src/sandfall/__main__.py` — EDIT: `main()` instantiates `Game` and calls `.run()`.
- `tests/test_renderer.py` — NEW. Headless tests of color lookup / surface size (no display required).
- `tests/test_smoke.py` — may need update: `main()` no longer returns 0 without args; see instructions.

## Implementation Instructions

### `src/sandfall/config.py`

```python
"""Central configuration / tunables for sandfall."""

from __future__ import annotations

from .elements import ElementId

WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
CELL_SIZE = 4                       # pixels per cell -> 200 x 150 grid
FPS = 60

GRID_WIDTH = WINDOW_WIDTH // CELL_SIZE   # 200
GRID_HEIGHT = WINDOW_HEIGHT // CELL_SIZE # 150

DEFAULT_ELEMENT = ElementId.SAND
DEFAULT_BRUSH_RADIUS = 3

BG_COLOR = (10, 10, 14)             # window background (visible if grid smaller than window)
```

### `src/sandfall/renderer.py`

Convert the grid to a `pygame.Surface` each frame. Use `pygame.surfarray.make_surface` which expects a `(width, height, 3)` uint8 RGB array — so transpose the grid's `(height, width)` array and map IDs → colors via a precomputed lookup table.

```python
"""Render the simulation grid to a pygame Surface."""

from __future__ import annotations

import numpy as np
import pygame

from .config import CELL_SIZE, GRID_HEIGHT, GRID_WIDTH
from .elements import ELEMENTS, ElementId
from .grid import Grid


def _build_color_lut() -> np.ndarray:
    """LUT: element id (0..max) -> (r, g, b) uint8."""
    lut = np.zeros((len(ElementId), 3), dtype=np.uint8)
    for eid, el in ELEMENTS.items():
        lut[int(eid)] = el.color
    return lut


class Renderer:
    """Converts a Grid into a scaled pygame Surface each frame."""

    def __init__(self) -> None:
        self._lut = _build_color_lut()
        # cell-sized surface (GRID_WIDTH x GRID_HEIGHT), scaled up per-frame.
        self._cell_surface = pygame.Surface((GRID_WIDTH, GRID_HEIGHT))

    def render(self, grid: Grid) -> pygame.Surface:
        """Return a window-sized Surface depicting the grid."""
        # grid.array is (height, width) uint8 of ids.
        ids = grid.array                         # (H, W)
        rgb = self._lut[ids]                      # (H, W, 3)
        # surfarray wants (W, H, 3)
        rgb_t = np.transpose(rgb, (1, 0, 2))      # (W, H, 3)
        pygame.surfarray.blit_array(self._cell_surface, rgb_t)
        # scale up to window size
        scaled = pygame.transform.scale(
            self._cell_surface, (GRID_WIDTH * CELL_SIZE, GRID_HEIGHT * CELL_SIZE)
        )
        return scaled
```

Notes:
- `pygame.transform.scale` (not `smoothscale`) — nearest-neighbor keeps the crisp pixel look. `smoothscale` would blur.
- Build the LUT once; do not allocate per frame.
- If `pygame.surfarray.blit_array` raises about pixel format, call `self._cell_surface = self._cell_surface.convert()` after `pygame.display.set_mode`. Keep a flag to convert lazily on first render (the display must be initialized first).

### `src/sandfall/game.py`

```python
"""The interactive game loop."""

from __future__ import annotations

import pygame

from .config import (
    BG_COLOR, CELL_SIZE, DEFAULT_BRUSH_RADIUS, DEFAULT_ELEMENT, FPS,
    GRID_HEIGHT, GRID_WIDTH, WINDOW_HEIGHT, WINDOW_WIDTH,
)
from .elements import ElementId
from .grid import Grid
from .renderer import Renderer
from .simulation import Simulation


class Game:
    def __init__(self) -> None:
        pygame.init()
        self._screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Sandfall")
        self._clock = pygame.time.Clock()
        self._grid = Grid(GRID_WIDTH, GRID_HEIGHT)
        self._sim = Simulation(self._grid)
        self._renderer = Renderer()
        self._selected: ElementId = DEFAULT_ELEMENT
        self._brush_radius: int = DEFAULT_BRUSH_RADIUS
        self._running = False

    def run(self) -> int:
        self._running = True
        while self._running:
            self._handle_events()
            self._paint_if_dragging()
            self._sim.step()
            self._screen.fill(BG_COLOR)
            self._screen.blit(self._renderer.render(self._grid), (0, 0))
            pygame.display.flip()
            self._clock.tick(FPS)
        pygame.quit()
        return 0

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._running = False

    def _paint_if_dragging(self) -> None:
        if pygame.mouse.get_pressed()[0]:  # left button held
            mx, my = pygame.mouse.get_pos()
            gx, gy = mx // CELL_SIZE, my // CELL_SIZE
            self._grid.fill_circle(gx, gy, self._brush_radius, self._selected)
```

Design notes:
- Painting happens every frame the left button is held (continuous brush), not only on `MOUSEBUTTONDOWN` — feels better.
- ESC and the window close button both quit cleanly; `pygame.quit()` runs in all exit paths so there's no orphaned SDL window.
- The selected element & brush radius are instance state here so Phase 05 (UI) can mutate them without restructuring. Keep these as attributes (not locals).

### `src/sandfall/__main__.py` — EDIT

Replace the stub `main()`:

```python
"""Entry point for the ``sandfall`` console script."""

__all__ = ["main"]


def main() -> int:
    from .game import Game

    return Game().run()


if __name__ == "__main__":
    raise SystemExit(main())
```

The `from .game import Game` is inside `main()` (lazy) so that importing the package (e.g. in tests, where there's no display) does NOT import pygame or open a window. Keep it lazy.

### `tests/test_smoke.py` — handle the lazy import

The Phase 01 test `test_main_returns_zero` calls `main()` which now opens a window — that will hang/fail in CI. **Replace** that test with one that asserts `main` is callable and is lazy (does not import `pygame` at module import time):

```python
def test_main_is_callable_and_lazy() -> None:
    import sys
    # Ensure pygame is not imported just by importing sandfall.__main__
    assert "pygame" not in sys.modules
    from sandfall.__main__ import main
    assert callable(main)
    # Do NOT call main() here — it opens a window.
```

Add a `tests/conftest.py` if you need a `pygame`-dummy fixture, but for now the lazy-import check is sufficient and keeps tests headless.

### `tests/test_renderer.py` (headless)

`pygame` can be imported without a display if you call `pygame.init()` carefully — but `pygame.surfarray` may need numpy + a video driver. For headless unit tests, test the **color LUT** and the **grid→RGB mapping** logic by extracting it into a pure function (no Surface) and testing that:

- `_build_color_lut()` returns shape `(len(ElementId), 3)` with SAND's row equal to SAND's color.
- A pure helper `grid_to_rgb(grid) -> np.ndarray` (extract from `render` for testability) returns `(H, W, 3)` with the right colors for a known small grid.

Refactor `renderer.py` so the numpy mapping is a standalone pure function `grid_to_rgb(grid, lut)` that `render()` calls. Test THAT. Do not instantiate a `Renderer` (or pygame display) in unit tests.

## Acceptance Criteria

- [ ] `src/sandfall/config.py`, `src/sandfall/renderer.py`, `src/sandfall/game.py` exist per spec.
- [ ] `__main__.main()` lazily imports `Game` (no pygame import at package import time).
- [ ] `uv run sandfall` opens an 800×600 window titled "Sandfall".
- [ ] **MANUAL**: left-click-drag paints sand (default element) that visibly falls and piles; ESC or window-close exits cleanly; no Python traceback in the console.
- [ ] Grid→RGB mapping is extracted into a pure, headless-testable function.
- [ ] All automated verification gates pass (including the updated `test_smoke.py` that does NOT open a window).

## Verification Commands

```bash
# Automated gates (all must exit zero):
uv run python -c "import sandfall; import sys; assert 'pygame' not in sys.modules; print('lazy ok')"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
```

Manual gate (cannot be automated in this environment — the implementer runs it locally and checks the box):
```bash
uv run sandfall
# -> window opens; paint sand with left-drag; watch it fall & pile; press ESC to quit.
```

ALL automated gates must exit zero before Phase 05.

## Documentation Updates

- Update `AGENTS.md` `## Commands` section is already correct (`uv run sandfall`); no change needed unless a new flag is added.
- Write `.agent/tasks/sandfall/04-rendering-game-loop-reflection.md`. Note: the lazy-import strategy, the `grid_to_rgb` extraction for headless testing, and any pygame-ce-specific quirks encountered (e.g. surfarray pixel format / `convert()` ordering).

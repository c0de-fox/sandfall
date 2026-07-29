"""Central configuration / tunables for sandfall.

All window, grid, and default-state constants live here so Phase 05 (UI)
and Phase 06 (packaging) can import them from a single place.
"""

from __future__ import annotations

from .elements import ElementId

# --- Window / grid geometry -------------------------------------------------
# The grid is derived from the window size and a fixed cell size so that one
# simulation cell maps to a CELL_SIZE x CELL_SIZE square of pixels exactly
# (800 / 4 == 200, 600 / 4 == 150 -> no leftover pixels). Changing CELL_SIZE
# here is the single knob that trades resolution for performance.
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
CELL_SIZE = 4  # pixels per side of one simulation cell -> 200 x 150 grid

GRID_WIDTH = WINDOW_WIDTH // CELL_SIZE  # 200
GRID_HEIGHT = WINDOW_HEIGHT // CELL_SIZE  # 150

# --- Loop -------------------------------------------------------------------
FPS = 60

# --- Brush / element defaults (Phase 05 will let the user mutate these) -----
DEFAULT_ELEMENT = ElementId.SAND
DEFAULT_BRUSH_RADIUS = 3

# --- Colors -----------------------------------------------------------------
# Window background. EMPTY cells render as this color (see renderer.build_color_lut),
# so the simulation area visually blends with the surrounding window if the grid
# ever fails to exactly fill it.
BG_COLOR: tuple[int, int, int] = (10, 10, 14)

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

# --- UI (Phase 05) ----------------------------------------------------------
# Element palette lives in a reserved strip at the bottom of the window. The
# strip is [PALETTE_BAR_HEIGHT] px tall where the bar height is derived below
# from the swatch size + margins so the swatches sit visually centered. The
# playfield grid still renders behind the strip; painting is suppressed while
# the cursor is inside the reserved strip (see UI.in_reserved_area) so the user
# never accidentally paints "under" the palette.
PALETTE_BG: tuple[int, int, int, int] = (0, 0, 0, 180)
# ^ semi-transparent black bar (RGBA) behind the palette swatches.
PALETTE_SWATCH = 24  # px size of each palette swatch (square)
PALETTE_PADDING = 4  # px between swatches
PALETTE_MARGIN = 8  # px margin around the palette strip / swatches
BRUSH_MIN = 1
BRUSH_MAX = 20
FPS_COLOR: tuple[int, int, int] = (255, 255, 0)  # yellow FPS / brush readout, top-left
HIGHLIGHT_COLOR: tuple[int, int, int] = (255, 255, 255)  # active-swatch border
PAUSED_COLOR: tuple[int, int, int] = (255, 80, 80)  # red "PAUSED" indicator

# Eraser swatch visual. EMPTY's registered color is (0, 0, 0) (invisible on the
# dark palette bar), so the Eraser swatch is rendered with a distinct fill +
# border + an "E" glyph (the font is already lazily created in UI.draw).
ERASER_SWATCH_COLOR: tuple[int, int, int] = (180, 180, 180)  # light-gray fill
ERASER_SWATCH_BORDER: tuple[int, int, int] = (90, 90, 90)  # darker border
ERASER_LABEL = "E"  # single-character glyph rendered centered in the swatch

FONT_NAME: str | None = None  # None -> pygame's bundled default font
FONT_SIZE = 16


def clamp_brush_radius(radius: int) -> int:
    """Clamp the brush radius into the inclusive range ``[BRUSH_MIN, BRUSH_MAX]``.

    Extracted as a pure helper so the scroll-wheel handler and its test share
    one definition of the bounds.
    """
    return max(BRUSH_MIN, min(BRUSH_MAX, radius))

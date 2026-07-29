"""Central configuration / tunables for sandfall.

All window, grid, and default-state constants live here so Phase 05 (UI)
and Phase 06 (packaging) can import them from a single place.
"""

from __future__ import annotations

from .elements import ElementId

# --- Window / grid geometry -------------------------------------------------
# All pixel/cell geometry derives from a small chain of constants here so the
# whole layout has a single source of truth. The window is RESIZABLE, so the
# INITIAL_WINDOW_* constants below are only the *starting* size; the current
# size lives as Game instance state and is converted to grid dims at runtime
# by compute_grid_dims (see the bottom of this module). The simulation
# occupies only the pixels ABOVE the palette bar (the palette is the sim
# floor, not an overlay): the grid's bottom pixel row lands exactly on the
# palette's top edge so elements pile ON the bar, never behind it. Changing
# CELL_SIZE here is the single knob that trades resolution for performance.
INITIAL_WINDOW_W = 800  # starting window width (the window is resizable)
INITIAL_WINDOW_H = 600  # starting window height (the window is resizable)
CELL_SIZE = 4  # pixels per side of one simulation cell

# Palette bar geometry (size of the reserved bottom strip drawn by the UI).
PALETTE_SWATCH = 24  # px size of each palette swatch (square)
PALETTE_PADDING = 4  # px between swatches
PALETTE_MARGIN = 8  # px margin around the palette strip / swatches

# Height of the reserved bottom palette strip. Derived from the swatch size +
# a margin top and bottom so swatches are visually centered. Lives in config
# (not ui.py) so the grid geometry below can derive from it in one place.
PALETTE_BAR_HEIGHT = PALETTE_SWATCH + 2 * PALETTE_MARGIN  # 24 + 16 == 40

# The simulation occupies only the pixels ABOVE the palette bar. At the
# default 800x600 window the grid's bottom pixel row lands exactly on the
# palette's top edge (== 560) so falling elements rest on top of the bar.
SIM_AREA_HEIGHT = INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT  # 600 - 40 == 560

GRID_WIDTH = INITIAL_WINDOW_W // CELL_SIZE  # 800 // 4 == 200  (initial cols)
GRID_HEIGHT = SIM_AREA_HEIGHT // CELL_SIZE  # 560 // 4 == 140  (initial rows)

# Minimum window size used to DERIVE the minimum grid cell counts below. Width
# must fit the whole palette (8 swatches incl. the Eraser: 8*24 + 7*4 + 2*8 ==
# 236px) with margin -> 256. Height must fit the 40px palette + a usable sim
# area (>= 40 cells == 160px) -> 200. The window itself is NOT clamped to these
# (clamping the window pixels fights the compositor on Wayland -- see
# Game._handle_resize); instead compute_grid_dims floor-clamps the GRID cols/
# rows to MIN_GRID_* so a tiny window still has a usable grid.
MIN_WINDOW_W = 256
MIN_WINDOW_H = 200
MIN_GRID_COLS = MIN_WINDOW_W // CELL_SIZE  # 256 // 4 == 64
MIN_GRID_ROWS = (MIN_WINDOW_H - PALETTE_BAR_HEIGHT) // CELL_SIZE  # 160 // 4 == 40

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
# strip is PALETTE_BAR_HEIGHT px tall (defined above with the rest of the
# geometry); the grid renders only in the pixels above it, and painting is
# suppressed while the cursor is inside the reserved strip (see
# UI.in_reserved_area) so the user never accidentally paints "under" the palette.
PALETTE_BG: tuple[int, int, int, int] = (0, 0, 0, 180)
# ^ semi-transparent black bar (RGBA) behind the palette swatches.
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


def compute_grid_dims(window_w: int, window_h: int) -> tuple[int, int]:
    """Compute ``(cols, rows)`` for a window of the given pixel size.

    Cells stay square at ``CELL_SIZE``: cols/rows are floor-divided so the
    grid is the largest whole-cell multiple that fits; leftover pixels (when
    the window isn't an exact multiple) are filled with ``BG_COLOR`` by the
    renderer. Rows exclude the fixed palette bar pinned to the bottom.
    Both dimensions are clamped to a minimum cell count (``MIN_GRID_COLS`` /
    ``MIN_GRID_ROWS``) so an aggressively shrunk window still has a usable
    grid and the palette always fits.

    Pure / pygame-free -> unit-tested headlessly. Called by ``Game`` on the
    initial window and on every ``VIDEORESIZE``.
    """
    cols = max(MIN_GRID_COLS, window_w // CELL_SIZE)
    rows = max(MIN_GRID_ROWS, (window_h - PALETTE_BAR_HEIGHT) // CELL_SIZE)
    return cols, rows

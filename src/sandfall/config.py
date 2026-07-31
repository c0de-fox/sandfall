"""Central configuration / tunables for sandfall.

All window, grid, and default-state constants live here so Phase 05 (UI)
and Phase 06 (packaging) can import them from a single place.
"""

from __future__ import annotations

from .elements import AMBIENT_TEMP, TEMP_MAX, TEMP_MIN, ElementId

# Re-export the temperature-band constants so callers that already import
# from config see them here too. The canonical definitions live at the top of
# elements.py (NOT here) to keep a one-way dependency: config -> elements.
# elements.py must not import from config (config imports ElementId from
# elements above), so defining the temp band in elements avoids the
# circular-import loop.
#
# ``__all__`` is required here because mypy is in strict mode
# (``no_implicit_reexport``) and ruff's F401 would otherwise flag these three
# names as unused imports; both tools honor ``__all__`` as the explicit
# re-export marker — the same pattern already used in ``rules/__init__.py``.
# Listing ONLY these three re-exported names is intentional: every other name
# in this module is DEFINED here (so mypy treats it as exported automatically).
# Nothing in the tree uses ``from config import *`` (config has 30+ names;
# star-importing it was never intended), so narrowing star-exports to these
# three is purely theoretical and is the documented re-export surface.
__all__ = [
    "AMBIENT_TEMP",
    "TEMP_MAX",
    "TEMP_MIN",
]

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

# Extra space inserted between the element group and the utility group (Eraser /
# Brush-shape / Magnifier) in the single bottom row, ON TOP of the normal
# PALETTE_PADDING. Visually separates elements (swatches) from tools. Drives the
# MIN_WINDOW_W math below and the layout boundary in ui.palette_layout.
PALETTE_GROUP_GAP = 3 * PALETTE_PADDING  # 12

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

# Minimum window size. Width must fit the whole palette (14 items: 11 element
# swatches + Eraser + Brush-shape + Magnifier). Width math:
#   14 * PALETTE_SWATCH + 13 * PALETTE_PADDING + PALETTE_GROUP_GAP + 2 * PALETTE_MARGIN
#   = 14*24 + 13*4 + 12 + 2*8 = 336 + 52 + 12 + 16 = 416  (== 104 * CELL_SIZE)
# 416 is the next clean CELL_SIZE multiple above the needed 416, = 104 cols.
# Height must fit the 40px palette + a usable sim area (>= 40 cells == 160px)
# -> 200. The minimum is enforced by the compositor via Window.minimum_size
# (see Game.__init__); compute_grid_dims additionally floor-clamps the GRID
# cols/rows to MIN_GRID_* so a tiny window still has a usable grid.
MIN_WINDOW_W = 416
MIN_WINDOW_H = 200
MIN_GRID_COLS = MIN_WINDOW_W // CELL_SIZE  # 416 // 4 == 104
MIN_GRID_ROWS = (MIN_WINDOW_H - PALETTE_BAR_HEIGHT) // CELL_SIZE  # 160 // 4 == 40

# --- Loop -------------------------------------------------------------------
FPS = 60

# --- Temperature field (Phase 01) ------------------------------------------
# Per-cell temperature, integer degrees-C-like, stored as int16 on Grid.
# AMBIENT_TEMP is the resting temperature every cell initializes to and that
# fill_circle resets to (mirrors how it zeroes life). The clip band is wide
# enough for sand melting (~1700) and sub-zero freezing; int16 headroom is huge.
# (AMBIENT_TEMP / TEMP_MIN / TEMP_MAX are defined at the top of elements.py and
# re-exported here — see the import block above.)

# Diffusion pre-pass tunables. diffuse_temps now uses a CONSERVATIVE face-flux
# (finite-volume) discretization with per-cell heat capacity:
#     flux across each interior face = k_face * rate * (t_left - t_right)
#     k_face = (cond[left] + cond[right]) / 2      (arithmetic mean)
#     new_t  = t + (net signed face flux into the cell) / cp[cell]
# The signed face fluxes telescope to zero over the grid, so total heat
# sum(cp*temp) is CONSERVED up to rounding/clip. The form reduces to standard
# explicit diffusion with coefficient rate*k/cp, so the stability bound is
#     rate * max(cond) / min(cp) <= 0.25
# With the defaults below: 0.20 * 0.50 (FIRE) / 0.5 (FIRE/SMOKE/STEAM) = 0.20
# <= 0.25 — comfortable. diffuse_temps additionally clips to [TEMP_MIN, TEMP_MAX].
DIFFUSION_RATE = 0.20

# Per-material heat conductivity (0.0 = perfect insulator, 1.0 = max). Indexed
# by element id via build_conductivity_lut(). EMPTY is given a small non-zero
# value so heat propagates through air (otherwise fire could not warm fuel it
# is not adjacent to); high-conductivity materials (FIRE, metals) equilibrate
# fast, insulators (STONE) equilibrate slowly.
COND_EMPTY = 0.10
COND_SAND = 0.15
COND_WATER = 0.35
COND_STONE = 0.08
COND_WOOD = 0.12
COND_FIRE = 0.50
COND_SMOKE = 0.20
COND_PLANT = 0.12
# Phase 03 new materials.
COND_STEAM = 0.25
COND_ICE = 0.18
COND_LAVA = 0.45
COND_GLASS = 0.10

# Per-material heat capacity (thermal inertia / thermal mass). Divides the
# temperature change in diffuse_temps: high cp = changes slowly = thermally
# massive (water/stone/lava); low cp = changes fast (gases); EMPTY (air) is the
# 1.0 baseline. Indexed by element id via build_heat_capacity_lut(). Every
# value is > 0 (diffusion divides by cp).
CP_EMPTY = 1.0  # air = baseline thermal mass
CP_SAND = 1.5
CP_WATER = 4.0  # high thermal mass (water heats/cools slowly)
CP_STONE = 2.0
CP_WOOD = 1.5
CP_FIRE = 0.5  # low mass (gas-like; changes fast)
CP_SMOKE = 0.5
CP_PLANT = 1.5
# Phase 03 new materials.
CP_STEAM = 0.5
CP_ICE = 2.0
CP_LAVA = 5.0  # VERY high thermal mass — lava persists (solidifies ~step 27)
CP_GLASS = 1.5

# --- Heat-overlay display band (Phase 04) -----------------------------------
# ``thermal.thermal_to_rgb`` maps the temp field's full color span across
# ``[HEAT_VIZ_COLD, HEAT_VIZ_HOT]``; temperatures outside the band saturate to
# the endpoint color (deep blue / red). The band is deliberately asymmetric
# around AMBIENT_TEMP (20): the interesting *hot* behavior (fire ~800, lava
# ~1500) spans a much wider range than the cold behavior (ice / sub-zero), so
# the hot side gets more of the color ramp. AMBIENT_TEMP is the neutral pivot
# of the gradient on BOTH sides, so an all-ambient scene reads as a flat
# 'no thermal activity' gray rather than a tinted one.
HEAT_VIZ_COLD = -40
HEAT_VIZ_HOT = 1000

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
    initial window and whenever a window-size change is detected (polled once
    per frame against ``Window.size``).
    """
    cols = max(MIN_GRID_COLS, window_w // CELL_SIZE)
    rows = max(MIN_GRID_ROWS, (window_h - PALETTE_BAR_HEIGHT) // CELL_SIZE)
    return cols, rows

"""The interactive game loop.

:class:`Game` owns the pygame window, the :class:`Simulation`, the
:class:`Renderer`, the brush state (selected element + radius), the
:class:`~sandfall.ui.UI` overlay, and the pause/step
:class:`~sandfall.control.LoopController`. The loop runs at a fixed ``FPS``
and:

* pumps events (QUIT / ESC stop the loop; SPACE pauses; N single-steps while
  paused; mouse wheel resizes the brush; left-click on the palette selects an
  element),
* paints the selected element wherever the left mouse button is held *outside
  the palette strip* (the :func:`~sandfall.brush.paint_brush` helper seeds
  per-cell life for FIRE/SMOKE so painted fire actually burns),
* steps the simulation one tick unless paused (a requested single step still
  advances it),
* renders + scales the grid to the window, blits the UI overlay, and flips.

A testing seam: when the ``SANDFALL_FRAMES`` environment variable is set to a
positive integer, the loop runs exactly that many frames and then exits
cleanly (returns 0). This lets automated checks run the full SDL init ->
render -> step -> teardown path without a human driving the window. It is read
once at the start of :meth:`run`.
"""

from __future__ import annotations

import os

import pygame

from .brush import paint_brush
from .config import (
    BG_COLOR,
    CELL_SIZE,
    DEFAULT_BRUSH_RADIUS,
    DEFAULT_ELEMENT,
    FPS,
    GRID_HEIGHT,
    GRID_WIDTH,
    INITIAL_WINDOW_H,
    INITIAL_WINDOW_W,
    MIN_WINDOW_H,
    MIN_WINDOW_W,
    clamp_brush_radius,
    compute_grid_dims,
)
from .control import LoopController
from .elements import ElementId
from .grid import Grid, migrate_grid
from .renderer import Renderer
from .simulation import Simulation
from .ui import UI


def _parse_frame_cap() -> int | None:
    """Read ``SANDFALL_FRAMES`` once and return a positive frame cap or None.

    A missing or unparseable value disables the cap (run until the user quits).
    A non-positive value is treated as no cap so the game is still playable if
    someone exports ``SANDFALL_FRAMES=0``.
    """
    raw = os.environ.get("SANDFALL_FRAMES")
    if raw is None:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


class Game:
    """Top-level controller wiring input, simulation, and rendering together."""

    _screen: pygame.Surface
    _window: pygame.Window
    _clock: pygame.time.Clock
    _grid: Grid
    _sim: Simulation
    _renderer: Renderer
    _ui: UI
    _loop: LoopController
    # Brush state is public-read/owner-write so external drivers (and tests)
    # can mutate it directly.
    selected_element: ElementId
    brush_radius: int
    _running: bool
    # Current window size in pixels (starts at INITIAL_*; updated on resize).
    _window_w: int
    _window_h: int

    def __init__(self) -> None:
        pygame.init()
        # Use the modern pygame.Window API (pygame-ce 2.5.2+) instead of
        # pygame.display.set_mode(): the Window is created ONCE and
        # get_surface() returns a surface that "will change size with the
        # Window" (per the pygame-ce stubs), so a resize never destroys /
        # recreates the display surface. The classic set_mode() API closes
        # the previous display on every call, which is what produced the
        # resize flicker (the window vanished and reappeared on each
        # VIDEORESIZE). The compositor enforces the minimum size via
        # window.minimum_size, replacing the old manual clamp.
        self._window = pygame.Window(
            "Sandfall",
            size=(INITIAL_WINDOW_W, INITIAL_WINDOW_H),
            resizable=True,
        )
        self._window.minimum_size = (MIN_WINDOW_W, MIN_WINDOW_H)
        self._screen = self._window.get_surface()
        self._clock = pygame.time.Clock()
        self._grid = Grid(GRID_WIDTH, GRID_HEIGHT)
        self._sim = Simulation(self._grid)
        self._renderer = Renderer()
        self._ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)
        self._loop = LoopController()
        self.selected_element = DEFAULT_ELEMENT
        self.brush_radius = DEFAULT_BRUSH_RADIUS
        self._running = False
        self._window_w = INITIAL_WINDOW_W
        self._window_h = INITIAL_WINDOW_H

    def run(self) -> int:
        """Run the main loop until QUIT/ESC or the ``SANDFALL_FRAMES`` cap.

        Always tears pygame down before returning so no SDL window is left
        orphaned. Returns 0.
        """
        frame_cap = _parse_frame_cap()
        self._running = True
        frame = 0
        try:
            while self._running:
                self._handle_events()
                self._paint_if_dragging()
                self._erase_if_dragging()
                if self._loop.consume_step():
                    self._sim.step()
                self._apply_resize_if_changed()
                self._draw()
                self._window.flip()
                self._clock.tick(FPS)
                frame += 1
                if frame_cap is not None and frame >= frame_cap:
                    self._running = False
        finally:
            pygame.quit()
        return 0

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._running = False
                elif event.key == pygame.K_SPACE:
                    self._loop.toggle_pause()
                elif event.key == pygame.K_n:
                    self._loop.request_step()
            elif event.type == pygame.MOUSEWHEEL:
                # event.y is +1 for scroll-up, -1 for scroll-down (pygame-ce).
                # Scroll-up grows the brush.
                self.brush_radius = clamp_brush_radius(self.brush_radius + event.y)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Only button 1 (left) selects; right-click erases (see
                # _erase_if_dragging) and must NOT select. The guard above
                # (`event.button == 1`) enforces that — a right-click (button 3)
                # falls through this whole elif without selecting a swatch.
                # A left-click inside a swatch selects that element and must
                # NOT also paint. Selection only happens on button-down; the
                # subsequent paint-this-frame is suppressed because the cursor
                # is still inside the reserved palette strip (see
                # _paint_if_dragging).
                mx, my = event.pos
                sel = self._ui.swatch_at(mx, my)
                if sel is not None:
                    self.selected_element = sel
            # NOTE: no VIDEORESIZE branch. Window resize is detected by polling
            # self._window.size every frame in _apply_resize_if_changed(); that
            # path is event-driver-independent and never recreates the window
            # (the pygame.Window API does not need a set_mode call on resize).

    def _apply_resize_if_changed(self) -> None:
        """Detect the window has resized and rebuild the grid + UI to match.

        Polled once per frame from :meth:`run` (not driven by a resize event),
        because the pygame.Window API auto-tracks the window size in its
        ``get_surface()`` surface — there is no ``set_mode`` call to make and
        no event to acknowledge. Comparing ``self._window.size`` against the
        last size we built for is event-driver-independent and robust on both
        Wayland and X11.

        The grid's minimum cell count is enforced by
        :func:`compute_grid_dims`; the window's minimum pixel size is enforced
        by the compositor via ``Window.minimum_size`` (set in ``__init__``),
        so no manual clamp is needed here. Cells stay square (floor snap);
        leftover pixels are ``BG_COLOR``. The palette bar stays a fixed
        ``PALETTE_BAR_HEIGHT`` pinned to the bottom. Content outside the
        overlapping region is lost permanently (see :func:`migrate_grid`).
        """
        w, h = self._window.size
        if (w, h) == (self._window_w, self._window_h):
            return
        cols, rows = compute_grid_dims(w, h)
        new_grid = Grid(cols, rows)
        migrate_grid(self._grid, new_grid)
        self._grid = new_grid
        self._sim = Simulation(self._grid)
        self._window_w, self._window_h = w, h
        # The get_surface() surface auto-tracks the window size; refresh our
        # reference so we render to the up-to-date surface this frame.
        self._screen = self._window.get_surface()
        self._ui.resize(w, h)

    def _paint_if_dragging(self) -> None:
        """Paint the selected element under the cursor while button 1 is held.

        Painting is suppressed while the cursor is inside the palette strip so
        the user can click/drag over swatches without painting beneath them.
        Continuous painting every frame (rather than only on MOUSEBUTTONDOWN)
        feels natural when dragging. The :func:`paint_brush` helper seeds
        per-cell life for FIRE/SMOKE so they do not expire instantly.
        """
        if not pygame.mouse.get_pressed()[0]:
            return
        mx, my = pygame.mouse.get_pos()
        if self._ui.in_reserved_area(mx, my):
            return
        gx, gy = mx // CELL_SIZE, my // CELL_SIZE
        paint_brush(self._grid, gx, gy, self.brush_radius, self.selected_element)

    def _erase_if_dragging(self) -> None:
        """Erase (paint EMPTY) under the cursor while the RIGHT button is held.

        Suppressed inside the palette strip, identical to left-button
        painting, so right-dragging over swatches does not erase beneath
        them. Right-click never selects a swatch (only button 1 does — see
        :meth:`_handle_events`). Runs every frame after
        :meth:`_paint_if_dragging`, so if both buttons are held, erase
        runs second and wins (acceptable edge case). The
        :func:`paint_brush` helper delegates to :meth:`Grid.fill_circle`,
        which clears the element id AND zeroes life on every painted cell.
        """
        if not pygame.mouse.get_pressed()[2]:
            return
        mx, my = pygame.mouse.get_pos()
        if self._ui.in_reserved_area(mx, my):
            return
        gx, gy = mx // CELL_SIZE, my // CELL_SIZE
        paint_brush(self._grid, gx, gy, self.brush_radius, ElementId.EMPTY)

    def _draw(self) -> None:
        # The grid renders to a (grid.width x grid.height) surface and is
        # scaled up to the grid's whole-cell pixel size; the screen is first
        # cleared to BG_COLOR so any leftover pixels (window not an exact
        # whole-cell multiple, or below the scaled grid) show the background.
        # After resize the grid dims derive from the current window size
        # (compute_grid_dims), so this redraws the entire scene every frame.
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

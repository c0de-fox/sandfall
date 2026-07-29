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
once at the start of :meth:`run.
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
        self._screen = pygame.display.set_mode(
            (INITIAL_WINDOW_W, INITIAL_WINDOW_H), pygame.RESIZABLE
        )
        pygame.display.set_caption("Sandfall")
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
                self._draw()
                pygame.display.flip()
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
            elif event.type == pygame.VIDEORESIZE:
                # The OS/window manager reports the new pixel size; clamp and
                # rebuild the grid + UI to match (see _handle_resize).
                self._handle_resize(event.w, event.h)

    def _handle_resize(self, raw_w: int, raw_h: int) -> None:
        """Acknowledge a window resize and rebuild the grid + UI to match.

        Accepts the compositor's configured size **verbatim** -- on Wayland the
        app must never request a different size (e.g. clamp to a minimum) or
        the compositor fights back and the window flickers / snaps instead of
        resizing. The grid's minimum cell count is enforced separately by
        :func:`compute_grid_dims`, so an aggressively small window still gets a
        usable grid while the window itself stays exactly what the user
        dragged. Cells stay square (floor snap); leftover pixels are
        ``BG_COLOR``. The palette bar stays a fixed ``PALETTE_BAR_HEIGHT``
        pinned to the bottom. Content outside the overlapping region is lost
        permanently (see :func:`migrate_grid`).
        """
        # No-op if nothing changed (also skips a redundant set_mode call).
        if (raw_w, raw_h) == (self._window_w, self._window_h):
            return
        w, h = raw_w, raw_h
        cols, rows = compute_grid_dims(w, h)
        new_grid = Grid(cols, rows)
        migrate_grid(self._grid, new_grid)
        self._grid = new_grid
        self._sim = Simulation(self._grid)
        self._window_w, self._window_h = w, h
        # Acknowledge the new size with the EXACT event pixels so the display
        # surface matches. Passing the exact size -- never a clamped/snapped
        # value -- is what keeps Wayland compositors from re-fighting the
        # resize (and we additionally prefer the X11 driver at startup on
        # Linux; see sandfall.__main__).
        self._screen = pygame.display.set_mode((w, h), pygame.RESIZABLE)
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

"""The interactive game loop.

:class:`Game` owns the pygame window, the :class:`Simulation`, the
:class:`Renderer`, and the brush state (selected element + radius). The loop
runs at a fixed ``FPS`` and:

* pumps events (QUIT / ESC stop the loop),
* paints the selected element wherever the left mouse button is held,
* steps the simulation one tick,
* renders + scales the grid to the window and flips.

A testing seam: when the ``SANDFALL_FRAMES`` environment variable is set to a
positive integer, the loop runs exactly that many frames and then exits
cleanly (returns 0). This lets automated checks run the full SDL init ->
render -> step -> teardown path without a human driving the window. It is read
once at the start of :meth:`run`.
"""

from __future__ import annotations

import os

import pygame

from .config import (
    BG_COLOR,
    CELL_SIZE,
    DEFAULT_BRUSH_RADIUS,
    DEFAULT_ELEMENT,
    FPS,
    GRID_HEIGHT,
    GRID_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from .elements import ElementId
from .grid import Grid
from .renderer import Renderer
from .simulation import Simulation


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
    # Brush state is public-read/owner-write so Phase 05 (UI) can mutate it.
    selected_element: ElementId
    brush_radius: int
    _running: bool

    def __init__(self) -> None:
        pygame.init()
        self._screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Sandfall")
        self._clock = pygame.time.Clock()
        self._grid = Grid(GRID_WIDTH, GRID_HEIGHT)
        self._sim = Simulation(self._grid)
        self._renderer = Renderer()
        self.selected_element = DEFAULT_ELEMENT
        self.brush_radius = DEFAULT_BRUSH_RADIUS
        self._running = False

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
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._running = False

    def _paint_if_dragging(self) -> None:
        """Paint the selected element under the cursor while button 1 is held.

        Continuous painting every frame (rather than only on MOUSEBUTTONDOWN)
        feels natural when dragging.
        """
        if pygame.mouse.get_pressed()[0]:
            mx, my = pygame.mouse.get_pos()
            gx, gy = mx // CELL_SIZE, my // CELL_SIZE
            self._grid.fill_circle(gx, gy, self.brush_radius, self.selected_element)

    def _draw(self) -> None:
        # The grid exactly fills the window (GRID_* * CELL_SIZE == WINDOW_*),
        # so the fill is just defensive against any future geometry mismatch.
        self._screen.fill(BG_COLOR)
        small = self._renderer.render(self._grid)
        scaled = pygame.transform.scale(small, (WINDOW_WIDTH, WINDOW_HEIGHT))
        self._screen.blit(scaled, (0, 0))

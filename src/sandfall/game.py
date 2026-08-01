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
    AMBIENT_TEMP,
    BG_COLOR,
    CELL_SIZE,
    DEFAULT_BRUSH_RADIUS,
    DEFAULT_ELEMENT,
    FPS,
    GRID_HEIGHT,
    GRID_WIDTH,
    HEAT_VIZ_COLD,
    HEAT_VIZ_HOT,
    HIGHLIGHT_COLOR,
    INITIAL_WINDOW_H,
    INITIAL_WINDOW_W,
    MAGNIFY_ZOOM,
    MIN_WINDOW_H,
    MIN_WINDOW_W,
    clamp_brush_radius,
    compute_grid_dims,
)
from .control import LoopController
from .elements import ElementId
from .grid import BrushShape, Grid, migrate_grid
from .renderer import Renderer, flow_arrow_samples
from .simulation import Simulation
from .thermal import build_colorbar_gradient
from .ui import UI, ToolId, magnifier_src_rect

# H-mode colorbar geometry / colors. The colorbar gradient is pure of
# temperature (built by thermal.build_colorbar_gradient), so it depends only on
# the sim-area pixel height; the surface is rebuilt only on a height change.
COLORBAR_W = 20  # px width of the temperature colorbar
COLORBAR_BORDER: tuple[int, int, int] = (220, 220, 220)
COLORBAR_LABEL: tuple[int, int, int] = (235, 235, 235)
# Sparse flow-arrow overlay (drawn over the heat colors in H mode).
ARROW_STRIDE = 10  # grid cells per flow-arrow sample block
ARROW_LEN = 12  # px arrow length on screen
ARROW_COLOR: tuple[int, int, int, int] = (255, 255, 255, 128)  # semi-transparent white


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
    # Current brush footprint shape (Phase 02). Cycled by Tab and the
    # Brush-shape palette button (Disk <-> Square).
    brush_shape: BrushShape
    _running: bool
    # Current window size in pixels (starts at INITIAL_*; updated on resize).
    _window_w: int
    _window_h: int
    # Heat-overlay toggle (Phase 04): when True, _draw renders the temperature
    # field (render_heat) instead of the element-id field (render). Bound to
    # the H key; defaults off so the default look is unchanged.
    _heat_overlay: bool
    # Follow-cursor magnifier toggle (Phase 03): when True, _draw draws a
    # ~MAGNIFY_ZOOM lens floating near the cursor showing zoomed grid content.
    # VISUAL ONLY -- it does NOT change painting input mapping (the cursor
    # still paints the cell at mx // CELL_SIZE at 1x). Bound to Z and the
    # Magnifier palette button; defaults off.
    _magnify: bool
    # Cached H-mode overlay surfaces (rebuilt only on resize). The colorbar
    # gradient is pure of temperature, so it depends only on the sim-area pixel
    # height; the arrow overlay is a screen-sized SRCALPHA cleared each frame.
    _colorbar_surf: pygame.Surface
    _colorbar_h: int
    _arrow_overlay: pygame.Surface

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
        self.brush_shape = BrushShape.DISK
        self._running = False
        self._window_w = INITIAL_WINDOW_W
        self._window_h = INITIAL_WINDOW_H
        self._heat_overlay = False
        self._magnify = False
        # H-mode overlay surfaces. The colorbar surface is rebuilt on first draw
        # (_colorbar_h == -1 forces it); the arrow overlay is a screen-sized
        # SRCALPHA surface cleared + redrawn each frame in _draw_heat_overlays.
        self._colorbar_surf = pygame.Surface((COLORBAR_W, 1))
        self._colorbar_h = -1  # forces a rebuild on first draw
        self._arrow_overlay = pygame.Surface(
            (INITIAL_WINDOW_W, INITIAL_WINDOW_H), pygame.SRCALPHA
        ).convert_alpha()

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
                elif event.key == pygame.K_h:
                    # Toggle the heat-map overlay (Phase 04). Only the grid
                    # surface is swapped; the palette + HUD stay visible so
                    # the player can still select elements while viewing heat.
                    self._heat_overlay = not self._heat_overlay
                elif event.key == pygame.K_z:
                    # Toggle the follow-cursor magnifier (Phase 03). VISUAL
                    # ONLY: it crops the rendered grid surface and scales it
                    # up; it does NOT change where paint lands (mx //
                    # CELL_SIZE stays at 1x). Shares the Magnifier palette
                    # button's toggle (the same _magnify flag).
                    self._magnify = not self._magnify
                elif event.key == pygame.K_TAB:
                    # Cycle the brush footprint shape (Disk <-> Square). The
                    # Brush-shape palette button does the same via the shared
                    # _cycle_brush_shape helper (DRY).
                    self._cycle_brush_shape()
            elif event.type == pygame.MOUSEWHEEL:
                # event.y is +1 for scroll-up, -1 for scroll-down (pygame-ce).
                # Scroll-up grows the brush.
                self.brush_radius = clamp_brush_radius(self.brush_radius + event.y)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                # Only button 1 (left) selects; right-click erases (see
                # _erase_if_dragging) and must NOT select. The guard above
                # (`event.button == 1`) enforces that — a right-click (button 3)
                # falls through this whole elif without selecting an item.
                # A left-click inside a palette item dispatches by item kind:
                # element items select that element; the Eraser TOOL maps to
                # EMPTY (so left-drag erases — behavior preserved); Brush-shape
                # and Magnifier are Phase-01 placeholders (no-op until Phase
                # 02/03). Selection only happens on button-down; the subsequent
                # paint-this-frame is suppressed because the cursor is still
                # inside the reserved palette strip (see _paint_if_dragging).
                mx, my = event.pos
                item = self._ui.item_at(mx, my)
                if item is not None:
                    if item.is_element:
                        assert item.element_id is not None
                        self.selected_element = item.element_id
                    elif item.tool == ToolId.ERASER:
                        # Eraser maps to EMPTY so left-drag erases (preserved).
                        self.selected_element = ElementId.EMPTY
                    elif item.tool == ToolId.BRUSH_SHAPE:
                        # Cycle the brush footprint shape (Disk <-> Square).
                        # Shares the Tab handler's logic via the helper (DRY).
                        self._cycle_brush_shape()
                    elif item.tool == ToolId.MAGNIFY:
                        # Toggle the follow-cursor magnifier (Phase 03).
                        # Shares the Z key's toggle (the same _magnify flag).
                        # VISUAL ONLY -- painting input is unchanged.
                        self._magnify = not self._magnify
            # NOTE: no VIDEORESIZE branch. Window resize is detected by polling
            # self._window.size every frame in _apply_resize_if_changed(); that
            # path is event-driver-independent and never recreates the window
            # (the pygame.Window API does not need a set_mode call on resize).

    def _cycle_brush_shape(self) -> None:
        """Advance the brush footprint shape to the next :class:`BrushShape`.

        Cycles Disk <-> Square in enum-definition order, wrapping at the end.
        Shared by the ``Tab`` key and the Brush-shape palette button so the
        two cycling paths can never drift apart.
        """
        shapes = list(BrushShape)
        self.brush_shape = shapes[(shapes.index(self.brush_shape) + 1) % len(shapes)]

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
        paint_brush(
            self._grid,
            gx,
            gy,
            self.brush_radius,
            self.selected_element,
            self.brush_shape,
        )

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
        paint_brush(
            self._grid, gx, gy, self.brush_radius, ElementId.EMPTY, self.brush_shape
        )

    def _draw(self) -> None:
        # The grid renders to a (grid.width x grid.height) surface and is
        # scaled up to the grid's whole-cell pixel size; the screen is first
        # cleared to BG_COLOR so any leftover pixels (window not an exact
        # whole-cell multiple, or below the scaled grid) show the background.
        # After resize the grid dims derive from the current window size
        # (compute_grid_dims), so this redraws the entire scene every frame.
        self._screen.fill(BG_COLOR)
        # Heat-overlay toggle (Phase 04): swap the grid surface for the
        # temperature field. The rest of _draw (scale + blit + UI overlay) is
        # unchanged, so the palette + HUD remain visible in both modes.
        if self._heat_overlay:
            small = self._renderer.render_heat(self._grid)
        else:
            small = self._renderer.render(self._grid)
        target = (self._grid.width * CELL_SIZE, self._grid.height * CELL_SIZE)
        scaled = pygame.transform.scale(small, target)
        self._screen.blit(scaled, (0, 0))

        # H-mode UI overlays (Phase 02): temperature colorbar (right edge) +
        # sparse flow arrows. Drawn only in heat mode, BEFORE the magnifier --
        # these are screen-space overlays while the lens crops grid-space, so
        # the magnifier (if on) magnifies the heat view without the overlays.
        if self._heat_overlay:
            self._draw_heat_overlays()

        # Follow-cursor magnifier (Phase 03, visual only). Crop the grid-sized
        # ``small`` surface around the cursor cell, scale up ~MAGNIFY_ZOOM, and
        # blit as a floating lens. Painting input mapping is UNCHANGED (mx //
        # CELL_SIZE stays at 1x): the lens is display-only, a painted cell
        # lands where the 1x cursor points, NOT where it appears in the lens.
        # Drawn BEFORE self._ui.draw so the palette + HUD + cursor outline
        # render on top of it (and the lens is hidden over the palette anyway).
        # Whichever surface ``_draw`` rendered is magnified -- element-id OR
        # heat-overlay -- so the lens shows zoomed heat too when H is toggled.
        if self._magnify:
            self._draw_magnifier(small)

        # Particle count: non-empty cells, once per frame (~0.04 ms — free).
        # Full-grid sum, NOT incremental tracking — cheap at current grid
        # sizes; revisit only if a much larger grid makes it non-negligible.
        count = int((self._grid.array != int(ElementId.EMPTY)).sum())
        self._ui.draw(
            self._screen,
            self.selected_element,
            self._clock.get_fps(),
            self.brush_radius,
            self._loop.paused,
            count,
            self.brush_shape,
            magnify_on=self._magnify,
        )

    def _draw_heat_overlays(self) -> None:
        """Draw the H-mode UI overlays: the temperature colorbar (right edge,
        with degree markers) and the sparse flow arrows.

        Neither affects the simulation; both are screen-space overlays drawn
        only when ``self._heat_overlay`` is True (called from :meth:`_draw`,
        before the magnifier). The colorbar surface is cached and rebuilt only
        when the sim-area pixel height changes (resize); the arrow overlay is a
        screen-sized SRCALPHA surface cleared and redrawn each frame.

        Colorbar placement: the rightmost ``COLORBAR_W`` px of the scaled grid
        region, full sim-area height. Degree markers at the four anchors that
        bracket the interesting range (``HEAT_VIZ_COLD``, ``AMBIENT_TEMP``,
        200, ``HEAT_VIZ_HOT``); labels sit just LEFT of the bar so they never
        run off the right edge.
        """
        scaled_h = self._grid.height * CELL_SIZE
        scaled_w = self._grid.width * CELL_SIZE

        # --- Temperature colorbar (right edge of the scaled grid region) -----
        if self._colorbar_h != scaled_h:
            grad = build_colorbar_gradient(scaled_h)  # (scaled_h, 3) uint8
            bar = pygame.Surface((1, scaled_h))  # 1px-wide column
            pygame.surfarray.blit_array(bar, grad.reshape(1, scaled_h, 3))
            self._colorbar_surf = pygame.transform.scale(bar, (COLORBAR_W, scaled_h))
            self._colorbar_h = scaled_h
        bx = scaled_w - COLORBAR_W  # right edge of sim area
        self._screen.blit(self._colorbar_surf, (bx, 0))
        pygame.draw.rect(
            self._screen, COLORBAR_BORDER, (bx, 0, COLORBAR_W, scaled_h), 1
        )
        # Degree markers at the four anchors that bracket the interesting range.
        font = self._ui.font
        span = HEAT_VIZ_HOT - HEAT_VIZ_COLD
        for temp in (HEAT_VIZ_COLD, AMBIENT_TEMP, 200, HEAT_VIZ_HOT):
            ty = int(round((HEAT_VIZ_HOT - temp) / span * scaled_h))
            pygame.draw.line(
                self._screen, COLORBAR_BORDER, (bx, ty), (bx + COLORBAR_W, ty), 1
            )
            label = font.render(f"{temp}", True, COLORBAR_LABEL)
            # Label sits just LEFT of the bar so it never runs off the right edge.
            self._screen.blit(
                label, (bx - label.get_width() - 3, ty - label.get_height() // 2)
            )

        # --- Sparse flow arrows (one per ARROW_STRIDE-cell block) -----------
        ov = self._arrow_overlay
        if ov.get_size() != (self._window_w, self._window_h):
            ov = pygame.Surface(
                (self._window_w, self._window_h), pygame.SRCALPHA
            ).convert_alpha()
            self._arrow_overlay = ov
        ov.fill((0, 0, 0, 0))
        for cx, cy, vx, vy in flow_arrow_samples(self._sim.flow, ARROW_STRIDE):
            sx = cx * CELL_SIZE + CELL_SIZE // 2
            sy = cy * CELL_SIZE + CELL_SIZE // 2
            length = (vx * vx + vy * vy) ** 0.5
            if length == 0:
                continue
            ux, uy = vx / length, vy / length
            x0 = sx - ux * ARROW_LEN / 2
            y0 = sy - uy * ARROW_LEN / 2
            x1 = sx + ux * ARROW_LEN / 2
            y1 = sy + uy * ARROW_LEN / 2
            pygame.draw.line(ov, ARROW_COLOR, (x0, y0), (x1, y1), 1)
            # Small arrowhead at the (x1, y1) tip.
            hx, hy = x1 - ux * 4 - uy * 2, y1 - uy * 4 + ux * 2
            hx2, hy2 = x1 - ux * 4 + uy * 2, y1 - uy * 4 - ux * 2
            pygame.draw.polygon(ov, ARROW_COLOR, [(x1, y1), (hx, hy), (hx2, hy2)])
        self._screen.blit(ov, (0, 0))

    def _draw_magnifier(self, small: pygame.Surface) -> None:
        """Crop + scale a grid region around the cursor into a magnifier lens.

        Visual only: does NOT affect painting coordinates (the cursor still
        paints the cell at ``mx // CELL_SIZE`` at 1x). The lens is hidden when
        the cursor is over the reserved palette strip (so it never magnifies
        the palette). Placement is offset up-and-right of the cursor by a small
        gap and clamped into the window so a cursor near an edge keeps the lens
        fully on-screen. The lens is large (MAGNIFY_LENS_CELLS *
        CELL_SIZE * MAGNIFY_ZOOM == 504 px) and can overlap the cursor region
        after clamping, but it is drawn BEFORE ``UI.draw`` -- so the always-on
        cursor outline (the exact brush footprint) renders ON TOP of the lens
        and the player always sees precisely where paint will land. The exact
        offset choice is pinned in the Phase 03 reflection.

        ``small`` is the already-rendered grid-sized surface (element-id OR
        heat-overlay, whichever ``_draw`` produced). A subsurface shares its
        pixels (no copy); ``pygame.transform.scale`` returns a new surface, so
        the whole crop+scale is cheap. ``magnifier_src_rect`` guarantees the
        crop rect is in-bounds, so the subsurface rect is always valid.
        """
        mx, my = pygame.mouse.get_pos()
        if self._ui.in_reserved_area(mx, my):
            return
        gx, gy = mx // CELL_SIZE, my // CELL_SIZE
        src = magnifier_src_rect(gx, gy, self._grid.width, self._grid.height)
        if src is None:
            return
        sx, sy, sw, sh = src
        lens_w = sw * CELL_SIZE * MAGNIFY_ZOOM
        lens_h = sh * CELL_SIZE * MAGNIFY_ZOOM
        # Crop at grid resolution (surface is grid.width x grid.height) then scale.
        lens_surf = pygame.transform.scale(
            small.subsurface((sx, sy, sw, sh)), (lens_w, lens_h)
        )
        # Offset placement: up-and-right of the cursor so the lens floats off
        # the brush point (the player can still see where they are painting),
        # then clamp into the window so a cursor near the top/right edge keeps
        # the lens fully on-screen.
        gap = CELL_SIZE * 2
        lx = mx + gap
        ly = my - gap - lens_h
        lx = max(0, min(lx, self._window_w - lens_w))
        ly = max(0, min(ly, self._window_h - lens_h))
        self._screen.blit(lens_surf, (lx, ly))
        # A thin border so the lens edge is visible against the scene.
        pygame.draw.rect(self._screen, HIGHLIGHT_COLOR, (lx, ly, lens_w, lens_h), 1)

"""In-game UI: element palette, FPS/brush readout, paused indicator.

The *layout* (which palette entry goes where on screen) is split from the
*drawing* (putting pixels on a Surface). Layout is a pure function
(:func:`palette_layout`) returning a list of :class:`PaletteItem` rects (each
either an element swatch or a tool button); hit-testing (:meth:`UI.item_at`) is
pure too. The :data:`TOOL_TOOLTIPS` mapping and the element/tool tooltip text
are pure as well. All three are unit-tested headlessly in ``tests/test_ui.py``.
The :class:`UI` draw method does the pygame rendering (hover tooltips, the
enabled Brush-shape button + its footprint glyph, the always-on cursor
outline, the enabled Magnifier button reflecting on/off) and is verified
manually via the running window / the ``SANDFALL_FRAMES`` seam.

Pygame is imported lazily inside :meth:`UI.draw` so importing this module (and
therefore the pure helpers) does not require a pygame runtime — important for
keeping the layout tests display-free.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .config import (
    CELL_SIZE,
    ERASER_LABEL,
    ERASER_SWATCH_BORDER,
    ERASER_SWATCH_COLOR,
    FONT_NAME,
    FONT_SIZE,
    FPS_COLOR,
    HIGHLIGHT_COLOR,
    MAGNIFY_LENS_CELLS,
    PALETTE_BAR_HEIGHT,
    PALETTE_BG,
    PALETTE_GROUP_GAP,
    PALETTE_MARGIN,
    PALETTE_PADDING,
    PALETTE_SWATCH,
    PAUSED_COLOR,
)
from .elements import ELEMENTS, ElementId
from .grid import BrushShape

if TYPE_CHECKING:
    # Annotations only (PEP 563): pygame is not imported at runtime here.
    import pygame


class ToolId(enum.Enum):
    """A non-element palette tool (utility button).

    Tools are NOT elements: selecting them does not set ``selected_element``
    (except ERASER, which conventionally maps to ``ElementId.EMPTY`` so
    left-drag erases). Each tool has its own dispatch in Game._handle_events.
    """

    ERASER = enum.auto()
    BRUSH_SHAPE = enum.auto()
    MAGNIFY = enum.auto()


# Tooltip label for each tool button. Pure (no pygame) so the tooltip text is
# unit-tested headlessly alongside palette_layout. Element tooltips are derived
# from ELEMENTS[eid].name.title() inside palette_layout.
TOOL_TOOLTIPS: dict[ToolId, str] = {
    ToolId.ERASER: "Eraser",
    ToolId.BRUSH_SHAPE: "Brush Shape",
    ToolId.MAGNIFY: "Magnifier",
}


@dataclass(frozen=True, slots=True)
class PaletteItem:
    """One palette entry's screen rectangle plus what it selects.

    A palette item is EITHER an element swatch (``element_id`` set, selects
    that ElementId on click) OR a tool button (``tool`` set, a ToolId).
    Exactly one of ``element_id`` / ``tool`` is non-None — an invariant
    enforced by palette_layout and pinned by a headless test. ``tooltip`` is
    the hover label (element name or tool name).

    Coordinates are screen pixels with origin at the top-left, matching pygame.
    ``x``/``y`` is the top-left corner; ``w``/``h`` the size.
    """

    x: int
    y: int
    w: int
    h: int
    tooltip: str
    element_id: ElementId | None = None
    tool: ToolId | None = None

    @property
    def is_element(self) -> bool:
        return self.element_id is not None

    @property
    def is_tool(self) -> bool:
        return self.tool is not None

    def contains(self, px: int, py: int) -> bool:
        """True if screen pixel ``(px, py)`` lies inside this item."""
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


def palette_layout(window_width: int, bar_y: int) -> list[PaletteItem]:
    """Compute the palette items: elements, then a group gap, then tools.

    Layout is a single left-aligned bottom row:
      [11 element swatches] [group gap] [Eraser] [Brush-shape] [Magnifier]

    Real elements are laid out in :class:`ElementId` ascending order (EMPTY
    skipped) starting from the left margin, each ``PALETTE_SWATCH`` square with
    ``PALETTE_PADDING`` between neighbors, vertically centered in the strip
    whose top is ``bar_y``. After the last element, an EXTRA
    ``PALETTE_GROUP_GAP`` is added (on top of the trailing PALETTE_PADDING) to
    visibly separate the utility group. The 3 tools follow in the fixed order
    ERASER, BRUSH_SHAPE, MAGNIFY. ``window_width`` is accepted for future
    layouts (centering/wrap) and to keep the API symmetric with the window
    geometry; the v1 layout does not wrap.

    Pure: no pygame -> unit-tested headlessly. The Eraser is a TOOL here (not
    an element swatch); Game maps selecting it to ``selected_element = EMPTY``
    so left-drag still erases. Brush-shape dispatch is wired (Phase 02, cycles
    Disk/Square); Magnifier remains a placeholder until Phase 03.
    """
    del window_width  # reserved for future layouts; not needed for the v1 row.
    items: list[PaletteItem] = []
    x = PALETTE_MARGIN
    y = bar_y + PALETTE_MARGIN
    # Element group.
    for eid in ElementId:
        if eid == ElementId.EMPTY:
            continue
        items.append(
            PaletteItem(
                x,
                y,
                PALETTE_SWATCH,
                PALETTE_SWATCH,
                tooltip=ELEMENTS[eid].name.title(),
                element_id=eid,
            )
        )
        x += PALETTE_SWATCH + PALETTE_PADDING
    # Group gap (extra space separating elements from utilities).
    x += PALETTE_GROUP_GAP
    # Utility group: Eraser, Brush-shape, Magnifier.
    for tool in (ToolId.ERASER, ToolId.BRUSH_SHAPE, ToolId.MAGNIFY):
        items.append(
            PaletteItem(
                x,
                y,
                PALETTE_SWATCH,
                PALETTE_SWATCH,
                tooltip=TOOL_TOOLTIPS[tool],
                tool=tool,
            )
        )
        x += PALETTE_SWATCH + PALETTE_PADDING
    return items


def format_hud(fps: float, brush_radius: int, count: int) -> str:
    """Format the top-left HUD line: FPS, brush radius, particle count.

    Pure (no pygame) so the HUD format is unit-testable headlessly, mirroring
    the layout/draw split used for the palette (:func:`palette_layout` is the
    pure counterpart to :meth:`UI.draw`'s swatch rendering). ``count`` is the
    number of non-empty cells on the grid (computed once per frame by the
    caller in :meth:`Game._draw`).
    """
    return f"{int(fps)} FPS  r={brush_radius}  n={count}"


def magnifier_src_rect(
    gx: int, gy: int, grid_w: int, grid_h: int, lens_cells: int = MAGNIFY_LENS_CELLS
) -> tuple[int, int, int, int] | None:
    """Grid-cell window to crop for the magnifier lens, centered on ``(gx, gy)``.

    Returns ``(x, y, w, h)`` in GRID cells (to be applied to the grid-sized
    render surface), or ``None`` if the grid is smaller than ``lens_cells`` in
    either axis (no useful zoom). The window is clamped to grid bounds: when
    the cursor is near an edge the window shifts so it stays fully inside the
    grid (the lens shows edge content rather than going off-grid). ``w``/``h``
    may be smaller than ``lens_cells`` at the very smallest grids.

    Pure (no pygame) -> unit-tested headlessly. This is the source-rect math
    for the follow-cursor magnifier lens drawn by ``Game._draw_magnifier``; it
    does NOT affect painting input mapping (the cursor still paints the cell at
    ``mx // CELL_SIZE`` at 1x).
    """
    if grid_w < lens_cells or grid_h < lens_cells:
        return None
    half = lens_cells // 2
    x = max(0, min(grid_w - lens_cells, gx - half))
    y = max(0, min(grid_h - lens_cells, gy - half))
    return (x, y, lens_cells, lens_cells)


class UI:
    """Owns the palette layout + on-screen HUD (FPS, brush radius, paused).

    The constructor performs no pygame calls, so it is safe to instantiate
    headlessly (the layout can be hit-tested without a display). All pygame
    rendering is deferred to :meth:`draw`, which lazily creates the font and
    the semi-transparent bar surface on first call.
    """

    _window_width: int
    _window_height: int
    _bar_y: int
    _items: list[PaletteItem]
    _font: pygame.font.Font | None
    _bar_surf: pygame.Surface | None

    def __init__(self, window_width: int, window_height: int) -> None:
        self._window_width = window_width
        self._window_height = window_height
        # Palette strip occupies the bottom PALETTE_BAR_HEIGHT pixels.
        self._bar_y = window_height - PALETTE_BAR_HEIGHT
        self._items = palette_layout(window_width, self._bar_y)
        self._font = None
        self._bar_surf = None

    def resize(self, window_width: int, window_height: int) -> None:
        """Recompute layout for a new window size.

        Called by ``Game`` whenever it detects the window size has changed
        (polled once per frame against ``Window.size``). Resets the cached
        palette-bar surface so it is rebuilt at the new width on the next draw
        (its width depends on ``window_width`` and the old surface would
        otherwise be scaled/clipped incorrectly).
        """
        self._window_width = window_width
        self._window_height = window_height
        self._bar_y = window_height - PALETTE_BAR_HEIGHT
        self._items = palette_layout(window_width, self._bar_y)
        self._bar_surf = None

    @property
    def items(self) -> list[PaletteItem]:
        """The cached palette layout (read-only view)."""
        return self._items

    @property
    def bar_y(self) -> int:
        """Top y pixel of the reserved palette strip."""
        return self._bar_y

    def in_reserved_area(self, px: int, py: int) -> bool:
        """True if screen pixel ``(px, py)`` is inside the palette strip.

        The Game uses this to suppress painting while the cursor is over the
        palette so the user can click items without painting underneath.
        """
        return py >= self._bar_y

    def item_at(self, px: int, py: int) -> PaletteItem | None:
        """Return the palette item containing ``(px, py)``, or None."""
        for item in self._items:
            if item.contains(px, py):
                return item
        return None

    def draw(
        self,
        screen: pygame.Surface,
        active: ElementId,
        fps: float,
        brush_radius: int,
        paused: bool,
        count: int,
        brush_shape: BrushShape = BrushShape.DISK,
        magnify_on: bool = False,
    ) -> None:
        """Render the palette + HUD onto ``screen``.

        ``active`` is the currently selected element (its swatch is
        outlined). ``fps``/``brush_radius``/``count`` are shown top-left
        (``count`` is the number of non-empty cells); ``paused`` toggles the
        centered PAUSED indicator. ``brush_shape`` drives the Brush-shape
        button glyph (circle for DISK, square for SQUARE) and the always-on
        cursor footprint outline drawn over the sim area. ``magnify_on``
        drives the Magnifier button's active outline (on/off state) — the lens
        itself is drawn by ``Game._draw_magnifier``, not here, because it
        needs the grid-sized render surface.
        """
        import pygame  # local: keeps module import pygame-free for the pure helpers

        if self._font is None:
            self._font = pygame.font.Font(FONT_NAME, FONT_SIZE)
        if self._bar_surf is None:
            bar_w = self._window_width
            bar_h = self._window_height - self._bar_y
            self._bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
            self._bar_surf.fill(PALETTE_BG)

        # FPS + brush + particle-count readout, top-left.
        assert self._font is not None
        hud = self._font.render(format_hud(fps, brush_radius, count), True, FPS_COLOR)
        screen.blit(hud, (PALETTE_MARGIN, PALETTE_MARGIN))

        # PAUSED indicator, centered along the top edge.
        if paused:
            paused_surf = self._font.render("PAUSED", True, PAUSED_COLOR)
            cx = self._window_width // 2 - paused_surf.get_width() // 2
            screen.blit(paused_surf, (cx, PALETTE_MARGIN))

        # Palette strip + items.
        assert self._bar_surf is not None
        screen.blit(self._bar_surf, (0, self._bar_y))
        for item in self._items:
            rect = (item.x, item.y, item.w, item.h)
            if item.is_element:
                # Element swatch: fill with the element's registered color.
                assert item.element_id is not None  # is_element guarantees this
                pygame.draw.rect(screen, ELEMENTS[item.element_id].color, rect)
            else:
                # Tool button. Eraser and Brush-shape are functional; Magnifier
                # is still a Phase-01 placeholder rendered DIMMED so a click
                # that does nothing is not mistaken for a bug (its dispatch
                # arrives in Phase 03). Placeholder styling pinned in the
                # Phase-01 reflection: dim fill + dark border + muted glyph.
                assert item.tool is not None
                if item.tool == ToolId.BRUSH_SHAPE:
                    # Enabled tool reflecting the CURRENT brush footprint
                    # shape: a circle outline (DISK) or square outline
                    # (SQUARE) drawn with pygame.draw inside the swatch.
                    # Cleaner than a font glyph and reads the shape at a
                    # glance; click/Tab cycles it. Always highlighted (it is
                    # always the current shape) via the active-outline block
                    # below. Styling pinned in the Phase-02 reflection:
                    # medium-gray fill + bright border + white shape outline.
                    fill = (70, 70, 80)
                    border = (180, 180, 190)
                    pygame.draw.rect(screen, fill, rect)
                    pygame.draw.rect(screen, border, rect, 1)
                    inset = item.w // 4  # glyph inset within the swatch
                    if brush_shape == BrushShape.SQUARE:
                        pygame.draw.rect(
                            screen,
                            HIGHLIGHT_COLOR,
                            (
                                item.x + inset,
                                item.y + inset,
                                item.w - 2 * inset,
                                item.h - 2 * inset,
                            ),
                            2,
                        )
                    else:  # DISK
                        pygame.draw.circle(
                            screen,
                            HIGHLIGHT_COLOR,
                            (item.x + item.w // 2, item.y + item.h // 2),
                            item.w // 2 - inset,
                            2,
                        )
                else:
                    if item.tool == ToolId.ERASER:
                        fill, border, glyph, glyph_color = (
                            ERASER_SWATCH_COLOR,
                            ERASER_SWATCH_BORDER,
                            ERASER_LABEL,
                            ERASER_SWATCH_BORDER,
                        )
                    else:  # MAGNIFY -- enabled (Phase 03 wired it: Z + click toggle).
                        # Styling mirrors the Brush-shape button's enabled
                        # look (medium-gray fill + bright border + a white
                        # glyph) so it reads as a functional tool, not a
                        # placeholder. The on/off state is carried by the
                        # active outline below (drawn when magnify_on is True).
                        fill, border, glyph, glyph_color = (
                            (70, 70, 80),
                            (180, 180, 190),
                            "Z",
                            HIGHLIGHT_COLOR,
                        )
                    pygame.draw.rect(screen, fill, rect)
                    pygame.draw.rect(screen, border, rect, 1)
                    assert self._font is not None
                    label = self._font.render(glyph, True, glyph_color)
                    screen.blit(
                        label,
                        (
                            item.x + (item.w - label.get_width()) // 2,
                            item.y + (item.h - label.get_height()) // 2,
                        ),
                    )
            # Active outline: element items highlight on their id; the Eraser
            # tool highlights when EMPTY is the selected element (so
            # left-drag-erase keeps its highlight); the Brush-shape tool is
            # ALWAYS highlighted (it always reflects the current shape); the
            # Magnifier tool highlights while it is toggled on (magnify_on).
            is_active = (
                (item.is_element and item.element_id == active)
                or (item.tool == ToolId.ERASER and active == ElementId.EMPTY)
                or item.tool == ToolId.BRUSH_SHAPE
                or (item.tool == ToolId.MAGNIFY and magnify_on)
            )
            if is_active:
                pygame.draw.rect(screen, HIGHLIGHT_COLOR, rect, 2)

        # Hover tooltip: render the hovered item's ``.tooltip`` just above the
        # palette bar, left-aligned with the cursor and clamped to the window
        # so it never overlaps the playfield or spills off-screen. The tooltip
        # TEXT is pure (item.tooltip) and headlessly asserted; only placement
        # is visual.
        mx, my = pygame.mouse.get_pos()
        hit = self.item_at(mx, my)
        if hit is not None:
            assert self._font is not None
            tip = self._font.render(hit.tooltip, True, FPS_COLOR)
            tx = max(
                PALETTE_MARGIN,
                min(mx, self._window_width - tip.get_width() - PALETTE_MARGIN),
            )
            ty = self._bar_y - tip.get_height() - 2
            screen.blit(tip, (tx, ty))

        # Always-on brush cursor outline (Phase 02): shows the footprint
        # (circle for DISK, square for SQUARE) at radius * CELL_SIZE px around
        # the cursor, so the player is not painting blind. Hidden over the
        # reserved palette area (so dragging over swatches shows no stray
        # outline). Geometry mirrors the paint footprint exactly: the bbox of
        # a brush of radius r centered on cell (gx, gy) spans
        # [gx-r, gx+r] x [gy-r, gy+r] cells -> screen px
        # [(gx-r)*CELL_SIZE, (gx+r+1)*CELL_SIZE). The DISK outline is a circle
        # enclosing that same bbox; the SQUARE outline IS the bbox. Visual
        # only (verified via SANDFALL_FRAMES, not pixel-asserted), like all
        # UI.draw rendering. Color/weight pinned in the Phase-02 reflection:
        # HIGHLIGHT_COLOR (white), width 1.
        if not self.in_reserved_area(mx, my):
            gx, gy = mx // CELL_SIZE, my // CELL_SIZE
            left = (gx - brush_radius) * CELL_SIZE
            top = (gy - brush_radius) * CELL_SIZE
            size = (2 * brush_radius + 1) * CELL_SIZE
            if brush_shape == BrushShape.SQUARE:
                pygame.draw.rect(screen, HIGHLIGHT_COLOR, (left, top, size, size), 1)
            else:  # DISK -- a circle enclosing the same bbox.
                pygame.draw.circle(
                    screen,
                    HIGHLIGHT_COLOR,
                    (left + size // 2, top + size // 2),
                    size // 2,
                    1,
                )

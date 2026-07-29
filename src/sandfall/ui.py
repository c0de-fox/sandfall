"""In-game UI: element palette, FPS/brush readout, paused indicator.

The *layout* (which swatch goes where on screen) is split from the *drawing*
(putting pixels on a Surface). Layout is a pure function
(:func:`palette_layout`) returning a list of :class:`Swatch` rects; hit-testing
(:meth:`UI.swatch_at`) is pure too. Both are unit-tested headlessly in
``tests/test_ui.py``. The :class:`UI` draw method does the pygame rendering
and is verified manually via the running window / the ``SANDFALL_FRAMES`` seam.

Pygame is imported lazily inside :meth:`UI.draw` so importing this module (and
therefore the pure helpers) does not require a pygame runtime — important for
keeping the layout tests display-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .config import (
    FONT_NAME,
    FONT_SIZE,
    FPS_COLOR,
    HIGHLIGHT_COLOR,
    PALETTE_BG,
    PALETTE_MARGIN,
    PALETTE_PADDING,
    PALETTE_SWATCH,
    PAUSED_COLOR,
)
from .elements import ELEMENTS, ElementId

if TYPE_CHECKING:
    # Annotations only (PEP 563): pygame is not imported at runtime here.
    import pygame


# Height of the reserved bottom palette strip. Swatches are vertically
# centered inside it (one PALETTE_MARGIN of slack top and bottom).
PALETTE_BAR_HEIGHT = PALETTE_SWATCH + 2 * PALETTE_MARGIN


@dataclass(frozen=True, slots=True)
class Swatch:
    """A palette entry's screen rectangle plus its element id.

    Coordinates are screen pixels with origin at the top-left, matching
    pygame. ``x``/``y`` is the top-left corner; ``w``/``h`` the size.
    """

    element_id: ElementId
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: int, py: int) -> bool:
        """True if screen pixel ``(px, py)`` lies inside this swatch."""
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


def palette_layout(window_width: int, bar_y: int) -> list[Swatch]:
    """Compute the swatch rects for every non-EMPTY element, left-to-right.

    Pure: no pygame. Swatches are laid out in :class:`ElementId` ascending
    order starting from the left margin, each ``PALETTE_SWATCH`` square with
    ``PALETTE_PADDING`` between neighbors, vertically centered inside the
    palette strip whose top is ``bar_y``. ``window_width`` is accepted for
    future layouts (e.g. right-alignment / wrapping) and to keep the API
    symmetric with the window geometry; the v1 layout does not wrap.
    """
    del window_width  # reserved for future layouts; not needed for the v1 row.
    swatches: list[Swatch] = []
    x = PALETTE_MARGIN
    y = bar_y + PALETTE_MARGIN
    for eid in ElementId:
        if eid == ElementId.EMPTY:
            continue
        swatches.append(Swatch(eid, x, y, PALETTE_SWATCH, PALETTE_SWATCH))
        x += PALETTE_SWATCH + PALETTE_PADDING
    return swatches


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
    _swatches: list[Swatch]
    _font: pygame.font.Font | None
    _bar_surf: pygame.Surface | None

    def __init__(self, window_width: int, window_height: int) -> None:
        self._window_width = window_width
        self._window_height = window_height
        # Palette strip occupies the bottom PALETTE_BAR_HEIGHT pixels.
        self._bar_y = window_height - PALETTE_BAR_HEIGHT
        self._swatches = palette_layout(window_width, self._bar_y)
        self._font = None
        self._bar_surf = None

    @property
    def swatches(self) -> list[Swatch]:
        """The cached palette layout (read-only view)."""
        return self._swatches

    @property
    def bar_y(self) -> int:
        """Top y pixel of the reserved palette strip."""
        return self._bar_y

    def in_reserved_area(self, px: int, py: int) -> bool:
        """True if screen pixel ``(px, py)`` is inside the palette strip.

        The Game uses this to suppress painting while the cursor is over the
        palette so the user can click swatches without painting underneath.
        """
        return py >= self._bar_y

    def swatch_at(self, px: int, py: int) -> ElementId | None:
        """Return the element whose swatch contains ``(px, py)``, or None."""
        for s in self._swatches:
            if s.contains(px, py):
                return s.element_id
        return None

    def draw(
        self,
        screen: pygame.Surface,
        active: ElementId,
        fps: float,
        brush_radius: int,
        paused: bool,
    ) -> None:
        """Render the palette + HUD onto ``screen``.

        ``active`` is the currently selected element (its swatch is
        outlined). ``fps``/``brush_radius`` are shown top-left; ``paused``
        toggles the centered PAUSED indicator.
        """
        import pygame  # local: keeps module import pygame-free for the pure helpers

        if self._font is None:
            self._font = pygame.font.Font(FONT_NAME, FONT_SIZE)
        if self._bar_surf is None:
            bar_w = self._window_width
            bar_h = self._window_height - self._bar_y
            self._bar_surf = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
            self._bar_surf.fill(PALETTE_BG)

        # FPS + brush readout, top-left.
        assert self._font is not None
        hud = self._font.render(f"{int(fps)} FPS  r={brush_radius}", True, FPS_COLOR)
        screen.blit(hud, (PALETTE_MARGIN, PALETTE_MARGIN))

        # PAUSED indicator, centered along the top edge.
        if paused:
            paused_surf = self._font.render("PAUSED", True, PAUSED_COLOR)
            cx = self._window_width // 2 - paused_surf.get_width() // 2
            screen.blit(paused_surf, (cx, PALETTE_MARGIN))

        # Palette strip + swatches.
        assert self._bar_surf is not None
        screen.blit(self._bar_surf, (0, self._bar_y))
        for s in self._swatches:
            color = ELEMENTS[s.element_id].color
            pygame.draw.rect(screen, color, (s.x, s.y, s.w, s.h))
            if s.element_id == active:
                pygame.draw.rect(screen, HIGHLIGHT_COLOR, (s.x, s.y, s.w, s.h), 2)

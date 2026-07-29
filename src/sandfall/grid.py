"""The simulation grid: a uint8 numpy array of element IDs."""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .elements import ElementId


class Grid:
    """2D grid of element IDs. Origin top-left; +y is down (gravity).

    The backing numpy array has shape ``(height, width)`` and dtype
    ``uint8``. Cell ``(x, y)`` is stored at ``array[y, x]``. The public
    API takes ``(x, y)`` in that order so callers do not have to remember
    the row-major layout.
    """

    _width: int
    _height: int
    _data: npt.NDArray[np.uint8]

    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"width and height must be positive ({width=}, {height=})")
        self._width = width
        self._height = height
        self._data = np.zeros((height, width), dtype=np.uint8)

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def array(self) -> npt.NDArray[np.uint8]:
        """Raw ``(height, width)`` uint8 view.

        Intended read-only access for renderers; callers must not mutate.
        """
        return self._data

    def in_bounds(self, x: int, y: int) -> bool:
        """True if ``(x, y)`` is inside the grid."""
        return 0 <= x < self._width and 0 <= y < self._height

    def get(self, x: int, y: int) -> int:
        """Return the element id at ``(x, y)`` as a plain ``int``.

        Raises ``IndexError`` if out of bounds.
        """
        if not self.in_bounds(x, y):
            raise IndexError(
                f"({x}, {y}) out of bounds for {self._width}x{self._height} grid"
            )
        return int(self._data[y, x])

    def set(self, x: int, y: int, element_id: ElementId | int) -> None:
        """Set the cell at ``(x, y)`` to ``element_id``.

        Out-of-bounds writes are silently ignored (brushes painting past an
        edge should not raise).
        """
        if not self.in_bounds(x, y):
            return
        self._data[y, x] = int(element_id)

    def fill_circle(
        self, cx: int, cy: int, radius: int, element_id: ElementId | int
    ) -> None:
        """Fill every cell within ``radius`` (Euclidean disk) of ``(cx, cy)``.

        Cells outside the grid are silently clipped. ``radius == 0`` paints a
        single cell. ``radius < 0`` raises ``ValueError``.
        """
        if radius < 0:
            raise ValueError(f"radius must be non-negative ({radius=})")
        if radius == 0:
            self.set(cx, cy, element_id)
            return
        r2 = radius * radius
        x0 = max(0, cx - radius)
        x1 = min(self._width - 1, cx + radius)
        y0 = max(0, cy - radius)
        y1 = min(self._height - 1, cy + radius)
        eid = int(element_id)
        for y in range(y0, y1 + 1):
            dy = y - cy
            for x in range(x0, x1 + 1):
                dx = x - cx
                if dx * dx + dy * dy <= r2:
                    self._data[y, x] = eid

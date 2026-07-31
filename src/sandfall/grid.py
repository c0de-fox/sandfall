"""The simulation grid: a uint8 numpy array of element IDs.

A second parallel ``uint8`` array ``life`` carries per-cell lifetime state
for finite-duration elements (FIRE, SMOKE). The element id alone cannot
encode life, so the two arrays are kept side by side and must stay
consistent: every rule that moves or transforms a cell must also move or
reset its life entry. The shared swap helper in :mod:`sandfall.rules._common`
does this for moves; rules that convert a cell (e.g. wood → fire) set life
explicitly.

A third parallel ``int16`` array ``temp`` carries per-cell temperature
(Phase 01). It mirrors the ``life`` consistency contract exactly: ``swap``
carries temp; ``fill_circle`` resets temp to ``AMBIENT_TEMP`` (mirrors
zeroing life); ``paint_brush`` sets element-specific ``temp_spawn`` afterward
(mirrors life-seeding); ``migrate_grid`` copies the temp overlap. Heat
diffusion (one vectorized op run before the movement scan) is the only
writer that touches the whole array at once; everything else goes through
``set_temp`` (which clips to ``[TEMP_MIN, TEMP_MAX]``).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .elements import AMBIENT_TEMP, TEMP_MAX, TEMP_MIN, ElementId


class Grid:
    """2D grid of element IDs. Origin top-left; +y is down (gravity).

    The backing numpy array has shape ``(height, width)`` and dtype
    ``uint8``. Cell ``(x, y)`` is stored at ``array[y, x]``. The public
    API takes ``(x, y)`` in that order so callers do not have to remember
    the row-major layout.

    A parallel ``life`` array of the same shape holds optional per-cell
    lifetime state (used by FIRE/SMOKE). It defaults to 0 everywhere;
    non-living cells always have life 0.
    """

    _width: int
    _height: int
    _data: npt.NDArray[np.uint8]
    _life: npt.NDArray[np.uint8]
    _temp: npt.NDArray[np.int16]

    def __init__(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"width and height must be positive ({width=}, {height=})")
        self._width = width
        self._height = height
        self._data = np.zeros((height, width), dtype=np.uint8)
        self._life = np.zeros((height, width), dtype=np.uint8)
        self._temp = np.full((height, width), AMBIENT_TEMP, dtype=np.int16)

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    @property
    def array(self) -> npt.NDArray[np.uint8]:
        """Raw ``(height, width)`` uint8 view of element IDs.

        Intended read-only access for renderers; callers must not mutate.
        """
        return self._data

    @property
    def life(self) -> npt.NDArray[np.uint8]:
        """Raw ``(height, width)`` uint8 view of per-cell life state.

        Intended read-only access; mutate via :meth:`set_life` so bounds
        and clipping are handled consistently.
        """
        return self._life

    @property
    def temp(self) -> npt.NDArray[np.int16]:
        """Raw ``(height, width)`` int16 view of per-cell temperature.

        Intended read-only access (e.g. for the diffusion pass and the heat
        overlay); mutate via :meth:`set_temp` so clipping is applied
        consistently. The diffusion pre-pass assigns a freshly-computed array
        back to the grid's ``_temp`` directly (see :class:`Simulation.step`).
        """
        return self._temp

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
        edge should not raise). This only updates the element id; the cell's
        life entry is untouched. Callers that clear a cell should also call
        :meth:`set_life` with 0, and callers that create a FIRE/SMOKE cell
        should seed its life.
        """
        if not self.in_bounds(x, y):
            return
        self._data[y, x] = int(element_id)

    def get_life(self, x: int, y: int) -> int:
        """Return the per-cell life value at ``(x, y)`` as a plain ``int``.

        Raises ``IndexError`` if out of bounds.
        """
        if not self.in_bounds(x, y):
            raise IndexError(
                f"({x}, {y}) out of bounds for {self._width}x{self._height} grid"
            )
        return int(self._life[y, x])

    def set_life(self, x: int, y: int, value: int) -> None:
        """Set the per-cell life at ``(x, y)`` to ``value`` (clipped to uint8).

        Out-of-bounds writes are silently ignored to mirror :meth:`set`.
        Negative values clip to 0; values above 255 clip to 255.
        """
        if not self.in_bounds(x, y):
            return
        if value < 0:
            value = 0
        elif value > 255:
            value = 255
        self._life[y, x] = value

    def get_temp(self, x: int, y: int) -> int:
        """Return the temperature at ``(x, y)`` as a plain ``int``.

        Raises ``IndexError`` if out of bounds.
        """
        if not self.in_bounds(x, y):
            raise IndexError(
                f"({x}, {y}) out of bounds for {self._width}x{self._height} grid"
            )
        return int(self._temp[y, x])

    def set_temp(self, x: int, y: int, value: int) -> None:
        """Set the temperature at ``(x, y)`` (clipped to ``[TEMP_MIN, TEMP_MAX]``).

        Out-of-bounds writes are silently ignored to mirror :meth:`set` /
        :meth:`set_life`.
        """
        if not self.in_bounds(x, y):
            return
        if value < TEMP_MIN:
            value = TEMP_MIN
        elif value > TEMP_MAX:
            value = TEMP_MAX
        self._temp[y, x] = value

    def fill_circle(
        self, cx: int, cy: int, radius: int, element_id: ElementId | int
    ) -> None:
        """Fill every cell within ``radius`` (Euclidean disk) of ``(cx, cy)``.

        Cells outside the grid are silently clipped. ``radius == 0`` paints a
        single cell. ``radius < 0`` raises ``ValueError``. Painted cells have
        their life reset to 0 and their temperature reset to
        ``AMBIENT_TEMP`` (brushes that overwrite a burning cell should not
        leave stale life or heat behind); callers painting FIRE/SMOKE should
        seed life afterwards, and callers wanting a hot spawn-temp should set
        it afterwards, if they want either to persist.
        """
        if radius < 0:
            raise ValueError(f"radius must be non-negative ({radius=})")
        if radius == 0:
            self.set(cx, cy, element_id)
            self.set_life(cx, cy, 0)
            self.set_temp(cx, cy, AMBIENT_TEMP)
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
                    self._life[y, x] = 0
                    self._temp[y, x] = AMBIENT_TEMP


def migrate_grid(old: Grid, new: Grid) -> None:
    """Copy the overlapping region of ``old`` into ``new`` (ids AND life AND temp).

    The copied region is ``min(old.width, new.width) x min(old.height,
    new.height)``. Old content outside the overlap is cropped and lost
    (permanent — there is no undo). Cells in ``new`` outside the overlap are
    left untouched (they keep whatever they had before — typically the
    default EMPTY / life 0 / temp ``AMBIENT_TEMP``). ``old`` is read-only
    here; ``new`` is mutated in place.

    Pure / pygame-free -> unit-tested headlessly. Used by ``Game`` on window
    resize to preserve the player's scene.
    """
    w = min(old.width, new.width)
    h = min(old.height, new.height)
    if w > 0 and h > 0:
        new._data[:h, :w] = old._data[:h, :w]
        new._life[:h, :w] = old._life[:h, :w]
        new._temp[:h, :w] = old._temp[:h, :w]

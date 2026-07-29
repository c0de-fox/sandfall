"""Headless tests for the UI layer.

Only the pure pieces are covered here: the palette layout
(:func:`palette_layout`) and the click hit-testing (:meth:`UI.swatch_at` /
:meth:`UI.in_reserved_area`). The actual pixel rendering (``UI.draw``) is
verified manually through the running window and through the
``SANDFALL_FRAMES`` loop seam; it is intentionally not asserted pixel-by-pixel.

No real display is needed: importing :mod:`sandfall.ui` does not import pygame
(pygame is pulled in lazily inside ``UI.draw``), and ``UI.__init__`` makes no
pygame calls, so these tests run completely headless.
"""

from __future__ import annotations

from sandfall.config import WINDOW_HEIGHT, WINDOW_WIDTH
from sandfall.elements import ElementId
from sandfall.ui import PALETTE_BAR_HEIGHT, UI, Swatch, palette_layout


def _non_empty_element_ids() -> list[ElementId]:
    return [eid for eid in ElementId if eid != ElementId.EMPTY]


def test_palette_layout_one_swatch_per_element_plus_eraser() -> None:
    swatches = palette_layout(WINDOW_WIDTH, WINDOW_HEIGHT - PALETTE_BAR_HEIGHT)

    # One swatch per ElementId member: 7 real elements + 1 Eraser (EMPTY).
    assert len(swatches) == len(ElementId)
    # EMPTY is included (representing the Eraser swatch) — the set of ids
    # in the palette covers every member of the enum.
    assert {s.element_id for s in swatches} == set(ElementId)


def test_palette_layout_left_to_right_in_enum_order() -> None:
    swatches = palette_layout(WINDOW_WIDTH, WINDOW_HEIGHT - PALETTE_BAR_HEIGHT)

    # Real elements appear in ElementId ascending order, then the Eraser
    # (EMPTY) appended last.
    assert [s.element_id for s in swatches] == _non_empty_element_ids() + [
        ElementId.EMPTY
    ]
    # x positions strictly increase...
    xs = [s.x for s in swatches]
    assert xs == sorted(xs)
    # ...and no two swatches overlap horizontally (next starts at/after this
    # one's right edge). Pairwise zip intentionally drops the last element.
    for left, right in zip(swatches, swatches[1:], strict=False):
        assert left.x + left.w <= right.x


def test_palette_layout_uses_configured_swatch_size() -> None:
    swatches = palette_layout(WINDOW_WIDTH, WINDOW_HEIGHT - PALETTE_BAR_HEIGHT)

    for s in swatches:
        assert s.w == s.h == swatches[0].w


def test_swatch_contains_is_inclusive_top_left_exclusive_bottom_right() -> None:
    s = Swatch(ElementId.SAND, x=10, y=20, w=5, h=5)

    assert s.contains(10, 20)  # top-left corner is inside
    assert s.contains(14, 24)  # last inside pixel (w=5 -> x in [10,15))
    assert not s.contains(15, 20)  # one past right edge
    assert not s.contains(10, 25)  # one past bottom edge
    assert not s.contains(9, 20)  # left of edge
    assert not s.contains(10, 19)  # above edge


def test_ui_swatch_at_returns_correct_element() -> None:
    ui = UI(WINDOW_WIDTH, WINDOW_HEIGHT)

    for s in ui.swatches:
        # The swatch's center pixel must map back to its own element id.
        cx = s.x + s.w // 2
        cy = s.y + s.h // 2
        assert ui.swatch_at(cx, cy) == s.element_id


def test_ui_swatch_at_returns_none_outside_swatches() -> None:
    ui = UI(WINDOW_WIDTH, WINDOW_HEIGHT)

    # A point in the gap between the first two swatches hits nothing.
    first = ui.swatches[0]
    second = ui.swatches[1]
    gap_x = first.x + first.w  # first pixel of the padding gap
    assert gap_x < second.x
    assert ui.swatch_at(gap_x, first.y + first.h // 2) is None

    # A point well inside the playfield (above the palette) hits nothing.
    assert ui.swatch_at(WINDOW_WIDTH // 2, WINDOW_HEIGHT // 2) is None

    # A point in the palette strip but off to the right of all swatches.
    last = ui.swatches[-1]
    assert ui.swatch_at(last.x + last.w + 1, last.y + last.h // 2) is None


def test_ui_reserved_area_covers_only_the_bottom_strip() -> None:
    ui = UI(WINDOW_WIDTH, WINDOW_HEIGHT)

    # Just above the strip -> not reserved.
    assert not ui.in_reserved_area(0, ui.bar_y - 1)
    assert not ui.in_reserved_area(WINDOW_WIDTH // 2, 0)
    # Inside the strip (at and below bar_y) -> reserved.
    assert ui.in_reserved_area(0, ui.bar_y)
    assert ui.in_reserved_area(WINDOW_WIDTH // 2, WINDOW_HEIGHT - 1)


def test_palette_strip_lies_within_the_window() -> None:
    ui = UI(WINDOW_WIDTH, WINDOW_HEIGHT)

    assert ui.bar_y == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT
    for s in ui.swatches:
        assert 0 <= s.x
        assert s.x + s.w <= WINDOW_WIDTH
        assert 0 <= s.y
        assert s.y + s.h <= WINDOW_HEIGHT


def test_palette_layout_includes_exactly_one_eraser_appended_last() -> None:
    """The Eraser (ElementId.EMPTY) appears exactly once, at the right end."""
    swatches = palette_layout(WINDOW_WIDTH, WINDOW_HEIGHT - PALETTE_BAR_HEIGHT)

    erasers = [s for s in swatches if s.element_id == ElementId.EMPTY]
    assert len(erasers) == 1
    # The eraser is the last swatch (appended after the real elements).
    assert swatches[-1].element_id == ElementId.EMPTY


def test_swatch_at_on_eraser_returns_empty() -> None:
    """Clicking the Eraser swatch selects EMPTY so left-drag erases too."""
    ui = UI(WINDOW_WIDTH, WINDOW_HEIGHT)
    eraser = [s for s in ui.swatches if s.element_id == ElementId.EMPTY][0]
    cx = eraser.x + eraser.w // 2
    cy = eraser.y + eraser.h // 2

    assert ui.swatch_at(cx, cy) == ElementId.EMPTY


def test_grid_height_makes_palette_top_the_sim_floor() -> None:
    """The grid's bottom pixel row lands exactly on the palette's top edge.

    GRID_HEIGHT * CELL_SIZE == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT, so the
    grid spans only the area above the palette (elements pile ON the bar).
    This is the core geometry invariant for Phase 02; it is what guarantees
    ``UI.bar_y == 560`` lines up with the grid's bottom row.
    """
    from sandfall.config import CELL_SIZE, GRID_HEIGHT, SIM_AREA_HEIGHT

    # The grid's pixel height equals the simulation area height (no leftover).
    assert GRID_HEIGHT * CELL_SIZE == SIM_AREA_HEIGHT
    # ...and the simulation area is exactly the window minus the palette strip.
    assert GRID_HEIGHT * CELL_SIZE == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT
    # At the default 800x600 window + 40px palette bar this is 560 px, which
    # also equals UI.bar_y (the palette's top edge) — so the grid's bottom
    # row rests on the palette's top.
    assert GRID_HEIGHT * CELL_SIZE == 560

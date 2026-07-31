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

from sandfall.config import INITIAL_WINDOW_H, INITIAL_WINDOW_W
from sandfall.elements import ElementId
from sandfall.ui import PALETTE_BAR_HEIGHT, UI, Swatch, format_hud, palette_layout


def _non_empty_element_ids() -> list[ElementId]:
    return [eid for eid in ElementId if eid != ElementId.EMPTY]


def test_palette_layout_one_swatch_per_element_plus_eraser() -> None:
    swatches = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)

    # One swatch per ElementId member: 11 real elements + 1 Eraser (EMPTY) = 12
    # after Phase 03 added STEAM/ICE/LAVA/GLASS. The count tracks
    # ``len(ElementId)`` so it auto-adjusted when the enum grew 8 -> 12.
    assert len(swatches) == len(ElementId) == 12
    # EMPTY is included (representing the Eraser swatch) — the set of ids
    # in the palette covers every member of the enum.
    assert {s.element_id for s in swatches} == set(ElementId)


def test_palette_layout_left_to_right_in_enum_order() -> None:
    swatches = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)

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
    swatches = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)

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
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)

    for s in ui.swatches:
        # The swatch's center pixel must map back to its own element id.
        cx = s.x + s.w // 2
        cy = s.y + s.h // 2
        assert ui.swatch_at(cx, cy) == s.element_id


def test_ui_swatch_at_returns_none_outside_swatches() -> None:
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)

    # A point in the gap between the first two swatches hits nothing.
    first = ui.swatches[0]
    second = ui.swatches[1]
    gap_x = first.x + first.w  # first pixel of the padding gap
    assert gap_x < second.x
    assert ui.swatch_at(gap_x, first.y + first.h // 2) is None

    # A point well inside the playfield (above the palette) hits nothing.
    assert ui.swatch_at(INITIAL_WINDOW_W // 2, INITIAL_WINDOW_H // 2) is None

    # A point in the palette strip but off to the right of all swatches.
    last = ui.swatches[-1]
    assert ui.swatch_at(last.x + last.w + 1, last.y + last.h // 2) is None


def test_ui_reserved_area_covers_only_the_bottom_strip() -> None:
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)

    # Just above the strip -> not reserved.
    assert not ui.in_reserved_area(0, ui.bar_y - 1)
    assert not ui.in_reserved_area(INITIAL_WINDOW_W // 2, 0)
    # Inside the strip (at and below bar_y) -> reserved.
    assert ui.in_reserved_area(0, ui.bar_y)
    assert ui.in_reserved_area(INITIAL_WINDOW_W // 2, INITIAL_WINDOW_H - 1)


def test_palette_strip_lies_within_the_window() -> None:
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)

    assert ui.bar_y == INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT
    for s in ui.swatches:
        assert 0 <= s.x
        assert s.x + s.w <= INITIAL_WINDOW_W
        assert 0 <= s.y
        assert s.y + s.h <= INITIAL_WINDOW_H


def test_palette_layout_includes_exactly_one_eraser_appended_last() -> None:
    """The Eraser (ElementId.EMPTY) appears exactly once, at the right end."""
    swatches = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)

    erasers = [s for s in swatches if s.element_id == ElementId.EMPTY]
    assert len(erasers) == 1
    # The eraser is the last swatch (appended after the real elements).
    assert swatches[-1].element_id == ElementId.EMPTY


def test_swatch_at_on_eraser_returns_empty() -> None:
    """Clicking the Eraser swatch selects EMPTY so left-drag erases too."""
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)
    eraser = [s for s in ui.swatches if s.element_id == ElementId.EMPTY][0]
    cx = eraser.x + eraser.w // 2
    cy = eraser.y + eraser.h // 2

    assert ui.swatch_at(cx, cy) == ElementId.EMPTY


def test_palette_resolves_phase03_elements_and_fits_min_window() -> None:
    """Phase 03 added STEAM/ICE/LAVA/GLASS swatches.

    They appear in the palette (iterating ``ElementId`` auto-added them),
    each resolves via ``swatch_at`` at its center pixel, and the whole
    12-swatch row fits inside ``MIN_WINDOW_W`` (bumped to 384 so the wider
    palette still fits at the minimum window size).
    """
    from sandfall.config import MIN_WINDOW_W, PALETTE_PADDING, PALETTE_SWATCH

    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)

    new_elements = [ElementId.STEAM, ElementId.ICE, ElementId.LAVA, ElementId.GLASS]
    by_id = {s.element_id: s for s in ui.swatches}
    for eid in new_elements:
        assert eid in by_id, f"{eid!r} missing from palette"
        s = by_id[eid]
        cx = s.x + s.w // 2
        cy = s.y + s.h // 2
        assert ui.swatch_at(cx, cy) == eid

    # The full 12-swatch row fits within MIN_WINDOW_W at the minimum size.
    last = ui.swatches[-1]
    needed = last.x + last.w + PALETTE_PADDING  # right edge + a margin
    assert needed <= MIN_WINDOW_W, (needed, MIN_WINDOW_W)
    # And the documented math: 12 swatches, 11 gaps, 2 outer margins.
    assert 12 * PALETTE_SWATCH + 11 * PALETTE_PADDING + 2 * 8 <= MIN_WINDOW_W


def test_grid_height_makes_palette_top_the_sim_floor() -> None:
    """The grid's bottom pixel row lands exactly on the palette's top edge.

    GRID_HEIGHT * CELL_SIZE == INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT, so the
    grid spans only the area above the palette (elements pile ON the bar).
    This is the core geometry invariant for Phase 02; it is what guarantees
    ``UI.bar_y == 560`` lines up with the grid's bottom row.
    """
    from sandfall.config import CELL_SIZE, GRID_HEIGHT, SIM_AREA_HEIGHT

    # The grid's pixel height equals the simulation area height (no leftover).
    assert GRID_HEIGHT * CELL_SIZE == SIM_AREA_HEIGHT
    # ...and the simulation area is exactly the window minus the palette strip.
    assert GRID_HEIGHT * CELL_SIZE == INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT
    # At the default 800x600 window + 40px palette bar this is 560 px, which
    # also equals UI.bar_y (the palette's top edge) — so the grid's bottom
    # row rests on the palette's top.
    assert GRID_HEIGHT * CELL_SIZE == 560


def test_ui_resize_recomputes_bar_y_and_swatches() -> None:
    """UI.resize recomputes bar_y/swatch positions for the new window size.

    This is the headless contract for Phase 03's resizable-window support:
    after resize, the palette stays pinned to the bottom (bar_y tracks the
    new window height) and every swatch sits inside the new palette strip.
    """
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)
    initial_bar_y = ui.bar_y
    assert initial_bar_y == INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT

    new_w, new_h = INITIAL_WINDOW_W, INITIAL_WINDOW_H + 80
    ui.resize(new_w, new_h)

    # bar_y moved down with the taller window; palette still pinned to bottom.
    assert ui.bar_y == new_h - PALETTE_BAR_HEIGHT
    assert ui.bar_y == initial_bar_y + 80
    # Every swatch lies inside the new palette strip (y >= new bar_y, below
    # the new window's bottom edge).
    for s in ui.swatches:
        assert s.y >= ui.bar_y
        assert s.y + s.h <= new_h


def test_format_hud_includes_fps_brush_and_count() -> None:
    """The HUD line shows FPS, brush radius, and particle count.

    Pure (no pygame) — tests the :func:`format_hud` helper that
    :meth:`UI.draw` renders. Pins the exact format so the count is actually
    surfaced to the user and so the format is stable across the signature
    change.
    """
    # Representative inputs, including the empty-grid case (count == 0).
    assert format_hud(59.7, 3, 0) == "59 FPS  r=3  n=0"
    assert format_hud(60.0, 5, 1234) == "60 FPS  r=5  n=1234"
    # fps is truncated to int (int()), not rounded.
    assert format_hud(59.9, 1, 7) == "59 FPS  r=1  n=7"

"""Headless tests for the UI layer.

Only the pure pieces are covered here: the palette layout
(:func:`palette_layout`), the click hit-testing (:meth:`UI.item_at` /
:meth:`UI.in_reserved_area`), and the tooltip text carried by each
:class:`PaletteItem`. The actual pixel rendering (``UI.draw`` — including the
hover tooltip placement, the dimmed placeholder buttons, the active outline) is
verified manually through the running window and through the
``SANDFALL_FRAMES`` loop seam; it is intentionally not asserted pixel-by-pixel.

No real display is needed: importing :mod:`sandfall.ui` does not import pygame
(pygame is pulled in lazily inside ``UI.draw``), and ``UI.__init__`` makes no
pygame calls, so these tests run completely headless.
"""

from __future__ import annotations

from sandfall.config import INITIAL_WINDOW_H, INITIAL_WINDOW_W
from sandfall.elements import ElementId
from sandfall.ui import (
    PALETTE_BAR_HEIGHT,
    PALETTE_MARGIN,
    UI,
    PaletteItem,
    ToolId,
    format_hud,
    palette_layout,
)


def _non_empty_element_ids() -> list[ElementId]:
    return [eid for eid in ElementId if eid != ElementId.EMPTY]


def test_palette_layout_has_11_elements_then_3_tools() -> None:
    items = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)

    elements = [it for it in items if it.is_element]
    tools = [it for it in items if it.is_tool]
    # 11 real element swatches (EMPTY excluded) + 3 utility tools.
    assert len(elements) == len(ElementId) - 1 == 11
    # Element swatches appear in ElementId ascending order (EMPTY skipped).
    assert [it.element_id for it in elements] == _non_empty_element_ids()
    # Tools follow in the fixed order Eraser, Brush-shape, Magnifier.
    assert [it.tool for it in tools] == [
        ToolId.ERASER,
        ToolId.BRUSH_SHAPE,
        ToolId.MAGNIFY,
    ]
    # Exactly one discriminator set per item (the model's core invariant).
    for it in items:
        assert it.is_element != it.is_tool  # xor: one and only one is set


def test_palette_layout_left_to_right_in_enum_order() -> None:
    items = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)

    # x positions strictly increase left-to-right...
    xs = [it.x for it in items]
    assert xs == sorted(xs)
    # ...and no two items overlap horizontally (the next starts at/after this
    # one's right edge). The group gap is just extra space, so it does not
    # break monotonicity. Pairwise zip intentionally drops the last item.
    for left, right in zip(items, items[1:], strict=False):
        assert left.x + left.w <= right.x


def test_palette_layout_group_gap_separates_elements_and_tools() -> None:
    """The gap between the last element and the first tool is visibly wider
    than the normal inter-element padding (PALETTE_PADDING + PALETTE_GROUP_GAP).
    """
    from sandfall.config import PALETTE_GROUP_GAP, PALETTE_PADDING

    items = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)
    last_elem = next(it for it in reversed(items) if it.is_element)
    first_tool = next(it for it in items if it.is_tool)
    boundary_gap = first_tool.x - (last_elem.x + last_elem.w)
    normal_gap = items[1].x - (items[0].x + items[0].w)
    assert boundary_gap == PALETTE_PADDING + PALETTE_GROUP_GAP
    assert boundary_gap > normal_gap


def test_palette_layout_uses_configured_swatch_size() -> None:
    items = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)

    for it in items:
        assert it.w == it.h == items[0].w


def test_palette_item_contains_is_inclusive_top_left_exclusive_bottom_right() -> None:
    it = PaletteItem(x=10, y=20, w=5, h=5, tooltip="x", element_id=ElementId.SAND)

    assert it.contains(10, 20)  # top-left corner is inside
    assert it.contains(14, 24)  # last inside pixel (w=5 -> x in [10,15))
    assert not it.contains(15, 20)  # one past right edge
    assert not it.contains(10, 25)  # one past bottom edge
    assert not it.contains(9, 20)  # left of edge
    assert not it.contains(10, 19)  # above edge


def test_ui_item_at_returns_correct_item() -> None:
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)

    for item in ui.items:
        # The item's center pixel must map back to an item with the same
        # discriminator (element id for element items, tool for tool items).
        cx = item.x + item.w // 2
        cy = item.y + item.h // 2
        hit = ui.item_at(cx, cy)
        assert hit is not None
        if item.is_element:
            assert hit.element_id == item.element_id
        else:
            assert hit.tool == item.tool


def test_ui_item_at_returns_none_outside_items() -> None:
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)

    # A point in the gap between the first two items hits nothing.
    first = ui.items[0]
    second = ui.items[1]
    gap_x = first.x + first.w  # first pixel of the padding gap
    assert gap_x < second.x
    assert ui.item_at(gap_x, first.y + first.h // 2) is None

    # A point inside the WIDE group gap (between the last element and the
    # first tool) also hits nothing.
    last_elem = next(it for it in reversed(ui.items) if it.is_element)
    first_tool = next(it for it in ui.items if it.is_tool)
    mid_gap_x = (last_elem.x + last_elem.w + first_tool.x) // 2
    assert ui.item_at(mid_gap_x, last_elem.y + last_elem.h // 2) is None

    # A point well inside the playfield (above the palette) hits nothing.
    assert ui.item_at(INITIAL_WINDOW_W // 2, INITIAL_WINDOW_H // 2) is None

    # A point in the palette strip but off to the right of all items.
    last = ui.items[-1]
    assert ui.item_at(last.x + last.w + 1, last.y + last.h // 2) is None


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
    for it in ui.items:
        assert 0 <= it.x
        assert it.x + it.w <= INITIAL_WINDOW_W
        assert 0 <= it.y
        assert it.y + it.h <= INITIAL_WINDOW_H


def test_eraser_is_first_tool_not_last_element() -> None:
    """The Eraser moves OUT of the element group INTO the utility group.

    It appears exactly once, as the FIRST tool (right after the group gap),
    and is NOT present as an element swatch.
    """
    items = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)

    erasers = [it for it in items if it.tool == ToolId.ERASER]
    assert len(erasers) == 1
    tools = [it for it in items if it.is_tool]
    assert tools[0].tool == ToolId.ERASER  # Eraser is the first tool
    # And it is not also representable as an element item.
    assert erasers[0].is_element is False
    assert erasers[0].element_id is None


def test_item_at_on_eraser_returns_eraser_tool() -> None:
    """Hitting the Eraser returns a PaletteItem with tool == ERASER.

    The EMPTY mapping happens in Game._handle_events (so left-drag erases),
    NOT in the hit-test: item_at reports the tool, Game translates it.
    """
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)
    eraser = [it for it in ui.items if it.tool == ToolId.ERASER][0]
    cx = eraser.x + eraser.w // 2
    cy = eraser.y + eraser.h // 2

    hit = ui.item_at(cx, cy)
    assert hit is not None
    assert hit.tool == ToolId.ERASER
    assert hit.is_element is False


def test_palette_resolves_phase03_elements_and_fits_min_window() -> None:
    """Phase 03 added STEAM/ICE/LAVA/GLASS swatches; Phase 01 reorged the row
    into 14 items (11 elements + 3 tools) separated by a group gap.

    The Phase-03 elements still resolve via ``item_at`` at their center pixel,
    and the whole 14-item + group-gap row fits inside ``MIN_WINDOW_W``
    (bumped to 416 = 104 cols so the wider gap-separated palette still fits at
    the minimum window size).
    """
    from sandfall.config import (
        MIN_WINDOW_W,
        PALETTE_GROUP_GAP,
        PALETTE_PADDING,
        PALETTE_SWATCH,
    )

    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)

    new_elements = [ElementId.STEAM, ElementId.ICE, ElementId.LAVA, ElementId.GLASS]
    by_id = {it.element_id: it for it in ui.items if it.is_element}
    for eid in new_elements:
        assert eid in by_id, f"{eid!r} missing from palette"
        it = by_id[eid]
        cx = it.x + it.w // 2
        cy = it.y + it.h // 2
        hit = ui.item_at(cx, cy)
        assert hit is not None
        assert hit.element_id == eid

    # The full 14-item + group-gap row fits within MIN_WINDOW_W at the min size.
    last = ui.items[-1]
    assert last.x + last.w + PALETTE_MARGIN <= MIN_WINDOW_W
    # And the documented math: 14 items, 13 inter-item paddings, 1 group gap,
    # 2 outer margins.
    assert (
        14 * PALETTE_SWATCH
        + 13 * PALETTE_PADDING
        + PALETTE_GROUP_GAP
        + 2 * PALETTE_MARGIN
        <= MIN_WINDOW_W
    )


def test_palette_item_tooltips_are_names() -> None:
    """Each item carries a hover tooltip: the element name (.title()) for
    element swatches, the TOOL_TOOLTIPS value for tool buttons. Pure (the
    string is set in palette_layout) -> headlessly asserted.
    """
    items = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)
    by_elem = {it.element_id: it for it in items if it.is_element}
    assert by_elem[ElementId.SAND].tooltip == "Sand"
    assert by_elem[ElementId.WATER].tooltip == "Water"
    by_tool = {it.tool: it for it in items if it.is_tool}
    assert by_tool[ToolId.ERASER].tooltip == "Eraser"
    assert by_tool[ToolId.BRUSH_SHAPE].tooltip == "Brush Shape"
    assert by_tool[ToolId.MAGNIFY].tooltip == "Magnifier"


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


def test_ui_resize_recomputes_bar_y_and_items() -> None:
    """UI.resize recomputes bar_y / item positions for the new window size.

    This is the headless contract for Phase 03's resizable-window support:
    after resize, the palette stays pinned to the bottom (bar_y tracks the
    new window height) and every item sits inside the new palette strip.
    """
    ui = UI(INITIAL_WINDOW_W, INITIAL_WINDOW_H)
    initial_bar_y = ui.bar_y
    assert initial_bar_y == INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT

    new_w, new_h = INITIAL_WINDOW_W, INITIAL_WINDOW_H + 80
    ui.resize(new_w, new_h)

    # bar_y moved down with the taller window; palette still pinned to bottom.
    assert ui.bar_y == new_h - PALETTE_BAR_HEIGHT
    assert ui.bar_y == initial_bar_y + 80
    # Every item lies inside the new palette strip (y >= new bar_y, below
    # the new window's bottom edge).
    for it in ui.items:
        assert it.y >= ui.bar_y
        assert it.y + it.h <= new_h


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

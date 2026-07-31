# Phase 01: Palette reorg + tooltips (palette-item model + gap-separated layout)

## Objective

Replace the flat `Swatch`/`ElementId`-only palette with a `PaletteItem` model
that can represent either an element swatch or a tool button; lay out
`[11 elements] [group gap] [Eraser] [Brush-shape] [Magnifier]` in one bottom
row; dispatch clicks via a discriminating `item_at`; and show a hover tooltip on
every item. Brush-shape and Magnifier ship as **visibly-disabled placeholders**
(Eraser is functional). Bump `MIN_WINDOW_W` to fit the wider row.

## Depends On

none — this is the spine; Phases 02 and 03 build on its model.

## Can Parallelize With

none — defines `PaletteItem`/`ToolId`/`palette_layout` that 02 and 03 extend.

## Recommended Agent

@implementer — a type-change refactor across `ui.py` + `game.py` + `config.py`
+ `tests/test_ui.py`. Small edits, but the ripple into `_handle_events` and the
test rewrite are the careful part. mypy strict throughout (the
`element_id | None` / `tool | None` discriminators must narrow cleanly).

## Changes Required

- `src/sandfall/config.py` — add `PALETTE_GROUP_GAP`; bump `MIN_WINDOW_W`
  384 → 416 (and re-derive `MIN_GRID_COLS`); rewrite the `MIN_WINDOW_W` comment.
- `src/sandfall/ui.py` — add `ToolId` enum + `PaletteItem` dataclass (evolved
  from `Swatch`); rewrite `palette_layout` to return `list[PaletteItem]` with
  the group gap + 3 tool buttons; add `TOOL_TOOLTIPS`; rename `swatch_at` →
  `item_at` (returns `PaletteItem | None`); rename the `swatches` property →
  `items`; extend `UI.draw` to render tool buttons (Eraser functional, the
  other two dimmed placeholders) + hover tooltips.
- `src/sandfall/game.py` — update `_handle_events` to call `item_at` and dispatch
  (element select; ERASER → `selected_element = EMPTY`; BRUSH_SHAPE/MAGNIFY →
  no-op placeholder).
- `tests/test_ui.py` — rewrite the layout/hit-test tests to the `PaletteItem`
  API; add group-gap + tooltip + item-count assertions.

## Implementation Instructions

> Re-read each file before editing — line numbers are current as of the
> post-dormant-cells source and will not have shifted yet, but verify.

### 1. `src/sandfall/config.py`

**1a. Add `PALETTE_GROUP_GAP`** near the palette geometry block
(`config.py:47-55`):

```python
PALETTE_GROUP_GAP = 3 * PALETTE_PADDING  # 12 — extra space between the element
#                                        # group and the utility group, on top
#                                        # of the normal PALETTE_PADDING. Visually
#                                        # separates elements from tools in the
#                                        # single bottom row.
```

**1b. Bump `MIN_WINDOW_W` and rewrite its comment** (`config.py:65-75`). The new
palette has 14 items (11 elements + Eraser + Brush-shape + Magnifier):

```python
# Minimum window size. Width must fit the whole palette (14 items: 11 element
# swatches + Eraser + Brush-shape + Magnifier). Width math:
#   14 * PALETTE_SWATCH + 13 * PALETTE_PADDING + PALETTE_GROUP_GAP + 2 * PALETTE_MARGIN
#   = 14*24 + 13*4 + 12 + 2*8 = 336 + 52 + 12 + 16 = 416  (== 104 * CELL_SIZE)
# 416 is the next clean CELL_SIZE multiple above the needed 416, = 104 cols.
# Height must fit the 40px palette + a usable sim area (>= 40 cells == 160px)
# -> 200. The minimum is enforced by the compositor via Window.minimum_size
# (see Game.__init__); compute_grid_dims additionally floor-clamps the GRID
# cols/rows to MIN_GRID_* so a tiny window still has a usable grid.
MIN_WINDOW_W = 416
MIN_WINDOW_H = 200
MIN_GRID_COLS = MIN_WINDOW_W // CELL_SIZE  # 416 // 4 == 104
MIN_GRID_ROWS = (MIN_WINDOW_H - PALETTE_BAR_HEIGHT) // CELL_SIZE  # 160 // 4 == 40
```

> `compute_grid_dims` (`config.py:195-212`) needs NO change — it references
> `MIN_GRID_COLS`, which auto-updates. Palette height is unchanged.

### 2. `src/sandfall/ui.py`

**2a. Imports.** Add `enum` to the stdlib imports (top of file, near
`from dataclasses import dataclass` at `ui.py:17`):

```python
import enum
from dataclasses import dataclass
```

Add `PALETTE_GROUP_GAP` to the `from .config import (...)` block
(`ui.py:20-34`).

**2b. Add `ToolId` + `TOOL_TOOLTIPS`** (place above the `Swatch`/`PaletteItem`
dataclass, ~`ui.py:41`). Pure (no pygame):

```python
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
```

**2c. Evolve `Swatch` into `PaletteItem`** (`ui.py:42-58`). Keep the frozen,
slotted dataclass + `contains`; carry the rect + tooltip; hold the two
mutually-exclusive discriminators:

```python
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
```

> Keep the old name `Swatch` available as a deprecated alias ONLY if some
> external importer needs it — grep first (`rg -n "Swatch"`). At planning time
> the only users are `ui.py` + `test_ui.py`, both rewritten here, so a clean
> rename is fine. If you keep an alias, document it; prefer the clean rename.

**2d. Rewrite `palette_layout`** (`ui.py:61-86`) to return `list[PaletteItem]`
with the group gap + tool group:

```python
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
    so left-drag still erases.
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
                x, y, PALETTE_SWATCH, PALETTE_SWATCH,
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
                x, y, PALETTE_SWATCH, PALETTE_SWATCH,
                tooltip=TOOL_TOOLTIPS[tool],
                tool=tool,
            )
        )
        x += PALETTE_SWATCH + PALETTE_PADDING
    return items
```

**2e. Rename `swatch_at` → `item_at`** (`ui.py:159-164`) and the `swatches`
property → `items` (`ui.py:141-144`). Update the internal field name
`_swatches` → `_items` (and its uses in `__init__` `ui.py:122`, `resize`
`ui.py:138`). `item_at` returns `PaletteItem | None`:

```python
@property
def items(self) -> list[PaletteItem]:
    """The cached palette layout (read-only view)."""
    return self._items

def item_at(self, px: int, py: int) -> PaletteItem | None:
    """Return the palette item containing ``(px, py)``, or None."""
    for item in self._items:
        if item.contains(px, py):
            return item
    return None
```

> `in_reserved_area` (`ui.py:151-157`) and `bar_y` (`ui.py:146-149`) are
> UNCHANGED.

**2f. Extend `UI.draw`** (`ui.py:166-227`) to (a) render tool buttons and
(b) render a hover tooltip. Tool rendering reuses the existing Eraser-style
fill+border+glyph; Brush-shape ("B") and Magnifier ("Z") are rendered DIMMED
(placeholders) in this phase. Add two small config constants for the disabled
look (or inline literals — pin in reflection; recommend literals to avoid
bloating config):

- Rendering loop becomes: for each `item`, if `item.is_element` and not EMPTY →
  element color fill (`ELEMENTS[item.element_id].color`); else (a tool) →
  tool-button fill+border+glyph (Eraser uses `ERASER_SWATCH_COLOR`/border/"E";
  BRUSH_SHAPE/MAGNIFY use a dimmed fill, e.g. `(60,60,60)`, border `(40,40,40)`,
  glyphs "B"/"Z").
- Active outline (`ui.py:226-227`): an element item is active when
  `item.element_id == active`; the ERASER tool is active when
  `active == ElementId.EMPTY` (preserves today's eraser-highlight behavior).
  BRUSH_SHAPE/MAGNIFY are never active in Phase 01 (placeholders). Sketch:

```python
for item in self._items:
    rect = (item.x, item.y, item.w, item.h)
    if item.is_element and item.element_id != ElementId.EMPTY:
        pygame.draw.rect(screen, ELEMENTS[item.element_id].color, rect)
    else:
        # Tool button (Eraser functional; Brush-shape/Magnifier dimmed placeholders).
        tool = item.tool
        if tool == ToolId.ERASER:
            fill, border, glyph = ERASER_SWATCH_COLOR, ERASER_SWATCH_BORDER, ERASER_LABEL
        else:  # BRUSH_SHAPE / MAGNIFY placeholders
            fill, border, glyph = (60, 60, 60), (40, 40, 40), "B" if tool == ToolId.BRUSH_SHAPE else "Z"
        pygame.draw.rect(screen, fill, rect)
        pygame.draw.rect(screen, border, rect, 1)
        assert self._font is not None
        label = self._font.render(glyph, True, border)
        screen.blit(label, (item.x + (item.w - label.get_width()) // 2,
                            item.y + (item.h - label.get_height()) // 2))
    # Active outline.
    is_active = (item.is_element and item.element_id == active) or (
        item.tool == ToolId.ERASER and active == ElementId.EMPTY
    )
    if is_active:
        pygame.draw.rect(screen, HIGHLIGHT_COLOR, rect, 2)
```

- Hover tooltip: at the end of `draw`, read the cursor and render the hovered
  item's `.tooltip` near the cursor (or top-left of the palette strip). Use
  `pygame.mouse.get_pos()` (pygame is already imported locally, `ui.py:182`):

```python
mx, my = pygame.mouse.get_pos()
hit = self.item_at(mx, my)
if hit is not None:
    tip = self._font.render(hit.tooltip, True, FPS_COLOR)
    # Place just above the palette bar, left-aligned with the cursor (clamped).
    tx = max(PALETTE_MARGIN, min(mx, self._window_width - tip.get_width() - PALETTE_MARGIN))
    ty = self._bar_y - tip.get_height() - 2
    screen.blit(tip, (tx, ty))
```

> Pin the tooltip placement (above-bar vs floating-near-cursor) in the
> reflection after the SDL eyeball; above-bar is the recommended default (never
> overlaps the playfield). The tooltip TEXT is pure (`item.tooltip`), so it is
> headlessly asserted; only placement is visual.

### 3. `src/sandfall/game.py`

**3a. Update `_handle_events`** (`game.py:175-188`) to dispatch on
`PaletteItem`. Replace the `swatch_at` → `selected_element` block:

```python
elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
    mx, my = event.pos
    item = self._ui.item_at(mx, my)
    if item is not None:
        if item.is_element:
            assert item.element_id is not None
            self.selected_element = item.element_id
        elif item.tool == ToolId.ERASER:
            # Eraser maps to EMPTY so left-drag erases (behavior preserved).
            self.selected_element = ElementId.EMPTY
        elif item.tool == ToolId.BRUSH_SHAPE:
            pass  # Wired in Phase 02 (brush-shape cycle).
        elif item.tool == ToolId.MAGNIFY:
            pass  # Wired in Phase 03 (magnifier toggle).
```

Add `ToolId` to the `from .ui import ...` import (`game.py:53`):

```python
from .ui import PALETTE_BAR_HEIGHT, UI  # (PALETTE_BAR_HEIGHT only if already imported; check)
```
→
```python
from .ui import ToolId, UI
```

> The right-click erase path (`_erase_if_dragging`, `game.py:243-261`) is
> UNCHANGED — it already paints EMPTY via `paint_brush(..., ElementId.EMPTY)`.

### 4. `tests/test_ui.py`

Rewrite the layout/hit-test tests to the `PaletteItem` API. Concretely:

- **Imports** (`test_ui.py:16-18`): `Swatch` → `PaletteItem`, add `ToolId`.
- `test_palette_layout_one_swatch_per_element_plus_eraser` (line 25) → rename to
  `test_palette_layout_has_11_elements_then_3_tools`:

```python
def test_palette_layout_has_11_elements_then_3_tools() -> None:
    items = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)
    elements = [it for it in items if it.is_element]
    tools = [it for it in items if it.is_tool]
    assert len(elements) == len(ElementId) - 1 == 11   # EMPTY excluded
    assert [it.element_id for it in elements] == [
        eid for eid in ElementId if eid != ElementId.EMPTY
    ]  # ascending enum order
    assert [it.tool for it in tools] == [
        ToolId.ERASER, ToolId.BRUSH_SHAPE, ToolId.MAGNIFY
    ]
    # Exactly one discriminator set per item.
    for it in items:
        assert it.is_element != it.is_tool  # xor
```

- `test_palette_layout_left_to_right_in_enum_order` (line 37) → keep the
  strictly-increasing-x + no-overlap assertions, operating on `items`. Add a
  **group-gap** assertion: the gap between the last element and the first tool
  is `PALETTE_PADDING + PALETTE_GROUP_GAP` (visibly wider than the normal
  `PALETTE_PADDING` gaps between elements):

```python
def test_palette_layout_group_gap_separates_elements_and_tools() -> None:
    from sandfall.config import PALETTE_GROUP_GAP, PALETTE_PADDING
    items = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)
    last_elem = next(it for it in reversed(items) if it.is_element)
    first_tool = next(it for it in items if it.is_tool)
    boundary_gap = first_tool.x - (last_elem.x + last_elem.w)
    normal_gap = items[1].x - (items[0].x + items[0].w)
    assert boundary_gap == PALETTE_PADDING + PALETTE_GROUP_GAP
    assert boundary_gap > normal_gap
```

- `test_swatch_contains...` (line 61) → `test_palette_item_contains...` using
  `PaletteItem(x=10, y=20, w=5, h=5, tooltip="x", element_id=ElementId.SAND)`.
- `test_ui_swatch_at_returns_correct_element` (line 72) →
  `test_ui_item_at_returns_correct_item`: iterate `ui.items`, hit each center,
  assert element items map to their `element_id` and tool items to their `tool`.
- `test_ui_swatch_at_returns_none_outside_swatches` (line 82) → same shape on
  `item_at`.
- `test_palette_layout_includes_exactly_one_eraser_appended_last` (line 122) →
  `test_eraser_is_first_tool_not_last_element`: assert exactly one
  `ToolId.ERASER`, it is the first tool, and it is NOT in the element list.
- `test_swatch_at_on_eraser_returns_empty` (line 132) →
  `test_item_at_on_eraser_returns_eraser_tool`: hitting the Eraser returns a
  PaletteItem with `tool == ToolId.ERASER` (the EMPTY mapping happens in Game,
  not in the hit-test).
- `test_palette_resolves_phase03_elements_and_fits_min_window` (line 142) →
  update the width math to 14 items + group gap:

```python
    assert 14 * PALETTE_SWATCH + 13 * PALETTE_PADDING + PALETTE_GROUP_GAP + 2 * PALETTE_MARGIN <= MIN_WINDOW_W
    last = ui.items[-1]
    assert last.x + last.w + PALETTE_MARGIN <= MIN_WINDOW_W
```

- **New** tooltip test (pure — the tooltip string is set in `palette_layout`):

```python
def test_palette_item_tooltips_are_names() -> None:
    items = palette_layout(INITIAL_WINDOW_W, INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT)
    by_elem = {it.element_id: it for it in items if it.is_element}
    assert by_elem[ElementId.SAND].tooltip == "Sand"
    assert by_elem[ElementId.WATER].tooltip == "Water"
    by_tool = {it.tool: it for it in items if it.is_tool}
    assert by_tool[ToolId.ERASER].tooltip == "Eraser"
    assert by_tool[ToolId.BRUSH_SHAPE].tooltip == "Brush Shape"
    assert by_tool[ToolId.MAGNIFY].tooltip == "Magnifier"
```

- `test_grid_height_makes_palette_top_the_sim_floor` (line 171),
  `test_ui_resize_recomputes_bar_y_and_swatches` (line 191),
  `test_format_hud_includes_fps_brush_and_count` (line 215) → update
  `ui.swatches` → `ui.items` references; otherwise unchanged.

## Acceptance Criteria

- [ ] `palette_layout` returns 11 element `PaletteItem`s (enum ascending, EMPTY
      skipped) followed by 3 tool items (ERASER, BRUSH_SHAPE, MAGNIFY); exactly
      one discriminator set per item (headless test).
- [ ] A group gap of `PALETTE_PADDING + PALETTE_GROUP_GAP` separates the last
      element from the first tool, visibly wider than inter-element padding
      (headless test).
- [ ] `item_at` returns the correct `PaletteItem` for every item's center pixel
      and `None` outside the items (headless test).
- [ ] Clicking the Eraser tool still sets `selected_element = ElementId.EMPTY`
      so left-drag erases (behavior preserved; covered by existing
      `test_brush.py:143` + the new dispatch).
- [ ] Hovering any item surfaces its tooltip text (`item.tooltip` equals the
      element name `.title()` / the `TOOL_TOOLTIPS` value — headless test);
      the tooltip renders visually (SDL smoke).
- [ ] `MIN_WINDOW_W == 416` and the 14-item + group-gap row fits within it
      (headless test with the documented math).
- [ ] BRUSH_SHAPE and MAGNIFY buttons render (dimmed placeholders) and their
      clicks are no-ops (visual via SDL smoke; no crash).
- [ ] The full existing suite stays green.

## Verification Commands

```bash
# Phase-focused (pure helpers: layout, gap, hit-test, tooltips):
uv run pytest tests/test_ui.py tests/test_brush.py -v
# Import smoke:
uv run python -c "import sandfall"
# FULL suite -- regression guard (must stay green):
uv run pytest
# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src
# SDL smoke -- visual verification of gap layout, tooltips, placeholder buttons:
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
```

All commands must exit zero. Do NOT proceed to Phase 02 until all pass.

## Documentation Updates

- `README.md` — Controls: note the palette now has a utility group
  (Eraser/Brush-shape/Magnifier) and that hovering shows a tooltip. (Hotkeys
  `Tab`/`Z` are documented in their phases; here just mention the layout.)
- `docs/ARCHITECTURE.md` — UI section: `PaletteItem` model, `ToolId`, the
  gap-separated single-row layout, the pure/draw split for `palette_layout` /
  `item_at` / `TOOL_TOOLTIPS`, and the `MIN_WINDOW_W` math.

Both done as part of this phase's commit.

## Reflection & Commit

After implementation, write `01-palette-reorg-tooltips-reflection.md` in this
directory. Pin in it: (a) whether you kept `Swatch` as an alias or did a clean
rename; (b) the chosen tooltip placement (above-bar vs near-cursor); (c) whether
the two placeholder buttons' dim styling used config constants or literals.
Then make ONE atomic git commit covering all changes in this phase.

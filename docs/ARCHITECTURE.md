# Architecture

A contributor-facing guide to how sandfall works internally. For setup and
usage, see the [root README](../README.md) first.

## Overview

sandfall is a cellular automaton. Every frame the `Simulation` walks the grid
and asks each non-empty cell's **rule** how it wants to move; rules mutate the
grid and report back; the `Renderer` turns the grid into an image; the `Game`
scales it to the window and overlays the UI.

```
                       input (mouse / keys)
                              |
                              v
                            Game  ---------> LoopController (pause / step)
                           /  |  \
                  paint_brush  |   UI (palette + HUD)
                        |      |
                        v      |
                 Grid (ids + life) <--- Simulation.step (scan + rules)
                        |
                        v
                  Renderer (LUT) -> grid-sized Surface -> scaled to window
```

Module dependency sketch (arrows mean "imports / uses"):

```
__main__ -> game
game -> {config, elements, grid, simulation, renderer, brush, control, ui}
simulation -> {grid, elements, rules}
renderer -> {grid, elements, config}
brush -> {grid, elements, rules}            # for seed_*_life
ui -> {config, elements}
rules/* -> {grid, elements, rules/_common}
rules/__init__ -> rules/{sand,water,stone,wood,fire,smoke,plant}
```

`pygame` is deliberately imported only by the leaves that need a display
(`game`, `renderer`, and lazily inside `ui.UI.draw`), so the pure model
classes (`Grid`, `Simulation`, rules, `brush`, `control`, `ui` layout helpers)
are importable and testable headlessly.

## The simulation model: `Grid`

`Grid` (`grid.py`) is the entire world state. It holds two parallel numpy
`uint8` arrays, both shape `(height, width)` = `(140, 200)`:

- `array` — the **element id** of each cell (`0` = EMPTY, see `ElementId`).
- `life` — a **per-cell lifetime** counter for finite-duration elements
  (FIRE, SMOKE). Defaults to 0 everywhere; non-living cells always read 0.

Conventions:

- **Origin top-left; `+y` is down** (this is the direction of gravity).
- Cell `(x, y)` is stored at `array[y, x]` (row-major). The public API takes
  `(x, y)` in that order so callers never deal with the layout directly.
- Out-of-bounds *writes* (`set`, `set_life`, `fill_circle`) are silently
  clipped so a brush painting past an edge never raises; out-of-bounds *reads*
  (`get`, `get_life`) raise `IndexError`.

### Geometry: the palette bar is the simulation floor

The grid does **not** fill the whole window. It spans only the pixels above
the 40px palette bar (`SIM_AREA_HEIGHT = INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT`
= 560), so at the default window size
`GRID_HEIGHT * CELL_SIZE == INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT` exactly.
The grid's bottom pixel row lands on the palette's top edge, which means
falling elements pile *on* the bar instead of falling behind it.
`UI.bar_y` (`== INITIAL_WINDOW_H - PALETTE_BAR_HEIGHT == 560`) is the same
value, so painting is suppressed exactly where the palette begins and mouse
coordinates map cleanly via `mx // CELL_SIZE, my // CELL_SIZE`.

The window is **resizable**, so the *initial* constants above are just the
starting size; the current grid dims come from `compute_grid_dims` (see
[Window resizing](#window-resizing) below).

### The scan: `Simulation.step`

`Simulation.step` (`simulation.py`) advances the world by exactly one frame.
For each cell, bottom row to top row (`y` descending so a grain falls at most
one cell per step and cannot teleport through the grid in a single frame),
with the `x` direction **randomized per row** (left-to-right or right-to-left
with equal probability, to avoid a leftward bias):

1. Skip cells flagged in the `moved` guard (something moved *into* them
   earlier this same scan).
2. Skip EMPTY cells.
3. Look up the cell's rule in `RULES`. If there is none, skip it.
4. Call the rule. If it returns a destination `(dx, dy)`, mark
   `moved[dy, dx] = True` so that cell is not processed again this frame.

## The element model

Defined in `elements.py`:

- **`ElementId`** — an `IntEnum` of stable integer ids stored in the grid's
  `uint8` array: `EMPTY=0, SAND=1, WATER=2, STONE=3, WOOD=4, FIRE=5,
  SMOKE=6, PLANT=7` (the v1 set, unchanged) plus the Phase-03 temperature
  additions `STEAM=8, ICE=9, LAVA=10, GLASS=11`. The v1 docstring once said
  the enum was "defined in full; never add new members"; that was superseded
  by the temperature feature (user-approved). Existing values 0..7 are
  unchanged, so every LUT index (renderer color LUT, conductivity LUT) that
  the v1 code relies on stays stable; new members take 8..11. `uint8` holds
  up to 255, so there is room for more.
- **`Phase`** — `IntEnum` describing physical behavior: `SOLID` (static),
  `POWDER` (falls, piles), `LIQUID` (falls, spreads), `GAS` (rises,
  diffuses). Phase drives default behavior and the displacement test.
- **`Element`** — a frozen dataclass holding the static definition of one
  element kind: `id`, `name`, `color` (RGB), `density`, `phase`, and
  `flammability` (0.0 = never burns, 1.0 = always burns on contact).
- **`ELEMENTS`** — the registry `dict[ElementId, Element]` consulted for
  colors (renderer), density (displacement), and flammability (fire spread).

## The rule contract

This is the heart of the simulation. Every element's behavior is a function
registered in `RULES` (`rules/__init__.py`):

```python
UpdateFn = Callable[[Grid, int, int], "tuple[int, int] | None"]
```

**Signature.** Each `update_*` function takes `(grid, x, y)` — the grid and
the cell to step — and returns either:

- the **destination `(x, y)` the element moved into**, or
- `None` if it did not move this step.

**The rule performs its own swap.** The rule mutates the grid itself (via the
shared `_common.swap` helper) and then returns the destination. `Simulation.
step` reads only the return value to update the moved-this-frame guard. A rule
must not otherwise perturb cells in a way the caller cannot account for.

**Static elements are registered as explicit no-ops.** `STONE` and `WOOD`
have rules that just `return None`. This is functionally identical to having
no entry (`Simulation.step` would skip a missing entry via `RULES.get`), but
registering the no-op documents "this element is intentionally static" and
keeps the registry enumerating every element.

**Documented side-effect exception.** A rule normally marks movement only via
its single return value. `fire` and `plant` legitimately break this for
chain-reaction effects: fire *ignites* neighbors and spawns smoke, and plant
*grows* into an empty neighbor. These writes do not return a destination, so
a freshly ignited fire or newly grown plant may also be processed later in
the same bottom-to-top scan. With the tuned low probabilities this is the
intended "chain reaction" feel and is bounded by grid size. See the docstring
at the top of `rules/fire.py` for the rationale.

## The `life` array and `_common.swap`

`life` exists because the element id alone cannot encode "how much longer
this fire burns." FIRE and SMOKE carry a per-step countdown; when it hits
zero the cell becomes EMPTY.

The invariant that makes this work: **the `array` and `life` arrays must
always describe the same cell.** Every move must carry life along. To
guarantee that, **every move goes through `_common.swap`** (`rules/_common.py`),
which exchanges *both* the element ids and the life values of two cells.
Rules that *convert* a cell in place (wood -> fire, fire/smoke expiring to
EMPTY, igniting/growing) set life explicitly with `grid.set_life`.

Lifetime ranges are centralized so that a user-brushed fire and a
rule-ignited fire live for the same window of steps:

- `seed_fire_life()`  -> `random.randint(20, 40)` steps
- `seed_smoke_life()` -> `random.randint(60, 120)` steps

These are re-exported from `rules/__init__.py` and used by both the fire rule
and `brush.paint_brush` (otherwise painted fire would have life 0 and expire
on the very next step — the "painted fire dies instantly" bug).

`_common.can_displace(src_id, target_id)` is the density/phase swap test: a
cell is displacable if it is EMPTY, or if it holds a strictly lower-density
LIQUID (so denser powders/liquids sink through lighter liquids — this is how
sand sinks through water). Solids, gases, and same/higher-density liquids are
not displacable.

## Rendering

`Renderer` (`renderer.py`) turns a `Grid` into a pygame `Surface`:

1. At construction it builds a **color lookup table** — a `(num_elements, 3)`
   `uint8` array where row `int(ElementId.EMPTY)` is the window background
   color and every other row is the element's registered `color`.
2. Each frame, `grid_to_rgb` indexes that LUT by the grid's id array
   (`lut[grid.array]`) to produce an `(H, W, 3)` RGB image — one numpy op,
   no Python-level loops.
3. The image is transposed to pygame's column-major `(W, H, 3)` order and
   pushed onto a grid-sized `Surface` via `pygame.surfarray.blit_array`.
   `render` is **self-healing against resize**: if `_cell_surface`'s size
   differs from the grid's (the window was just resized), it reallocates the
   surface first so `blit_array` never sees a size mismatch. A single
   `Renderer` therefore serves any grid shape across the program's lifetime.
4. `Game._draw` scales that `(grid.width x grid.height)` surface up to
   `(grid.width * CELL_SIZE, grid.height * CELL_SIZE)` — the grid's whole-cell
   pixel size — with `pygame.transform.scale` (nearest-neighbor, so the pixel
   look stays crisp), then blits the UI on top. The screen is cleared to
   `BG_COLOR` first, so any leftover pixels (a window that isn't an exact
   whole-cell multiple, or the area below the scaled grid) show the
   background. The palette bar is then drawn over the bottom 40px — it is the
   simulation floor, so elements pile on it instead of falling behind it.

The LUT builder and the id -> RGB mapper are split out as pure numpy
functions so the color mapping is unit-testable without a display.

## Window resizing

The display uses the **`pygame.Window` API** (pygame-ce ≥ 2.5.2), not the
classic `pygame.display.set_mode`. The window is created **once** in
`Game.__init__` with `pygame.Window("Sandfall", size=..., resizable=True)`;
`Window.get_surface()` returns the render target and **auto-tracks the window
size**, and `Window.flip()` presents it. This matters because
`display.set_mode()` destroys and recreates the window on every call — calling
it on each resize event flickered (the window disappeared/reappeared) on
Wayland/X11 compositors. The `Window` API never recreates the window, so
resizing is flicker-free and Wayland-native.

`Game._apply_resize_if_changed` runs once per frame and **polls
`Window.size`** (robust across drivers/compositors, rather than relying on
`VIDEORESIZE`/`WINDOWRESIZED` events). When the size has changed it rebuilds
the scene without recreating the window:

1. **Recompute grid dims** via `compute_grid_dims(w, h)` (pure, headless-tested
   in `tests/test_config.py`). Cells stay square at `CELL_SIZE`: cols/rows are
   floor-divided so the grid is the largest whole-cell multiple that fits;
   leftover pixels become `BG_COLOR`. Rows exclude the 40px palette bar.
2. **Migrate content** via `migrate_grid(old, new)` (pure, headless-tested in
   `tests/test_grid.py`): the `min(old, new) x min(old, new)` overlap of
   *both* the element-id array and the life array is copied from the old grid
   into the new one. Old content outside the overlap is **cropped and lost
   permanently**; newly exposed cells stay at their default (EMPTY / life 0).
3. **Rebuild** the `Simulation` (its `moved` guard references the old grid's
   shape), refresh the screen-surface reference via `Window.get_surface()`
   (it has auto-tracked to the new size), and call `UI.resize(w, h)` to recompute
   `bar_y`, re-layout swatches, and invalidate the cached palette-bar surface so
   it redraws at the new width.

The minimum window size is enforced by the compositor via
`Window.minimum_size = (MIN_WINDOW_W, MIN_WINDOW_H)` (256 x 200, set in
`Game.__init__`); `compute_grid_dims` additionally floor-clamps the grid
cols/rows to `MIN_GRID_*` so a too-small window still has a usable grid.

The palette bar stays a fixed `PALETTE_BAR_HEIGHT` pinned to the bottom at
every size; `UI.in_reserved_area` and the mouse-mapping (`mx // CELL_SIZE,
my // CELL_SIZE`) both read the current `bar_y` so painting is suppressed
exactly where the palette begins regardless of the current window size.

`INITIAL_WINDOW_W` / `INITIAL_WINDOW_H` in `config.py` are the *starting*
window size (800 x 600); the *current* size lives as `Game` instance state
(`_window_w`, `_window_h`) and is updated by `_apply_resize_if_changed`.

## The `SANDFALL_FRAMES` testing seam

`Game.run` reads the `SANDFALL_FRAMES` environment variable once at startup
(via `_parse_frame_cap`). When set to a positive integer, the loop runs
exactly that many frames and then exits cleanly (returns 0); missing,
unparseable, or non-positive values disable the cap (run until the user
quits).

This lets automated checks exercise the full `SDL init -> render -> step ->
teardown` path headlessly, without a human driving the window, and without
the loop hanging forever waiting for a QUIT event.

## Adding a new element

Adding an element is a small, well-defined change touching five places:

1. **`elements.ElementId`** — add a new enum member. (The v1 docstring once
   guarded the enum with a "do not add members" note; the temperature
   feature already extended it 8 -> 12 with STEAM/ICE/LAVA/GLASS, so that
   note has been retired — adding members is now a supported operation.
   Keep existing values stable: new members take the next free integer so
   every LUT index the existing code relies on stays valid.)
2. **`elements.ELEMENTS`** — add an `Element` entry with `name`, `color`,
   `density`, `phase`, and (if relevant) `flammability`. The renderer picks
   up its color automatically via the LUT.
3. **`rules/<name>.py`** — write an `update_<name>` function implementing the
   rule contract above. Use `_common.swap` for every move and
   `_common.can_displace` for displacement tests; set `life` explicitly for
   any finite-duration element and expose a `seed_<name>_life` helper if the
   brush should be able to paint it.
4. **`rules/__init__.py`** — import the function and add it to the `RULES`
   dict. (Static solids get an explicit no-op rule.)
5. **Tests** — add a `tests/test_<name>.py` covering the rule's behavior
   (movement in each direction, displacement, interactions, lifetimes).

The palette UI (`ui.palette_layout`) iterates `ElementId` automatically, so a
new element appears in the bottom strip with no extra wiring.

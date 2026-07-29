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
the 40px palette bar (`SIM_AREA_HEIGHT = WINDOW_HEIGHT - PALETTE_BAR_HEIGHT`
= 560), so `GRID_HEIGHT * CELL_SIZE == WINDOW_HEIGHT - PALETTE_BAR_HEIGHT`
exactly. The grid's bottom pixel row lands on the palette's top edge, which
means falling elements pile *on* the bar instead of falling behind it.
`UI.bar_y` (`== WINDOW_HEIGHT - PALETTE_BAR_HEIGHT == 560`) is the same
value, so painting is suppressed exactly where the palette begins and mouse
coordinates map cleanly via `mx // CELL_SIZE, my // CELL_SIZE`.

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
  SMOKE=6, PLANT=7`. The enum is defined in full up front; it is the set of
  things that can ever exist in a cell.
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
4. `Game._draw` scales that 200 x 140 surface up to the 800 x 560 playfield
   (the 800 x 600 window minus the 40px palette bar) with
   `pygame.transform.scale` (nearest-neighbor, so the pixel look stays
   crisp), then blits the UI on top. The palette bar is then drawn over the
   bottom 40px — it is the simulation floor, so elements pile on it instead
   of falling behind it.

The LUT builder and the id -> RGB mapper are split out as pure numpy
functions so the color mapping is unit-testable without a display.

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

1. **`elements.ElementId`** — add a new enum member. (The enum is currently
   defined in full with a "do not add members" comment guarding the v1 set,
   so this is an intentional extension of that invariant — update the
   comment.)
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

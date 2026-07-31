# Architecture

A contributor-facing guide to how sandfall works internally. For setup and
usage, see the [root README](../README.md) first.

## Overview

sandfall is a cellular automaton. Every frame the `Simulation` walks the grid
and asks each non-empty cell's **rule** how it wants to move; rules mutate the
grid and report back; the `Renderer` turns the grid into an image; the `Game`
scales it to the window and overlays the UI.

```
                     input (mouse / keys; H toggles the heat overlay)
                              |
                              v
                           Game  ---------> LoopController (pause / step)
                          /  |  \
                 paint_brush  |   UI (palette + HUD)
                       |      |
                       v      |
           Grid (ids + life + temp) <--- Simulation.step
                       |              (thermal.diffuse_temps pre-pass, then scan + rules)
                       |
                       v
                 Renderer -----> grid-sized Surface -----> scaled to window
                 (color LUT, or thermal.thermal_to_rgb when the heat overlay is on)
```

Module dependency sketch (arrows mean "imports / uses"):

```
__main__ -> game
game -> {config, elements, grid, simulation, renderer, brush, control, ui}
simulation -> {grid, elements, rules, thermal}
renderer -> {grid, elements, config, thermal}
thermal -> {config, elements}            # pure numpy: no pygame import
brush -> {grid, elements, rules}         # for seed_*_life; sets temp via grid.set_temp
ui -> {config, elements}
rules/* -> {grid, elements, rules/_common}
rules/__init__ -> rules/{sand,water,stone,wood,fire,smoke,plant,steam,ice,lava,glass}
```

`pygame` is deliberately imported only by the leaves that need a display
(`game`, `renderer`, and lazily inside `ui.UI.draw`), so the pure model
classes (`Grid`, `Simulation`, `thermal`, rules, `brush`, `control`, `ui`
layout helpers) are importable and testable headlessly.

## The simulation model: `Grid`

`Grid` (`grid.py`) is the entire world state. It holds three parallel numpy
arrays, all shape `(height, width)` = `(140, 200)`:

- `array` — the **element id** of each cell (`uint8`, `0` = EMPTY, see
  `ElementId`).
- `life` — a **per-cell lifetime** counter (`uint8`) for finite-duration
  elements (FIRE, SMOKE, STEAM). Defaults to 0 everywhere; non-living cells
  always read 0.
- `temp` — the **per-cell temperature** (`int16`, degrees-C-like) added by
  the temperature feature. Defaults to `AMBIENT_TEMP` (20) everywhere and is
  clipped to `[TEMP_MIN, TEMP_MAX]` = `[-200, 3000]` on write. `int16` (not
  `uint8`) because sand melts near 1700 and freezing needs sub-zero; the
  band fits `int16` with enormous headroom.

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

The x scan is **dormant-cell-aware (active-region)**: instead of iterating
the full `range(width)` of each row, the scan computes the x indices that
are BOTH **active** AND non-empty with `np.nonzero(active[y] & (row != 0))[0]`
and visits only those. A cell whose `active` flag is False is *dormant* — it
provably cannot move or react next frame (nothing in its world changed) and
is skipped. An entirely-inactive row is skipped in a single numpy call. This
is a performance optimization only — a dormant cell's rule, when dispatched,
returned "no move" and drew no RNG, so the result is **identical** to the old
full-row scan. (Because the scan reads the raw `grid.array` directly, a cheap
mid-scan re-check re-reads the cell and skips it if it emptied/transformed
earlier in the same scan.) The heat-diffusion pre-pass stays whole-grid and
unchanged — it is one numpy op over the `(H, W)` `int16` field, and it MUST
stay whole-grid so dormant cells' temperatures still propagate (a heat source
reaching a dormant cell raises its temp, which wakes it).

Each `step` rebuilds the `active` array from scratch (an **overwrite**, not
`|=` — carrying the old set forward would let cells marked once stay active
forever and never sleep) from four **wake conditions**; a cell firing none
of them goes dormant:

1. **Movement / identity-change + dilation** — a cell that moved, changed
   identity (`data != data_before`), or is orthogonally adjacent to one
   (one-cell 4-neighborhood dilation), so eroding support / opening a hole
   wakes the cells above/beside to fall/flow.
2. **Temperature change** — a cell whose temperature changed (via diffusion
   or a rule) must be rescanned: phase transitions (water boil/freeze, wood
   ignite) check the cell's OWN temperature.
3. **FIRE / LAVA persistent heat sources + their neighborhood** — a clinging
   fire / a lava cell re-asserts its burn-temp and reacts each step but may
   neither move nor change identity nor (at burn-temp) change temp; without
   this rule fire/lava and their fuel neighbors would go dormant and
   combustion/reactions would never chain.
4. **Brush-painted / erased cells** — OR-marked into `active` between steps
   by `Grid.fill_circle` (the brush path) and consumed by the next scan; they
   are not carried into the next `active` set unless the sim dynamics woke
   them. (Erasing opens a hole; `fill_circle` marks the erased cell's
   neighborhood so the cells beside/above wake and fall/flow into it.)

`Grid.set` deliberately does NOT mark `active`: it sits on the hottest path
(`swap` calls it twice per move) and regressed a maximally-busy scene by
~30%. Wake correctness is fully preserved without it — `id_changed` (wake 1)
captures every cell `set` touched *during* a scan, the `Simulation.__init__`
bootstrap seeds the first frame from all non-empty cells, and `fill_circle`
marks the brush path. The net effect: a settled ~7,300-grain sand pile drops
from ~73 ms/frame to ~5–7 ms/frame (the movement front is ~0 once settled),
while a maximally-busy scene is roughly break-even with the prior scan
(everything is already active, so there is nothing to skip — the busy-scene
win is a separate, out-of-scope faster-rules lever).

## Temperature field

The `temp` array is advanced by a **separate vectorized heat-diffusion pass**
that lives in the pure `thermal` module and runs ONCE at the top of
`Simulation.step`, BEFORE the movement scan — so every rule below it reads a
freshly-diffused temperature. Keeping diffusion out of the per-cell scan is
what holds 60 FPS: it is one numpy op over the `(H, W)` `int16` field rather
than `O(cells)` of Python.

`thermal.diffuse_temps(temp, ids, cond_lut, cp_lut, rate)` advances the
temperature field one **conservative** face-flux (finite-volume) step with
per-cell heat capacity:

```
flux across each interior face = k_face * rate * (t_left - t_right)
k_face = (cond[left] + cond[right]) / 2          (arithmetic mean)
new_t  = t + (net signed face flux into the cell) / cp[cell]
```

- **Insulated walls** — only INTERIOR faces carry flux (edge cells simply have
  fewer faces), so no heat crosses the grid edge. No padding is used.
- **Conservation** — the signed face fluxes telescope to zero over the grid
  (every flux appears once negative and once positive), so total heat
  `sum(cp*temp)` is conserved up to the int16 round-to-nearest. This replaces
  the non-conservative own-conductivity stencil the model originally shipped
  with (which annihilated heat/cold at material boundaries).
- **Heat capacity / thermal inertia** — each material has a `cp` scalar
  (`config.CP_*`, mirrored on `Element.heat_capacity`); `div / cp` means
  high-cp materials (lava 5.0, water 4.0) change temperature slowly and low-cp
  gases (fire/smoke/steam 0.5) change fast. Every `CP_*` is > 0 (diffusion
  divides by cp).
- **Stability** of this explicit form (coefficient `rate*k/cp`) requires
  `rate * max(cond) / min(cp) <= 0.25`; the defaults (`DIFFUSION_RATE = 0.20`,
  max `COND_FIRE = 0.50`, min `CP_* = 0.5` → `0.20`) sit comfortably inside
  that bound, and `diffuse_temps` additionally clips the result to
  `[TEMP_MIN, TEMP_MAX]`. Computation is `float64` throughout; the result is
  rounded to nearest (`np.rint`, NOT truncated — truncation drained heat
  toward 0) and cast to `int16`. The function returns a NEW array and does not
  mutate the input; `Simulation.step` assigns the result back to `grid._temp`.
- **Conductivity + heat-capacity LUTs** — `thermal.build_conductivity_lut` and
  `thermal.build_heat_capacity_lut` mirror `renderer.build_color_lut`: each is
  a `(len(ElementId),)` `float64` array, row `int(eid)` is that material's
  `COND_*` / `CP_*` scalar, indexed by the grid's id array to get a per-cell
  field in one fancy-index. Sized from `len(ElementId)`, so they grow
  automatically when elements are added. `EMPTY` carries a small non-zero
  conductivity so heat propagates through air (otherwise fire could not warm
  fuel it is not adjacent to).

The `temp` array mirrors the `life` consistency contract exactly:
`get_temp`/`set_temp` mirror `get_life`/`set_life`; `_common.swap` carries
temp on every move; `Grid.fill_circle` resets temp to `AMBIENT_TEMP`
(mirrors zeroing life); `brush.paint_brush` sets each element's
`temp_spawn` afterward (mirrors life-seeding); `migrate_grid` copies the
temp overlap on resize. One new array, the same seams. The diffusion
pre-pass is the only writer that touches the whole array at once.

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
  element kind: `id`, `name`, `color` (RGB), `density`, `phase`,
  `flammability` (legacy — unused now that combustion is heat-driven; kept
  on the dataclass for backward compatibility), and the thermal fields added
  by the temperature feature:
  - `temp_spawn` — temperature a freshly painted/spawned cell starts at
    (`AMBIENT_TEMP` for most; hot for FIRE/LAVA, cold for ICE). Mirrors how
    `brush.paint_brush` seeds life for FIRE/SMOKE/STEAM.
  - `flashpoint` — auto-ignition threshold; a cell ignites (becomes FIRE)
    when its OWN temp exceeds it. `0` means NEVER (the default). Replaces the
    old probabilistic per-neighbor spread.
  - `conductivity` — heat conductivity scalar in `[0.0, 1.0]`, mirrored in
    the `COND_*` LUT.
  - `burn_temp` — temperature a FIRE cell (or other heat source) of this
    material holds while burning; the fire rule re-asserts it each step.
  - `melt_point` / `boil_point` / `freeze_point` / `condense_point` —
    phase-change thresholds. `0` means "this element does not undergo that
    transition" — except 0 is a VALID active threshold for water's
    `freeze_point` and ice's `melt_point` (water freezes at/below 0, ice
    melts above 0), so those rules are not guarded by a `> 0` predicate.
- **`ELEMENTS`** — the registry `dict[ElementId, Element]` consulted for
  colors (renderer), density (displacement), and all thermal behavior
  (conductivity, flashpoint, burn/spawn temp, phase-change thresholds).

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

**Reactive rules: transform own cell in place, return `None`.** A rule may
transform its OWN cell in place (set a new element id, life, and temp) and
return `None` instead of a destination. This is the documented mechanism for
**every** temperature-driven transition: WOOD/PLANT ignite to FIRE when
their own temp exceeds their `flashpoint`; WATER boils to STEAM / freezes to
ICE; SAND melts to GLASS; LAVA cools to STONE. Because such a transform does
not MOVE anything, the `moved`-this-frame guard is unaffected (its job is
"don't move a cell twice", and nothing moved). The transformed cell is not
marked in the guard, so it may be re-dispatched later in the same
bottom-to-top scan — this is intended (it lets chain reactions like
water → steam → condense → water cascade within a frame) and is bounded
because each transition consumes its own condition (e.g. water at 110°
becomes steam; the steam rule then runs but will not re-trigger unless its
temp crosses the *other* threshold). This generalizes the v1 "documented
side-effect exception" `fire.py` once relied on for spread/smoke into the
explicit, general transition mechanism.

**Combustion is heat-driven, not probabilistic.** Phase 02 removed the v1
`SPREAD_FACTOR` probabilistic neighbor-ignition loop. Fire is now a heat
SOURCE: it maintains a `burn_temp` (~800°) each step, the diffusion pre-pass
carries that heat outward, and a flammable fuel ignites ITSELF when its own
temp crosses its `flashpoint` — one physical cause (heat diffusion) instead
of two competing models. See `rules/fire.py` for the cling behavior that
keeps a fire cell next to fuel from rising away before the diffusion
pre-pass can raise the fuel to its flashpoint (otherwise combustion would
never chain).

## The `life` array and `_common.swap`

`life` exists because the element id alone cannot encode "how much longer
this fire burns." FIRE and SMOKE carry a per-step countdown; when it hits
zero the cell becomes EMPTY.

The invariant that makes this work: **the `array`, `life`, and `temp`
arrays must always describe the same cell.** Every move must carry all three
along. To guarantee that, **every move goes through `_common.swap`**
(`rules/_common.py`), which exchanges the element ids, life values, AND
temperatures of two cells. Rules that *convert* a cell in place (wood →
fire, water → steam, fire/smoke expiring to EMPTY, igniting/growing) set
life and temp explicitly with `grid.set_life` / `grid.set_temp`. The
`temp` array obeys the same contract; see [Temperature field](#temperature-field).

Lifetime ranges are centralized so that a user-brushed fire and a
rule-ignited fire live for the same window of steps:

- `seed_fire_life()`  -> `random.randint(20, 40)` steps
- `seed_smoke_life()` -> `random.randint(60, 120)` steps
- `seed_steam_life()` -> `random.randint(80, 160)` steps (steam lingers
  longer than smoke so it drifts visibly before condensing)

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

### Heat-overlay mode (`H`)

The temperature field is normally invisible — it has no effect on element
colors. Pressing **`H`** toggles `Game._heat_overlay`, which makes `_draw`
call `Renderer.render_heat` instead of `render`. `render_heat` paints the
temp field via `thermal.thermal_to_rgb` — a pure numpy map from the `int16`
temp field to an `(H, W, 3)` `uint8` image with the gradient
**deep blue (cold) → cyan → neutral gray (ambient) → yellow → red (hot)**.
The display band `[HEAT_VIZ_COLD, HEAT_VIZ_HOT]` (`-40`..`1000`) is mapped
to the full color span; temps outside the band saturate to the endpoint
color (clipped before coloring, so there is no `uint8` overflow).
`AMBIENT_TEMP` is the neutral pivot of the ramp on **both** sides, so an
all-ambient scene reads as a flat "no thermal activity" gray rather than a
tinted one.

`render_heat` reuses the same self-healing `_cell_surface` and the same
row-major → column-major `(W, H, 3)` transpose as `render` (the output
layout of `thermal_to_rgb` matches `grid_to_rgb` deliberately); only the
grid surface is swapped, so the palette + HUD remain visible and the player
can still select elements while watching heat flow. Like `grid_to_rgb`,
`thermal_to_rgb` is split out as a pure numpy function so the gradient
mapping is unit-tested headlessly.

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
   `density`, `phase`, and the thermal fields: `conductivity` (plus a
   matching `COND_<NAME>` constant in `config.py` and a row in
   `thermal.build_conductivity_lut`), `heat_capacity` (plus a matching
   `CP_<NAME>` constant > 0 in `config.py` and a row in
   `thermal.build_heat_capacity_lut` — diffusion divides by cp, so it must be
   positive), `temp_spawn` if it should paint
   hotter/colder than ambient (FIRE/LAVA/ICE), `flashpoint`/`burn_temp` if
   it is a fuel or a heat source, and whichever of `melt_point` /
   `boil_point` / `freeze_point` / `condense_point` drive its transitions
   (recall `0` means "no transition" except for water/ice where `0` is a
   valid active threshold). The renderer picks up its color automatically
   via the color LUT.
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

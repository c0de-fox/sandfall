# Phase 04: Heat visualization + docs (H overlay)

## Objective

Make the (otherwise-invisible) temperature field observable, and write up the
entire temperature feature. Add an **`H` key toggle** in `game.py` that switches
the renderer into a **heat-overlay mode** (blue→cyan→yellow→red by temp,
ambient-neutral) instead of element colors, backed by a pure
`thermal_to_rgb(temp)` helper in `thermal.py` and a `Renderer.render_heat` path.
Update `README.md` (Features + Controls) and `docs/ARCHITECTURE.md` (thermal
module, diffusion pre-pass, three-array Grid, reactive-rule relaxation, the 4
new elements, the heat-overlay path). Unit-test the gradient mapping headlessly.

## Depends On

03 (Phase changes + 4 new elements) — must have passed all its gates. The overlay
is the primary way to *see* the phase changes and the combustion chains the
prior phases added.

## Can Parallelize With

none — final phase; consolidates the feature in code and docs.

## Recommended Agent

@implementer for the code, then @docs-writer (or the same agent) for the
README/ARCHITECTURE pass. The gradient helper and the key handler are small;
the bulk of this phase is accurate documentation of Phases 01–03.

## Changes Required

- `src/sandfall/thermal.py` — add pure `thermal_to_rgb(temp) -> (H, W, 3)
  uint8` (blue→cyan→yellow→red, ambient-neutral).
- `src/sandfall/renderer.py` — add `Renderer.render_heat(grid)` (or a
  `heat=True` flag on `render`) that paints the temp field via
  `thermal_to_rgb` onto the same self-healing `_cell_surface`.
- `src/sandfall/game.py` — add a `_heat_overlay: bool` toggle; bind `H` in
  `_handle_events`; branch in `_draw` between `render` and `render_heat`.
- `tests/test_thermal.py` — headless gradient-mapping assertions.
- `tests/test_renderer.py` — `render_heat` returns a grid-sized Surface.
- `README.md` — Features (temperature field, phase changes, 4 new elements,
  rewritten Fire row); Controls (`H` overlay row).
- `docs/ARCHITECTURE.md` — full thermal section.

## Implementation Instructions

> Re-read `thermal.py`, `renderer.py` (`render` + `grid_to_rgb`), `game.py`
> (`_handle_events` KEYDOWN at `game.py:154-160`, `_draw` at `game.py:253-271`),
> `README.md`, `docs/ARCHITECTURE.md` before editing.

### 1. `src/sandfall/thermal.py`

**1a. Add `thermal_to_rgb`.** A pure numpy mapping from the `int16` temp field to
an `(H, W, 3) uint8` RGB image. Gradient: cold (blue) → ambient (neutral
gray/dark) → warm (yellow) → hot (red). Clamp the temp to a display band
`[HEAT_VIZ_COLD, HEAT_VIZ_HOT]` (e.g. -40 .. 1000) so the mapping uses its full
color range across the interesting temperatures; everything outside is saturated
to the endpoint color. `AMBIENT_TEMP` maps to a neutral midpoint so a room-temp
scene reads as "nothing happening":

```python
def thermal_to_rgb(temp: npt.NDArray[np.int16]) -> npt.NDArray[np.uint8]:
    """Map a temperature field to an ``(H, W, 3)`` uint8 RGB image.

    Gradient: blue (cold) -> cyan -> neutral (ambient) -> yellow -> red (hot).
    The temp range is clamped to ``[HEAT_VIZ_COLD, HEAT_VIZ_HOT]`` so the full
    color span covers the interesting temperatures; out-of-band cells saturate
    to the endpoint color. ``AMBIENT_TEMP`` maps to a neutral gray so an
    all-ambient scene reads as 'no thermal activity'. Pure / pygame-free ->
    unit-tested headlessly. Output layout matches :func:`renderer.grid_to_rgb`
    (row-major ``(H, W, 3)``) so the renderer can transpose it the same way.
    """
    lo = float(HEAT_VIZ_COLD)
    hi = float(HEAT_VIZ_HOT)
    t = np.clip(temp.astype(np.float64), lo, hi)
    # Normalize to [0, 1] across the display band, with ambient at 0.5-ish.
    f = (t - lo) / (hi - lo)            # 0=cold .. 1=hot
    h, w = temp.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    # Piecewise gradient: blue -> cyan -> (neutral) -> yellow -> red.
    cold = (1.0 - np.clip(f * 2.0, 0.0, 1.0))      # 1 at f=0 .. 0 at f>=0.5
    hot = np.clip((f - 0.5) * 2.0, 0.0, 1.0)        # 0 at f<=0.5 .. 1 at f=1
    mid = 1.0 - np.abs(f - 0.5) * 2.0               # peaks at ambient
    # Blue channel: strong when cold, fades as it warms.
    rgb[..., 2] = np.clip(cold * 255.0 + mid * 40.0, 0, 255).astype(np.uint8)
    # Red channel: strong when hot, faint when cold.
    rgb[..., 0] = np.clip(hot * 255.0 + mid * 40.0, 0, 255).astype(np.uint8)
    # Green channel: cyan (cold) and yellow (hot) both raise green; neutral low.
    rgb[..., 1] = np.clip(cold * 180.0 + hot * 200.0 + mid * 30.0, 0, 255).astype(np.uint8)
    return rgb
```

Add the display-band constants to `config.py`:

```python
# Heat-overlay display band (Phase 04). Maps the temp field's full color range
# across [HEAT_VIZ_COLD, HEAT_VIZ_HOT]; temps outside saturate to the endpoint.
HEAT_VIZ_COLD = -40
HEAT_VIZ_HOT = 1000
```

(The exact gradient is a starting point — the implementer may retune the
channel mixes for a prettier ramp; pin the final formula in the reflection. The
contract is: monotone-ish cold→hot, ambient reads as neutral, output `(H,W,3)
uint8`, pure function.)

### 2. `src/sandfall/renderer.py`

**2a. Add `render_heat`.** Mirror `render` (`renderer.py:70-81`) but index
`thermal_to_rgb(grid.temp)` instead of `grid_to_rgb(grid, self._lut)`. Reuse the
same self-healing `_cell_surface`:

```python
from .thermal import thermal_to_rgb
...
def render_heat(self, grid: Grid) -> pygame.Surface:
    """Paint the grid's TEMPERATURE field (heat-overlay mode) and return it.

    Same surface/sizing contract as :meth:`render`: returns the grid-sized
    ``_cell_surface`` (reallocated on a size mismatch), mutated in place by
    ``blit_array``. Used by ``Game._draw`` when the heat-overlay toggle is on.
    """
    if self._cell_surface.get_size() != (grid.width, grid.height):
        self._cell_surface = pygame.Surface((grid.width, grid.height))
    rgb = thermal_to_rgb(grid.temp)            # (H, W, 3)
    rgb_t = np.transpose(rgb, (1, 0, 2))       # (W, H, 3) column-major
    pygame.surfarray.blit_array(self._cell_surface, rgb_t)
    return self._cell_surface
```

(No new state on `Renderer`; the toggle lives on `Game`. A `heat: bool` flag on
`render` is an acceptable alternative — pick one and stay consistent; the
separate method keeps each path readable.)

### 3. `src/sandfall/game.py`

**3a. Add the toggle state.** Declare `_heat_overlay: bool` (near the other
instance attrs, `game.py:76-91`) and initialize `self._heat_overlay = False`
in `__init__`.

**3b. Bind the `H` key** in the `KEYDOWN` branch (`game.py:154-160`), alongside
SPACE/N/ESC:

```python
elif event.key == pygame.K_h:
    self._heat_overlay = not self._heat_overlay
```

**3c. Branch in `_draw`** (`game.py:253-271`). Replace the single
`small = self._renderer.render(self._grid)` with a branch:

```python
if self._heat_overlay:
    small = self._renderer.render_heat(self._grid)
else:
    small = self._renderer.render(self._grid)
```

The rest of `_draw` (scale + blit + UI overlay) is unchanged — the heat overlay
replaces only the grid surface, not the palette/HUD, so the player can still
select elements while viewing heat. Optionally show a "HEAT" indicator in the
HUD when the overlay is on (mirror the PAUSED indicator in `ui.py:184-187`);
this is a nice-to-have, not an acceptance criterion.

### 4. Tests

**4a. `tests/test_thermal.py`** — headless gradient assertions:

```python
def test_thermal_to_rgb_shape_and_dtype():
    temp = np.full((4, 5), 20, dtype=np.int16)
    rgb = thermal_to_rgb(temp)
    assert rgb.shape == (4, 5, 3)
    assert rgb.dtype == np.uint8

def test_thermal_to_rgb_hot_is_redder_than_cold():
    cold = np.full((1, 1), -40, dtype=np.int16)
    hot = np.full((1, 1), 1000, dtype=np.int16)
    rc = thermal_to_rgb(cold)[0, 0]
    rh = thermal_to_rgb(hot)[0, 0]
    assert rh[0] > rc[0]   # hot has more red
    assert rc[2] > rh[2]   # cold has more blue

def test_thermal_to_rgb_saturates_outside_band():
    from sandfall.config import HEAT_VIZ_HOT
    at_band = thermal_to_rgb(np.array([[HEAT_VIZ_HOT]], dtype=np.int16))[0, 0]
    above = thermal_to_rgb(np.array([[HEAT_VIZ_HOT + 5000]], dtype=np.int16))[0, 0]
    assert tuple(at_band) == tuple(above)   # saturates, no overflow

def test_thermal_to_rgb_ambient_is_neutral():
    from sandfall.config import AMBIENT_TEMP
    rgb = thermal_to_rgb(np.full((1, 1), AMBIENT_TEMP, dtype=np.int16))[0, 0]
    # Neutral: no channel maxed out (not pure red/blue).
    assert rgb[0] < 250 and rgb[2] < 250
```

**4b. `tests/test_renderer.py`** — `render_heat` returns a grid-sized surface
(reuse the session-scoped dummy-driver fixture at `test_renderer.py:23-38`):

```python
def test_renderer_render_heat_returns_grid_sized_surface():
    grid = Grid(GRID_WIDTH, GRID_HEIGHT)
    grid.set_temp(0, 0, 900)
    renderer = Renderer()
    surf = renderer.render_heat(grid)
    assert surf.get_size() == (GRID_WIDTH, GRID_HEIGHT)
```

### 5. `README.md`

- **Features intro** (`README.md:7-8`): "seven elements" → "twelve elements with
  a per-cell **temperature field**: heat diffuses, fuels ignite above their
  flashpoint, and materials boil / freeze / melt / condense."
- **Features table** (`README.md:16-24`): rewrite the **Fire** row to "Gas-like
  heat source. Holds a burn-temp while it has life; the diffusion pass carries
  that heat outward; flammable neighbors (wood, plant) ignite themselves when
  their own temp exceeds their flashpoint. Emits smoke and rises." Add rows for
  **Steam**, **Ice**, **Lava**, **Glass** describing their behavior (steam
  rises/condenses; ice melts; lava flows/cools/reacts with water; glass is made
  by melting sand). Add a short paragraph noting the temperature field + phase
  changes.
- **Controls table** (`README.md:35-45`): add the row
  `| **H** | Toggle the heat-map overlay (blue = cold, red = hot; ambient is neutral). The element palette and HUD stay visible. |`

### 6. `docs/ARCHITECTURE.md`

Write the thermal feature up in one coherent pass. Concretely:

- **Overview diagram** (`ARCHITECTURE.md:13-26`): add the `thermal` module and
  the diffusion pre-pass arrow (`Simulation.step` → `thermal.diffuse_temps`
  before the scan); note the three-array `Grid` (id + life + temp).
- **The simulation model: `Grid`** (`ARCHITECTURE.md:46-74`): add the third
  array `_temp` (`int16`, defaults to `AMBIENT_TEMP`, clipped to
  `[TEMP_MIN, TEMP_MAX]`); note `get_temp`/`set_temp` mirror `get_life`/`set_life`
  and that `swap`/`fill_circle`/`migrate_grid`/`paint_brush` carry temp exactly
  as they carry life.
- **New "Temperature field" section** (after the scan section,
  `ARCHITECTURE.md:80-94`): describe the diffusion pre-pass — `diffuse_temps`
  runs once at the top of `Simulation.step` BEFORE the movement scan; the
  4-neighborhood Laplacian `new = temp + rate*cond[cell]*(sum-4*temp)`;
  edge-padded insulated walls; stability `rate*max(cond) <= 0.25`; the
  conductivity LUT (`build_conductivity_lut`) mirrors `build_color_lut`.
- **The element model** (`ARCHITECTURE.md:95-110`): add the thermal `Element`
  fields (`temp_spawn`, `flashpoint`, `conductivity`, `burn_temp`, the transition
  thresholds); note the 12 members and the new STEAM/ICE/LAVA/GLASS.
- **The rule contract** (`ARCHITECTURE.md:112-145`): **formalize** the
  reactive-rule relaxation (a rule may transform its own cell in place and
  return `None`) as the documented mechanism for temp-driven transitions
  (wood/plant ignition, water boil/freeze, sand melt, lava cool) — generalizing
  the `fire.py:14-19` exception. Note the `moved` guard is unaffected (transforms
  don't move anything). Note Phase 02 replaced probabilistic `SPREAD_FACTOR`
  spread with heat-driven combustion.
- **The `life` array section** (`ARCHITECTURE.md:147-174`): rename/extend to
  cover the temp array too, or add a parallel "The `temp` array" subsection.
- **Rendering** (`ARCHITECTURE.md:176-202`): document `thermal_to_rgb` + the
  `render_heat` path and the `H` toggle.
- **"Adding a new element"** (`ARCHITECTURE.md:262-285`): the recipe now also
  covers setting thermal fields (`conductivity` in `COND_*` + the LUT,
  `flashpoint`/transition thresholds, `temp_spawn`) and noting the enum-members
  comment was lifted in Phase 03.

## Acceptance Criteria

- [ ] `thermal.thermal_to_rgb` is pure, returns `(H, W, 3) uint8`, is hotter-red
      / colder-blue, saturates outside the display band without overflow, and
      reads ambient as neutral (tests pass).
- [ ] `Renderer.render_heat` returns the grid-sized `_cell_surface` (self-heals
      on resize like `render`) (test passes).
- [ ] Pressing `H` toggles `_heat_overlay`; `_draw` switches between `render` and
      `render_heat`; the palette/HUD remain visible in both modes.
- [ ] `README.md` Features describe twelve elements + the temperature field +
      phase changes; the Fire row describes heat-source behavior; the Controls
      table has the `H` row.
- [ ] `docs/ARCHITECTURE.md` documents the thermal module, the diffusion
      pre-pass, the three-array Grid, the reactive-rule relaxation, the 4 new
      elements, and the heat-overlay render path; the "Adding a new element"
      recipe covers thermal fields.
- [ ] All six gates exit zero. This is the final phase of the temperature plan.

## Verification Commands

```bash
# Phase-specific (pure helper + render path):
uv run pytest tests/test_thermal.py tests/test_renderer.py -v
# Confirm the H toggle wiring exists:
rg -n 'K_h|_heat_overlay|render_heat' src/sandfall/game.py src/sandfall/renderer.py

# The six gates (all must exit zero):
uv run python -c "import sandfall"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall
#   (headless fallback: SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall)
#   Manual check on DISPLAY=:1: paint FIRE/LAVA, press H, confirm the heat halo
#   spreads and recedes as fuels ignite and burn out; press H again to return to
#   the normal element view.
```

All commands must exit zero. The plan is complete when all pass.

## Documentation Updates

- `README.md` — Features + Controls (described above).
- `docs/ARCHITECTURE.md` — full thermal section (described above).

Both done as part of this phase's commit.

## Reflection & Commit

After implementation, write `04-heat-viz-docs-reflection.md`. Include the final
gradient formula you settled on (the channel mixes above are a starting point)
and any tuning needed to make ambient read as "neutral" on your monitor. Then
make ONE atomic git commit covering all changes in this phase. This is the final
phase of the temperature plan — note in the reflection whether the whole feature
(phases 01–04) hangs together in a manual playthrough (fire chains, water cycle,
lava+water, sand→glass, heat overlay).

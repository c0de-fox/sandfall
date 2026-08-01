# Phase 02: Heatmap enhancements — temperature colorbar + sparse flow arrows

## Objective

Make the H (heatmap) mode legible and make the convection currents VISIBLE.
Three additions, all UI overlays in H mode that do NOT affect the simulation:

1. A per-step `_flow` direction array recorded during `Simulation.step` (one
   `uint8` write per moved cell) and exposed via a `Simulation.flow` property.
2. Two pure numpy helpers: `flow_arrow_samples(flow, stride)` in `renderer.py`
   (block-averaged dominant-flow arrows) and `build_colorbar_gradient(height)`
   in `thermal.py` (the exact `thermal_to_rgb` gradient column) — both headlessly
   unit-testable.
3. A `Game._draw_heat_overlays` method (called from `_draw` when
   `self._heat_overlay`) that draws the cached colorbar + degree markers on the
   right edge and the sparse semi-transparent flow arrows on a cached SRCALPHA
   overlay.

## Depends On

Phase 01 — the flow arrows visualize the convection currents Phase 01 creates.
Without convection, intra-phase movement is too sparse to be worth overlaying.

## Can Parallelize With

none — depends on Phase 01.

## Recommended Agent

@implementer — a small `_flow` addition to `Simulation.step`, two pure numpy
helpers, and one new `Game` render method with two cached surfaces. Re-read every
cited file before editing (line numbers below are current at planning time and
may have drifted). Read `00-overview.md` first. The arrow-direction averaging +
threshold and the colorbar placement are the tunable unknowns (pin final values
in the reflection).

## Changes Required

- `src/sandfall/simulation.py` — add the `FLOW_*` direction-code constants + a
  `_flow_code(ddx, ddy)` helper; allocate `self._flow` in `__init__`
  (`simulation.py:93-105`); zero + (re)allocate it at the start of `step()`
  (`simulation.py:111-126`); record the direction when a rule returns a
  destination (`simulation.py:154-157`); add a `flow` property.
- `src/sandfall/thermal.py` — add `build_colorbar_gradient(height)` after
  `thermal_to_rgb` (`thermal.py:232-275`); it reuses `thermal_to_rgb` on a 1-D
  temp ramp. `HEAT_VIZ_COLD`/`HEAT_VIZ_HOT`/`AMBIENT_TEMP` are already imported
  (`thermal.py:54-56,60`); no new import.
- `src/sandfall/renderer.py` — add `flow_arrow_samples(flow, stride=10)` near the
  other pure helpers (`renderer.py:27-52`); import the `FLOW_*` codes from
  `.simulation`. `numpy` is already imported (`renderer.py:17`).
- `src/sandfall/game.py` — add `HEAT_VIZ_COLD`, `HEAT_VIZ_HOT`, `AMBIENT_TEMP`
  to the config import (`game.py:33-49`); add two cached-surface fields
  (`_colorbar_surf`, `_arrow_overlay`) initialized in `__init__`
  (`game.py:108-139`); call `self._draw_heat_overlays(scaled)` from `_draw` when
  `self._heat_overlay` (`game.py:334-340`); add the `_draw_heat_overlays` method
  (near `_draw_magnifier`, `game.py:369`).
- `tests/test_simulation.py` — add a test that `Simulation.flow` records the
  direction of a moved cell.
- `tests/test_renderer.py` — add a test for `flow_arrow_samples`.
- `tests/test_thermal.py` — add a test for `build_colorbar_gradient`.

## Implementation Instructions

> Re-read each file before editing — line numbers below are current at planning
> time and may have drifted.

### 1. `src/sandfall/simulation.py` — the `_flow` array + direction codes

**1a. Add the direction-code constants + helper** near the top of the module
(after the imports, before `_dilate` at `simulation.py:16`). These are the
protocol `renderer.flow_arrow_samples` consumes (imported there).

```python
# Per-cell flow direction recorded during the movement scan, for the H-mode
# flow-arrow overlay. Codes are uint8; 0 means "no movement this step". The
# renderer (flow_arrow_samples) imports these and maps each to a unit vector.
FLOW_NONE = 0
FLOW_UP = 1      # dy < 0  (toward the top of the grid; +y is down)
FLOW_DOWN = 2    # dy > 0
FLOW_LEFT = 3    # dx < 0
FLOW_RIGHT = 4   # dx > 0


def _flow_code(ddx: int, ddy: int) -> int:
    """Map a movement delta (dest - source) to a flow direction code.

    Vertical-preferred on diagonals: a down-diagonal move (e.g. water flowing
    down-left, delta (-1, +1)) records DOWN (the dominant gravity/convection
    direction). This keeps convection (up) and gravity flow (down) legible as
    clean vertical arrows; horizontal spread records LEFT/RIGHT.
    """
    if ddy < 0:
        return FLOW_UP
    if ddy > 0:
        return FLOW_DOWN
    if ddx < 0:
        return FLOW_LEFT
    if ddx > 0:
        return FLOW_RIGHT
    return FLOW_NONE  # dest == source (rules never return this, but be safe)
```

**1b. Allocate `self._flow` in `__init__`** (`simulation.py:93-105`), right after
the `grid._active[:] = ...` bootstrap line (`simulation.py:105`):

```python
        # Per-step movement-direction field for the H-mode flow-arrow overlay.
        # Pure render transient: NOT carried by swap/migrate_grid, NOT a wake
        # signal. Zeroed at the start of each step(); read by the renderer via
        # the `flow` property between steps.
        self._flow = np.zeros((grid.height, grid.width), dtype=np.uint8)
```

**1c. Zero + (re)allocate `_flow` at the start of `step()`** — add right after
`moved = np.zeros(...)` (`simulation.py:126`):

```python
        # Reset the flow-direction overlay for this step (reallocate if a resize
        # changed the grid shape since __init__ -- defensive; a resize builds a
        # new Simulation, so the shape normally already matches).
        if self._flow.shape != (grid.height, grid.width):
            self._flow = np.zeros((grid.height, grid.width), dtype=np.uint8)
        else:
            self._flow.fill(0)
        flow = self._flow
```

**1d. Record the direction when a rule returns a destination.** Edit the
existing block (`simulation.py:154-157`) to also write the source cell's flow
code:

```python
                dest = fn(grid, x, y)
                if dest is not None:
                    dx, dy = dest
                    moved[dy, dx] = True
                    flow[y, x] = _flow_code(dx - x, dy - y)
```

**1e. Add the `flow` property** next to the `grid` property
(`simulation.py:107-109`):

```python
    @property
    def flow(self) -> npt.NDArray[np.uint8]:
        """Per-cell movement direction from the LAST step, for the H-mode
        flow-arrow overlay. Codes: 0=none, 1=up, 2=down, 3=left, 4=right
        (see FLOW_*). Read-only view; the simulation owns the writes."""
        return self._flow
```

Note: nothing else in `step()` changes. The four wake conditions
(`simulation.py:159-188`) are UNCHANGED — `_flow` is not a wake signal.

### 2. `src/sandfall/thermal.py` — `build_colorbar_gradient`

Add after `thermal_to_rgb` (end of file, after `thermal.py:275`). It reuses
`thermal_to_rgb` on a 1-D temp ramp so the bar is a perfect mirror of the cell
coloring (hot at row 0 / top, cold at row `height-1` / bottom):

```python
def build_colorbar_gradient(height: int) -> npt.NDArray[np.uint8]:
    """Build the vertical colorbar gradient as a ``(height, 3)`` uint8 column.

    Row 0 is the HOT endpoint (``HEAT_VIZ_HOT``) and row ``height-1`` is the
    COLD endpoint (``HEAT_VIZ_COLD``), matching screen orientation (row 0 is the
    top). The gradient is produced by calling :func:`thermal_to_rgb` on a 1-D
    temperature ramp, so the bar is an EXACT mirror of the per-cell heat coloring
    (no second gradient definition to drift). ``AMBIENT_TEMP`` lands at its
    natural position in the ramp.

    Pure / pygame-free -> unit-tested headlessly. The renderer transposes it to
    ``(1, height, 3)`` and scales it to the bar width.
    """
    if height < 1:
        raise ValueError(f"height must be positive ({height=})")
    temps = np.linspace(
        float(HEAT_VIZ_HOT), float(HEAT_VIZ_COLD), num=height, dtype=np.float32
    ).reshape(height, 1)
    rgb = thermal_to_rgb(temps)  # (height, 1, 3) uint8
    return rgb.reshape(height, 3)
```

### 3. `src/sandfall/renderer.py` — `flow_arrow_samples`

Add the `simulation` import and the helper near the other pure helpers
(`renderer.py:27-52`). `renderer → simulation` is acyclic (simulation does not
import renderer).

```python
from .simulation import FLOW_DOWN, FLOW_LEFT, FLOW_NONE, FLOW_RIGHT, FLOW_UP
```

```python
# Map a flow code (0..4) to its (dx, dy) unit vector. Indexed by code; row 0
# (FLOW_NONE) is (0, 0). Must match the FLOW_* constants in simulation.py.
_FLOW_VEC: npt.NDArray[np.int16] = np.array(
    [[0, 0], [0, -1], [0, 1], [-1, 0], [1, 0]], dtype=np.int16
)


def flow_arrow_samples(
    flow: npt.NDArray[np.uint8], stride: int = 10, threshold: int | None = None
) -> list[tuple[int, int, int, int]]:
    """Sample the per-step flow array at ``stride``-cell blocks and return arrow
    descriptors for each block's DOMINANT flow.

    Returns a list of ``(cx, cy, vx, vy)``: ``(cx, cy)`` is the block center in
    GRID coords; ``(vx, vy)`` is the block's net flow vector (a small int pair,
    NOT normalized -- the renderer normalizes for drawing). Blocks whose net flow
    magnitude is below ``threshold`` (default ``stride``: roughly "fewer than
    ``stride`` net directional cells") produce NO arrow (still or turbulent/
    balanced blocks are omitted).

    Each cell's code is mapped to a unit vector (up/down/left/right); the block's
    resultant is the vector SUM over the block (so a half-up/half-down block
    cancels to ~zero -> no arrow, while a uniform updraft sums to a strong up
    vector). Pure numpy / pygame-free -> unit-tested headlessly.
    """
    h, w = flow.shape
    if threshold is None:
        threshold = stride
    half = stride // 2
    samples: list[tuple[int, int, int, int]] = []
    for cy in range(half, h, stride):
        for cx in range(half, w, stride):
            y0, y1 = max(0, cy - half), min(h, cy + half + 1)
            x0, x1 = max(0, cx - half), min(w, cx + half + 1)
            block = flow[y0:y1, x0:x1]
            vsum = _FLOW_VEC[block].sum(axis=0)  # (2,) int16 resultant
            vx, vy = int(vsum[0]), int(vsum[1])
            if abs(vx) + abs(vy) < threshold:
                continue  # still / mixed / balanced -> no arrow
            samples.append((cx, cy, vx, vy))
    return samples
```

Note: `_FLOW_VEC[block]` fancy-indexes the (blockH, blockW) code array to a
(blockH, blockW, 2) vector array; `.sum(axis=0)` reduces it to (2,). Codes are
always in `0..4` (they come from `_flow_code`), so the index is always in range.

### 4. `src/sandfall/game.py` — `_draw_heat_overlays` + cached surfaces

**4a. Add config imports.** Extend the `from .config import (...)` block
(`game.py:33-49`) with `AMBIENT_TEMP`, `HEAT_VIZ_COLD`, `HEAT_VIZ_HOT`
(alphabetical within the block). Also import the two new helpers:

```python
from .renderer import Renderer, flow_arrow_samples
from .thermal import build_colorbar_gradient
```

(Adjust the existing `from .renderer import Renderer` line at `game.py:53` and
add the `thermal` import near it — `game.py` does not currently import `thermal`.)

**4b. Add cached-surface fields + constants.** Near the `_heat_overlay` field
(`game.py:97-100`) and in `__init__` (`game.py:108-139`):

```python
    # Cached H-mode overlay surfaces (rebuilt only on resize). The colorbar
    # gradient is pure of temperature, so it depends only on the sim-area pixel
    # height; the arrow overlay is a screen-sized SRCALPHA cleared each frame.
    _colorbar_surf: pygame.Surface
    _colorbar_h: int
    _arrow_overlay: pygame.Surface
```

Constants (module-level in `game.py`, near the other tunables):

```python
# H-mode colorbar geometry / colors.
COLORBAR_W = 20          # px width of the temperature colorbar
COLORBAR_BORDER = (220, 220, 220)
COLORBAR_LABEL = (235, 235, 235)
# Sparse flow-arrow overlay.
ARROW_STRIDE = 10        # grid cells per flow-arrow sample block
ARROW_LEN = 12           # px arrow length on screen
ARROW_COLOR = (255, 255, 255, 128)  # semi-transparent white (RGBA)
```

In `__init__`, after `self._heat_overlay = False` (`game.py:138`):

```python
        self._colorbar_surf = pygame.Surface((COLORBAR_W, 1))
        self._colorbar_h = -1   # forces a rebuild on first draw
        self._arrow_overlay = pygame.Surface(
            (INITIAL_WINDOW_W, INITIAL_WINDOW_H), pygame.SRCALPHA
        ).convert_alpha()
```

**4c. Call `_draw_heat_overlays` from `_draw`.** In `_draw`
(`game.py:334-340`), after the scaled grid is blitted (`game.py:340`) and BEFORE
the magnifier (`game.py:351-352`), add (only in heat mode):

```python
        if self._heat_overlay:
            self._draw_heat_overlays()
```

(Place it before the magnifier so the magnifier — if on — magnifies the heat
view without the overlays, which is correct: overlays are screen-space, the lens
crops grid-space.)

**4d. Add the `_draw_heat_overlays` method** near `_draw_magnifier`
(`game.py:369`). It (1) rebuilds the colorbar surface if the sim-area height
changed, blits it at the right edge + draws degree markers; (2) clears the arrow
overlay, draws the sparse arrows, blits it. Both use the current window/grid
size so they survive resize.

```python
    def _draw_heat_overlays(self) -> None:
        """Draw the H-mode UI overlays: the temperature colorbar (right edge,
        with degree markers) and the sparse flow arrows.

        Neither affects the simulation; both are screen-space overlays drawn
        only when ``self._heat_overlay`` is True. The colorbar surface is cached
        and rebuilt only when the sim-area height changes (resize); the arrow
        overlay is a screen-sized SRCALPHA surface cleared and redrawn each frame.
        """
        scaled_h = self._grid.height * CELL_SIZE
        scaled_w = self._grid.width * CELL_SIZE

        # --- Temperature colorbar (right edge of the scaled grid region) -----
        if self._colorbar_h != scaled_h:
            grad = build_colorbar_gradient(scaled_h)        # (scaled_h, 3) uint8
            bar = pygame.Surface((1, scaled_h))             # 1px-wide column
            pygame.surfarray.blit_array(bar, grad.reshape(1, scaled_h, 3))
            self._colorbar_surf = pygame.transform.scale(bar, (COLORBAR_W, scaled_h))
            self._colorbar_h = scaled_h
        bx = scaled_w - COLORBAR_W                          # right edge of sim
        self._screen.blit(self._colorbar_surf, (bx, 0))
        pygame.draw.rect(
            self._screen, COLORBAR_BORDER, (bx, 0, COLORBAR_W, scaled_h), 1
        )
        # Degree markers at the four anchors that bracket the interesting range.
        font = self._ui.font
        span = HEAT_VIZ_HOT - HEAT_VIZ_COLD
        for temp in (HEAT_VIZ_COLD, AMBIENT_TEMP, 200, HEAT_VIZ_HOT):
            ty = int(round((HEAT_VIZ_HOT - temp) / span * scaled_h))
            pygame.draw.line(
                self._screen, COLORBAR_BORDER, (bx, ty), (bx + COLORBAR_W, ty), 1
            )
            label = font.render(f"{temp}", True, COLORBAR_LABEL)
            # Label sits just LEFT of the bar so it never runs off the right edge.
            self._screen.blit(label, (bx - label.get_width() - 3, ty - label.get_height() // 2))

        # --- Sparse flow arrows (one per ARROW_STRIDE-cell block) -----------
        ov = self._arrow_overlay
        if ov.get_size() != (self._window_w, self._window_h):
            ov = pygame.Surface((self._window_w, self._window_h), pygame.SRCALPHA).convert_alpha()
            self._arrow_overlay = ov
        ov.fill((0, 0, 0, 0))
        for cx, cy, vx, vy in flow_arrow_samples(self._sim.flow, ARROW_STRIDE):
            sx = cx * CELL_SIZE + CELL_SIZE // 2
            sy = cy * CELL_SIZE + CELL_SIZE // 2
            length = (vx * vx + vy * vy) ** 0.5
            if length == 0:
                continue
            ux, uy = vx / length, vy / length
            x0 = sx - ux * ARROW_LEN / 2
            y0 = sy - uy * ARROW_LEN / 2
            x1 = sx + ux * ARROW_LEN / 2
            y1 = sy + uy * ARROW_LEN / 2
            pygame.draw.line(ov, ARROW_COLOR, (x0, y0), (x1, y1), 1)
            # Small arrowhead at the (x1, y1) tip.
            hx, hy = x1 - ux * 4 - uy * 2, y1 - uy * 4 + ux * 2
            hx2, hy2 = x1 - ux * 4 + uy * 2, y1 - uy * 4 - ux * 2
            pygame.draw.polygon(ov, ARROW_COLOR, [(x1, y1), (hx, hy), (hx2, hy2)])
        self._screen.blit(ov, (0, 0))
```

Notes for the implementer:
- `self._ui.font` — verify `UI` exposes a `font` attribute (the palette already
  renders text via a lazily-created font in `UI.draw`; if it is private, either
  expose it or create a small `pygame.font.Font(None, FONT_SIZE)` on `Game`. Pin
  the choice in the reflection; do NOT duplicate the font if `UI` already has
  one — expose it). If unsure, re-read `src/sandfall/ui.py` first.
- `surfarray.blit_array` on a `(1, scaled_h)` surface takes a `(1, scaled_h, 3)`
  column-major array — hence the `.reshape(1, scaled_h, 3)` (mirrors
  `renderer.render` at `renderer.py:78-81`).
- The arrow overlay uses an RGBA color on an SRCALPHA surface so the `128` alpha
  is honored (semi-transparent). `convert_alpha()` is called once at creation;
  re-created only on resize.
- If arrows are too subtle on the heat colors (Risks #5), raise
  `ARROW_COLOR`'s alpha to ~180 or add a 1px dark outline. Pin the final value.

### 5. Tests

**5a. `tests/test_simulation.py`** — add a test that `Simulation.flow` records a
moved cell's direction:

```python
def test_flow_records_movement_direction() -> None:
    """A cell that moved DOWN (sand falling) is recorded as FLOW_DOWN in
    Simulation.flow; a static cell stays FLOW_NONE."""
    import random
    random.seed(0)
    from sandfall.simulation import FLOW_DOWN, FLOW_NONE
    grid = Grid(width=3, height=4)
    grid.set(1, 0, ElementId.SAND)   # sand at top, falls down
    sim = Simulation(grid)
    sim.step()
    # The sand fell from (1,0) to (1,1) -> flow at the SOURCE (1,0) is DOWN.
    assert sim.flow[0, 1] == FLOW_DOWN
    # A cell that did not move (e.g. an empty cell) has no flow.
    assert sim.flow[0, 0] == FLOW_NONE
    # flow resets each step: after a second step with nothing moving into (1,0),
    # that cell's flow is cleared.
    sim.step()
    assert sim.flow[0, 1] == FLOW_NONE
```

(Adapt the exact assertions to where the sand lands after one step with
`random.seed(0)`; the key claims are: a moved source cell has the right code, a
static cell is `FLOW_NONE`, and the array resets each step.)

**5b. `tests/test_renderer.py`** — add a test for `flow_arrow_samples`:

```python
def test_flow_arrow_samples_dominant_direction() -> None:
    """A block of uniform UP flow yields one up-pointing arrow; a still block
    yields none."""
    import numpy as np
    from sandfall.renderer import flow_arrow_samples
    from sandfall.simulation import FLOW_NONE, FLOW_UP
    # A 10x10 block of uniform upflow, rest still.
    flow = np.full((20, 20), FLOW_NONE, dtype=np.uint8)
    flow[0:10, 0:10] = FLOW_UP
    samples = flow_arrow_samples(flow, stride=10)
    # Exactly one sample in the upflow block, pointing up (vy < 0).
    up = [(cx, cy, vx, vy) for (cx, cy, vx, vy) in samples if cx < 10 and cy < 10]
    assert len(up) == 1
    _, _, vx, vy = up[0]
    assert vy < 0 and vx == 0
    # The all-still block (cols 10..19) produced no arrow.
    still = [(cx, cy) for (cx, cy, _, _) in samples if cx >= 10 or cy >= 10]
    assert still == []
```

**5c. `tests/test_thermal.py`** — add a test for `build_colorbar_gradient`:

```python
def test_build_colorbar_gradient_shape_and_endpoints() -> None:
    """The colorbar gradient is (height, 3) uint8; row 0 is the HOT endpoint
    color, row -1 is the COLD endpoint color (matching thermal_to_rgb)."""
    import numpy as np
    from sandfall.config import HEAT_VIZ_COLD, HEAT_VIZ_HOT
    from sandfall.thermal import build_colorbar_gradient, thermal_to_rgb
    grad = build_colorbar_gradient(50)
    assert grad.shape == (50, 3)
    assert grad.dtype == np.uint8
    # Row 0 == thermal_to_rgb(HEAT_VIZ_HOT); row -1 == thermal_to_rgb(HEAT_VIZ_COLD).
    hot = thermal_to_rgb(np.array([[HEAT_VIZ_HOT]], dtype=np.float32))[0, 0]
    cold = thermal_to_rgb(np.array([[HEAT_VIZ_COLD]], dtype=np.float32))[0, 0]
    assert tuple(grad[0]) == tuple(hot)
    assert tuple(grad[-1]) == tuple(cold)
```

(Add `build_colorbar_gradient` to the `from sandfall.thermal import (...)` block
in `tests/test_thermal.py` if that test file uses a grouped import.)

## Acceptance Criteria

- [ ] `Simulation` defines `FLOW_NONE/UP/DOWN/LEFT/RIGHT` + `_flow_code`;
      allocates `self._flow` in `__init__`; zeroes (and reallocates on shape
      mismatch) it at the start of `step()`; records `_flow_code(dx-x, dy-y)` at
      the source cell when a rule returns a destination; exposes it via a
      read-only `flow` property. The four wake conditions are UNCHANGED.
- [ ] `thermal.build_colorbar_gradient(height)` returns a `(height, 3)` uint8
      array whose row 0 matches `thermal_to_rgb(HEAT_VIZ_HOT)` and last row
      matches `thermal_to_rgb(HEAT_VIZ_COLD)` (test passes).
- [ ] `renderer.flow_arrow_samples(flow, stride)` returns one `(cx, cy, vx, vy)`
      per block whose net flow magnitude ≥ `stride`, pointing in the block's
      resultant direction; still/mixed blocks yield no arrow (test passes).
- [ ] `Game._draw_heat_overlays` draws (in H mode only) a vertical colorbar at
      the right edge of the scaled grid with degree markers at `HEAT_VIZ_COLD`,
      `AMBIENT_TEMP`, 200, `HEAT_VIZ_HOT`, AND sparse semi-transparent flow
      arrows over the heat colors. Both overlay surfaces are cached (colorbar
      rebuilt only on height change; arrow overlay reused, cleared each frame).
- [ ] `_draw` calls `_draw_heat_overlays` only when `self._heat_overlay` is True,
      and BEFORE the magnifier (overlays are screen-space; the lens crops
      grid-space).
- [ ] `tests/test_simulation.py::test_flow_records_movement_direction`,
      `tests/test_renderer.py::test_flow_arrow_samples_dominant_direction`, and
      `tests/test_thermal.py::test_build_colorbar_gradient_shape_and_endpoints`
      all pass.
- [ ] **Re-verified, not pre-emptively changed:** the existing
      `tests/test_renderer.py`, `tests/test_simulation.py`,
      `tests/test_thermal.py`, and `tests/test_ui.py` still pass (the colorbar/
      arrows are additive UI; no existing assertion should change). Record the
      outcome in the reflection.
- [ ] The SDL smoke (`SANDFALL_FRAMES=60`) shows the colorbar + arrows in H mode
      without crashing (visual confirmation; pin observations in the reflection).
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the new helper tests are the headline):
uv run pytest tests/test_simulation.py tests/test_renderer.py tests/test_thermal.py -v

# Import smoke:
uv run python -c "import sandfall"

# Full suite -- re-verifies the renderer/sim/ui regression:
uv run pytest

# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
# Toggle H on a scene with convection (a heated water pool from Phase 01, or
# LAVA under WATER): confirm the colorbar renders on the right with degree
# markers, and sparse white arrows show the updraft/downdraft currents.
SANDFALL_FRAMES=60 uv run sandfall
```

All commands must exit zero.

## Documentation Updates

- `docs/ARCHITECTURE.md` — if it describes the H (heat-overlay) mode, add a note
  that H mode now also shows a temperature colorbar (right edge) and sparse flow
  arrows (dominant per-block fluid movement). If it does not describe H mode at
  that level, leave it. Note whichever you find in the reflection.
- Inline docstrings in `simulation.py`, `thermal.py`, `renderer.py`, and
  `game.py` are the source of truth (updated as part of the code changes above).

## Reflection & Commit

After implementation, write `02-heatmap-enhancements-reflection.md` in this
directory. **Specifically include:**
- How `self._ui.font` was obtained (exposed vs. a new `Game` font) — pin the
  choice and why.
- The final `ARROW_COLOR` alpha + whether a dark outline was needed for
  visibility against the heat colors (Risks #5).
- The final colorbar placement/width and whether it intruded on the sim view
  (Risks #7) — pin the choice.
- The re-verification outcome of the renderer/sim/ui/thermal suites — did they
  pass as-is?
- Whether the SDL smoke showed the colorbar + arrows correctly in H mode over a
  convecting scene, and any visual tuning applied.
- Anything difficult/unexpected, deviations from this plan + why, and anything
  fun discovered.

Then make ONE atomic git commit covering all changes in this phase.

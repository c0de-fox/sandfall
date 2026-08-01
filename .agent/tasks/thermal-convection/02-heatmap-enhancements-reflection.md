# Phase 02 Reflection — Heatmap enhancements (colorbar + flow arrows)

Builds on HEAD `d72b69d` (Phase 01 convection shipped). All six verification
gates exit zero (see the bottom of this file). **No git operations performed —
changes are left unstaged per the task contract.**

## What shipped

Three additive UI-overlay pieces for H (heatmap) mode, none of which touch the
simulation movement logic, the rules, `grid.py`, `thermal.py` diffusion, or
`elements.py`:

1. **`Simulation._flow`** — a per-step `uint8` direction field recorded as a
   byproduct of the existing movement scan.
2. **Two pure numpy helpers** — `thermal.build_colorbar_gradient(height)` and
   `renderer.flow_arrow_samples(flow, stride)`, both headlessly unit-tested.
3. **`Game._draw_heat_overlays`** — draws the cached colorbar (right edge +
   degree markers) and the sparse flow arrows over the heat colors.

## The `_flow` implementation (`simulation.py`)

- Module-level constants `FLOW_NONE=0 / FLOW_UP=1 / FLOW_DOWN=2 / FLOW_LEFT=3 /
  FLOW_RIGHT=4` and a `_flow_code(ddx, ddy)` helper that maps a movement delta
  `(dest - source)` to a code, **vertical-preferred on diagonals** (a down-left
  water move records DOWN). Placed after the imports, before `_dilate`.
- `self._flow = np.zeros((H, W), uint8)` allocated in `__init__` right after the
  `_active` bootstrap.
- At the start of `step()`, immediately after `moved = np.zeros(...)`, the field
  is reset — `realloc` if the grid shape changed since `__init__` (defensive; a
  resize builds a new `Simulation` so the shape normally already matches),
  else `.fill(0)`. A local alias `flow = self._flow` is used in the scan.
- In the scan, when a rule returns `dest`, the SOURCE cell records its code:
  `flow[y, x] = _flow_code(dx - x, dy - y)` — one extra `uint8` write per MOVED
  cell. `dest` is an ABSOLUTE destination coord (the existing code unpacks
  `dx, dy = dest`), so the delta is `dx - x, dy - y`. Verified against the
  sand-falls-one-row case: source `(x,1,y=0)` → dest `(x,1,y=1)` →
  `_flow_code(0, 1)` → `FLOW_DOWN`. ✓
- A read-only `flow` property exposes `self._flow` for the renderer.
- **The four wake conditions are UNCHANGED** — `_flow` is not a wake signal
  (it is render-only). `Grid` is untouched (Decision #8: `_flow` is a
  per-step transient on `Simulation`, not persistent state).

The new `tests/test_simulation.py::test_flow_records_movement_direction` pins
all three guarantees: a moved source cell gets the right code (`FLOW_DOWN` for
falling sand); a static cell stays `FLOW_NONE`; and the array resets each step
(after a second step the first-step source — now empty — is cleared, and the
new source records `FLOW_DOWN`).

## The colorbar gradient formula — confirmed EXACT match to `thermal_to_rgb`

`thermal.build_colorbar_gradient(height)`:

```python
temps = np.linspace(HEAT_VIZ_HOT, HEAT_VIZ_COLD, num=height,
                    dtype=np.float32).reshape(height, 1)
rgb = thermal_to_rgb(temps)        # (height, 1, 3) uint8
return rgb.reshape(height, 3)
```

Row 0 = `HEAT_VIZ_HOT` (1000 °C) → the HOT endpoint color; last row =
`HEAT_VIZ_COLD` (-40 °C) → the COLD endpoint. There is **no second gradient
definition** — the bar calls `thermal_to_rgb` on a 1-D temp ramp, so by
construction it cannot drift from the per-cell coloring. The headless overlay
driver confirmed this directly: sampling the built `(20, 560)` colorbar surface
gave top pixel `[255, 40, 40]` (red) and bottom pixel `[40, 40, 255]` (blue),
both matching `grad[0]` / `grad[-1]` and `thermal_to_rgb([[HEAT_VIZ_HOT]])` /
`thermal_to_rgb([[HEAT_VIZ_COLD]])` exactly.

Two headless tests pin it: `test_build_colorbar_gradient_shape_and_endpoints`
(shape `(50,3)`, dtype `uint8`, endpoints match `thermal_to_rgb`) and
`test_build_colorbar_gradient_middle_is_neutral` (the row nearest `AMBIENT_TEMP`
reads as the flat neutral-gray pivot: all three channels equal, no channel
maxed — mirroring `test_thermal_to_rgb_ambient_is_neutral`).

## The arrow sampling + rendering approach

**Sampling (`renderer.flow_arrow_samples`, pure numpy):** a `_FLOW_VEC` lookup
table maps each code to its `(dx, dy)` unit vector in grid coords (`+y` is
DOWN). The grid is walked in `stride`-cell blocks (default 10); for each block
`_FLOW_VEC[block]` fancy-indexes the `(bH, bW)` code array to a `(bH, bW, 2)`
vector array, `.sum(axis=(0, 1))` reduces it to the `(2,)` block resultant, and
an arrow `(cx, cy, vx, vy)` is emitted only when `|vx| + |vy| >= stride`
(default threshold = stride). A still block → `(0,0)` → no arrow; a half-up /
half-down block cancels → no arrow; a uniform updraft sums to a strong up
vector → arrow.

**One bug caught and fixed during implementation:** the first version used
`.sum(axis=0)`, which only reduces one spatial axis of the `(bH, bW, 2)` array
and leaves `(bW, 2)` — `int(vsum[0])` then raised
`TypeError: only 0-dimensional arrays can be converted to Python scalars`. Fixed
to `.sum(axis=(0, 1))`. The `tests/test_renderer.py::
test_flow_arrow_samples_dominant_direction` test would have caught it, but it
fired first in the focused new-test run — exactly the expected-failing-validator
discipline.

**Rendering (`Game._draw_heat_overlays`):** for each sample, the block center
is converted to screen px, the net vector `(vx, vy)` is normalized, and a line
of length `ARROW_LEN` (12 px) is drawn on a screen-sized `SRCALPHA` overlay
plus a small triangular arrowhead at the tip. The overlay is cleared
(`fill((0,0,0,0))`) and redrawn each frame; `ARROW_COLOR = (255,255,255,128)`
(honored because the surface is `SRCALPHA` + `convert_alpha()`). The whole
overlay is then blitted on top of the heat colors.

## How `self._ui.font` was obtained — EXPOSED (not duplicated)

The plan flagged this as a tunable choice. `UI._font` was private and lazily
created inside `UI.draw`. But `_draw` calls `_draw_heat_overlays` BEFORE
`ui.draw()` in the frame, so the font would still be `None` when the colorbar
labels render. I exposed a public `UI.font` property that **lazily creates** the
font on first access (mirroring the init in `draw`, local `import pygame` to
keep the module import pygame-free for the pure helpers). This honors the
plan's "do NOT duplicate the font if UI already has one — expose it": the
colorbar reuses the exact same `pygame.font.Font(FONT_NAME, FONT_SIZE)` instance
the HUD/tooltips use. No second font is created.

## Tuning notes (Risks #5 and #7)

- **`ARROW_COLOR` alpha = 128, no dark outline added.** The headless overlay
  driver over a convecting water pool produced **20 arrows, all 20
  vertical-dominant** (clean updraft/downdraft convection) at the default
  `ARROW_STRIDE=10` / `ARROW_LEN=12` / alpha 128. Against saturated red (hot)
  and blue (cold) heat colors the semi-transparent white reads fine; against
  ambient-gray regions there is little flow anyway, so washout is a non-issue.
  Kept the plan's defaults; **no outline needed**. If real playtesting shows
  washout, the recovery knob is `ARROW_COLOR`'s alpha (→~180) or a 1px dark
  outline (the plan's fallback). Pinned here: alpha 128, stride 10, len 12.
- **Colorbar placement = right edge of the scaled grid, `COLORBAR_W = 20` px
  wide, full sim-area height.** At the default 800×600 window the grid is
  200×140 cells → scaled region is 800×560 px; the 20-px bar covers the
  rightmost ~5 columns of the heat view. This is the acceptable intrusion
  called out in Risks #7 (the bar IS the legend for those colors). Degree
  labels sit just LEFT of the bar so they never run off the right edge. Kept
  the plan's defaults; no narrowing/move needed.

## Re-verification of the existing suites

The colorbar/arrows are additive UI + one `uint8` write per moved cell; no
existing assertion should change. Confirmed: **240 → 244** (the four new tests
are the only additions). The renderer/sim/ui/thermal/convection/phase suites
all pass as-is. `test_renderer.py` 10/10, `test_simulation.py` 15/15,
`test_thermal.py` 17/17, `test_convection.py` 7/7, `test_phase.py` 28/28,
`test_ui.py` 19/19.

## SDL smoke / visual confirmation

The literal `SANDFALL_FRAMES=60 SDL_VIDEODRIVER=dummy uv run sandfall` gate
exits 0, but with the default empty grid and `_heat_overlay=False` it does not
exercise the overlay path. To get real evidence I ran a focused headless driver
(`/tmp/opencode/phase2_overlay_check.py`, not committed) that enabled H mode,
built a sustained-convection water pool (bottom row pinned hot-but-sub-boil at
95 °C — mirroring `test_convection_accelerates_pool_equilibration`; lava+water
reacts to steam+stone instantly and consumes the source, so it does NOT produce
sustained convection), stepped, and inspected the cached surfaces directly:

- 20 flow arrows over the pool, all 20 vertical-dominant (updrafts/downdrafts).
- Colorbar surface built `(20, 560)` on first heat-mode draw; cached across
  frames (rebuilt only on height change).
- Colorbar top pixel `[255,40,40]` (red/hot), bottom `[40,40,255]` (blue/cold),
  matching `grad[0]`/`grad[-1]` and `thermal_to_rgb` endpoints exactly.
- 40+ subsequent `_draw` + `step` frames stable, no crash.

So: **the colorbar renders and the flow arrows show direction over a convecting
scene** (verified headlessly against surface pixels + arrow samples).

## Deviations from the plan

Only two small ones, both defensive improvements, both called out above:

1. **`_FLOW_VEC` import-time assert.** The plan said to import `FLOW_*` into
   `renderer.py`, but `_FLOW_VEC` is laid out positionally so the named
   constants were unreferenced → ruff F401. Rather than drop the imports
   (losing the protocol coupling the plan wanted) or `# noqa` them, I added an
   import-time `assert` that each `_FLOW_VEC[FLOW_*]` row equals its documented
   vector. This references all five constants, satisfies ruff, AND upgrades a
   silent positional coupling into an import-time-checked contract (renumber
   `FLOW_*` in `simulation.py` without reordering the rows → loud failure at
   import).
2. **A second colorbar test (`_middle_is_neutral`).** The plan specified one
   colorbar test; I added a second that pins the ambient row is the neutral-gray
   pivot. Cheap, headless, and locks in the "the bar mirrors `thermal_to_rgb`"
   claim at the gradient's most diagnostic point (the pivot). Mirror of the
   existing `test_thermal_to_rgb_ambient_is_neutral`.

No other deviations. The implementation follows the phase file literally.

## Six-gate results (all exit zero)

| # | Gate                                                | Result                              |
|---|-----------------------------------------------------|-------------------------------------|
| 1 | `pytest tests/test_convection.py tests/test_phase.py tests/test_thermal.py -v` | 51 passed                  |
| 2 | `python -c "import sandfall"`                       | OK (import smoke)                   |
| 3 | `pytest` (FULL suite)                               | **244 passed** (240 → 244)          |
| 4 | `ruff check .`                                      | All checks passed!                  |
| 5 | `ruff format --check .`                             | 59 files already formatted          |
| 6 | `mypy src`                                          | Success: no issues in 32 files      |
| 6*| `SANDFALL_FRAMES=60 SDL_VIDEODRIVER=dummy uv run sandfall` | exit 0 (+ headless overlay driver: all checks pass) |

The phase file's own verification (`pytest tests/test_simulation.py
tests/test_renderer.py tests/test_thermal.py -v`) also passes: 42 passed.

## Files changed

- `src/sandfall/simulation.py` — `FLOW_*` constants, `_flow_code`, `_flow`
  array + `flow` property.
- `src/sandfall/thermal.py` — `build_colorbar_gradient`.
- `src/sandfall/renderer.py` — `flow_arrow_samples` + `_FLOW_VEC` (+ assert),
  `FLOW_*` import.
- `src/sandfall/ui.py` — public `font` property.
- `src/sandfall/game.py` — colorbar/arrow constants, cached surfaces, imports,
  `_draw` call, `_draw_heat_overlays`.
- `tests/test_simulation.py`, `tests/test_renderer.py`, `tests/test_thermal.py`
  — three new tests (+ one extra colorbar test).
- `docs/ARCHITECTURE.md` — H-mode section now documents the colorbar + arrows.

## Fun / unexpected

- `dest` from a rule is an **absolute destination coord**, not a delta — the
  existing `dx, dy = dest` unpacking reads as "delta" but isn't. The recording
  `flow[y, x] = _flow_code(dx - x, dy - y)` computes the delta explicitly so
  the naming is honest at the call site even though the local var names (`dx`,
  `dy`) upstream are a historical misnomer.
- `_FLOW_VEC[block].sum(axis=0)` looking correct at a glance but reducing only
  one of two spatial axes — a classic numpy rank trap. The `.sum(axis=(0,1))`
  fix and the import-time assert are both belt-and-suspenders against the same
  class of "looks right, isn't" coupling.

# Phase 04 Reflection — Heat visualization + docs

The final phase of the sandfall-temperature feature. Heat overlay shipped,
docs written end-to-end. **All six gates pass.** No git operations performed
(changes left unstaged per the hard constraints).

## What was done

- `src/sandfall/thermal.py` — added pure `thermal_to_rgb(temp) -> (H,W,3)
  uint8` plus a module-private `_lerp3` 3-stop piecewise-linear helper.
- `src/sandfall/config.py` — added `HEAT_VIZ_COLD = -40` / `HEAT_VIZ_HOT =
  1000` (additive; the `__all__` re-export list is untouched because these
  are defined here, not re-exported).
- `src/sandfall/renderer.py` — added `Renderer.render_heat(grid)` mirroring
  `render` (same self-healing `_cell_surface`, same `(H,W,3)→(W,H,3)`
  transpose), sourcing RGB from `thermal_to_rgb(grid.temp)`.
- `src/sandfall/game.py` — added `_heat_overlay: bool` (init `False`), bound
  `K_h` in the KEYDOWN branch, branched `_draw` between `render` /
  `render_heat`. Palette + HUD stay visible in both modes.
- `tests/test_thermal.py` — 5 new headless gradient tests (shape/dtype,
  hot-redder/cold-bluer, saturation-without-overflow at BOTH ends,
  ambient-is-neutral, monotone red↑/blue↓ sweep).
- `tests/test_renderer.py` — 1 new test reusing the existing session-scoped
  `_headless_pygame` dummy-driver fixture (no new SDL init).
- `README.md` + `docs/ARCHITECTURE.md` — full feature write-up (details
  below).

**Scope respected:** only the 8 allowed files were touched. No edits to
`simulation.py`, `grid.py`, `rules/*`, `elements.py`, or
`thermal.diffuse_temps` — confirmed via `git status` (this phase is viz +
docs only).

## The gradient formula I settled on

I did **not** use the spec's starting formula. That formula normalized
`f = (t - lo)/(hi - lo)` across `[-40, 1000]`, which puts ambient (20°) at
`f ≈ 0.058` — i.e. ambient lands near the cold end and reads as a strong
**blue-cyan**, not neutral. The contract says "ambient reads neutral", so I
retuned to a **neutral-pivot design**.

Final design — two mutually-exclusive normalized halves sharing ambient as
their `0` pivot:

```
cold = clip((AMBIENT - t) / (AMBIENT - HEAT_VIZ_COLD), 0, 1)   # 0 at ambient, 1 at -40
hot  = clip((t - AMBIENT) / (HEAT_VIZ_HOT - AMBIENT), 0, 1)    # 0 at ambient, 1 at 1000
```

Each channel is a 3-stop piecewise lerp (`_lerp3`: linear 0→0.5 and
0.5→1.0):

| channel | cold side stops (0, 0.5, 1.0)        | hot side stops (0, 0.5, 1.0)         |
|---------|--------------------------------------|--------------------------------------|
| R       | neutral throughout (40)              | 40 → 235 (yellow) → 255 (red)        |
| G       | 40 → 215 (cyan peak) → 40            | 40 → 210 (yellow peak) → 40          |
| B       | 40 → 215 (cyan) → 255 (deep blue)    | neutral throughout (40)              |

`R = _lerp3(hot, ...)`, `B = _lerp3(cold, ...)`, and `G = max(cold-side,
hot-side)` (max == sum here because `cold` and `hot` are mutually exclusive
away from ambient — at most one is nonzero per cell). Stop constants:
`_NEUTRAL_BASE=40`, `_CYAN=(40,215,215)`, `_BLUE=(40,40,255)`,
`_YELLOW=(235,210,40)`, `_RED=(255,40,40)`.

**Why this satisfies the contract (measured):**

```
band=[-40,1000] ambient=20
  t=  -40 -> (40, 40,255) deep blue      # cold endpoint
  t=  -10 -> (40,215,215) cyan            # mid-cold
  t=   20 -> (40, 40, 40) FLAT GRAY       # ambient: R==G==B, true neutral
  t=  100 -> (71, 67, 40) dim warm        # water boil: mild tint (100° is "warm", not "hot")
  t=  500 -> (231,206, 40) yellow         # hot mid
  t=  800 -> (246,109, 40) orange-red     # fire burn-temp — reads clearly hot
  t= 1000 -> (255, 40, 40) red            # hot endpoint
  t= 6000 -> (255, 40, 40) red            # saturation: identical to 1000, no overflow
```

The band is deliberately **asymmetric around ambient** (cold span 60°, hot
span 980°) because the interesting hot range (fire ~800, lava ~1500) is far
wider than the cold range. Ambient reading as a flat `(40,40,40)` rather
than `(0,0,0)` is intentional: 40 is visibly lighter than `BG_COLOR`
`(10,10,14)`, so ambient cells distinguish from the window background
without becoming a bright tint. No tuning-by-monitor was possible
headlessly; the neutrality is guaranteed **algebraically** (at ambient both
`cold` and `hot` are exactly 0.0, so every channel reduces to
`_NEUTRAL_BASE`).

The monotone-ish contract is pinned by an extra test
(`test_thermal_to_rgb_monotone_red_and_blue`) sweeping the band in 20°
steps: red is non-decreasing and blue is non-increasing across the whole
range. (Green legitimately rises-then-falls on each side, so it is not
asserted monotone — that is the cyan/yellow hump by design.)

## H-toggle wiring (confirmed)

`rg -n 'K_h|_heat_overlay|render_heat' src/sandfall/game.py src/sandfall/renderer.py`:

```
src/sandfall/renderer.py:84:    def render_heat(self, grid: Grid) -> pygame.Surface:
src/sandfall/game.py:95:    _heat_overlay: bool
src/sandfall/game.py:126:        self._heat_overlay = False
src/sandfall/game.py:166:                elif event.key == pygame.K_h:
src/sandfall/game.py:170:                    self._heat_overlay = not self._heat_overlay
src/sandfall/game.py:274:        if self._heat_overlay:
src/sandfall/game.py:275:            small = self._renderer.render_heat(self._grid)
```

The toggle replaces **only** the grid surface — the rest of `_draw` (scale +
blit + `UI.draw` palette/HUD) is unchanged, so element selection works in
heat mode. The optional "HEAT" HUD indicator was **skipped** deliberately:
it is explicitly a nice-to-have (not an acceptance criterion) and would have
required widening `UI.draw`'s signature, rippling into `test_ui.py` — out of
scope for a viz+docs phase.

## Six-gate results

| # | gate | command | result |
|---|------|---------|--------|
| 1 | import smoke | `uv run python -c "import sandfall"` | ✅ exit 0 |
| 2 | tests | `uv run pytest` | ✅ 154 passed (was 148; +6 new) |
| 3 | lint | `uv run ruff check .` | ✅ All checks passed |
| 4 | format | `uv run ruff format --check .` | ✅ 47 files already formatted |
| 5 | types | `uv run mypy src` | ✅ no issues in 25 source files |
| 6 | SDL smoke | `SANDFALL_FRAMES=60 uv run sandfall` | ✅ exit 0 — **real display available, no `SDL_VIDEODRIVER=dummy` fallback needed** |

Test count 148 → **154** (+5 in `test_thermal.py`, +1 in `test_renderer.py`).

Two iteration cycles were needed for gates 3/4: my first pass had three
`E501 line-too-long` lines (a long `_NEUTRAL_BASE` comment, the `_lerp3`
signature, and a `np.arange(...).reshape(...)` test line). Fixed by moving
the comment to its own line and letting `ruff format` wrap the two code
lines — no semantic change, all tests stayed green.

## Whole-feature coherence (phases 01–04) — final assessment

Reasoning + the SDL smoke give me good confidence the feature hangs together
end-to-end. The mechanism is one consistent cause-and-effect chain:

- **Fire chains via heat.** Fire re-asserts `burn_temp` (~800) each step
  (`fire.py`); the diffusion pre-pass carries that heat through air
  (`COND_EMPTY=0.10` > 0) into fuel; WOOD/PLANT ignite *themselves* when
  their own temp exceeds `flashpoint` (`wood.py`/`plant.py`). The fire-cling
  behavior keeps a fire cell from rising off fuel before diffusion can raise
  it to flashpoint — without cling, combustion would never chain (documented
  in `fire.py`'s docstring). I did NOT re-verify the chain in a live window
  this phase (see "needs human playthrough" below), but the Phase 02 + lava
  reflections already established it and no rule code changed here.
- **Water cycle.** WATER boils→STEAM above 100°, freezes→ICE at/below 0°;
  STEAM condenses→WATER below 60°; ICE melts→WATER above 0°. All four are
  reactive rules (transform own cell, return None) reading post-diffusion
  temp. Symmetric and self-consistent.
- **Lava + water → steam + stone.** Reliable at 1500° per the committed
  lava-crust fix (HEAD `d65c4ab`); the earlier caveat is resolved, so the
  docs state it plainly with no hedging.
- **Sand → glass.** SAND melts→GLASS above ~1700° (only reachable next to
  lava); GLASS is then a static solid. Drop sand on lava → glass.
- **Heat overlay.** `H` makes the otherwise-invisible field observable, so
  all of the above can be *seen*: a fire's heat halo spreading into wood
  before it ignites, the cold front off painted ice, lava's heat plume, the
  flash where water meets lava. The same diffusion field that *drives* the
  transitions is the field the overlay *displays* — one model, two uses.

The reactive-rule relaxation (formalized in ARCHITECTURE this phase) is the
single mechanism behind every transition: WOOD/PLANT ignition, WATER
boil/freeze, SAND melt, LAVA cool, STEAM condense. Phase 02's removal of
probabilistic `SPREAD_FACTOR` means there is exactly one ignition model
(heat), not two competing ones. The architecture is coherent.

## Verified vs. needs human playthrough

**Verified directly this phase:**
- `thermal_to_rgb` contract headlessly (5 tests: shape/dtype, color
  ordering, saturation at both band ends, ambient neutrality, monotone
  sweep) plus the printed sample table above.
- `render_heat` returns the grid-sized self-healing surface headlessly
  (`test_renderer_render_heat_returns_grid_sized_surface`, reusing the dummy
  SDL fixture).
- Full SDL init→render→step→teardown for 60 frames exit 0 on a **real**
  display (gate 6, no dummy fallback). This exercises the default
  `_heat_overlay=False` path; `render_heat` through real SDL `blit_array` is
  the *same* code path as `render` (only the RGB source differs), and that
  source's `(H,W,3) uint8` layout is headless-tested, so I am confident the
  `H`-on path does not crash.

**NOT verified this phase (needs a human on a real display):**
- Pressing `H` *during* the run and watching the heat halo spread/recede as
  fuels ignite and burn out, then pressing `H` again to return to the
  element view. The wiring is confirmed present and the render path is
  tested in isolation, but the live keypress→overlay swap was not driven
  headlessly (the `SANDFALL_FRAMES` seam pumps no synthetic key events).
- Subjective gradient readability on a real monitor (the neutrality is
  algebraic, but "does fire read clearly hot and does ambient read calm" is
  ultimately a judgment for the playthrough). Stop constants are centralized
  at the top of `thermal.py` if the ramp wants retuning after playtesting.

## Suggestions for future work

- A `HEAT` HUD indicator (mirror the `PAUSED` one) is a natural follow-up;
  it was skipped only to avoid widening `UI.draw` this phase. Adding a
  `heat: bool` kwarg to `UI.draw` and rendering a small "HEAT" glyph
  top-center when on would close that loop.
- The overlay currently rebuilds the `(H,W,3)` image every frame even when
  paused; fine at 200×140, but if the grid ever grows large, a "paused →
  reuse last RGB" short-circuit in `render_heat` would be the cheap fix.
- Glow/lighting from hot cells (out of scope per the master plan's "Future
  Work") would be the prettier successor to the flat `H` overlay.

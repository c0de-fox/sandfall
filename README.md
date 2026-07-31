# sandfall

A falling-sand sandbox game built with [pygame-ce] and numpy. Paint elements
onto a grid and watch them fall, flow, burn, and grow — in the spirit of
*sand:box*, *The Powder Toy*, and *Sandustry*.

This is a complete **v1**: twelve interacting elements with a per-cell
**temperature field**, mouse painting, a UI palette, and a single
self-contained Linux binary build.

[pygame-ce]: https://pyga.me/

## Features

Twelve elements, each with its own physics and interactions, all sharing a
per-cell **temperature field**: heat diffuses through the grid every frame,
fuels ignite when their own temperature exceeds their flashpoint, and
materials boil / freeze / melt / condense across phase boundaries.

| Element | Behavior |
| --- | --- |
| **Sand** | Powder. Falls straight down; piles sideways down-diagonals when blocked. Sinks through water (it is denser). Melts into **glass** above ~1700°. |
| **Water** | Liquid. Falls, slips down-diagonals, and spreads one cell sideways into empty space to find its level. Boils into **steam** above 100° and freezes into **ice** at/below 0°. |
| **Stone** | Static solid. Never moves. |
| **Wood** | Static solid. Never moves, but is **flammable** — it ignites into fire when its own temperature exceeds its flashpoint (heated by a nearby fire or lava). |
| **Fire** | Gas-like heat source and short-lived. Holds a burn-temp (~800°) while it has life; the heat-diffusion pass carries that heat outward into neighbors. It does **not** spread by probability — flammable fuels (wood, plant) ignite themselves once their own temp crosses their flashpoint. Fire clings to fuel in reach, emits smoke above, and rises once the fuel is gone. |
| **Smoke** | Gas and short-lived. Rises straight up, drifts up-diagonals, and occasionally wafts sideways. Dissipates after a random lifetime. |
| **Plant** | Static solid. **Grows** into an empty neighbor when water is adjacent (water is not consumed). Also flammable (ignites above its flashpoint). |
| **Steam** | Hot gas. Rises like smoke and drifts up-diagonals; condenses back into water when it cools below its condense point. Produced by boiling water and by the lava+water reaction. |
| **Ice** | Cold static solid. Melts into water above 0°. Paint it cold, or freeze water by cooling it below freezing. |
| **Lava** | Very hot dense liquid. Flows like water but denser; cools into stone as it loses heat, and reacts with adjacent water (lava + water → steam + stone). Hot enough to ignite fuel and melt sand into glass. |
| **Glass** | Static solid made only by melting sand (drop sand on lava). Never moves once formed. |

The simulation runs at a fixed 60 FPS over a 200 x 140 grid — an 800 x 560
playfield (an 800 x 600 window with a 40px palette bar at the bottom and
4 x 4 pixel cells). Elements pile up on top of the palette bar, which acts
as the simulation floor. The window is **resizable**: drag the border and
the grid grows or shrinks in whole 4px cells (the 200 x 140 default is just
the starting size).

## Controls

| Input | Action |
| --- | --- |
| **Left-click / drag** | Paint the selected element under the cursor (ignored over the palette strip at the bottom). |
| **Right-click / drag** | Erase (paint EMPTY) under the cursor (ignored over the palette strip). |
| **Click a palette swatch** | Select that element. |
| **Eraser swatch** | Select the Eraser (rightmost swatch) so left-drag erases instead of painting. |
| **Mouse wheel** | Grow / shrink the brush radius (range 1–20). Scroll up to grow. |
| **Tab** | Cycle the brush footprint shape: **Disk** ↔ **Square** (the Brush-shape palette button does the same). |
| **Resize window** | Drag the window border to resize the playfield. The grid grows/shrinks in whole 4px cells; content outside the new area is **lost permanently** (only the top-left overlap is preserved). The 40px palette bar stays pinned to the bottom; an enforced minimum size keeps the palette usable. |
| **Space** | Pause / resume the simulation. |
| **N** | Advance exactly one step while paused (no-op while running). |
| **H** | Toggle the heat-map overlay (blue = cold, red = hot; ambient is neutral). The element palette and HUD stay visible, so you can still select elements while watching heat flow. |
| **Esc / close window** | Quit. |

Defaults: the selected element is **Sand**, the brush radius is **3**, and the
brush shape is **Disk**.

The top-left HUD shows the current FPS and brush radius. A red **PAUSED**
indicator appears centered at the top when the simulation is paused. The
active palette swatch is outlined in white. An always-on **cursor outline**
(circle for Disk, square for Square, sized to the brush radius) shows exactly
where the brush will land; it hides while the cursor is over the palette strip.

## Requirements

- **Python** >= 3.12
- **uv** (manages Python and all dependencies; the `uv.lock` lockfile is committed)
- **OS:** Linux. Windows and macOS builds are future work (see
  [Status](#status)) — the game itself runs anywhere pygame-ce does, but only
  the Linux single-binary build has been validated.

## Quick start (development)

From the repo root:

```bash
uv sync          # create the venv and install all dependencies (incl. dev deps)
uv run sandfall  # launch the game
```

## Tests, lint, and type-check

```bash
uv run pytest            # run the test suite
uv run ruff check .      # lint
uv run ruff format .     # format
uv run mypy src          # strict type-check
```

## Building the single-file binary

The build produces a single self-contained executable at `dist/sandfall`
(about 50 MiB, mostly SDL + numpy native libraries). No Python installation
is required on the target machine.

```bash
uv sync                                      # ensures PyInstaller is installed (a dev dep)
uv run pyinstaller sandfall.spec --noconfirm
./dist/sandfall                              # run it
```

Notes:

- `sandfall.spec` is a hand-written, git-tracked PyInstaller **one-file** spec
  (it builds the `EXE` directly from `PYZ + scripts + binaries + datas` with
  no `COLLECT` block, which would otherwise produce a directory of loose
  files).
- It pulls in pygame and numpy with `collect_all(...)` so their data files,
  native binaries, and hidden imports are all bundled.
- `console=True` is currently set so any startup traceback is visible on
  stderr — a console window will appear on launch. Flip this to `console=False`
  in the spec for a release GUI build.
- UPX compression (`upx=True`) is enabled but is a harmless no-op when UPX is
  not installed on the build host.
- `build/` and `dist/` are gitignored.

## Project layout

```
sandfall.spec              # PyInstaller one-file build spec
src/sandfall/
  __main__.py              # entry point (console script + PyInstaller target)
  game.py                  # main loop: input, paint, step, render, HUD, H overlay
  config.py                # window/grid/brush/UI tunables + thermal/diffusion knobs
  grid.py                  # Grid: uint8 id + uint8 life + int16 temp arrays
  elements.py              # ElementId enum, Phase enum, Element dataclass, ELEMENTS
  simulation.py            # Simulation.step: heat-diffusion pre-pass + scan + moved guard
  thermal.py               # diffuse_temps (heat pre-pass) + thermal_to_rgb (heat overlay)
  renderer.py              # Grid -> RGB via color LUT -> grid-sized Surface (+ render_heat)
  brush.py                 # paint_brush: disk/square paint + life + temp_spawn seeding
  control.py               # LoopController: pause / single-step state machine
  ui.py                    # palette layout + HUD (FPS, brush radius, paused)
  rules/
    __init__.py            # RULES registry: ElementId -> update function
    _common.py             # can_displace, swap, seed_*_life helpers
    sand.py                # POWDER: fall + diagonal pile (+ melt -> glass)
    water.py               # LIQUID: flow (+ boil -> steam / freeze -> ice)
    stone.py               # SOLID: no-op
    wood.py                # SOLID: reactive — ignites -> fire above flashpoint
    fire.py                # GAS-like heat source: age, maintain burn-temp, smoke, rise
    smoke.py               # GAS: age, rise, drift
    plant.py               # SOLID: grow near water (+ ignite above flashpoint)
    steam.py               # GAS: rise + condense -> water
    ice.py                 # SOLID: melt -> water
    lava.py                # LIQUID: flow, cool -> stone, lava+water -> steam+stone
    glass.py               # SOLID: no-op (made by sand melting)
tests/                     # pytest suite (grid, simulation, every rule, UI, brush, packaging)
```

For how the pieces fit together, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Status

**v1 is complete and Linux-only.** The game is fully playable and the
single-file binary build is validated on Linux x86-64.

Cross-platform packaging is deferred:

- **Windows `.exe` and macOS `.app` builds.** PyInstaller cannot
  cross-compile, so a Windows executable must be produced on Windows and a
  macOS app on macOS. The spec should generalize cleanly (the only
  platform-specific lines are `console=` and the bootloader, which
  PyInstaller picks automatically), but each platform will likely need its
  own spec tweaks (icon, code-signing, `console=False`).
- **CI matrix (GitHub Actions)** to run `uv sync && uv run pyinstaller <spec>`
  on Windows, macOS, and Linux runners and upload `dist/sandfall*` artifacts
  against release tags — the natural place to flip `console=False` and apply
  signing.

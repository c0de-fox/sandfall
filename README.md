# sandfall

A falling-sand sandbox game built with [pygame-ce] and numpy. Paint elements
onto a grid and watch them fall, flow, burn, and grow — in the spirit of
*sand:box*, *The Powder Toy*, and *Sandustry*.

This is a complete **v1**: seven interacting elements, mouse painting, a UI
palette, and a single self-contained Linux binary build.

[pygame-ce]: https://pyga.me/

## Features

Seven elements, each with its own physics and interactions:

| Element | Behavior |
| --- | --- |
| **Sand** | Powder. Falls straight down; piles sideways down-diagonals when blocked. Sinks through water (it is denser). |
| **Water** | Liquid. Falls, slips down-diagonals, and spreads one cell sideways into empty space to find its level. |
| **Stone** | Static solid. Never moves. |
| **Wood** | Static solid. Never moves, but is **flammable** — it catches fire when fire is next to it. |
| **Fire** | Gas-like and short-lived. Each step it ages, may ignite flammable neighbors (wood, plant), may puff out smoke above, and rises into empty space. It burns out and disappears after a random lifetime. |
| **Smoke** | Gas and short-lived. Rises straight up, drifts up-diagonals, and occasionally wafts sideways. Dissipates after a random lifetime. |
| **Plant** | Static solid. **Grows** into an empty neighbor when water is adjacent (water is not consumed). Also flammable. |

The simulation runs at a fixed 60 FPS over a 200 x 150 grid (an 800 x 600
window with 4 x 4 pixel cells).

## Controls

| Input | Action |
| --- | --- |
| **Left-click / drag** | Paint the selected element under the cursor (ignored over the palette strip at the bottom). |
| **Right-click / drag** | Erase (paint EMPTY) under the cursor (ignored over the palette strip). |
| **Click a palette swatch** | Select that element. |
| **Eraser swatch** | Select the Eraser (rightmost swatch) so left-drag erases instead of painting. |
| **Mouse wheel** | Grow / shrink the brush radius (range 1–20). Scroll up to grow. |
| **Space** | Pause / resume the simulation. |
| **N** | Advance exactly one step while paused (no-op while running). |
| **Esc / close window** | Quit. |

Defaults: the selected element is **Sand**, and the brush radius is **3**.

The top-left HUD shows the current FPS and brush radius. A red **PAUSED**
indicator appears centered at the top when the simulation is paused. The
active palette swatch is outlined in white.

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
  game.py                  # main loop: input, paint, step, render, HUD
  config.py                # window/grid/brush/UI tunables + brush clamping
  grid.py                  # Grid: uint8 element-id array + parallel life array
  elements.py              # ElementId enum, Phase enum, Element dataclass, ELEMENTS
  simulation.py            # Simulation.step: bottom-to-top scan + moved guard
  renderer.py              # Grid -> RGB via color LUT -> grid-sized Surface
  brush.py                 # paint_brush: disk paint + FIRE/SMOKE life seeding
  control.py               # LoopController: pause / single-step state machine
  ui.py                    # palette layout + HUD (FPS, brush radius, paused)
  rules/
    __init__.py            # RULES registry: ElementId -> update function
    _common.py             # can_displace, swap, seed_fire_life, seed_smoke_life
    sand.py                # POWDER: fall + diagonal pile
    water.py               # LIQUID: fall + diagonal + sideways flow
    stone.py               # SOLID: no-op
    wood.py                # SOLID: no-op (flammability lives on the ELEMENTS entry)
    fire.py                # GAS-like: age, spread, smoke, rise
    smoke.py               # GAS: age, rise, drift
    plant.py               # SOLID: grow near water
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

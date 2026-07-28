# Sandfall — Master Plan

## Problem Statement

Build a falling-sand / cellular-automata sandbox game (à la "sand:box", The Powder Toy, Sandustry, Atom Craft) from scratch using Python + pygame. The project is greenfield: the repo currently contains only `AGENTS.md` and a single initial commit. There is no `pyproject.toml`, no source, and `uv` is not even installed on the dev machine yet.

The user wants:
- A pygame-based interactive sandbox with multiple interacting elements (powders, liquids, solids, fire/gas, growth).
- `uv` for Python + dependency management.
- A build system that produces a **single self-contained binary** per platform (Windows + Linux minimum; Mac optional).

## Solution Summary

We build a minimal-but-complete vertical slice first, then layer on richness:

- **Engine**: a numpy `uint8` grid of element IDs + a per-cell rule-dispatch step loop. Bottom-to-top scan, randomized horizontal direction, "moved-this-frame" guard to prevent double updates.
- **Elements (v1 = exactly 7)**: `sand` (powder), `water` (liquid), `stone` (static solid), `wood` (flammable solid), `fire` (gas, finite life, ignites flammables), `smoke` (gas, rises & dissipates), `plant` (solid, grows near water).
- **Rendering**: pygame-ce, grid→Surface each frame via `pygame.surfarray`, scaled by `CELL_SIZE`.
- **UI**: element palette, scroll-wheel brush radius, FPS overlay, pause/step.
- **Packaging**: PyInstaller `--onefile` spec, Linux-only for now. Windows/mac + CI deferred.

## Phase List

| #  | Phase                                        | Cx | Depends On | Parallelizable With |
|----|----------------------------------------------|----|------------|---------------------|
| 01 | Project scaffolding (uv, pyproject, tooling) | S  | —          | —                   |
| 02 | Core simulation engine (grid + sand + tests) | M  | 01         | —                   |
| 03 | Minimal element set (water/stone/wood/fire/smoke/plant) | M  | 02 | 04         |
| 04 | Rendering & game loop (pygame-ce window)     | M  | 02         | 03         |
| 05 | UI (palette, brush radius, FPS, pause/step)  | M  | 04         | 06         |
| 06 | PyInstaller single-binary packaging (Linux)  | M  | 04         | 05         |

## Dependency Map

```
01 ──► 02 ──┬──► 03 (element rules)      ┐
            │                            │
            └──► 04 (rendering/loop) ──┬─┴──► 05 (UI)         ──► done
                                       │
                                       └──► 06 (packaging)    ──► done
```

- **01 → 02**: strict (need pyproject + tooling before writing code).
- **02 → 03 & 04**: both build on the engine; **03 and 04 are parallelizable** (pure rules vs pure rendering — they touch disjoint files).
- **04 → 05 & 06**: both build on the working game loop; **05 and 06 are parallelizable** (UI polish vs binary packaging — disjoint files). However, since 03 must also be done before "all 7 elements" are testable in-game, in practice 03 finishes around the same time as 04 and unblocks 05.
- A phase may only START once all its dependencies have passed their verification gates.

## Decision Log

All decisions below are **approved by the user** and must not be re-litigated.

1. **Name**: `sandfall` — used for the project name, the binary, the console-script entry, and the import package. `src/sandfall/` layout. *(Alternative considered: `sand-falling-game` / `powder-py` — rejected: less terse, more typing.)*
2. **Python**: 3.12 managed by uv. `pyproject.toml` + tracked `uv.lock`. *(Alternative: system Python / poetry — rejected: user explicitly wants uv.)*
3. **pygame flavor**: `pygame-ce` (Community Edition). Import is still `pygame`. *(Alternative: classic `pygame` — rejected: CE has better maintenance, bug fixes, and modern features while staying API-compatible.)*
4. **Grid representation**: numpy 2D `uint8` array of element IDs. *(Alternative: list-of-lists of Cell objects — rejected: too slow for bulk fills / rendering; numpy enables `surfarray` fast path.)*
5. **Element set for v1 (exactly 7)**: sand, water, stone, wood, fire, smoke, plant. Covers powders, liquids, static solids, combustion chains, gas rising, and growth — the minimum that exercises every physics phase. *(Alternative: ship 20+ elements up front — rejected: scope creep; ship a thin verifiable core first.)*
6. **Build scope (now)**: LOCAL LINUX single-binary via PyInstaller `--onefile` only. Windows, macOS, and CI are **explicitly deferred** — do NOT create phases for them. *(Alternative: set up cross-platform CI immediately — rejected: get a working Linux artifact first, then generalize.)*
7. **Tooling**: `pytest` (tests), `ruff` (lint + format), `mypy` (types, strict on `sandfall`). All managed as uv dev dependencies. *(Alternative: black+isort+flake8 — rejected: ruff replaces all three with one fast tool.)*

Additional design decisions encoded into phases (implementer should follow, not re-argue):

- **Coordinate convention**: origin (0,0) at **top-left**; **+y is DOWN** (gravity direction). +x is right.
- **Scan order**: `y` ascending top→bottom but cells fall *down*, so process bottom-to-top (`y` descending) so a single grain can fall at most one cell per step (prevents teleporting through the grid in one frame). `x` direction randomized per row to avoid left-bias.
- **Moved-this-frame guard**: maintain a set/`bool` array of cells already moved this step so a cell isn't updated twice.
- **Density-based swaps**: powders can sink into lower-density liquids (sand displaces water).
- **Plant growth rule**: requires *adjacency* to a WATER cell (proximity only; water is NOT consumed). Documented in phase 03.
- **Fire**: finite `life` decremented each step; spreads to flammable neighbors (wood/plant) with a per-step probability; chance to spawn SMOKE; on `life <= 0` becomes EMPTY; slight upward drift.
- **`.spec` is tracked, `uv.lock` is tracked, `dist/`/`build/`/caches are ignored** — see phase 01 `.gitignore`.

## Estimated Complexity

| Phase | Cx  | Why |
|-------|-----|-----|
| 01    | S   | Scaffolding + tool config; no logic. |
| 02    | M   | Core data model + step loop + careful ordering rules; foundational. |
| 03    | M   | Six elements with non-trivial interaction (fire chain, plant growth). |
| 04    | M   | pygame-ce setup, surfarray rendering, event loop, mouse painting. |
| 05    | M   | UI surface with several independent widgets. |
| 06    | M   | PyInstaller + pygame-ce bundling quirks. |

## Risks & Unknowns

1. **Pure-Python per-frame performance on large grids.** A 200×150 grid at 60 FPS with per-cell Python dispatch is ~1.8M cell-updates/sec — borderline. Mitigations if needed (deferred unless measured): vectorize common rules with numpy, dirty-cell tracking (only update cells that changed or have changed neighbors), cython/nuitka later. Phase 02 should leave a clean enough seam to swap in dirty-tracking later.
2. **PyInstaller + pygame-ce bundling quirks.** pygame-ce ships native libs and font data; the first build may segfault or miss fonts. Mitigation: `console=True` first for logs, add `hiddenimports`/`collect_data_files('pygame')` to the spec as needed. May require iteration.
3. **`uv` is not yet installed** on the dev machine. Phase 01 step 0 installs it via the official installer. This is a one-time environmental prerequisite, not a code risk.
4. **`pygame.MOUSEWHEEL` API** differs slightly across pygame versions; phase 05 should use the unified `pygame.MOUSEWHEEL` event (available in CE) with `.y` for vertical scroll.
5. **Non-deterministic tests.** Rules use randomness (fire spread, plant growth, x-scan direction). Tests must seed `random` or assert *eventually* / *within bounds* rather than exact positions. Phase 03 calls this out.

## Verification Philosophy (applies to ALL phases)

Every phase's `Verification Commands` block MUST include these five gates (in addition to any phase-specific commands), and ALL must exit zero before the next phase may begin:

```bash
uv run python -c "import sandfall"   # import / build smoke
uv run pytest                        # tests
uv run ruff check .                  # lint
uv run ruff format --check .         # format check
uv run mypy src                      # types
```

After each phase, the implementer MUST write `NN-<phase>-reflection.md` in this directory capturing: what was difficult/unexpected, deviations from the plan + why, what to pursue next, anything fun discovered.

## Out of Scope (Future Work — DO NOT plan now)

- Windows and macOS PyInstaller builds.
- CI (GitHub Actions) for automated cross-platform builds.
- More than the 7 v1 elements (acid, lava, oil, salt, electricity, etc.).
- Save/load, undo, scene presets.
- Sound, particles, screen shake, shaders.
- Dirty-cell / vectorized perf optimization (only if measured to be needed).

# Phase 02 Reflection — Particle-count HUD + pure `format_hud`

## What was done

- **`src/sandfall/ui.py`** — added a pure module-level `format_hud(fps,
  brush_radius, count) -> str` helper immediately after `palette_layout`
  (mirrors the existing pure-layout / pygame-draw split). `UI.draw` gained a
  required trailing `count: int` parameter; its docstring now mentions
  `count` is the non-empty-cell count shown in the HUD. The HUD render line
  (`ui.py:194`) calls `format_hud(fps, brush_radius, count)` with the existing
  `self._font` + `FPS_COLOR` — no new font/color/resource.
- **`src/sandfall/game.py`** — `Game._draw` computes the count ONCE per frame
  right before the `self._ui.draw(...)` call via
  `count = int((self._grid.array != int(ElementId.EMPTY)).sum())` and passes
  it as the new trailing positional argument. Uses the public `grid.array`
  property, not `grid._data`. `ElementId` was already imported.
- **`tests/test_ui.py`** — added `format_hud` to the existing
  `from sandfall.ui import ...` line and added
  `test_format_hud_includes_fps_brush_and_count`, pinning the exact format
  `f"{int(fps)} FPS  r={brush_radius}  n={count}"` for representative inputs
  including the empty-grid `count == 0` case and the `int(fps)` truncation
  (not rounding) case.

## Prompt-discrepancy flag — honored

The prompt asserted there was an existing HUD-string assertion in
`tests/test_ui.py` to update. There is no such test: `tests/test_ui.py`'s
module docstring (`tests/test_ui.py:1-12`) explicitly states `UI.draw`
rendering is *"intentionally not asserted pixel-by-pixel"* and is verified
manually via the `SANDFALL_FRAMES` seam. Per the plan's Decision Log #9 and
the prompt-discrepancy flag in `02-particle-count-hud.md`, this phase
**ADDs** a new test for the pure `format_hud` helper rather than updating an
existing one. The pure helper was extracted specifically to make the format
headlessly unit-testable (no pygame display needed in the test), exactly
mirroring `palette_layout`.

## Measured cost of the per-frame count

Measured on the default 200×140 grid (`uv run python -c "..."`, 1000 iters,
`time.perf_counter`, empty cache warmed):

| Grid state            | Count | Cost per frame     |
|-----------------------|-------|--------------------|
| empty                 | 0     | **0.0454 ms**      |
| ~50% full (top half)  | 14000 | **0.0390 ms**      |

Confirms the plan's `~0.04 ms` prediction — free at current grid sizes, well
below the ~16.6 ms frame budget. The full-grid sum is the right call vs.
incremental active-set tracking (which would add complexity for no measurable
gain). NOT a gate; reported here as evidence per the plan.

## HUD renders `n=<count>` — confirmed

`SANDFALL_FRAMES=60 uv run sandfall` exited 0 with **real SDL** (no
`SDL_VIDEODRIVER=dummy` fallback needed in this environment). For stronger
evidence than "exit 0", I drove `Game._draw` headlessly under
`SDL_VIDEODRIVER=dummy`, captured + 4×-zoomed the top-left HUD region, and
OCR'd it:

- empty grid: OCR reads **`0 FPS  r=3  n=0`**
- after `paint_brush(grid, 10, 10, 3, SAND)`: OCR reads **`0 FPS  r=3  n=29`**

The `n=` value tracks paint/erase exactly (computed counts: 0 → 29 → 0
across paint → erase). The `0 FPS` is because the clock hasn't ticked in a
single manual `_draw` (correct — `get_fps()` returns 0 until `tick()` runs);
in the real `SANDFALL_FRAMES=60` run the FPS reads normally. The format is
exact.

The pure-helper unit test additionally pins the format string itself, so the
HUD format is regression-protected independent of OCR.

## `docs/ARCHITECTURE.md`

Checked. `docs/ARCHITECTURE.md` references "HUD" only as a component label
(`UI (palette + HUD)`) and once in passing re: the heat overlay ("palette +
HUD remain visible"). It does **not** document the HUD readout at the
format level (no FPS/brush-radius/format_hud mention). Per the spec's
instruction ("If it does not document the HUD at that level, leave it"),
`docs/ARCHITECTURE.md` was left unchanged. Noting here for the record.

## Six verification gates — all green

| # | Gate                                         | Result |
|---|----------------------------------------------|--------|
| 1 | `uv run pytest tests/test_ui.py -v`          | ✅ 14 passed (13 prior + 1 new) |
| 2 | `uv run python -c "import sandfall"`         | ✅ exit 0 |
| 3 | `uv run pytest`                              | ✅ 159 passed (158 → 159) |
| 4 | `uv run ruff check .`                        | ✅ All checks passed |
| 5 | `uv run ruff format --check .`               | ✅ 47 files already formatted |
| 6 | `SANDFALL_FRAMES=60 uv run sandfall`         | ✅ exit 0 (real SDL) |

## Difficult / unexpected

- **Dummy-driver segfault on post-`run()` screenshot.** My first visual-check
  attempt set `SANDFALL_FRAMES=30` and called `pygame.image.save(screen, ...)`
  *after* `g.run()` returned. `Game.run()`'s `finally: pygame.quit()` had
  already destroyed the screen surface, so the save segfaulted
  (`pygame_parachute: Segmentation Fault`, exit 134). This is a test-harness
  bug, not a game bug — the game itself ran fine. Fix: drive `_draw()`
  manually without going through `run()`'s teardown, so the surface is still
  live when I save. Future agents doing visual verification of the HUD should
  note that `SANDFALL_FRAMES` + post-run screenshot is incompatible; either
  capture mid-loop or drive `_draw` directly.
- Nothing else unexpected. The signature-thread ripple was exactly one
  caller (`Game._draw`) — `tests/test_ui.py` does not call `UI.draw`, as the
  plan stated.

## Files touched

- `src/sandfall/ui.py` (pure `format_hud` helper + `UI.draw` signature + HUD line)
- `src/sandfall/game.py` (`Game._draw` count computation + threaded arg)
- `tests/test_ui.py` (import + new `test_format_hud_includes_fps_brush_and_count`)

No other files touched. Did NOT touch `simulation.py`, `rules/*`, `grid.py`,
`thermal.py`, `elements.py`, or `renderer.py`. Did NOT commit, stage, push,
or amend — changes left unstaged per instructions.

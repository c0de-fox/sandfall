# Phase 02: Particle-count HUD + pure `format_hud`

## Objective

Add a live count of non-empty cells next to the FPS/brush readout in the
top-left HUD. Compute the count once per frame in `Game._draw` (a full-grid
`!= EMPTY` sum, ~0.04 ms — free), thread it through `UI.draw`'s signature,
and render it in the existing HUD line at `ui.py:180`. Extract the HUD format
string into a **pure module-level helper** `format_hud(fps, brush_radius,
count) -> str` so the format is headlessly unit-testable (mirroring the
existing `palette_layout` pure/draw split). Add a focused test for the helper.

> **Prompt-discrepancy flag (read before starting):** the planning prompt
> asserted there is *"the one existing UI test that asserts the HUD string
> format"* in `tests/test_ui.py` and asked to update it. **There is no such
> test** — `tests/test_ui.py:1-12` explicitly states `UI.draw` rendering is
> *"intentionally not asserted pixel-by-pixel"* and is verified manually via
> the `SANDFALL_FRAMES` seam. This phase therefore **ADDs** a new test for the
> pure `format_hud` helper rather than updating an existing one. (See
> `00-overview.md` Decision Log #9 + the prompt-discrepancy flag.) The
> acceptance criterion ("the HUD shows `n=<count>`") is unchanged.

## Depends On

none — independent of Phase 01 (disjoint files).

## Can Parallelize With

Phase 01 (disjoint files: this phase touches `ui.py` + `game.py` +
`tests/test_ui.py`; Phase 01 touches `simulation.py` +
`tests/test_simulation.py`).

## Recommended Agent

@implementer — a mechanical signature thread + a pure-helper extraction + a
format-string change + one headless test. Read `00-overview.md` (Decision Log
#9-#10 and Risks #6) first.

## Changes Required

- `src/sandfall/ui.py` — add a pure module-level `format_hud(fps,
  brush_radius, count) -> str` helper (near `palette_layout`, `ui.py:61-86`);
  add a required `count: int` parameter to `UI.draw` (`ui.py:154-161`) at the
  END of the signature (positional, after `paused`); change the HUD render
  line (`ui.py:180`) to use `format_hud(fps, brush_radius, count)`.
- `src/sandfall/game.py` — in `Game._draw` (`game.py:263-287`), compute
  `count = int((self._grid.array != int(ElementId.EMPTY)).sum())` once before
  the `self._ui.draw(...)` call, and pass `count` as the new trailing
  positional argument at `game.py:281-287`.
- `tests/test_ui.py` — import `format_hush` from `sandfall.ui`; ADD
  `test_format_hud_includes_fps_brush_and_count` asserting the exact format
  string `f"{int(fps)} FPS  r={brush_radius}  n={count}"` for representative
  inputs (including `count == 0`).

## Implementation Instructions

> Re-read `src/sandfall/ui.py`, `src/sandfall/game.py`, and
> `tests/test_ui.py` before editing — line numbers below are current at
> planning time and may have drifted.

### 1. `src/sandfall/ui.py` — add the pure `format_hud` helper

Add the helper immediately AFTER `palette_layout` (which ends at `ui.py:86`),
before the `class UI:` definition (`ui.py:89`). It is the pure counterpart to
`UI.draw`'s HUD rendering, exactly mirroring how `palette_layout` is the pure
counterpart to `UI.draw`'s swatch rendering:

```python
def format_hud(fps: float, brush_radius: int, count: int) -> str:
    """Format the top-left HUD line: FPS, brush radius, particle count.

    Pure (no pygame) so the HUD format is unit-testable headlessly, mirroring
    the layout/draw split used for the palette (``palette_layout`` is the pure
    counterpart to ``UI.draw``'s swatch rendering). ``count`` is the number of
    non-empty cells on the grid (computed once per frame by the caller).
    """
    return f"{int(fps)} FPS  r={brush_radius}  n={count}"
```

### 2. `src/sandfall/ui.py` — extend `UI.draw` signature and use the helper

**2a. Add the `count: int` parameter** to `UI.draw` (`ui.py:154-161`) at the
END of the signature (positional, after `paused`, so the single caller in
`Game._draw` just appends one positional arg — minimal ripple):

```python
    def draw(
        self,
        screen: pygame.Surface,
        active: ElementId,
        fps: float,
        brush_radius: int,
        paused: bool,
        count: int,
    ) -> None:
```

Update the `UI.draw` docstring (`ui.py:162-167`) to mention `count` is the
non-empty-cell count shown in the HUD. One sentence appended to the existing
docstring is enough, e.g.:

```python
        ``active`` is the currently selected element (its swatch is
        outlined). ``fps``/``brush_radius``/``count`` are shown top-left
        (count is the number of non-empty cells); ``paused`` toggles the
        centered PAUSED indicator.
```

**2b. Change the HUD render line** (`ui.py:180`) from:

```python
        hud = self._font.render(f"{int(fps)} FPS  r={brush_radius}", True, FPS_COLOR)
```

to:

```python
        hud = self._font.render(format_hud(fps, brush_radius, count), True, FPS_COLOR)
```

Reuse the existing `self._font` (lazily created, `ui.py:170-171`) and the
existing `FPS_COLOR` import (`ui.py:26`). **No new font, no new color.**

### 3. `src/sandfall/game.py` — compute the count and thread it through

In `Game._draw` (`game.py:263-287`), compute the count ONCE before the
`self._ui.draw(...)` call and pass it as the new trailing positional argument.
The count uses the public `self._grid.array` property (`grid.py:66-71`, raw
uint8 `(H, W)` view; `ElementId.EMPTY == 0`):

```python
        # Particle count: non-empty cells, once per frame (~0.04 ms — free).
        # Full-grid sum, NOT incremental tracking — cheap at current grid
        # sizes; revisit only if a much larger grid makes it non-negligible.
        count = int((self._grid.array != int(ElementId.EMPTY)).sum())
        self._ui.draw(
            self._screen,
            self.selected_element,
            self._clock.get_fps(),
            self.brush_radius,
            self._loop.paused,
            count,
        )
```

(`ElementId` is already imported in `game.py` — `game.py:49`.) Compute it
ONCE; do NOT recompute per cell or per swatch. Place the computation right
before the `self._ui.draw(...)` call (after the grid render + scale + blit at
`game.py:278-280`), so it reflects the frame that is about to be drawn.

### 4. `tests/test_ui.py` — ADD a focused test for `format_hud`

`tests/test_ui.py` does NOT currently call `UI.draw` (its module docstring,
`tests/test_ui.py:1-12`, states rendering is verified manually via the
`SANDFALL_FRAMES` seam). The pure `format_hud` helper is the testable surface.

**4a. Update the import** at `tests/test_ui.py:18` to also import
`format_hud`:

```python
from sandfall.ui import PALETTE_BAR_HEIGHT, UI, Swatch, format_hud, palette_layout
```

**4b. ADD the test** (append after the existing tests):

```python
def test_format_hud_includes_fps_brush_and_count() -> None:
    """The HUD line shows FPS, brush radius, and particle count.

    Pure (no pygame) — tests the ``format_hud`` helper that ``UI.draw``
    renders. Pins the exact format so the count is actually surfaced to the
    user and so the format is stable across the signature change.
    """
    # Representative inputs, including the empty-grid case (count == 0).
    assert format_hud(59.7, 3, 0) == "59 FPS  r=3  n=0"
    assert format_hud(60.0, 5, 1234) == "60 FPS  r=5  n=1234"
    # fps is truncated to int (int()), not rounded.
    assert format_hud(59.9, 1, 7) == "59 FPS  r=1  n=7"
```

Notes for the implementer:
- This is the test the prompt called "a focused test that `UI.draw` renders
  the count." It tests the pure helper that `UI.draw` calls — transitively
  pinning what `UI.draw` renders, without requiring a pygame display. (There
  is no existing HUD-string assertion to update; see the prompt-discrepancy
  flag at the top of this file.)
- The `count` value is computed by `Game._draw`; the helper itself just
  formats. A separate integration-style check that painting N cells raises
  the count is covered by the existing brush tests + the `SANDFALL_FRAMES`
  smoke; do NOT add a pygame-driven count test here (it would require a
  display and break the headless contract of this file).

## Acceptance Criteria

- [ ] `ui.format_hud(fps, brush_radius, count)` is a pure module-level
      function returning `f"{int(fps)} FPS  r={brush_radius}  n={count}"`
      (test passes).
- [ ] `UI.draw`'s signature ends with `count: int` (positional, after
      `paused`); its docstring mentions `count`.
- [ ] The HUD render line (`ui.py:180`) uses `format_hud(fps, brush_radius,
      count)` with the existing font and `FPS_COLOR` (no new font, no new
      color).
- [ ] `Game._draw` computes `count = int((self._grid.array !=
      int(ElementId.EMPTY)).sum())` ONCE per frame and passes it to
      `self._ui.draw(...)` as the trailing positional argument.
- [ ] `tests/test_ui.py::test_format_hud_includes_fps_brush_and_count` passes
      (covers the empty-grid `count == 0` case and the `int(fps)` truncation).
- [ ] `UI.draw`'s signature change is threaded through the single caller
      (`Game._draw`); no other caller exists (verify `uv run mypy src` +
      `uv run pytest` are green).
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the new format_hud test + the existing pure UI tests):
uv run pytest tests/test_ui.py -v

# Import smoke:
uv run python -c "import sandfall"

# FULL suite — confirms the UI.draw signature thread didn't break anything:
uv run pytest

# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy) — visually confirm the
# HUD now reads e.g. "60 FPS  r=3  n=0" on an empty grid and that painting
# raises n=:
SANDFALL_FRAMES=60 uv run sandfall
```

All commands must exit zero. The `SANDFALL_FRAMES` smoke is the manual visual
check that the count actually appears on screen and tracks painting/erasing
(the pure helper test covers the format string itself).

## Documentation Updates

- The `UI.draw` docstring is updated as part of the code change above (it is
  the source of truth for the HUD).
- `docs/ARCHITECTURE.md` — if it documents the HUD readout, mention the
  particle count (`n=<count>`) and the pure `format_hud` helper. If it does
  not document the HUD at that level, leave it. Note whichever you find in
  the reflection.

## Reflection & Commit

After implementation, write `02-particle-count-hud-reflection.md` in this
directory. **Specifically include:**

- Confirmation that the prompt-discrepancy flag was honored: there was no
  existing HUD-string assertion in `tests/test_ui.py` to update, so a new
  `test_format_hud_includes_fps_brush_and_count` was ADDED instead (and the
  pure `format_hud` helper was extracted to make it headlessly testable,
  matching the `palette_layout` pure/draw split).
- The measured cost of `int((self._grid.array != int(ElementId.EMPTY)).sum())`
  on the default grid (confirm it is sub-millisecond — should be ~0.04 ms).
  NOT a gate; report as evidence.
- Whether `docs/ARCHITECTURE.md` documented the HUD and was updated.
- Anything difficult/unexpected, deviations from this plan + why, and
  anything fun discovered.

Then make ONE atomic git commit covering all changes in this phase.

# Phase 05 Reflection — UI (palette, brush wheel, FPS overlay, pause/step)

## What was done

Implemented Phase 05 (UI) AND fixed the carry-over FIRE/SMOKE brush
life-seeding bug deferred from Phase 04. The game is now fully usable from
the keyboard + mouse: a clickable element palette at the bottom of the
window, scroll-wheel brush sizing with on-screen readout, an FPS overlay,
SPACE to pause, N to single-step while paused, plus painted fire/smoke that
actually burns.

End state (52 → 75 tests, all 5 gates green, frame-cap smoke clean):

- `src/sandfall/rules/_common.py` — EDIT. Promoted FIRE/SMOKE lifetime
  seeding to **public** `seed_fire_life()` (`randint(20,40)`) and
  `seed_smoke_life()` (`randint(60,120)`), the new single source of truth
  for those ranges. Added `import random`.
- `src/sandfall/rules/__init__.py` — EDIT. Re-exports
  `seed_fire_life`/`seed_smoke_life` so callers can do
  `from sandfall.rules import seed_fire_life`; added `__all__`.
- `src/sandfall/rules/fire.py` — EDIT. Removed its private `_seed_*`
  copies; now imports the public helpers from `_common`. The ignition and
  smoke-spawn paths call the same functions the brush uses.
- `src/sandfall/brush.py` — NEW. Pure `paint_brush(grid, gx, gy, radius,
  element_id)` wrapping `Grid.fill_circle` + a life-seeding pass for
  FIRE/SMOKE (the deferred-bug fix). No pygame → headless-testable.
- `src/sandfall/control.py` — NEW. Pure `LoopController` dataclass: the
  pause/single-step state machine (`paused`, `toggle_pause`,
  `request_step`, `consume_step`). No pygame → headless-testable.
- `src/sandfall/ui.py` — NEW. `Swatch` frozen dataclass with correct
  `contains`; pure `palette_layout(window_width, bar_y)` → left-to-right
  swatches for non-EMPTY elements; `UI` class with `swatch_at`,
  `in_reserved_area`, and a `draw(...)` that renders FPS + brush radius
  (top-left), a centered PAUSED indicator, and the semi-transparent
  palette bar with swatches + active highlight.
- `src/sandfall/config.py` — EDIT. UI tunables (`PALETTE_BG` RGBA,
  `PALETTE_SWATCH=24`, `PALETTE_PADDING=4`, `PALETTE_MARGIN=8`,
  `BRUSH_MIN=1`, `BRUSH_MAX=20`, `FPS_COLOR`, `HIGHLIGHT_COLOR`,
  `PAUSED_COLOR`, `FONT_NAME=None`, `FONT_SIZE=16`) and a pure
  `clamp_brush_radius(radius) -> int` helper.
- `src/sandfall/game.py` — EDIT. Wires `UI`, `LoopController`,
  `paint_brush`, `clamp_brush_radius`; handles `MOUSEWHEEL`, palette
  `MOUSEBUTTONDOWN`, `K_SPACE`/`K_n`; gates `sim.step()` on
  `loop.consume_step()`; suppresses painting in the palette strip; calls
  `ui.draw(...)` after the grid blit.
- `tests/test_brush.py` — NEW. 8 tests covering the life-seeding fix:
  seed helpers in range, FIRE/SMOKE painted with non-zero in-range life,
  **painted fire survives a `Simulation.step`** (the explicit regression),
  non-life elements leave life 0, radius-0 single cell, out-of-bounds
  safety, and stale-life overwrite.
- `tests/test_control.py` — NEW. 7 tests pinning the
  pause/step state machine incl. the stale-request edge case (request
  step, unpause before it fires → no surprise step after re-pause).
- `tests/test_ui.py` — NEW. 8 headless tests: one swatch per non-EMPTY
  element, left-to-right enum order with no overlap, configured swatch
  size, `Swatch.contains` semantics, `swatch_at` round-trip + None
  outside / in gaps, `in_reserved_area` covers only the bottom strip, and
  strip lies inside the window.

Tests: **75 passed** (was 52). +8 brush, +7 control, +8 ui = +23.

## Verification gate results (all pass, exit 0)

| Gate | Result |
|------|--------|
| `uv run python -c "import sandfall; from sandfall.ui import palette_layout; ..."` | `palette swatches: 7`, `lazy ok` (`pygame` not in `sys.modules` after `import sandfall`) |
| `uv run pytest` | `75 passed in 0.63s` |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `35 files already formatted` |
| `uv run mypy src` | `Success: no issues found in 20 source files` |
| `SANDFALL_FRAMES=60` loop (in-process, `SDL_VIDEODRIVER=dummy`) | `main() returned: 0`, no traceback |

The frame-cap smoke is run via `uv run python /tmp/opencode/smoke_frames.py`
(body: `os.environ['SANDFALL_FRAMES']='60'; setdefault SDL_VIDEODRIVER=dummy;
from sandfall.__main__ import main; sys.exit(main())`). Same `main()` the
console script invokes. The orchestrator will additionally run
`SANDFALL_FRAMES=60 uv run sandfall` on the real `DISPLAY=:1`.

## Palette / HUD geometry

- The palette occupies a **reserved bottom strip** of height
  `PALETTE_BAR_HEIGHT = PALETTE_SWATCH + 2*PALETTE_MARGIN = 24 + 16 = 40px`,
  i.e. `bar_y = WINDOW_HEIGHT - 40 = 560`. Swatches are 24×24 squares laid
  out left-to-right from x = `PALETTE_MARGIN = 8`, `PALETTE_PADDING = 4`
  between neighbors, vertically centered in the strip (y = `bar_y +
  PALETTE_MARGIN = 568`). At 800px wide there is plenty of room for the 7
  swatches (7×24 + 6×4 + 2×8 = 208px); the remaining right side is empty
  bar — fine for v1; future elements fit until ~30 swatches before needing
  to wrap.
- The strip is rendered as a **semi-transparent black RGBA bar**
  (`PALETTE_BG=(0,0,0,180)`) via a lazily-created `pygame.Surface(...,
  SRCALPHA)` blitted once per frame, so the playfield is faintly visible
  behind it. Swatches are opaque `ELEMENTS[eid].color` rects; the active
  element gets a 2px white `HIGHLIGHT_COLOR` outline.
- HUD top-left: `"{int(fps)} FPS  r={brush_radius}"` in yellow
  (`FPS_COLOR`). When paused, a red `PAUSED` text is centered along the
  top edge (`PAUSED_COLOR`).
- `pygame.font.Font(None, 16)` = pygame's **bundled** default font, so no
  system font lookup is required.

## How palette clicks are separated from grid painting

The grid renders across the *entire* window (800×600) including behind the
palette strip, so there are two concerns: (a) a click on a swatch must
select, not paint; (b) dragging across the strip must not paint under it.

Resolution, single mechanism:

- On `MOUSEBUTTONDOWN` button 1, `ui.swatch_at(mx, my)` is queried; if it
  returns an element, `selected_element` is updated and nothing else
  happens that event.
- `_paint_if_dragging` checks `ui.in_reserved_area(mx, my)` (true for
  `my >= bar_y`) and **returns early** when the cursor is in the strip.
  This single guard handles every case: a click-down on a swatch (cursor
  in strip → no paint), dragging from the playfield up over the strip
  (painting pauses while over the strip), and dragging from a swatch down
  into the playfield (painting resumes with the newly-selected element
  once the cursor leaves the strip). No `_just_clicked_palette` flag was
  needed — the reserved-area check subsumes it.

## Brush radius

- `MOUSEWHEEL` event: `self.brush_radius = clamp_brush_radius(
  self.brush_radius + event.y)`. `event.y` is +1 for scroll-up, −1 for
  scroll-down in pygame-ce, so **scroll-up grows the brush**. Range is
  `[BRUSH_MIN=1, BRUSH_MAX=20]` enforced by the pure `clamp_brush_radius`
  helper (also unit-tested). The current radius is shown in the HUD
  (`r={brush_radius}`) so the wheel effect is visible without a cursor
  preview.

## Pause / step

- **SPACE** → `loop.toggle_pause()`. **N** → `loop.request_step()` (only
  queues a step while paused). The main loop calls
  `loop.consume_step()` once per frame and steps the sim only when it
  returns True: continuously while running, exactly once after an N press
  while paused, never otherwise.
- The pause/step logic is **extracted into `LoopController`** (its own
  pygame-free `control.py`) so its state machine is unit-tested headlessly
  (7 tests), including a stale-request edge case I added (see
  "Difficulties"). Painting and rendering still run while paused — only
  `sim.step()` is gated — so you can set up a scene while paused and then
  N-step through it.
- A red `PAUSED` indicator is drawn centered along the top edge so the
  frozen state is obvious.

## The FIRE/SMOKE life-seeding fix (Phase 04 carry-over bug)

Root cause: `Grid.fill_circle` paints the element id but **zeros life** on
every painted cell (documented contract). So brushing FIRE/SMOKE produced
cells with `life=0` that the fire/smoke rules immediately expired to EMPTY
on the first `Simulation.step` — painted fire literally never burned.

Fix:

1. Promoted the rules' private `_seed_fire_life`/`_seed_smoke_life` to
   public `seed_fire_life`/`seed_smoke_life` in `rules/_common.py` and
   re-exported from `rules/__init__.py`. Now there is **one** place that
   owns those ranges; the fire rule and the brush both call it.
2. `paint_brush` calls `grid.fill_circle(...)` then, for FIRE/SMOKE only,
   walks the same disk again and calls `grid.set_life(x, y, seed())` on
   each painted cell. For all other elements the seeding pass is skipped
   (life stays 0, matching `fill_circle`'s default).
3. `Game._paint_if_dragging` now calls `paint_brush(...)` instead of
   `fill_circle(...)` directly.

Regression coverage (hard requirement this phase):
`test_paint_brush_fire_does_not_expire_on_first_step` paints a FIRE disk
on a stone floor, runs exactly one `Simulation.step`, and asserts
`remaining_fire > 0`. Before the fix this would assert (all fire →
EMPTY); after, the fire persists. Plus range assertions (FIRE 20–40,
SMOKE 60–120) on every painted cell.

## Difficult / unexpected

1. **`zip(swatches, swatches[1:], strict=True)` is wrong for pairwise
   iteration.** My first test draft used `strict=True` (bugbear B905
   nudges toward `strict=`), but the standard pairwise idiom deliberately
   drops the last element, so the two args are intentionally unequal
   length → `strict=True` raises `ValueError`. Fix: `strict=False`
   (explicit, B905-clean, documents intent).
2. **`LoopController` had a stale-request leak.** Original `consume_step`
   only cleared `_step_once` in the paused branch. So: pause → N
   (queue) → unpause before the frame ticks → re-pause → the old request
   fired as a surprise step. My test
   `test_step_request_does_not_persist_across_pause_cycles` caught it.
   Fix: `consume_step` clears `_step_once` when running too (a continuous
   run already advanced the sim, so the queued single step is moot). This
   is a real correctness improvement, not just a test artifact — a user
   can absolutely hit "press N then SPACE twice quickly".
3. **ruff UP037 flags string-quoted annotations** under
   `from __future__ import annotations` (PEP 563 already makes all
   annotations strings, so explicit quotes are redundant). My first
   `ui.py` draft quoted the pygame annotations (`"pygame.font.Font |
   None"`); ruff wanted them unquoted. Removing the quotes is safe — PEP
   563 keeps them lazy at runtime, and mypy still resolves `pygame` via
   the `if TYPE_CHECKING: import pygame` guard. Net: `ui.py` has **no
   runtime pygame import** at all (only a local `import pygame` inside
   `draw`), so the pure layout/hit-test helpers are importable without a
   pygame runtime.
4. **B905 also flags the default zip in tests** (no `strict=` given) —
   fixed with explicit `strict=False` (see #1).
5. **E501 on the `PALETTE_BG` line** (inline RGBA comment pushed it past
   88 cols). `ruff format` wanted to explode the 4-tuple across 6 lines,
   which is ugly for a simple constant. Fix: moved the comment to its own
   line above the assignment.

## Deviations from the phase file

1. **Kept `selected_element` / `brush_radius` as PUBLIC `Game`
   attributes.** The phase-05 snippet renamed them to `self._selected` /
   `self._brush_radius`, but the Phase 04 reflection documented them as
   the public Phase-05 mutation seam and the task brief explicitly says
   "Game exposes `selected_element: ElementId` and `brush_radius: int`
   for you to mutate." Kept public, documented in the class comment.
2. **Added two new modules (`brush.py`, `control.py`)** beyond the
   phase file's `ui.py`-only NEW list. Both exist purely to make the
   life-seeding fix and the pause/step state machine **headless-testable**
   (Game needs pygame, so any logic worth testing must live elsewhere).
   The phase file explicitly endorses extracting pure helpers
   ("separate the layout from the drawing"; "extract a pure Stepper"),
   so this is in spirit. Each new module is small and single-purpose.
3. **Moved FIRE/SMOKE seed helpers to `rules/_common.py` (public)** and
   re-exported from `rules/__init__.py`, per the phase file's first
   suggestion ("move/alias them into a shared spot like
   `rules/__init__.py` or a small `rules/_common.py` function"). Removed
   the private `_seed_*` copies from `fire.py`.
4. **Extended `UI.draw`'s signature** to `(screen, active, fps,
   brush_radius, paused)`. The phase snippet had only `(screen, active,
   fps)`; the brief asked to show the brush radius somewhere and display
   a PAUSED indicator, so `brush_radius` and `paused` are passed in. The
   HUD string is `"{fps} FPS  r={radius}"` top-left; PAUSED is centered
   top.
5. **`ui.py` uses `TYPE_CHECKING` + lazy `import pygame` inside `draw`**
   (not a top-level `import pygame`). This keeps `import sandfall.ui`
   pygame-free at runtime, so `test_ui.py`'s layout/hit-test tests run
   with zero pygame — slightly cleaner than the phase snippet (which
   only made the font lazy).
6. **Implemented the palette bar as a semi-transparent SRCALPHA
   surface** (the phase file's `PALETTE_BG=(0,0,0,180)` is RGBA, implying
   transparency). A plain opaque `draw.rect` would have ignored the
   alpha; the SRCALPHA surface honors it so the playfield shows through
   faintly behind the swatches.

## IMPORTANT for Phase 06 (packaging)

- **`pygame.font.Font(None, 16)` uses pygame's BUNDLED default font**
  (`freesansbold.ttf`, shipped inside the pygame-ce wheel). It does NOT
  call into system fontconfig, so a PyInstaller binary with no system
  fonts will still render the HUD — **as long as the bundled font data
  is collected**. The standard `PyInstaller.utils.hooks
 .collect_data_files('pygame')` (or `collect_all('pygame')`) should pull
  `freesansbold.ttf` in. If the packaged binary raises
  `pygame.error: font not initialized` or renders blank text, the
  missing piece is almost certainly the font data not being collected —
  add `--collect-data pygame` (or the hook) to the spec. Verified
  manually: under `SDL_VIDEODRIVER=dummy`, `Font(None,16).render(...)`
  works and returns a non-zero-sized Surface (the frame-cap smoke called
  `UI.draw` 60 times).
- **`MOUSEWHEEL` (`event.y`)** is a core SDL event; no extra pygame
  submodule or data is needed for it to fire in a frozen binary.
- **`pygame.Surface((w,h), pygame.SRCALPHA)`** + `transform.scale` are
  pure SDL ops; no extra resources.
- The `SANDFALL_FRAMES` seam still works identically; Phase 06 should
  smoke-test the packaged binary with `SANDFALL_FRAMES=60 ./sandfall`
  (the same in-process form is fine, but the real CLI form
  `SANDFALL_FRAMES=60 sandfall` is the canonical one — and unlike the
  agent allowlist here, a packaging CI shell can use the env-prefix form
  directly).
- No new native deps. `brush.py` / `control.py` / `ui.py`'s pure helpers
  import only numpy (transitively via `grid`) + stdlib; `ui.draw` is the
  only new pygame-API surface (font + Surface + draw.rect), all of which
  are already used elsewhere in the codebase.

## Suggestions for future work / agent improvements

- **The "reserved area" painting pattern generalizes.** Any future
  on-screen UI (toolbar, side panel, modal) should follow the same
  contract: a pure `in_reserved_area(px, py)` predicate the painter
  consults. Worth capturing in the project AGENTS.md if more UI regions
  appear.
- **`Grid.fill_circle`'s life-zeroing contract is a footgun for brushes.**
  Long-term, consider a `Grid.paint_circle(cx, cy, r, eid, *,
  seed_life=False)` that owns the seeding inline, so callers can't forget.
  Out of scope for this phase (would change `fill_circle` semantics that
  52 existing tests rely on); flagged for a future refactor.
- **Agent-prompt note (global):** bugbear B905 (`zip()` without
  `strict=`) collides with the classic pairwise idiom
  `zip(xs, xs[1:])`. When a phase encourages pairwise iteration, the
  agent should reach for `strict=False` explicitly rather than
  `strict=True` — the latter is wrong for unequal-length pairwise. Could
  be added to the project AGENTS.md "testing" notes.
- **`ui.py`'s TYPE_CHECKING + lazy-import-inside-draw pattern** keeps
  pure helpers display-free while still satisfying mypy strict. This is
  the same lesson as Phase 04's lazy-entry pattern; could be generalized
  into a "headless pygame modules" note in the project AGENTS.md:
  *prefer `if TYPE_CHECKING: import pygame` + a local `import pygame`
  inside the draw method over a top-level import, so layout/pure helpers
  stay importable without a pygame runtime.*

## Fun discovered

- `pygame.Surface(..., pygame.SRCALPHA).fill((r,g,b,a))` blitted onto the
  opaque screen surface Just Works under both the real and dummy SDL
  drivers — no `convert_alpha()` needed. The semi-transparent palette bar
  composites correctly on the first try.
- The whole UI layer (palette + HUD + paused indicator) added ~0
  measurable overhead to the 60-frame loop smoke — still well under a
  second wall for 60 frames at 60 FPS (most of which is `clock.tick`
  sleeping). `pygame.font.Font.render` of a 12-char string is cheap.
- Extracting `LoopController` made the pause/step behavior genuinely
  obvious to reason about: the "consume_step returns bool" contract is a
  4-line method, and the 7 tests pin every transition including one I
  would not have thought to manual-test (the stale-request leak). This
  is the testability dividend the phase file was pushing toward.

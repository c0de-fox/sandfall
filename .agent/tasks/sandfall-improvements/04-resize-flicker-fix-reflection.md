# Phase 04 Reflection — Resize flicker fix (pygame.Window backend swap)

A follow-up to Phase 03 (resizable window). Phase 03's resize worked headlessly
and in the frame-cap smoke, but on a real Wayland compositor the window
**flickered (disappear/reappear) and didn't change size** while dragging.
Fullscreen worked. This phase fixed it by swapping the display backend.

## What was done

Two atomic commits via the **@refactorer** agent (plus an orchestrator doc pass):

1. **`c0b05f7`** — Reverted the X11-forcing hack from `ff179bd`
   (`_prefer_x11_video_driver` + `tests/test_main.py`). It hadn't fixed the
   flicker and the user rejected forcing X11 (not future-proof for Wayland-only
   distros).
2. **`2d25532`** — Swapped `Game` from `pygame.display.set_mode` to the
   **`pygame.Window` API** (pygame-ce ≥ 2.5.2): one `pygame.Window(resizable=True)`
   created in `__init__`; `Window.get_surface()` (which auto-tracks the window
   size) + `Window.flip()`; `Window.minimum_size = (256, 200)` for the floor.
   Resize is detected by **polling `Window.size` once per frame** in the new
   `Game._apply_resize_if_changed`, which runs `compute_grid_dims` →
   `migrate_grid` (preserve overlap) → rebuild `Simulation` → refresh the
   surface ref → `UI.resize`. **No `display.set_mode` call remains anywhere.**
   Added `tests/test_resize.py` (grow preserves overlap, shrink crops, no-op
   when unchanged, constructor pins the new wiring) — all headless under
   `SDL_VIDEODRIVER=dummy`.
3. **`9ef58e7`** — Refreshed stale doc references the refactorer intentionally
   left (`VIDEORESIZE` / `_handle_resize` → per-frame `Window.size` poll).

**Verified:** 107 tests; ruff / format / mypy-strict clean; source
`SANDFALL_FRAMES=60 uv run sandfall` exit 0; dev + release binaries rebuild and
run exit 0. **User confirmed** smooth interactive resize with the sand
following the new play area.

## Difficult / unexpected

1. **Misdiagnosis.** First fix (`ff179bd`) blamed the Wayland video driver and
   forced X11/XWayland. It didn't work — pygame-ce *already* often uses
   XWayland on Wayland desktops by default, so forcing it changed nothing. The
   user also (correctly) objected to forcing X11 for Wayland-only distros.
2. **Real root cause** (from the pygame-ce display docs): `display.set_mode()`
   *"will close the previous display"* — it **destroys and recreates the
   window** on every call. Phase 03 called it on every `VIDEORESIZE`, so
   dragging repeatedly recreated the window → the flicker. The cached display
   surface can't be refreshed any other way with the legacy API, so the
   *resize approach itself* was the problem, not the driver.
3. **The fix was simpler than feared.** Option B initially looked like a heavy
   `Renderer`/`Texture` refactor. Reading the `pygame.Window` docs revealed
   `Window.get_surface()` returns a surface that *"will change size with the
   Window"* — software rendering with an auto-resizing surface, no
   Renderer/Texture needed.

## Deviations

- **Spike first.** The flicker only manifests under a live compositor drag
  (unreproducible headlessly), so a throwaway `scripts/resize_spike.py` (~40
  lines) was built for the user to validate the `pygame.Window` approach BEFORE
  committing to the refactor. It de-risked the direction; the user confirmed
  smooth resize; the spike was then deleted.
- **Used @refactorer** (user suggestion) rather than @implementer. Framed it as
  a "modernize" backend swap preserving gameplay behavior; the refactorer's
  behavior-preservation discipline fit well. The resize-bug fix was an inherent
  consequence of the API swap, not a separate change.
- The refactorer can't run `./dist/sandfall` or `VAR=val uv ...` (allowlist), so
  the orchestrator did the real-display + packaged-binary smoke.

## Suggestions for future work / agent improvements

- **Global AGENTS.md (pygame-specific lesson):** *"For flicker-free, Wayland-
  native window resize in pygame-ce ≥ 2.5.2, use the `pygame.Window` API —
  `Window.get_surface()` auto-tracks the window. Never call
  `pygame.display.set_mode()` on resize; it destroys and recreates the window
  and causes flicker."* This cost a misdiagnosis round and would be reused on
  any future GUI project.
- **Process:** when a bug only reproduces under live GUI interaction, build a
  minimal spike for the user to validate the approach before a big refactor.
  Saved real time here and is worth capturing in the global process notes.
- **Allowlist:** the refactorer/implementer bash allowlists block
  `VAR=val uv ...` and `git rm` / executing built binaries. Adding those would
  smooth smoke-test ergonomics.

## Fun discovered

- `Window.minimum_size` pushes min-size enforcement **down to the compositor**
  — cleaner than any in-app clamp, and it Just Works across platforms.
- Per-frame `Window.size` polling turned out more robust than handling
  `VIDEORESIZE`/`WINDOWRESIZED` events — it's driver/compositor-independent,
  which is exactly what you want for something this finicky.

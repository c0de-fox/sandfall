# Phase 01 Reflection — Thermal data model (temp array + diffusion + plumbing)

## Summary

Implemented the foundational temperature field as a third parallel `int16`
array on `Grid`, mirroring the existing `life` consistency contract across
every seam (`swap`, `fill_circle`, `migrate_grid`, `paint_brush`). Added the
thermal `Element` dataclass fields (all defaulted), `AMBIENT_TEMP` + diffusion
tunables, a new pure `thermal.py` module (`diffuse_temps` +
`build_conductivity_lut`), the diffusion pre-pass wired into
`Simulation.step`, spawn-temp seeding in `paint_brush`, and full test coverage.
**No visible behavior change** — `fire.py`/`wood.py`/`plant.py` were not
touched; the old probabilistic fire spread is intact (Phase 02's job).

## Files changed

- `src/sandfall/elements.py` — `AMBIENT_TEMP`/`TEMP_MIN`/`TEMP_MAX` defined at
  the top (above the dataclass); `Element` extended with `temp_spawn`,
  `flashpoint`, `conductivity`, `burn_temp`, `melt_point`, `boil_point`,
  `freeze_point`, `condense_point` (all defaulted); WOOD/PLANT/FIRE/WATER/etc.
  populated with the plan's thermal values.
- `src/sandfall/config.py` — re-exports the three temp-band constants (via
  `__all__`); adds `DIFFUSION_RATE` + `COND_*` per-material conductivities.
- `src/sandfall/grid.py` — `_temp: NDArray[int16]` + `temp` property +
  `get_temp`/`set_temp` (clip to `[TEMP_MIN, TEMP_MAX]`); temp carried in
  `fill_circle` (→ `AMBIENT_TEMP`) and `migrate_grid`.
- `src/sandfall/rules/_common.py` — `swap` now carries temp (id + life + temp).
- `src/sandfall/brush.py` — `paint_brush` sets `ELEMENTS[id].temp_spawn` after
  `fill_circle`.
- `src/sandfall/thermal.py` (NEW) — pure `diffuse_temps` + `build_conductivity_lut`.
- `src/sandfall/simulation.py` — `__init__` builds the LUT once; `step` runs
  diffusion before the movement scan.
- `tests/test_grid.py`, `tests/test_brush.py` — extended; `tests/test_thermal.py`
  (NEW) — 7 diffusion-math tests.

Tests: **107 → 124 passed** (+17).

## Decision pinned: config↔elements import direction

Followed the plan's RECOMMENDED option: `AMBIENT_TEMP`/`TEMP_MIN`/`TEMP_MAX`
are **defined at the top of `elements.py`** (above the dataclass) and
**re-exported from `config.py`**. `elements.py` therefore has **zero
dependency on `config.py`** (one-way: `config → elements`), which is what
breaks the would-be circular import (`config` already imports `ElementId`
from `elements`). The `Element.temp_spawn`/`burn_temp` defaults reference
`AMBIENT_TEMP` directly since it is now in the same module.

## What was difficult / unexpected

The re-export mechanism was the only friction. Three tools constrain it:

1. **mypy `strict = true`** enables `no_implicit_reexport` → a plain
   `from .elements import AMBIENT_TEMP` in `config.py` is treated as NOT
   exported, so `thermal.py`'s `from .config import TEMP_MAX` failed with
   `Module does not explicitly export attribute`.
2. **ruff `F401`** flags the same plain import as "imported but unused" (the
   names are only re-exported, never used inside `config.py`).
3. **ruff `I001` (isort)** wants the `from x import a as a` explicit-re-export
   form split into N separate `from .elements import` statements, which is
   verbose/ugly.

**Resolution:** used `__all__ = ["AMBIENT_TEMP", "TEMP_MAX", "TEMP_MIN"]` in
`config.py`. This satisfies all three (ruff F401 honors `__all__`; isort keeps
one clean import block; mypy treats listed names as explicit exports) and is
**consistent with the codebase's existing convention** — `rules/__init__.py`
already re-exports `seed_fire_life`/`seed_smoke_life` via `__all__`. Listing
ONLY these three is correct: every other name in `config.py` is *defined*
there, so mypy treats it as exported automatically; only *re-exported*
(imported-then-exposed) names need the marker. The narrow star-export surface
(`from config import *` would now yield only these 3) is theoretical — no
file in the tree uses star imports of `config` (it has 30+ names; star-importing
it was never intended). I first tried the `import X as X` form but reverted
because isort's split was worse than `__all__`.

## Deviations from the plan (minor)

1. **`paint_brush` early-return:** added
   `if spawn_temp == AMBIENT_TEMP and seed is None: return` before walking the
   disk, so the common case (SAND/WATER/STONE/etc.) skips the second disk walk.
   The plan explicitly blessed this ("The `AMBIENT_TEMP` short-circuit is a
   minor perf nicety"); contract ("painted cell has `temp_spawn`") preserved.
2. **`diffuse_temps` padding dtype:** cast the padded array to `float64` at pad
   time (`np.pad(temp, ...).astype(np.float64)`) rather than padding int16 then
   slicing — mathematically identical to the plan's snippet, slightly fewer
   casts. Verified by `test_no_overshoot_at_stability_bound` + `test_clips_to_int16_band`.
3. **Two extra tests** beyond the plan's list: `test_build_conductivity_lut_shape_and_values`
   (pins LUT shape/dtype/indexing) and `test_paint_brush_overwrites_stale_temp`
   (pins overwrite of pre-existing heat). The plan's `_ids_fill` test helper
   stub was unused, so omitted.

## Measured perf (Risk #2 acceptance criterion)

Default grid is 200×140 (`GRID_WIDTH=200`, `GRID_HEIGHT=140`).

- **`diffuse_temps` alone:** **~1.33 ms / call** (1334 µs), measured via
  `timeit` over 1000 iterations on a 200×140 int16 temp array + uint8 id array.
  That is **~8% of a 16.6 ms frame budget at 60 FPS** — comfortably within
  budget. The pass is pure numpy (pad + 4 slices + LUT index + float64
  Laplacian + clip + cast) and allocates ~7 temp arrays; cheap.
- **Full `Simulation.step` (diffusion + movement scan) ceiling:** ~23 ms →
  ~43 steps/s. The diffusion pre-pass is **~6% of the full step**; the
  pre-existing Python-level movement scan (unchanged this phase — the v1
  `O(cells)` cost the original plan's perf risk #1 flagged) dominates. Phase 01
  does **not** regress the hot path.
- **`SANDFALL_FRAMES=60` smoke:** ran clean to completion, `EXIT=0`, under the
  **real SDL video driver** (no `SDL_VIDEODRIVER=dummy` fallback needed). The
  loop caps at 60 FPS via `_clock.tick(FPS)`; it does not print FPS to stdout
  (FPS is drawn on-screen by the UI overlay), so the timeit number above is the
  authoritative per-frame diffusion cost.

Conclusion: the diffusion pre-pass is cheap and does not threaten 60 FPS by
itself. The full-step ceiling is bounded by the existing scan, which is out of
scope for Phase 01.

## Six gates — all green

| # | Gate | Result |
|---|------|--------|
| 1 | `uv run python -c "import sandfall"` | ✅ exit 0 |
| 2 | `uv run pytest` | ✅ 124 passed |
| 3 | `uv run ruff check .` | ✅ All checks passed |
| 4 | `uv run ruff format --check .` | ✅ 42 files already formatted |
| 5 | `uv run mypy src` | ✅ Success: no issues found in 21 source files |
| 6 | `SANDFALL_FRAMES=60 uv run sandfall` (real SDL) | ✅ exit 0 |

Phase-specific focused suite (`test_thermal.py test_grid.py test_brush.py`):
53 passed. Fire/smoke/plant suites (the "no visible behavior change"
criterion): 11 passed.

## Commit

**Not committed.** All changes left unstaged per instructions; the commit
decision is deferred to the user. Working tree: 8 modified + 2 new tracked
files, plus the untracked `.agent/tasks/sandfall-temperature/` plan dir (which
was already untracked at baseline).

## Notes for Phase 02

- The reactive-ignition contract is ready: `ELEMENTS[WOOD].flashpoint=300`,
  `burn_temp=800`; `PLANT` flashpoint 250 / burn_temp 700; `FIRE.temp_spawn=800`.
  These are the knobs to tune combustion chaining against.
- `diffuse_temps` returns a NEW array and `Simulation.step` assigns it back to
  `grid._temp` directly (sibling-module private access, consistent with the
  `migrate_grid` precedent). If Phase 02/03 prefer a setter, add
  `Grid.set_temp_array(...)`; not needed yet.
- `flammability` field left in place (harmless registry datum); Phase 02 removes
  its only reader (`SPREAD_FACTOR` in `fire.py:31`).

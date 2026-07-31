# Phase 01 Reflection — Grid.move raw-array fast-swap + swap delegation

## Outcome (one line)

`Grid.move` landed as the raw 3-array tuple-swap; `swap` is now a one-line
delegate; **zero rule edits**; full suite green **173 → 174**; measured busy-scene
speedup **1.60×** (below the ~2-3× target — see Why).

## Changes (3 files, unstaged — NO git operations performed)

- `src/sandfall/grid.py` — added `Grid.move(x1, y1, x2, y2) -> None` between
  `set_temp` and `fill_circle`. Raw numpy tuple-assignment across `_data` /
  `_life` / `_temp` (each array bound to a local to drop 3 `self.` lookups),
  **no per-access bounds check, no clip**, with the documented in-bounds
  precondition + no-clip rationale in the docstring.
- `src/sandfall/rules/_common.py` — `swap()` body replaced with the one-line
  delegate `grid.move(x1, y1, x2, y2)`; docstring updated to note the
  delegation + inherited precondition. Signature `(grid, x1, y1, x2, y2)`
  byte-for-byte unchanged.
- `tests/test_grid.py` — added `test_grid_move_swaps_id_life_and_temp`
  (mirrors `test_swap_carries_temp` but exercises id+life+temp, pinning the
  tuple-swap + the three-array carry directly against `Grid.move`).

## Bounds-safety audit — ALL 16 SITES CONFIRMED PRE-CHECKING (clean)

Re-grep'd `swap(` across `src/sandfall/rules/` → 17 matches; 16 are call sites,
the 17th is the `def swap(...)` definition itself. Every call site is guarded
immediately before the call. The spec's audit table is **byte-accurate against
the current source** (line numbers had NOT drifted — `set_temp` ends at :235,
`fill_circle` at :237, `swap` at :75-94, all call sites at the cited lines):

| Rule | swap site | Pre-check (verified in source) |
|------|-----------|--------------------------------|
| sand.py :46 (down) | `y + 1 < grid.height` (:45) |
| sand.py :56 (down-diag) | `grid.in_bounds(nx, ny)`, ny=y+1 (:55) |
| water.py :63 (down) | `y + 1 < grid.height` (:62) |
| water.py :73 (down-diag) | `grid.in_bounds(nx, ny)`, ny=y+1 (:72) |
| water.py :83 (sideways) | `grid.in_bounds(nx, ny)`, ny=y (:82) |
| lava.py :85 (down) | `y + 1 < grid.height` (:84) |
| lava.py :95 (down-diag) | `grid.in_bounds(nx, ny)`, ny=y+1 (:94) |
| lava.py :105 (sideways) | `grid.in_bounds(nx, ny)`, ny=y (:104) |
| steam.py :54 (up) | `y - 1 >= 0` (:53) |
| steam.py :61 (up-diag) | `grid.in_bounds(nx, ny)`, ny=y-1 (:60) |
| steam.py :71 (sideways) | `grid.in_bounds(nx, ny)`, ny=y (:70) |
| smoke.py :37 (up) | `y - 1 >= 0` (:36) |
| smoke.py :44 (up-diag) | `grid.in_bounds(nx, ny)`, ny=y-1 (:43) |
| smoke.py :54 (sideways) | `grid.in_bounds(nx, ny)`, ny=y (:53) |
| fire.py :116 (up) | `y - 1 >= 0` (:115) |
| fire.py :123 (up-diag) | `grid.in_bounds(nx, ny)`, ny=y-1 (:122) |

For straight-down/up sites, `y ± 1` is checked and `x` is unchanged (and `x` is
valid because the cell is being scanned); for every diagonal/sideways site,
`grid.in_bounds(nx, ny)` confirms the destination and the source `(x, y)` is
in-bounds because it is the scanned cell. **Conclusion: dropping the per-access
bounds check in `Grid.move` is safe at every caller; a missed pre-check would
raise `IndexError` loudly (the `SANDFALL_FRAMES=60` SDL smoke ran clean, no OOB
crash).**

`git diff --stat src/sandfall/rules/{sand,water,lava,steam,smoke,fire}.py` is
**empty** — zero rule edits.

## Six verification gates (all exit zero)

| # | Gate | Result |
|---|------|--------|
| 1 | `uv run pytest tests/test_grid.py -v` | ✅ 36 passed (incl. new `test_grid_move_swaps_id_life_and_temp`) |
| 2 | `uv run python -c "import sandfall"` | ✅ import OK |
| 3 | `uv run pytest` (full) | ✅ 174 passed (was 173; +1 new test) |
| 4 | `uv run ruff check .` | ✅ All checks passed |
| 5 | `uv run ruff format --check .` | ✅ 47 files already formatted |
| 6 | `uv run mypy src` | ✅ Success: no issues found in 25 source files |
| 7 | `SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall` | ✅ EXIT=0, no IndexError (used the `SDL_VIDEODRIVER=dummy` fallback — headless env) |

(Bonus 7th: the SDL smoke caught no OOB — the headline risk of dropping the
per-access bounds check. It is the load-bearing regression guard for the audit.)

## Measured perf (`Simulation.step`, median of 5 repeats; same scene + seed)

Measurement method: one-off script `/tmp/opencode/measure_grid_move.py` +
`/tmp/opencode/count_moves.py`. The "before" path is a **faithful monkeypatch** —
a module-level `swap_before` with the exact original 12-call body using the real
`grid.get/set/get_life/set_life/get_temp/set_temp`, patched into all 6 rule
modules + `_common`. The "after" path uses the real delegating `_common.swap`.
Both rebuild the identical scene from `random.seed(0)` and seed `random` before
the timed window, so the trajectory is identical (swap is behavior-preserving)
and the only variable is the swap cost. **No source files or git state were
touched** (monkeypatch affects runtime module attributes only; verified
`git diff --stat` afterward still shows exactly the 3 files).

Scene: `200x150 = 30000` cells; busy scene `7477` non-empty SAND cells
(**24.9% fill** — the target). 30 timed steps after a 2-step warmup.

### (a) BUSY / falling ~25% fill — the headline

| metric | before | after | speedup |
|--------|--------|-------|---------|
| `Simulation.step` total | **93.9 ms/step** | **58.8 ms/step** | **1.60×** |
| per-move cost (≈7477 moves/step) | 11.95 µs/move | 7.25 µs/move | 1.65× |

The whole pile is still falling during the window (~7477 moves/step ≈ every
non-empty cell moves each step). `Grid.move` removed ~**4.7 µs/move** (the
12-call get/set + bounds-check + `int()` cast overhead). The residual ~7.25
µs/move is now dominated by **`can_displace`** (2 `ELEMENTS` dict lookups × up
to 3 candidate neighbors probed before a move succeeds) + the scan-loop
dispatch in `Simulation.step` + the rules' own `grid.get` reads.

### (b) SETTLED pile (dormant) — the guard

| metric | before | after |
|--------|--------|-------|
| `Simulation.step` total | 4.34 ms/step | 4.58 ms/step |

**Essentially unchanged** (0.95×; the ~0.24 ms/step delta is noise over 30
steps). Confirms dormancy is untouched — a dormant cell is skipped before its
rule (and thus before `swap`/`move`) ever runs, exactly as the plan predicted
(Decision Log #6). This isolates "did we touch dormancy? no" from "did we
speed up moving cells? yes."

## Was the win smaller than the ~2-3× target? Yes — and why

The measured busy-scene win is **1.60×** (step) / **1.65×** (per-move), below
the ~2-3× headline target. The plan explicitly flagged this as the likely
outcome (Decision Log #5, Risks #3): `swap` was the biggest single chunk of
the moving-cell cost but **not** all of it. Concretely, on a moving cell the
non-swap costs that `Grid.move` did not touch are:

- **`can_displace`** — now the largest remaining chunk. Each candidate neighbor
  costs 2 `ELEMENTS` dict lookups (`ELEMENTS[src_id]` + `ELEMENTS[target_id]`)
  + a phase/density compare. Sand/water/lava probe up to 3 candidates
  (down + 2 diagonals) before a move succeeds → up to 6 dict lookups/cell.
  This is the **next deferred lever** (Out of Scope: a `(src_id, target_id)`
  density/phase LUT would collapse it to one array read).
- **Scan-loop dispatch** in `Simulation.step` (the `for x in xs` per-active-cell
  call into the rule function) — pure Python per-cell overhead.
- **The rules' own `grid.get` reads** (e.g. `grid.get(x, y+1)` inside
  `can_displace`'s argument, and the reactive `get_temp` checks) — each is a
  bounds check + `int()` cast + indexed read.
- **Diffusion pre-pass** — vectorized, ~constant per step (subtracted via the
  settled-pile baseline when deriving per-move cost).

Rough decomposition of the ~7.25 µs/move residual: `swap`/`move` itself is now
~2-3 numpy indexed ops (sub-µs); the rest is `can_displace` + scan dispatch +
rule `grid.get`s. So **the next ~2× busy-scene win is sitting in `can_displace`**,
which is exactly the deferred LUT phase.

## Documentation

`docs/ARCHITECTURE.md` describes `swap` at the **behavioral** level only
("exchanges the element ids, life values, AND temperatures of two cells",
lines 333-346) — it does **not** enumerate the get/set sequence or cite "12 Grid
method calls". Per the plan's Documentation Updates: "If it does not describe
`swap` at that level of detail, leave it." **No update made** (and the
behavioral description stays 100% accurate — `swap` still does exactly that,
just via `Grid.move` now).

## Difficult / unexpected

- **Edit-tool substring-corruption (caught and fixed before any gate ran).**
  The first `grid.py` edit used an `oldString` beginning `if value > TEMP_MAX:`,
  but that exact substring lives **inside** the `elif value > TEMP_MAX:` line of
  `set_temp`. The edit matched there, leaving a dangling `el` + the `move`
  method inserted in the wrong place, producing a SyntaxError. `ruff`/`mypy`
  caught it immediately on the first gate run. Fixed by re-reading the damaged
  region and repairing line 233 back to `elif value > TEMP_MAX:`. **Lesson:**
  when an `oldString` could be a substring of a longer token (here `if` ⊂
  `elif`), include enough unique leading context (the `el`-bearing line, or the
  preceding `if value < TEMP_MIN:` block) so the match is unambiguous. No
  semantic impact — all gates green after the fix.
- No deviation from the plan. `swap` delegates; the 16 rule call sites are
  untouched; the new test is deterministic (no timing assertions).

## Fun / structurally informative

- The busy scene moves ~7477 cells/step for ~30 steps straight — a falling
  front, not a settling trickle — which is the right workload to stress `swap`
  (every active cell hits `move` each step). The per-move delta (11.95 → 7.25 µs
  = −4.7 µs) × 7477 moves × 30 steps ≈ 1054 ms saved over the window, matching
  the observed 93.9→58.8 ms/step × 30 = 1053 ms step-time delta to within
  rounding. The accounting closes.
- `Grid.move` adds a second Python call frame (`swap` → `move`) but still wins
  big because the 12 grid method calls it replaces each carried a bounds check +
  `int()` cast + attribute lookup. The local-binding micro-opt (`d =
  self._data`) was kept per the spec.
- The `elif` corruption was the only thing standing between "edit applied" and
  "green" — a reminder that "Edit applied successfully" only means the
  oldString matched once, not that it matched at the *intended* location. The
  type-checker/linter is the cheap, reliable backstop.

## Stop-rule check

All declared acceptance criteria and the six (seven, incl. SDL smoke)
verification gates pass. Full suite 174 green. No rule file edited. Changes
left unstaged (no commit/stage/push/amend). **Phase complete.**

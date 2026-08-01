# Phase 01 Reflection: Gas rise through liquid (buoyancy)

## What was done

- `src/sandfall/rules/_common.py`: added the precomputed `_LIQUID_IDS` frozenset
  (built once at import from `ELEMENTS[e].phase == Phase.LIQUID`) and the
  `is_riseable(cell_id)` helper (`EMPTY or cell_id in _LIQUID_IDS`), placed right
  after `can_displace` so the two "can a cell move into another" predicates sit
  together. Added the `is_riseable` bullet to the module docstring.
- `src/sandfall/rules/steam.py`: added `is_riseable` to the `._common` import;
  changed the **straight-up** (`:56`) and **up-diagonal** (`:63`) rise checks
  from `== ElementId.EMPTY` to `is_riseable(grid.get(...))`; **left the sideways
  drift check (`:73`) as `== ElementId.EMPTY`**; updated the module docstring.
- `src/sandfall/rules/smoke.py`: mirrored steam — import, rise checks at `:39`
  and `:46` use `is_riseable`; drift at `:56` untouched; docstring updated.
- `tests/test_gas_buoyancy.py` (NEW, 6 tests): steam-through-water single swap,
  steam reaches a pool surface, smoke-through-water, steam-through-oil,
  steam-does-NOT-rise-through-solid/gas, drift-stays-EMPTY-only.
- **FIRE untouched.** `simulation.py`, `grid.py`, `elements.py`, `thermal.py`,
  renderer/ui/game untouched. No git operations performed.

## Behavior confirmation

- **Steam + smoke rise through water/liquids.** The headline single-step test
  (`test_steam_rises_through_water`) holds: after one step steam is one row up,
  water one row down. Mirror passes for smoke and for oil (proving the buoyancy
  is generic over `Phase.LIQUID`, not water-specific).
- **Steam reaches the surface.** `test_steam_rises_to_surface_of_water_pool`
  bubbles the steam from row 6 up through the water column (rows 1–5) and into
  the air at row 0 within 200 steps (the deterministic climb is ~6 swaps; the
  stone side-walls force straight-up-only rise).
- **Drift stays air-only.** `test_drift_does_not_go_sideways_through_liquid`
  confirms a steam cell flanked by water does not drift sideways through it.
- **Fire unchanged** — `rules/fire.py` not edited; its rise stays EMPTY-only.

## Surprises / corrections (why this was not a literal copy-paste of the spec)

Three things in the spec's literal test code would have produced **false
positives or flaky failures**; each was corrected and is pinned here.

1. **Water boils at `temp > 100` (`water.py:53`).** The spec's steam tests set
   the water cell to `temp_spawn` (120). If the steam had failed to rise (e.g.
   condensed first), the water at 120 would instead **boil to steam** at the
   steam's old cell — producing `(STEAM, WATER)` in the right cells for the
   *wrong reason* (boil + condense, not buoyancy). To eliminate this
   false-positive window entirely, all steam tests use **`_WARM = 80`**:
   `60 < 80 <= 100` ⇒ steam stays gaseous (above `condense_point`) AND water
   never boils (the boil check is strictly `> 100`). Whole-grid uniform warming
   also zeroes the diffusion Laplacian, so the buoyancy swap is the only thing
   under test. (`temp_spawn` 120 would have worked for the *happy* single-step
   case — the water is swapped down before its row scans — but 80 is robust to
   scan-order changes and is the honest isolation temp.)

2. **The drift test's literal geometry leaked in two places.** The spec's
   `test_drift_does_not_go_sideways_through_liquid` left the up-diagonal corners
   `(0,0)/(2,0)` EMPTY (steam could escape diagonally — `is_riseable(EMPTY)` is
   True) AND left `(0,2)/(2,2)` EMPTY (the flanking water would simply **fall
   away** into them, breaking `g.get(0,1) == WATER`). The spec note explicitly
   anticipated this and recommended "fill the up-diagonal corners with stone."
   Pinned geometry: **fully-boxed 3×3** — all border cells STONE, steam center,
   water flanking left/right. Now both steam and water provably stay put
   (steam's every rise/drift target is stone or non-EMPTY water; water's every
   fall/spread target is stone or non-displacable steam).

3. **The gas-gas test's smoke rose away.** The spec's
   `test_steam_does_not_rise_through_solid_or_gas` part (b) left `(1,0)` EMPTY
   above the smoke. The smoke (scanned after the steam, y-descending) would
   **rise into the open air at `(1,0)`**, leaving `(1,1)` EMPTY and failing
   `g.get(1,1) == SMOKE`. The spec note flagged this ("if the scan order ever
   lets the smoke move first, box it tighter"). Fix: added a **stone cap at
   `(1,0)`** so the smoke cannot rise out; now both gases stay put and the
   "steam and smoke do not swap" assertion is deterministic.

None of these touch the *production* code (`_common.py` / `steam.py` /
`smoke.py`) — the spec's literal before/after for the rule edits was followed
exactly. Only the *tests* were tightened, within the latitude the spec's own
notes granted.

## Note on steam condensing mid-pool in cool water

Realistic and already handled: steam's condense check runs BEFORE movement, and
diffusion cools the steam each step. In the pool test, uniform 80 °C warming
isolates buoyancy from condensation (the documented isolation strategy). In a
real game with ambient (20 °C) water, a steam bubble released at the bottom of a
deep cold pool will condense back to water before surfacing — physically correct
(a cold steam bubble collapses) and already covered by the existing condense
path; no new code needed.

## Existing-suite impact

None. No existing test relied on gas being trapped under a liquid — the existing
steam/smoke tests exercise rising into EMPTY (still permitted by `is_riseable`)
and condense/age on 1×1 grids (no liquid involved). All 217 baseline tests
stayed green; the 6 new tests bring the total to **223**.

## Six-gate results (all ✅, each observed exit 0)

| # | Command | Result |
|---|---------|--------|
| 1 | `uv run pytest tests/test_phase.py tests/test_fire.py -v` | ✅ 29 passed |
| 2 | `uv run python -c "import sandfall; ... is_riseable ..."` | ✅ `buoyancy OK`; `_LIQUID_IDS = {2,10,12,13,14}` (WATER/LAVA/ACID/BASE/OIL) |
| 3 | `uv run pytest` (full suite) | ✅ **223 passed** (217 baseline + 6 new) |
| 4 | `uv run ruff check .` | ✅ All checks passed! |
| 5 | `uv run ruff format --check .` | ✅ 56 files already formatted |
| 6 | `uv run mypy src` | ✅ no issues found in 30 source files |
| 7 | `SANDFALL_FRAMES=60 uv run sandfall` (+ `SDL_VIDEODRIVER=dummy` fallback) | ✅ exit 0, no traceback, 60 frames |

## Drift / fire invariants (confirmed by re-read after edit)

- `steam.py:73` and `smoke.py:56` are still `grid.get(nx, ny) == ElementId.EMPTY`
  (drift unchanged — buoyancy is upward only).
- `rules/fire.py` was not opened or edited (FIRE stays EMPTY-only — out of
  scope).

## Commit

Not committed — per instructions, changes left unstaged for the human approval
gate.

# Phase 02 Reflection: Liquid nitrogen (transient cold liquid)

**Result: GREEN — all six gates exit zero.** Liquid nitrogen
(`ElementId.LN2 = 17`) ships as a light (density 0.8 → floats on water),
transient cryogenic liquid that re-asserts **`LN2_COLD_TARGET = -196`** while
alive, freezes adjacent water aggressively, then boils off to EMPTY. This
**completes the thermal-realism rework** (Phase 1's realistic ice + dry ice +
now LN2).

## Final tunables

- **`LN2_COLD_TARGET = -196`** (module constant in `rules/ln2.py`; LN2's boiling
  point). Far colder than `DRY_ICE_COLD_TARGET` (-78), so LN2 freezes water much
  faster than dry ice — but only for as long as its finite life lasts.
- **`seed_nitrogen_life()` = `randint(30, 80)`** (in `rules/_common.py`,
  re-exported from `rules/__init__.py`). The first-pass range **needed NO
  widening or narrowing**: even at the top of the window (life=80) a 2×2 LN2
  blob in water froze **20 ice cells** before boiling off (see spread table
  below) — comfortably "aggressive". At a typical painted life (30..80) a blob
  still freezes a visible patch. LN2 earns its freeze through cold, not through
  lingering (the plan's Risk #5 gate is satisfied).

## Behavior — confirmed

- **Freezes water aggressively** (`test_ln2_freezes_water_aggressively`): a 2×2
  LN2 blob (life=80) seeded in an 8×8 water pool, `random.seed(0)`, real
  `Simulation`, ice count over steps:

  ```
  step  1: ice= 0  ln2=4
  step  5: ice= 0  ln2=4   (cold front traversing the first water shell)
  step 10: ice= 7  ln2=4   (first freezes)
  step 20: ice=10  ln2=4
  step 40: ice=12  ln2=4
  step 60: ice=18  ln2=4
  step 80: ice=20  ln2=4   (test asserts ice>0 here -> 20)
  step100: ice=20  ln2=0   (LN2 fully boiled off ~step 81-100)
  ```

  For comparison, Phase-01 dry ice (-78) made **12 ice in 150 steps** from a
  2×2 seed; LN2 (-196) made **20 ice in ~80 steps**. The steeper gradient
  (~2.5× colder) more than compensates for the shorter life. The first ice
  appears around step 5-10 (water adjacent to -196 cools ~3.5 °C/step → reaches
  ≤0 in ~6 steps). Residual cold in the frozen shell continues to freeze a few
  more cells (ice=26 by step 140) even after the LN2 is gone.

- **Boils off** (`test_ln2_boils_off`): a 3×3 all-LN2 blob (life=80) is entirely
  EMPTY by step ~80 (200 steps run, asserts LN2 count → 0). Transient, as
  designed.

- **Floats on water** (`test_ln2_floats_on_water`): `can_displace(WATER, LN2)`
  is True and the reverse is False (density 0.8 < 1.0). A column of LN2 above
  water settles with LN2 ABOVE the (frozen) water column within ~2 steps and
  stays there. **See the ripple note below** — the water freezes during the run,
  so the assertion counts WATER-or-ICE as the water column.

- **Brush seeds life + spawn temp** (`test_paint_brush_ln2_seeds_life`): a
  painted LN2 disk gets life in [30, 80] and temp -196 (no "painted LN2 dies
  instantly" bug).

## Dormant-wake finding — DID need a `simulation.py` edit (the pooled-LN2 stall)

Unlike Phase 01's dry ice (which needed NO wake edit — its freeze test stayed
awake via the adjacent water's temp changes), **LN2 required adding it to wake
condition 3** (`simulation.py`, the `FIRE | LAVA` dilate). This is the exact
"pooled LN2 cell stalls" case the plan's hard constraint #5 authorized fixing
("add LN2 to wake only if a pooled LN2 cell stalls").

**The stall, diagnosed:** `test_ln2_boils_off` initially failed — a 3×3 all-LN2
pool went **dormant after step 1** (active=0) and life froze at 78 forever. The
mechanism: every cell at -196 → diffusion is a no-op (no gradient) → the re-
assert `if get_temp > -196` is a no-op (already at target) → no movement, no
identity change, no temp change, not FIRE/LAVA → none of the four wake
conditions fire → dormant. `set_life` does NOT mark active, so the aging itself
produces no wake signal. The cell never reaches the expiry identity change that
the plan assumed would self-wake it.

This is NOT just a test artifact: a single pooled LN2 cell on a solid floor
(walls all around, ambient neighbors cooled to -196) stalls the same way in real
play. A transient element MUST age regardless of its thermal neighborhood.

**The fix** (minimal, one line + comments): add `| (data == int(ElementId.LN2))`
to the condition-3 dilate, and extend its docstring to explain LN2 is a
temp-re-asserting cell that must also age each step (the same structural reason
FIRE/LAVA are there). The freeze test was unaffected (it was already awake via
the adjacent water's temp changes); the fix is belt-and-suspenders there and
load-bearing for the all-cold pool. After the fix, `test_ln2_boils_off` passes
and the full suite stays green (verified across 5 consecutive runs).

**Why dry ice didn't need this but LN2 does:** dry ice is PERSISTENT (no life to
decrement) and in its freeze test it sits next to 20 °C water that constantly
warms it → the re-assert constantly re-cools it → perpetual temp change →
condition 2 keeps it awake. LN2's all-cold pool has no such warm neighbor, and
LN2 additionally carries a life it must decrement — a wake signal dry ice never
needed.

## An UNEXPECTED ripple — `test_ln2_floats_on_water` (water freezes, documented)

The plan's float test (copied verbatim) asserts LN2 ends above WATER after 40
steps. But LN2 re-asserts -196, so the water column **freezes to ICE** during
the run (correct cold-source behavior), leaving `water_y` empty → assertion
failed (`ln2_y=[2]`, `water_y=[]`; the water was ICE at y=3). This is the
analog of Phase 01's `test_acid_dissolves_ice` ripple: a realistic-consequence
interaction the test setup didn't anticipate.

**Fix (intent-preserving, NOT a weakening):** the positional assertion now treats
WATER-or-ICE as "the water column" and asserts LN2 sits ABOVE it. The density
evidence is unchanged (LN2 never sank below the water/frozen-water column), and
the authoritative `can_displace` density assertions are intact. The assertion is
if anything STRICTER about the float property (LN2 above the whole water column,
not just "some water"). No assertion was weakened or skipped.

No other sibling-test ripple: Phase 02 only ADDS LN2 (no existing element's
behavior changes), so the simulation.py wake edit is the only behavioral change.
Full suite is stable across 5 runs (234 passed each time).

## What was NOT touched (per the hard constraints)

- `grid.py`, `thermal.py` diffusion math, `renderer.py`, `ui.py`, `game.py` —
  untouched. The palette/renderer/LUTs auto-resized from `len(ElementId)`
  (17→18) with no code edit, as the plan predicted; only the hardcoded count
  literals in tests were bumped (16→17 element swatches, 19→20 palette items,
  17→18 LUT rows, 556→584 MIN_WINDOW_W, 139→146 MIN_GRID_COLS).
- `docs/ARCHITECTURE.md` refreshed: `ElementId` member list (+`LN2=17`,
  8..16→8..17), the cold-source category sentence (now names BOTH dry ice
  persistent + LN2 transient, dropping the "(future) LN2" hedge), and the
  `seed_*_life` list (+`seed_nitrogen_life -> randint(30, 80)`, noting LN2
  joins FIRE/SMOKE/STEAM in the brush life-seeding pass).
- `.agent/tasks/BACKLOG.md`: "Thermal realism rework" struck as SHIPPED (both
  phases delivered), with the cold-gas sub-item noted as still deferred.

## Out-of-Scope note (for a future pass)

LN2 boil-off → EMPTY is the minimal choice. A cold SMOKE puff on boil-off (a
visible cryogenic vapor) is the noted visual option and remains deferred per the
plan's Out-of-Scope — same for a dedicated cryogenic gas element for dry-ice
sublimation. Both are future work.

## Six-gate results

| Gate | Command | Result |
|------|---------|--------|
| Phase-focused | `uv run pytest tests/test_phase.py tests/test_thermal.py -v` | ✅ 43 passed |
| Enum+registry+life | `uv run python -c "...LN2==17...in RULES...seed_nitrogen_life..."` | ✅ OK |
| Palette math | `uv run python -c "...MIN_WINDOW_W==584..."` | ✅ palette fits 584 <= 584 |
| Full suite | `uv run pytest` | ✅ 234 passed (230 → 234, net +4) |
| Lint / format / types | `ruff check . && ruff format --check . && mypy src` | ✅ all clean (58 files formatted, 32 mypy files) |
| SDL smoke | `SANDFALL_FRAMES=60 SDL_VIDEODRIVER=dummy uv run sandfall` | ✅ exit 0 |

## Did NOT commit

Per the hard constraint, no git operations were performed (no commit, stage,
push, or amend). All changes (15 modified + 1 new `rules/ln2.py`) are left
unstaged for the human approval gate.

---

**This phase completes the thermal-realism rework.** The cold-source end state
is now the Powder Toy / Sandboxels model the user asked for: realistic ice
(melts >0 °C, non-source), dry ice (-78 °C persistent solid), and liquid
nitrogen (-196 °C transient liquid). Freezing water requires a colder-than-
freezing cold source; ice no longer does it alone.

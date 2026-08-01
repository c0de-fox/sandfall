# Phase 02 Reflection: Oil (light flammable liquid; floats on water)

## What was done

Added `ElementId.OIL = 14` — a light flammable liquid (density 0.8 < WATER 1.0)
that floats on water via the existing density-based `can_displace` and ignites
to FIRE when heated above a low flashpoint (150). The simplest reactive-liquid
shape: burn first (mirror `wood.py`), then flow (mirror `water.py`). No
dissolve/dilute of its own. Extended both thermal LUTs and recomputed
`MIN_WINDOW_W` for the wider 17-item palette. 8 new tests; full suite 197 → 205.

**Files changed:**
- `src/sandfall/elements.py` — `OIL=14` enum member + ELEMENTS entry; extended
  the enum docstring to note the oil extension.
- `src/sandfall/config.py` — `COND_OIL=0.12`, `CP_OIL=1.5`; `MIN_WINDOW_W`
  472 → 500 (125 cols); updated the width-math comment.
- `src/sandfall/thermal.py` — imported the 2 new constants; row 14 in both
  `build_conductivity_lut` and `build_heat_capacity_lut`.
- `src/sandfall/rules/oil.py` (NEW) — burn-then-flow rule.
- `src/sandfall/rules/__init__.py` — imported + registered `update_oil`.
- `tests/test_oil.py` (NEW, 8 tests).
- `tests/test_ui.py` — element count 13 → 14; added OIL to the resolution
  check; palette math 16 → 17 items / 15 → 16 paddings.
- `tests/test_config.py` — min-window math 16 → 17 items; `MIN_WINDOW_W`
  472 → 500; `MIN_GRID_COLS` 118 → 125.
- `tests/test_renderer.py` — `len(ElementId)` 14 → 15; LUT shape `(14,3)`
  → `(15,3)`; added the OIL color-at-index-14 check.
- `tests/test_acid_base.py` — `test_color_lut_has_14_rows` now asserts against
  `len(ElementId)` (so the next element pass does not need to re-edit it).
- `docs/ARCHITECTURE.md` — appended `ACID=12, BASE=13, OIL=14` to the
  ElementId member list (was deferred from Phase 01 — see Scope note).
- `README.md` — "twelve" → "fifteen" elements; added ACID/BASE/OIL table rows
  (also deferred from Phase 01).
- `.agent/tasks/BACKLOG.md` — struck "acid" and "oil" from the More-elements
  line (acid was deferred from Phase 01).

No git operations performed — all changes left unstaged in the working tree.

## Final tuned values (Decision #12)

All first-pass values held — no tuning was needed. The deterministic tests +
the runtime smoke both read well as-is:

| Constant | Oil | Notes |
|---|---|---|
| `density` | 0.8 | < WATER 1.0 → floats on water via `can_displace` |
| `flashpoint` | 150 | low → ignites easily (oil slick catches from one fire) |
| `burn_temp` | 20 (AMBIENT default) | documentation only — on ignition oil becomes FIRE, whose rule re-asserts `_FIRE.burn_temp` (800). Same shape as wood/plant (overview Risk #6). |
| `conductivity` | 0.12 | thermal insulator → fire front advances visibly across the slick rather than flashing the whole pool at once |
| `heat_capacity` | 1.5 | mid-range mass — slower than a gas (0.5), faster than water (4.0) |
| color | (70, 45, 25) | dark oily brown |

Diffusion stability unchanged: `0.20 * max(cond) / min(cp) == 0.20 * 0.50 /
0.5 == 0.20 <= 0.25` (COND_OIL=0.12 is below FIRE's 0.50; CP_OIL=1.5 is above
the 0.5 min), so no `DIFFUSION_RATE` change.

## Behavior confirmation (all four observed at runtime)

1. **Oil floats on water.** A 1×5 column (oil above water, stone floor) after
   60 steps: `[., ., OIL, WATER, STONE]` — oil at row 2, water at row 3, oil
   strictly above water. The density relation holds both ways:
   `can_displace(WATER, OIL)` True (water sinks), `can_displace(OIL, WATER)`
   False (oil cannot push water down).
2. **Oil ignites when heated.** A single oil cell at `flashpoint+50` (200°)
   → FIRE on the next step (1×1 grid, diffusion no-op so the rule reads
   exactly 200°).
3. **Burning oil spreads across water.** A 9-cell oil slick on water, ignited
   at one end, reached a peak of **8 FIRE cells** and burned the slick down to
   **0 oil** over 150 steps — combustion chained across the entire surface.
   Mechanism: FIRE is a persistent heat source (wake condition #3), its
   diffusion heats the neighboring oil cell above oil's flashpoint, the oil
   rule ignites it next step → the front advances along the slick. The oil's
   low conductivity (0.12) is what makes the front advance one cell at a time
   rather than igniting the whole slick in one frame.
4. **Acid dissolves oil** (Decision #10). `OIL ∉ ACID_RESIST` (and `∉
   BASE_RESIST`), so acid eats oil by default: acid+oil adjacent → both EMPTY
   in one step (pinned at DISSOLVE_CHANCE=1.0). No resist-set edit was needed;
   guarded by an explicit `test_oil_not_in_acid_resist_set` assertion so a
   future contributor cannot accidentally add OIL to a resist set.

## Float-test step count

The spec's 40-step budget was more than enough. In the 1×4 float test the oil
settled above the water well within 40 steps; the 1×5 column with a floor
settled within ~60 steps. 40 is a comfortable upper bound for the assertion
(`min(oil_y) < max(water_y)`).

## Fire-spread test tightness

The spec's `oil_after < oil_before` (relative-disturbance) assertion is the
robust choice — it is insensitive to the exact FIRE life rolls. A tighter
exact-FIRE-count assertion would be flaky: FIRE is finite-life (20–40 steps
via `seed_fire_life`), so by the time the front reaches the far end of the
slick the early-ignited cells may have already expired to SMOKE/EMPTY. The
peak-FIRE counter (8/9 cells observed in the runtime smoke) is the tightest
stable signal but still seed-dependent. Left as the relative assertion; the
`< 8` drop is deterministic under `random.seed(0)` and reliably chains.

## Dormant-wake finding (Risk #1, continued)

Oil has NO dormant-interaction risk (it only flows or ignites; it is never
consumed-on-dissolve like acid/base). Flowing oil wakes via condition #1
(`moved`); igniting oil wakes via condition #1 (`id_changed`) AND condition #3
(once it is FIRE, FIRE joins the persistent-source wake). The fire-spread test
passing confirms the wake chain end-to-end: the FIRE front would stall against
dormant oil if any wake condition were missing, but it crosses the whole slick.

## Scope note: Phase-01 deferred docs completed here

Phase 01's reflection (`01-acid-base-reflection.md:109-125`) explicitly
**deferred** three documentation edits (its executing prompt had a narrower
file scope). Phase 02's spec listed the OIL doc updates and "the ACID/BASE
rows from Phase 01 if not already added", so I completed all of them here to
keep the docs truthful (the enum now has 15 members, not 12):

- `docs/ARCHITECTURE.md` — ElementId member list now ends at `OIL=14`
  (previously stopped at `GLASS=11` — neither Phase 03 nor Phase 01 had
  extended it). Includes ACID=12, BASE=13, OIL=14 in one edit.
- `README.md` — "twelve elements" → "fifteen"; ACID/BASE/OIL table rows added.
- `.agent/tasks/BACKLOG.md` — struck BOTH "acid" and "oil" (acid was also
  deferred from Phase 01).

The `docs/ARCHITECTURE.md` "Adding a new element" recipe dissolve-resist
obligation note (overview Risk #2) is still outstanding — it is a doc-only
non-blocking nicety; left for a future doc pass.

## Six-gate results (all observed exit zero)

1. `uv run pytest tests/test_oil.py -v` — 8 passed ✅
2. `uv run python -c "...enum+registry..."` — enum+registry OK; palette fits
   500 <= 500 ✅
3. `uv run pytest` (FULL) — 205 passed ✅ (197 → 205)
4. `uv run ruff check .` — All checks passed! ✅
5. `uv run ruff format --check .` — 52 files already formatted ✅
6. `uv run mypy src` — Success: no issues found in 28 source files ✅
7. `SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall` — exit 0, 60
   frames, no crash ✅

## This completes the new-elements feature (acid + base + oil)

Phase 01 added the acid/base pair (ACID=12, BASE=13); Phase 02 added oil
(OIL=14). The enum is now 15 members (0–14), all three new elements share the
existing mechanisms (liquid flow, reactive flashpoint ignition, density
displacement, auto-resizing renderer/thermal LUTs, dormant-wake), and the full
suite + all six gates are green. The new-elements master plan
(`00-overview.md`) is fully delivered.

## Anything fun

The "burning oil on water" emergent behavior is genuinely pretty: because
oil's conductivity is low (0.12) and FIRE is a persistent heat source, the
fire front crawls across the slick one cell at a time rather than flashing the
whole pool — you can watch the flame race across the surface. And because oil
floats (density 0.8) while acid/base sink (1.2), the three new liquids layer
invisibly-correct ways: oil on top of water on top of acid, with fire able to
ride the oil-water boundary. The acid-resists-glass / base-resists-stone /
acid-eats-oil matrix gives a satisfying materials-interaction table that fell
out of frozenset membership alone.

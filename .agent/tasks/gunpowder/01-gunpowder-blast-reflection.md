# Phase 01 Reflection — Gunpowder + reusable `blast.explode`

Phase shipped cleanly. All six verification gates exit zero; the full suite is
**207 → 217** (+10 new in `tests/test_gunpowder.py`; existing palette/LUT tests
updated for the wider 18-item palette). No `simulation.py` rule-logic edit was
needed (the dormant wake sufficiency held — verified at scale).

## Final tuned constants (Decision #11)

Pinned at the plan's first-pass values — eyeballed via the headless pile test
(the 1000-cell detonation read well, no tweaking required):

| Constant | Value | Notes |
|---|---|---|
| `BLAST_RADIUS` | **4** | ~50 cells touched per blast; modest enough to stay perf-safe (Risk #2). |
| `CRATER_RADIUS` | **2** | inner destroy zone (~13 cells incl. diagonals). |
| `BLAST_HEAT` | **1200.0** | peak center heat. NOT bumped for sand→glass (see below). |
| `CORE_FIRE_CHANCE` | **0.8** | d≤1 → FIRE (the fireball). |
| `CRATER_SMOKE_CHANCE` | **0.15** | crater (beyond core) → SMOKE for visual. |
| `SCATTER_CHANCE` | **0.5** | loose material in outer ring pushed outward. |
| `flashpoint` (Element) | **200** | thermal trigger. |
| `density` (Element) | **1.5** | sand-like POWDER. |
| `conductivity` / `heat_capacity` | **0.15 / 1.5** | identical to SAND. |

Diffusion stability unchanged: `0.20 * max(cond=0.50 FIRE) / min(cp=0.5) = 0.20
<= 0.25` (gunpowder's 0.15 < 0.50 and 1.5 > 0.5 move neither bound — Risk #6).

## The headline deviation: `blast.explode` visit order (Risk #3)

The plan's recommended skeleton used a ring-band selector
`abs(d - dist_ring) > 0.9` to process the radius "outer ring first". I did NOT
ship that selector verbatim — **it double-processes cells.** A width-1.8 band
overlaps for any distance near a half-integer: e.g. a diagonal cell at
`d = sqrt(2) ≈ 1.414` lies within 0.9 of BOTH ring 1 (`|1.414−1|=0.414`) and
ring 2 (`|1.414−2|=0.586`), so it would be selected twice and **heated twice**
(or crater-destroyed twice — harmless only because the second visit sees EMPTY
and `continue`s, but the double HEAT is real and would compound across a chain).
The plan note claiming "a cell is selected only when `dist_ring == round(d)`" is
incorrect at threshold 0.9.

**Fix (keeps the exact contract — heat everything / spare GUNPOWDER / crater the
inner / scatter loose outward):** collect every in-radius offset into one flat
list with its true Euclidean distance, then `sort(key=d, reverse=True)`. Each
cell is visited **exactly once**, and descending distance still gives
outer-first — so scatter (which pushes a cell to a strictly larger distance)
always lands in an already-processed position and is never re-scattered. The
scatter test was strengthened to assert every surviving sand cell that left its
origin is within Chebyshev-distance 1 of some origin (no double-move). Pinned
here so the next explosive pass reuses the flat-sort, not the band selector.

## Chain-reaction test geometry (corrected from the plan)

The plan's literal chain test placed the gunpowder line at **row 2** of a 13×5
grid and ignited the left end with FIRE. **That geometry provably fails** —
verified empirically:

```
mid-grid (row 2) gp_after = 12   (plan asserts <= 2)   ← FAILS
  row 4: 12 gunpowder             ← all of it fell to the floor, un-ignited
```

Why: gunpowder is a POWDER. With two empty rows below row 2, the whole line
drops to the bottom in two steps. Meanwhile the igniting FIRE (a gas) only
**clings** to a flammable *orthogonal* neighbor (`fire.py::_has_flammable_neighbor`);
once the adjacent gunpowder falls away, the fire rises and the two separate
before diffusion can raise the gunpowder past its 200° flashpoint (~34°/step of
contact needed, ~6 steps). The fire then expires (life 40) having lit nothing.

**Correction (preserves intent + every assertion):** the line rests on the
**bottom row** (`y = h-1`) so the powder cannot fall away from the igniting fire.
Fire clings to the flammable gunpowder, stays put, heats it via diffusion until
the first cell detonates, and the chain then rips across via each blast's heat
burst. Result: `gp_after <= 2` (prototype-clean = 0). `gp_before == 12` and the
assertions are otherwise byte-identical to the plan. This is a test-geometry
fix, not a weakening — a chain that stalls because the powder fell away from the
fuse isn't a working chain.

## `BLAST_HEAT`-vs-melt decision (Risk #4)

**Sand → GLASS is NOT asserted and `BLAST_HEAT` was NOT bumped.** Per the plan's
analysis: the crater (`d ≤ CRATER_RADIUS=2`) *destroys* sand rather than melting
it, and outside the crater at `BLAST_HEAT=1200` the falloff (`1 − 3/5 = 0.4` →
+480°C) reaches only ~500°C — far below `SAND.melt_point` (1700). Reaching a
melt at the crater edge needs `BLAST_HEAT ≥ ~3360` (above `TEMP_MAX=3000`). The
robust heat-burst proofs are **wood→FIRE** (flashpoint 300, reached at d≈3) and
**water→STEAM** (boil_point 100, reached across the outer ring); both are
asserted in `test_blast_heat_ignites_wood_and_boils_water`. Bumping the heat to
chase a marginal sand-melt would make every blast absurdly hot (every flammable
in a wide radius would flash instantly, killing the visible fire-front spread).
Left at 1200.

## Dormant-wake finding (Risk #1) — NO `simulation.py` edit

**Confirmed: no wake-condition edit was needed.** A detonation fires both
existing conditions:

- **Condition #1** (`id_changed` = `data != data_before`, dilated): every crater
  cell that went EMPTY/FIRE/SMOKE is an id change → it + its orthogonal
  neighborhood wake.
- **Condition #2** (`grid._temp != temp_before`): every heat-burst cell whose
  temp was raised wakes — **including gunpowder cells that were only heated (not
  destroyed)**. This is the key: the spared gunpowder in the radius sees its
  temp jump past flashpoint and wakes, so its own rule detonates it next frame.

GUNPOWDER therefore does **not** join FIRE/LAVA in wake condition #3. Verified
at scale: a 1000-cell gunpowder pile (5 rows × 200 cols on the real 200×140
grid), ignited at one corner, **fully detonates to 0 over ~200 steps** via heat
alone. The chain is O(1) stack depth per blast (Decision #6 — heat, not
recursion) and unfolds over the scan/a few frames.

## Destroys-everything + scatter (Decisions #5, #9)

- **Crater destroys everything.** `test_blast_destroys_everything_in_crater`
  pins STONE/GLASS/SAND/WOOD (d=2 axial) and WATER (d≈1.41 diagonal) all leaving
  their original id. No blast-resistant material (user choice).
- **GUNPOWDER in the radius is spared** (heated only) so the chain propagates —
  the crater check is gated behind `if nb == GUNPOWDER: continue` after the heat
  burst.
- **Scatter** pushes POWDER/LIQUID-phase cells one step outward, carries `temp`
  explicitly but not `life` (loose materials have life 0 always — Decision #9).
  Solids/gases are never scattered (they carry life/temp that the manual `set`
  would drop).

## Acid-dissolves-gunpowder choice (Risk #7)

**Left at the default.** GUNPOWDER is NOT in `ACID_RESIST` / `BASE_RESIST`, so
acid/base dissolve it harmlessly (→ EMPTY/SMOKE, no detonation — dissolving is
not heating). This is the documented "default" of the recipe and is fine for v1;
if a future scene wants to store gunpowder in an acid bath, adding it to the
resist frozensets is a one-line change in each of `rules/acid.py` / `rules/base.py`.

## Performance (Risk #2)

A 1000-cell gunpowder pile chain-detonating over 200 frames on the full 200×140
grid: **worst single step 10.20 ms** (the 60 FPS budget is 16.67 ms/frame).
Several blasts fire per frame during the cascade and the per-blast cost is
~π·R²≈50 cells in pure Python — modest at R=4. No frame hitched. The dormant
system keeps the non-blast cells cheap, so the cost is confined to the active
blast zone. Do NOT cap chain depth (Decision #6 — the cascade is the point);
`BLAST_RADIUS=4` is the perf knob if a future explosive needs a bigger radius.

## Six-gate results

| # | Gate | Result |
|---|---|---|
| 1 | `uv run pytest tests/test_gunpowder.py tests/test_phase.py -v` | ✅ 31 passed |
| 2 | enum+registry sanity + palette-math `-c` checks | ✅ `enum+registry OK`, `palette fits 528 <= 528` |
| 3 | `uv run pytest` (full suite) | ✅ 217 passed (was 207) |
| 4a | `uv run ruff check .` | ✅ All checks passed |
| 4b | `uv run ruff format --check .` | ✅ 55 files already formatted |
| 5 | `uv run mypy src` | ✅ Success: no issues found in 30 source files |
| 6 | `SDL_VIDEODRIVER=dummy SANDFALL_FRAMES=60 uv run sandfall` | ✅ exit 0 |

## Files changed

- `src/sandfall/elements.py` — `GUNPOWDER = 15` enum member + docstring +
  `ELEMENTS` entry.
- `src/sandfall/config.py` — `COND_GUNPOWDER` (0.15), `CP_GUNPOWDER` (1.5),
  `MIN_WINDOW_W` 500→528 (132 cols) + math comment.
- `src/sandfall/thermal.py` — import 2 constants + row 15 in both LUTs.
- `src/sandfall/rules/blast.py` (NEW) — reusable `explode` (flat outer-first
  sort; heat burst + crater + scatter; module tunables).
- `src/sandfall/rules/gunpowder.py` (NEW) — detonate-or-flow (wood trigger +
  sand powder shape).
- `src/sandfall/rules/__init__.py` — import + register `update_gunpowder`.
- `tests/test_gunpowder.py` (NEW) — 10 tests.
- `tests/test_ui.py`, `tests/test_config.py`, `tests/test_renderer.py`,
  `tests/test_oil.py` — palette-count / min-width / LUT-shape literals updated
  for the 16-member enum (15 elements + 3 tools = 18 palette items).
- `docs/ARCHITECTURE.md`, `.agent/tasks/BACKLOG.md`, `README.md` —
  GUNPOWDER=15 doc additions.

## Fun / unexpected

- The blast's most elegant property is that it needs **zero new transition
  code**: it just adds heat, and the *existing* wood/oil/plant flashpoint rules,
  the water boil rule, and the gunpowder rule itself do all the cascading. The
  crater is the only "destroy" logic; everything else is the thermal model doing
  what it already did.
- The fire-cling rule (`fire.py`) was already exactly what gunpowder needed to
  ignite from a dropped spark — no special fuse wiring. Fire treats any
  `flashpoint > 0` neighbor as fuel, and gunpowder's flashpoint is 200, so a
  single fire cell reliably lights a pile given contact time.

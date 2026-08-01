# Phase 01 Reflection: Acid + Base (the dissolving pair)

## What was done

Added two dense reactive liquids — `ElementId.ACID = 12`, `ElementId.BASE = 13`
— implementing the Powder-Toy-style consumed-on-dissolve model with a fixed
5-step precedence (burn → neutralize → dilute → dissolve → flow). Acid resists
glass; base resists stone (deliberate mirror). Extended both thermal LUTs and
recomputed `MIN_WINDOW_W` for the wider 16-item palette. 19 new tests; full
suite 178 → 197.

**Files changed:**
- `src/sandfall/elements.py` — `ACID=12`, `BASE=13` enum members + 2 ELEMENTS
  entries.
- `src/sandfall/config.py` — `COND_ACID/BASE`, `CP_ACID/BASE`; `MIN_WINDOW_W`
  416 → 472 (118 cols).
- `src/sandfall/thermal.py` — imported the 4 new constants; rows 12–13 in both
  `build_conductivity_lut` and `build_heat_capacity_lut`.
- `src/sandfall/rules/acid.py` (NEW) — 5-step rule + `ACID_RESIST` + 3 tunables.
- `src/sandfall/rules/base.py` (NEW) — mirror with `BASE_RESIST` (STONE).
- `src/sandfall/rules/__init__.py` — imported + registered both rules.
- `tests/test_acid_base.py` (NEW, 19 tests).
- `tests/test_ui.py`, `tests/test_config.py`, `tests/test_renderer.py` —
  updated palette-count / min-width / enum-count assertions for 14 members.

## Final tuned values (Decision #12)

All first-pass values held — no tuning was needed (the SDL smoke + the
deterministic tests both read well as-is):

| Constant | Acid | Base |
|---|---|---|
| `DISSOLVE_CHANCE` | 0.5 | 0.5 |
| `DILUTE_CHANCE` | 0.08 | 0.08 |
| `DISSOLVE_SMOKE_CHANCE` | 0.10 | 0.10 |
| `flashpoint` | 200 | 200 |
| `burn_temp` | 600 (doc only) | 600 (doc only) |
| `density` | 1.2 | 1.2 |
| `conductivity` | 0.30 | 0.30 |
| `heat_capacity` | 2.0 | 2.0 |
| color | (110,220,70) green | (180,90,200) violet |

The 4 tunables are duplicated as module globals in `acid.py` AND `base.py`
(mirrors `LAVA_SOLIDIFY_TEMP` living in `lava.py` — "each rule file owns its
knobs"). If a future pass wants acid/base to dissolve/dilute at different
rates, they are independent; today they are intentionally identical.

## Dormant-wake finding (Risk #1) — NO wake change needed

**Confirmed: ACID/BASE do NOT join FIRE/LAVA in wake condition #3.** Two pieces
of evidence:

1. `test_acid_eats_through_sand_wall` passes: a 4-cell acid column dropped on a
   12-sand wall strictly reduces the sand count over 200 steps
   (`sand_after < sand_before`).
2. A `paint_brush`-driven blob of acid dropped above a 96-sand wall ate 5 sand
   cells over 150 steps with zero acid remaining at the end (consumed-on-
   dissolve confirmed end-to-end through the brush path + dormant scan).

Why it works: every dissolve changes the identity of TWO cells — the eaten
target (→ EMPTY/SMOKE) AND the acid cell itself (→ EMPTY, consumed). Both
register in `id_changed = data != data_before`, and the 1-cell dilation
(`_dilate(id_changed | moved)`) wakes the next wall cell AND the next acid
cell above the hole. The front is self-sustaining while acid exists; once the
acid is fully consumed the front naturally stops (correct — there is no more
acid to eat). No `simulation.py` edit was made.

## Neutralization scan-order safety (Risk #3) — confirmed

`test_acid_base_neutralize_both_become_water` loops 20 seeds. Both randomized
x-scan directions produce WATER on both cells, because EACH rule performs the
idempotent side-effect write on BOTH cells (acid sets self+WATER and neighbor+
WATER; base does the identical write). Whichever rule scans first leaves both
cells WATER; the second rule then sees WATER (no-op). Idempotent by
construction.

## Implementation choices pinned

- **Dilute scan = single neighborhood pass, fires on FIRST water neighbor.**
  The neutralize+dilute checks share one 4-neighborhood loop (per the spec
  skeleton). Dilute consumes at most one acid cell per step regardless of how
  many water neighbors exist, so first-vs-collect is equivalent for the
  consumed-once contract.
- **Ignition uses `_FIRE.burn_temp` (FIRE's 800), NOT the element's own 600**
  (Risk #6). Mirrors `wood.py:29` / `plant.py:51` byte-for-byte. The declared
  `burn_temp=600` is documentation of the fuel character; the active heat comes
  from the FIRE rule re-asserting its own burn_temp. Pinning the element's own
  burn_temp would be a deliberate deviation — left for a future pass if a
  cooler-burning fuel is wanted.
- **Minor precedence edge (not tested, accepted):** because neutralize and
  dilute share one pass, in the contrived case where an acid cell has BOTH a
  WATER and a BASE neighbor and the WATER neighbor is scanned first AND the
  ~8% dilute roll succeeds, the acid dilutes instead of neutralizing that step.
  Pure acid+base (the realistic neutralization case) is fully deterministic.
  A two-pass split (neutralize-scan-all, then dilute-scan-all) would make the
  precedence bulletproof; left as-is to match the spec skeleton literally.

## Six-gate results (all observed exit zero)

1. `uv run pytest tests/test_phase.py -v` — 21 passed ✅
2. `uv run python -c "...enum+registry..."` — enum+registry OK ✅
3. `uv run pytest` (FULL) — 197 passed ✅
4. `uv run ruff check .` — All checks passed! ✅
5. `uv run ruff format --check .` — 50 files already formatted ✅
6. `uv run mypy src` — Success: no issues found in 27 source files ✅
7. `SANDFALL_FRAMES=60 uv run sandfall` (real DISPLAY=:1 AND dummy fallback) —
   exit 0, 60 frames, no crash ✅

## Scope note (deviation from the spec's Changes Required)

The spec's "Changes Required" + "Documentation Updates" listed
`docs/ARCHITECTURE.md` (ElementId member list + the "Adding a new element"
recipe dissolve-resist obligation note) and `.agent/tasks/BACKLOG.md` (strike
"acid"). The executing task prompt's hard constraint #6 explicitly enumerated
the file scope as **elements.py + config.py + thermal.py + acid.py + base.py
+ rules/__init__.py + tests** (no docs). I followed the prompt's narrower scope
and **deferred** the ARCHITECTURE.md / BACKLOG.md edits. These are non-blocking
(no gate depends on them) and should be picked up either as a follow-up or
folded into Phase 02's doc pass. Flagging here so it is not forgotten:

- `docs/ARCHITECTURE.md:250-256` — append `ACID=12, BASE=13`.
- `docs/ARCHITECTURE.md:509-544` — add the dissolve-resist obligation to the
  recipe (Risk #2): when adding a future element, decide per-element whether
  acid/base dissolves it and update `ACID_RESIST` / `BASE_RESIST`.
- `.agent/tasks/BACKLOG.md:30-31` — strike "acid".

I also updated `tests/test_renderer.py` (`test_build_color_lut_grew_*`), which
hardcoded `len(ElementId) == 12` — not listed in the spec's "update these
tests" but it IS an enum-count test of the same class as the palette-count
tests, and the FULL-suite gate (`uv run pytest`) would have failed without it.

## Notes for Phase 02 (Oil)

- **Acid dissolves oil.** `OIL` is absent from `ACID_RESIST` (and `BASE_RESIST`),
  so once `ElementId.OIL = 14` exists, acid/base will dissolve it with no
  further rule change. Phase 02 should add a test asserting this (the
  overview Decision #10 explicitly keeps the acid↔oil interaction minimal —
  "acid dissolves oil too — documented, kept minimal").
- **`MIN_WINDOW_W` second recompute.** Phase 02 grows the palette 16 → 17 items
  (14 elements + 3 tools) → `17*24 + 16*4 + 12 + 2*8 = 500` (125 cols). Update
  `config.py` comment + the `test_config.py` / `test_ui.py` math again, plus
  this file's `test_color_lut_has_14_rows` → `(15, 3)` and
  `test_renderer.py`'s `len(ElementId) == 15`.
- **Oil rule is the simplest reactive liquid** (burn first, then flow) — no
  dissolve/dilute. Builds directly on this phase's enum/registry.
- The duplicated-tunables pattern (acid.py + base.py each own their constants)
  is fine for one more simple rule; if a 4th reactive liquid appears, consider
  factoring the 5-step skeleton into a shared helper.

## Anything fun

The "consumed-on-dissolve keeps the dormant front alive via double id-change
+ dilation" analysis (overview Risk #1) held exactly as predicted — the
cleanest confirmation that the dormant-wake design generalizes beyond
fire/lava/ice. The deliberate acid-resists-glass / base-resists-stone mirror
makes for a nice gameplay property (glass beakers hold acid; stone resists
caustic base) that fell out of two one-line frozenset edits.

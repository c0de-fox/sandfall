# New Elements: Acid + Base (pair) and Oil — Master Plan

## Problem Statement

The sandfall game ships **12 elements** (`ElementId` EMPTY=0 … GLASS=11, the v1
set + the temperature feature's STEAM/ICE/LAVA/GLASS). The thermal model, the
reactive-rule contract relaxation, density-based liquid displacement
(`can_displace`), and the dormant-cell active-set optimization are all proven.
`.agent/tasks/BACKLOG.md:30-34` has tracked "acid (dissolves materials), oil
(flammable liquid, floats on water)" as the next element pass since the original
plan (`.agent/tasks/sandfall/00-overview.md:107`).

This plan adds **three new elements** in two phases:

- **Phase 1 — the Acid + Base pair.** Two dense liquids that **dissolve**
  neighboring materials (Powder Toy's consumed-on-dissolve model), **neutralize**
  each other into water, **dilute** probabilistically in water, and **burn**
  (flashpoint → FIRE) when heated. Acid dissolves everything except glass; base
  dissolves everything except stone (a deliberate mirror so glass containers hold
  acid and stone resists base).
- **Phase 2 — Oil.** A light flammable liquid (density 0.8 < water 1.0) that
  **floats on water** via the existing `can_displace`, and **ignites to FIRE**
  when heated above a low flashpoint — so burning oil spreads fire across a water
  surface.

All three reuse mechanisms the codebase already has: the LIQUID movement shape
(`rules/water.py`), the reactive neighbor-reaction side-effect write
(`rules/lava.py`), the reactive `flashpoint` ignition (`rules/wood.py` /
`rules/plant.py`), the auto-resizing renderer/palette LUTs, and the dormant-cell
wake conditions (no new wake condition is needed — see Risks #1).

## Solution Summary

Two sequential phases. Each is a single atomic commit + reflection and follows
the documented "Adding a new element" recipe (`docs/ARCHITECTURE.md:509-544`):
enum member → `ELEMENTS` entry → rule file → `RULES` registration → tests, plus
the geometry ripple (thermal LUT rows, `config.COND_*`/`CP_*`, `MIN_WINDOW_W`
recompute) and the existing-test updates that hardcode palette counts.

- **Phase 01 — Acid + Base (the pair).** `ElementId.ACID = 12`,
  `ElementId.BASE = 13` (v1 values 0–11 unchanged; new members 12–13). Both are
  LIQUID, density ~1.2 (denser than WATER 1.0 → sink through water), with
  `flashpoint` ~200 (heat → FIRE) and `burn_temp` ~600. The per-step rule
  precedence (deterministic, same for both): **1)** burn (temp > flashpoint);
  **2)** neutralize (adjacent opposite → BOTH become WATER via a side-effect
  write on the neighbor, idempotent); **3)** dilute (adjacent water, probabilistic
  `DILUTE_CHANCE` ~0.08 → self WATER); **4)** dissolve (eat ONE adjacent
  dissolvable neighbor, probabilistic `DISSOLVE_CHANCE` ~0.5, target → EMPTY
  or SMOKE `DISSOLVE_SMOKE_CHANCE` ~0.10, and the acid/base cell itself → EMPTY,
  consumed); **5)** flow like a liquid (water.py shape). Resist sets: acid does
  NOT dissolve `{GLASS, EMPTY, ACID, BASE, WATER, LAVA, FIRE, SMOKE, STEAM}`;
  base does NOT dissolve `{STONE, EMPTY, ACID, BASE, WATER, LAVA, FIRE, SMOKE,
  STEAM}`. Module constants mirror `LAVA_SOLIDIFY_TEMP` (`rules/lava.py:43`).
- **Phase 02 — Oil.** `ElementId.OIL = 14`. LIQUID, density ~0.8 (LESS than
  WATER 1.0 → floats on water via `can_displace`). Low `flashpoint` ~150 →
  ignites to FIRE when heated by fire/lava (the thermal-ignition path). Oil rule:
  **1)** burn (temp > flashpoint → FIRE) checked FIRST; **2)** flow like a liquid.
  No dissolve / dilute. Burning oil on water spreads fire across the surface (fire
  is already a persistent heat source). Acid dissolves oil too (oil is not in
  acid's resist set — documented, kept minimal).

## Phase List

| #  | Phase                              | Cx | Depends On | Parallelizable With |
|----|------------------------------------|----|------------|---------------------|
| 01 | Acid + Base (the pair)             | L  | —          | —                   |
| 02 | Oil (floats on water, flammable)   | M  | 01         | —                   |

## Dependency Map

```
01 (acid + base) ──► 02 (oil) ──► done
```

**Both are strictly sequential — DO NOT parallelize.** Reason: both phases
mutate the same shared core files (`elements.py`, `config.py`, `thermal.py`,
`rules/__init__.py`, plus the palette-count / `MIN_WINDOW_W` tests). Phase 02
extends the enum to 14 on top of Phase 01's 12→13, recomputes `MIN_WINDOW_W` a
second time (16→17 palette items), and its tests assert acid-dissolves-oil which
requires acid to exist. A phase may only START once its dependency has passed
**all** verification gates (see each phase file).

## Decision Log

All decisions below are **user-confirmed** and must not be re-litigated. The
phrasing "user-confirmed" is taken from the prompt that authorized this plan.

1. **Acid + Base are a pair; Oil is a separate phase.** They are added as
   `ACID = 12`, `BASE = 13` (Phase 1) then `OIL = 14` (Phase 2). Existing values
   0–11 are unchanged, so every LUT index the existing code relies on (renderer
   color LUT, conductivity LUT, heat-capacity LUT) stays stable; `uint8` holds up
   to 255, so there is ample room. *(User-specified ids.)*
2. **Acid and Base are dense LIQUIDs (density ~1.2).** Denser than WATER (1.0)
   so they sink through water via `can_displace` (`_common.py:29-41`). *(Powder
   Toy model — user-confirmed "denser than water → sink through water".)*
3. **Consumed-on-dissolve (Powder Toy model).** Each step an acid/base cell may
   eat ONE adjacent dissolvable neighbor and is itself consumed (→ EMPTY). This
   is the headline behavior. Crucially, because the cell is **consumed**
   (id-changed) on every dissolve, the dormant-cell wake condition #1
   (`id_changed | moved`, dilated — `simulation.py:158-159`) keeps the dissolve
   front alive: the eaten neighbor + the consumed acid both change identity, and
   their 1-cell dilation wakes the next wall cell and the next acid cell. **No
   dormant-wake change is needed** (see Risks #1) — ACID/BASE do NOT join
   FIRE/LAVA in wake condition #3.
4. **Acid resists glass; base resists stone (deliberate mirror).** Acid's resist
   set = `{GLASS}` + the special non-dissolve cases; base's resist set =
   `{STONE}` + the same special cases. Net: glass containers hold acid; stone
   resists base. The shared non-dissolve set is `{EMPTY, ACID, BASE, WATER, LAVA,
   FIRE, SMOKE, STEAM}` (acids/bases don't eat each other directly — they
   neutralize instead; they don't eat fire/lava/smoke/steam/water). *(User
   -confirmed resist sets.)*
5. **Neutralization handled in BOTH rules via a side-effect write.** Acid
   adjacent to base → BOTH become WATER. Each rule, on finding the opposite,
   sets **both** cells to WATER (a side-effect neighbor write, exactly like
   `lava.py:67-75` setting lava→STONE + water→STEAM). This is idempotent —
   setting WATER on already-WATER is harmless — so the randomized scan order does
   not matter (verified by a multi-seed test). *(User-confirmed model.)*
6. **Dilution is simple probabilistic (no concentration field).** Acid/base
   adjacent to WATER has a per-step chance (`DILUTE_CHANCE` ~0.08) to become
   WATER itself; if it does NOT dilute that step, it falls through to
   dissolve/flow (so it still sinks through water). A per-cell concentration
   field was explicitly **rejected** (Out of Scope) in favor of this one-arg
   probabilistic model. *(User-confirmed.)*
7. **Burn reuses the existing thermal-ignition path.** `flashpoint` ~200
   (acid/base) / ~150 (oil); `if flashpoint > 0 and get_temp > flashpoint: →
   FIRE (seed life, set burn-temp)`. This mirrors `wood.py:24-30` / `plant.py:48-
   52` exactly. Lava/fire heat the fuel via the diffusion pre-pass and the
   thermal-wake condition (`simulation.py:163`); no new heat source is added
   (acid/base/oil become FIRE when they ignite, and FIRE is already a persistent
   wake source).
8. **Dissolution target → EMPTY, with a small SMOKE chance for feedback.**
   `DISSOLVE_SMOKE_CHANCE` ~0.10 → target becomes SMOKE (seeded via
   `seed_smoke_life`); otherwise EMPTY. The acid/base cell itself → EMPTY
   (consumed). *(User-confirmed visual-feedback model.)*
9. **Rule precedence is fixed and deterministic per step** (acid and base both):
   burn → neutralize → dilute → dissolve → flow. Top priority is burn (a cell
   that is igniting does not also dissolve/flow that step); flow is last (a cell
   that ate nothing this step still moves). *(User-confirmed precedence.)*
10. **Oil floats (density 0.8) and is flammable (flashpoint ~150).** No dissolve
    / dilute — just reactive burn first, then liquid flow. Acid dissolves oil too
    (oil is absent from acid's resist set) — documented, kept minimal; no special
    acid↔oil interaction beyond that. *(User-confirmed.)*
11. **`MIN_WINDOW_W` is recomputed each phase for the wider palette.** Phase 1:
    16 items (13 elements + 3 tools) → `16*24 + 15*4 + 12 + 2*8 = 472` (118 cols).
    Phase 2: 17 items (14 elements + 3 tools) → `17*24 + 16*4 + 12 + 2*8 = 500`
    (125 cols). Both are exact `CELL_SIZE` multiples. The math is shown in the
    `config.py` comment, mirroring the existing comment (`config.py:71-79`).
12. **Tuning values are starting points; pin final values in the reflection.**
    `DISSOLVE_CHANCE` / `DILUTE_CHANCE` / `DISSOLVE_SMOKE_CHANCE` / flashpoints /
    densities / conductivities / heat-capacities are first-pass values tuned by
    eyeballing the SDL smoke. The implementer records the final tuned numbers in
    the phase reflection. *(User-confirmed.)*

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | L  | Two new enum members, two ELEMENTS entries, TWO new rule files each with a 5-step precedence (burn/neutralize/dilute/dissolve/flow) + module constants + resist sets, the cross-rule neutralization, the thermal LUT rows, the `MIN_WINDOW_W` recompute, the existing palette-count/min-width test updates, and a new test file covering 7+ behaviors (dissolve each material, glass survives, neutralize, dilute, burn, consumed, smoke). Largest surface area of the plan. |
| 02    | M  | One new enum member, one ELEMENTS entry, one new rule file (burn + liquid flow — the simplest reactive-liquid shape), thermal LUT rows, a second `MIN_WINDOW_W` recompute, the existing-test updates, and a small test file (floats, ignites, fire-spreads). Builds directly on Phase 01's enum/registry; oil is the simplest possible new element. |

## Risks & Unknowns

1. **Dormant interaction (the headline risk).** ACID/BASE are consumed-on-
   dissolve, so while they exist they are always either flowing (`moved`) or
   eating (`id_changed`) — both captured by wake condition #1 + dilation
   (`simulation.py:158-159`). The analysis says no wake-condition change is
   needed. **Verify with an integration test**: a column of acid dropped onto a
   sand wall must eat through it over many steps (eventual-assertion style,
   mirroring `test_phase.py:83-116`'s freeze-spread test). If a pooled acid
   stalls against a dormant wall, the fallback is adding `ACID`/`BASE` to wake
   condition #3 (`simulation.py:168-170`) — pin the finding in the reflection.
   OIL never has this issue (it only flows / ignites).
2. **Dissolve resist-set maintenance.** The resist sets are hardcoded per rule
   (frozensets in each rule file). When future elements are added (salt, metal,
   gunpowder — `BACKLOG.md:30-32`), each must be **decided per-element**: does
   acid dissolve it? does base? Document this obligation in the "Adding a new
   element" recipe update (Phase 01 doc task) so it is not forgotten.
3. **Neutralization scan-order.** Handled idempotently via the side-effect write
   on BOTH cells (Decision #5). Verify with a multi-seed test (loop `random.seed`
   like `test_phase.py:262-280`) that BOTH scan orders produce WATER on both
   cells.
4. **`MIN_WINDOW_W` bump shrinks the smallest window slightly.** 416 → 472
   (Phase 1) → 500 (Phase 2). Documented math in the `config.py` comment; the
   existing `test_min_window_width_fits_full_palette_with_group_gap`
   (`test_config.py:93-122`) and `test_palette_resolves_phase03_elements_and_fits
   _min_window` (`test_ui.py:198-238`) hardcode the old 14-item math and MUST be
   updated each phase.
5. **Diffusion numerical stability is preserved.** The stability bound is
   `rate * max(cond) / min(cp) <= 0.25` (`config.py:104-107`). The new
   conductivities (0.30/0.30/0.12) are below the existing max (FIRE 0.50) and the
   new heat-capacities (1.5–2.0) are above the existing min (FIRE/SMOKE/STEAM
   0.5), so `0.20 * 0.50 / 0.5 == 0.20 <= 0.25` is unchanged. No new tunable
   needed.
6. **`burn_temp` on acid/base is documentation, like wood/plant.** The existing
   ignition path sets the cell to FIRE and sets temp to `_FIRE.burn_temp` (FIRE's
   800), NOT the fuel's own `burn_temp` (`wood.py:29`, `plant.py:51`). So
   acid/base's declared `burn_temp` ~600 is the documented fuel character; the
   active heat comes from the FIRE rule. Mirror wood/plant exactly; the
   implementer may pin in the reflection whether to use the element's own
   burn_temp instead.
7. **Line numbers in this plan are current as of the post-`thermal-float-ice`
   source** (verified at planning time by reading every file cited). They WILL
   shift during implementation. Re-read each file before editing rather than
   blind-applying line numbers (same caveat as the temperature plan's Risk #8).

## Documentation Updates (cross-phase)

- **`docs/ARCHITECTURE.md`** — extend the `ElementId` member list
  (`ARCHITECTURE.md:250-256`, currently "...STEAM=8, ICE=9, LAVA=10, GLASS=11")
  to include ACID/BASE/OIL; extend the "Adding a new element" recipe
  (`ARCHITECTURE.md:509-544`) with a note on the **dissolve-resist obligation**
  for future elements (Risk #2). Phase 01 does the acid/base entries; Phase 02
  adds oil.
- **`.agent/tasks/BACKLOG.md`** — strike "acid" and "oil" from the "More
  elements" line (`BACKLOG.md:30-31`) once their phases land (leave salt/metal/
  gunpowder/electricity). Phase 01 strikes acid; Phase 02 strikes oil.
- **`README.md`** — if it enumerates elements (Features table), add ACID/BASE/OIL
  rows. (Check at implementation time; the temperature plan deferred README to its
  viz/docs phase.)

## Verification Philosophy (applies to ALL phases)

Every phase's `Verification Commands` block MUST include these gates, and ALL
must exit zero before the next phase may begin:

```bash
uv run pytest tests/test_<name>.py -v     # phase-focused new tests
uv run python -c "...enum+registry sanity..."   # ids stable + count grew
uv run pytest                              # FULL suite (existing tests stay green)
uv run ruff check . && uv run ruff format --check . && uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall         # SDL smoke (fallback SDL_VIDEODRIVER=dummy)
```

After each phase, the implementer MUST write `NN-<phase>-reflection.md` in this
directory capturing: what was difficult/unexpected, deviations from the plan +
why, the **final tuned values** (Decision #12), the dormant-interaction finding
(Risk #1), and anything fun. Each phase is ONE atomic git commit.

## Out of Scope (Future Work — DO NOT plan now)

- **Acid/base concentration field** (rejected — simple probabilistic dilution
  chosen, Decision #6).
- **Complex acid↔oil interaction** beyond "acid dissolves oil" (kept minimal,
  Decision #10).
- **More elements: salt, metal, gunpowder** — separate future pass; tracked in
  `BACKLOG.md:30-32`.
- **Electricity** (needed for metal to conduct current) — Tier 2 backlog
  (`BACKLOG.md:34`). Note the name clash already flagged in the temperature plan:
  this codebase's `conductivity` is *heat* conductivity, not electrical.

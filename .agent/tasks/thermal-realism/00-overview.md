# Sandfall Thermal Realism — Master Plan

## Problem Statement

Ice is currently an **interim persistent cold source** (shipped under
`thermal-float-ice/02`, commit `b2669a9`): `update_ice` re-asserts
`ICE_COLD_TARGET = -50` each step (`rules/ice.py:39,80-81`), freezes water
through the thermal system, and **does NOT melt in ambient** — the `if temp >
melt_point: -> WATER` branch was deliberately deleted because melt-at-`>0` is
logically incompatible with being a cold source. That compromise was made so
ice could freeze water *until real cold-source elements existed*. It is now the
documented interim model (`rules/ice.py:11-20`, BACKLOG Tier 2 "Thermal realism
rework", `.agent/tasks/BACKLOG.md:74-84`).

The user's stated end state is the **Powder Toy / Sandboxels model**:

1. **Ice reverts to a realistic non-source "frozen water"** — it melts to WATER
   when its own temp exceeds its `melt_point` (0°C), so a lone ice block in 20°C
   ambient melts, and ice **no longer freezes water on its own** (it sits at
   ~0°C and cannot pull 20°C water below 0).
2. **Real colder-than-freezing cold sources** do the freezing: **dry ice**
   (~−78°C, persistent solid) and **liquid nitrogen** (~−196°C, transient
   liquid). Their diffusion cools adjacent water to/below its `freeze_point`
   (0°C); the WATER rule then freezes it (the existing `water.py:62-65` branch).

This retires the "ice doesn't melt in ambient" interim compromise and the
`ICE_COLD_TARGET` mechanism entirely — dry ice replaces ice in that role, named
and tuned realistically.

## Solution Summary

A **two-phase rework**, each independently verifiable and committable:

- **Phase 01 — Revert ice to realistic + add dry ice (together).** The ice
  revert and dry ice MUST land together: without a cold source there is no way
  to freeze water (the reverted ice can't), so dry ice fills the freeze role
  the moment ice vacates it. Concretely:
  - `rules/ice.py` is reverted: drop the `ICE_COLD_TARGET` re-assert, **restore
    the thermal melt** (`if get_temp > melt_point: -> WATER`), keep the direct
    fire/lava contact melt (FIRE→WATER, LAVA→STEAM). `ICE.temp_spawn`: −5 → **0**
    (frozen water ~0°C; `elements.py:238`). Ice no longer freezes water.
  - `rules/water.py` freeze branch (`:62-65`) stops seeding the new ice cold
    (drop the `ICE_COLD_TARGET` import + the `set_temp` write, `:33,64`); the
    new ice keeps the water's already-≤0 temp (realistic).
  - **`ElementId.DRY_ICE = 16`** is added — a SOLID persistent cold source that
    re-asserts `DRY_ICE_COLD_TARGET = -78` (mirroring the *exact* interim-ice
    mechanism that is being retired from ice), `temp_spawn=-78`. It freezes
    adjacent water via diffusion, and sublimates ONLY via direct fire/lava
    contact (FIRE→EMPTY, LAVA→SMOKE), NOT ambient. It is "old ice behavior at
    −78, named dry ice."
- **Phase 02 — Liquid nitrogen (`ElementId.LN2 = 17`).** A LIQUID transient
  cold source: density **0.8** (floats on water, like oil — `rules/oil.py`),
  re-asserts `LN2_COLD_TARGET = -196` (its boiling point) while alive, and is
  **TRANSIENT** — it carries a per-cell `life` countdown (new
  `seed_nitrogen_life()` in `_common.py`, short window `randint(30, 80)`) and
  boils off to EMPTY at ambient (room temp ≫ −196). Extreme cold freezes water
  aggressively before it boils away. Rule precedence mirrors oil (flow) prefixed
  by age + cold-reassert. `paint_brush` seeds LN2 life (new branch, mirroring
  FIRE/SMOKE/STEAM).

**Freezing mechanism (unchanged from the interim model):** a cold source
(dry ice / LN2) re-asserts its cold target → the whole-grid diffusion pre-pass
carries that cold outward → adjacent water cools to ≤ `freeze_point` (0) → the
WATER rule freezes it to ICE (`water.py:62-65`). Freeze persists while the cold
source lasts (dry ice = indefinitely; LN2 = until it boils off). One realism
nuance encoded in the plan: because the *newly-formed ice* is no longer a cold
source, the freeze front advances by cold diffusing **through the growing ice
shell** from the dry-ice source (slower than the interim 1→9-in-120 spread,
where every new ice cell re-asserted cold) — but it DOES advance, and the
Phase-01 integration test is the gate.

## Phase List

| #  | Phase                                       | Cx | Depends On | Parallelizable With |
|----|---------------------------------------------|----|------------|---------------------|
| 01 | Revert ice to realistic + add dry ice       | M  | —          | —                   |
| 02 | Liquid nitrogen (transient cold liquid)     | M  | 01         | —                   |

## Dependency Map

```
01 (ice revert + dry ice) ──► 02 (liquid nitrogen) ──► done
```

**Strictly sequential.** Phase 02 extends the enum 16→17 (from Phase 01's
15→16), recomputes `MIN_WINDOW_W` a second time, and adds a second thermal-LUT
row + palette item. Phase 01 must be fully green first. Critically, the **ice
revert is inside Phase 01** (not its own phase) because landing it without dry
ice would leave the simulation with no element capable of freezing water.

## Decision Log

All decisions below are **user-approved** and must not be re-litigated. The
phrasing "user-confirmed" is taken from the prompt that authorized this plan.

1. **Both cold elements ship (dry ice AND liquid nitrogen).** Not either/or.
   The user explicitly confirmed both. Dry ice is the persistent solid cold
   source (the role ice used to play); LN2 is the transient cryogenic liquid.
   *(Alternative considered: ship dry ice only — rejected by the user.)*
2. **Ice reverts to a realistic non-source.** `ICE_COLD_TARGET` and the re-assert
   are removed entirely; the thermal melt (`> melt_point → WATER`) is restored;
   `ICE.temp_spawn` goes −5 → 0. Ice melts in ambient and does not freeze water.
   This is the deliberate retirement of the `thermal-float-ice/02` interim model
   (its Decision Log #2-#5 are reversed here). *(Rationale: it was always the
   documented interim until real cold sources existed; dry ice now exists.)*
3. **Dry ice is the persistent cold source (replaces ice in that role, at −78).**
   Dry ice re-asserts `DRY_ICE_COLD_TARGET = -78` each step — the *same mechanism*
   ice used at −50, just colder and named realistically (CO₂ sublimation point).
   It does NOT melt in ambient (re-asserts cold) and sublimates only via direct
   fire/lava contact, mirroring the interim-ice fire/lava-melt shape. This keeps
   the prototype-validated cold-source mechanism and its dormant-wake sufficiency
   finding intact under a new name/value.
4. **Liquid nitrogen is TRANSIENT (boils off).** LN2 re-asserts `LN2_COLD_TARGET
   = -196` while alive but carries a finite `life` (`seed_nitrogen_life`, short
   window) and expires to EMPTY — room temperature is far above its −196°C
   boiling point, so it boils rapidly. *(Alternative considered: make LN2
   persistent like dry ice — rejected by the user: LN2 is transient.)* On
   boil-off it becomes EMPTY (minimal scope). A cold SMOKE puff is a noted
   visual option, explicitly deferred (see Out of Scope).
5. **`DRY_ICE_COLD_TARGET` / `LN2_COLD_TARGET` live as module constants** in
   `rules/dry_ice.py` / `rules/ln2.py` (mirrors `LAVA_SOLIDIFY_TEMP` at
   `lava.py:43` and the retired `ICE_COLD_TARGET`). NOT new `Element` fields and
   NOT in `config.py`: they are rule-level tunables for spread rate, not material
   properties. No sibling-rule import is needed (unlike the old
   `water → ice` for `ICE_COLD_TARGET`): the water freeze branch no longer seeds
   the new ice cold, so `water.py` drops its `.ice` import entirely — the
   one-way `water → ice` dependency that existed under the interim model is gone.
6. **Dry ice fire/lava sublimation: FIRE → EMPTY, LAVA → SMOKE.** Two-tier like
   interim ice (FIRE=mild, LAVA=dramatic). Dry ice has no liquid phase, so fire
   gently sublimates it to EMPTY and intense lava heat flashes it to a SMOKE puff
   (seeded via `seed_smoke_life`). *(Judgment call; document in the reflection
   if flipped.)*
7. **Newly-frozen ice keeps the water's temp (no cold seeding).** The water rule
   freeze branch no longer writes the new ice's temp; the new ice naturally
   starts at the water's already-≤0 value. This is the realistic model and it is
   what makes ice melt in ambient (it warms back toward ambient via diffusion
   once the cold source is gone).
8. **Dormant-wake: audit-only, integration-test-gated (mirror thermal-float-ice).**
   Dry ice (persistent cold source, may neither move nor change identity nor, at
   its target, change temp) is the SAME wake-sufficiency case interim ice was.
   Analysis: the whole-grid diffusion pre-pass carries cold from a dormant dry
   ice cell regardless of `active`; adjacent water cools (temp change → wake
   condition 2); it freezes (identity change → wake condition 1 + dilate); the
   dry ice cell self-wakes via its own temp change as cold flows out. So the
   existing four wake conditions (`simulation.py:158-170`) should keep a
   spreading freeze alive **without** adding DRY_ICE (or LN2) to condition 3.
   **Verified, not assumed:** the Phase-01 integration test
   (`test_dry_ice_freezes_water`) is the gate; only if it stalls, add
   `| (data == int(ElementId.DRY_ICE))` to `simulation.py:168-170`.
9. **Tests assert the NEW behavior (not the interim).** The interim tests that
   encoded "ice is a cold source" / "ice does not melt in ambient" are reworked
   to the realistic model (ice melts in ambient; dry ice does the freezing).
   This is a deliberate, user-requested behavior change — the reworked tests are
   the spec, not a regression.

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | M  | The ice revert (rewrite `ice.py` to realistic, drop `ICE_COLD_TARGET`; touch `water.py` freeze branch + import) lands **together** with a new element `DRY_ICE=16` (enum + ELEMENTS + config constants + 2 LUT rows + new rule file `dry_ice.py` mirroring interim-ice + registry + `MIN_WINDOW_W` recompute 528→556 + test reworks in `test_phase.py` + palette-width tests). Touches ≤4 subsystems (elements, rules, thermal, tests) and the dormant-wake sufficiency is the verified unknown. |
| 02    | M  | A new element `LN2=17` (enum + ELEMENTS + config + 2 LUT rows + new rule `ln2.py` = oil-flow prefixed by age+cold-reassert + new `seed_nitrogen_life` in `_common.py` + brush life-seeding branch + registry re-export + `MIN_WINDOW_W` 556→584 + new tests). The transient-life + boil-off tuning (must freeze water before boiling away) is the unknown. |

## Risks & Unknowns

1. **Deliberate behavior change (encode, do not "fix" back).** Ice no longer
   freezes water and now melts in ambient; the interim persistent-cold-source
   model is retired. The reworked tests assert the NEW behavior. A future
   contributor reading the old `ice.py` docstring must not re-introduce
   `ICE_COLD_TARGET` — the new `ice.py` docstring states the realistic model and
   points at dry ice / LN2 as the cold sources.
2. **Freeze now requires a cold source.** Phase 01 lands dry ice *alongside* the
   ice revert so there is never a window with no way to freeze water. The two
   changes are one phase (and one commit) for this reason.
3. **Slower freeze spread than the interim model.** Because newly-formed ice no
   longer re-asserts cold, the dry-ice freeze front advances by cold diffusing
   through the growing ice shell (only the dry-ice cell is the source), which is
   slower than the interim 1→9-in-120 spread. `DRY_ICE_COLD_TARGET=-78` (colder
   than the interim −50) compensates somewhat. The integration test asserts
   strict growth (>0 ice), not a rate; pin the measured spread in the reflection.
4. **Dormant-wake sufficiency (verified, not assumed).** Dry ice / LN2 are NOT in
   wake condition 3 today (`simulation.py:168-170`, FIRE/LAVA only). Analysis
   (Decision #8) says `temp_changed` wake suffices; the Phase-01 freeze-spread
   test is the gate. If a pooled cold source stalls, add it to condition 3.
5. **LN2 boil-off tuning.** `seed_nitrogen_life` range (`randint(30, 80)`) +
   −196 re-assert must let LN2 visibly freeze water before boiling away. If LN2
   boils off too fast to freeze anything, widen the window; if it lingers too
   long, narrow it. Pin the final range in the Phase-02 reflection.
6. **Palette / registry ripple.** Two enum growths (16→17→18) each force a
   `MIN_WINDOW_W` recompute + 2 LUT rows + palette-width test updates. The
   math: 18 items (current) → 19 (Phase 1, 556px = 139 cols) → 20 (Phase 2,
   584px = 146 cols). Renderer/palette auto-resize from `len(ElementId)`
   (verify, no edit expected). Existing `test_ui.py` / `test_config.py`
   hardcode the 18-item / 528 math and MUST be updated each phase.
7. **`ICE_COLD_TARGET` removal ripples through tests.** `tests/test_phase.py`
   imports it (`:31`) and asserts it in `test_water_freezes_to_ice` (`:80`) and
   the spreading-freeze test (`:108`). All three are reworked in Phase 01.
8. **Line numbers in this plan are current as of the gunpowder-complete source**
   (verified at planning time by reading every file cited). The implementer must
   re-read each file before editing rather than blind-applying line numbers.

## Verification Philosophy (applies to both phases)

Each phase's `Verification Commands` block includes these gates, and ALL must
exit zero before the phase is considered done:

```bash
uv run pytest tests/test_phase.py tests/test_thermal.py -v   # phase-focused
uv run python -c "<enum + registry check -- per phase>"
uv run pytest                                                 # FULL suite -- regression guard
uv run ruff check .; uv run ruff format --check .; uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall                           # SDL smoke (fallback SDL_VIDEODRIVER=dummy)
```

After each phase, the implementer MUST write `0N-<phase>-reflection.md` in this
directory. Each phase is ONE atomic git commit. Do NOT write reflections during
planning — only after execution.

## Out of Scope (Future Work — DO NOT implement now)

- **A distinct "cold gas" element** for dry-ice sublimation / LN2 evaporation.
  Dry-ice/LAVA emits SMOKE (reused); dry-ice/FIRE and LN2 boil-off emit EMPTY.
  A dedicated cryogenic gas is a separate future element.
- **Fire + water extinguish mechanic.** Water currently shoves fire aside (the
  `liquid-through-gas` displacement in `can_displace`); a real extinguish is
  separately deferred.
- **Concentration / dilution for acid-base (Scope B chemistry).** Separately
  deferred (see BACKLOG Tier 2).
- **Re-tuning existing thermal thresholds** beyond what this rework requires
  (only `ICE.temp_spawn` −5→0 and the new cold-target constants change).
- **`float64` temp storage** (settled under `thermal-float-ice`; `float32` is
  enough).

## Foundation Reference

This plan is the *deliberate follow-on* to the interim persistent-cold-source
ice. For architecture context, read:

- `.agent/tasks/thermal-float-ice/02-ice-cold-source.md` — the interim model
  being RETIRED (its `update_ice` re-assert + fire/lava-melt shape is lifted
  verbatim into `rules/dry_ice.py` at −78, then deleted from `ice.py`).
- `.agent/tasks/thermal-float-ice/00-overview.md` — the float-temps foundation
  + the cold-source mechanism + dormant-wake analysis this plan reuses.
- `.agent/tasks/new-elements/01-acid-base.md` + `02-oil.md` — the proven "add an
  element" recipe (enum + ELEMENTS + rule + LUT rows + `MIN_WINDOW_W` + tests)
  that `DRY_ICE` and `LN2` follow.
- `docs/ARCHITECTURE.md` "Adding a new element" (`:511-553`) + the temperature-
  field / rule-contract sections.
- `src/sandfall/rules/ice.py` (interim rule to revert), `rules/water.py` (freeze
  branch), `rules/oil.py` (light-LIQUID pattern LN2 mirrors), `rules/_common.py`
  (`seed_*_life` helpers), `elements.py`, `thermal.py`, `config.py`,
  `simulation.py:158-170` (wake conditions), `tests/test_phase.py` — the exact
  code these phases edit. **Re-read before editing; line numbers shift.**

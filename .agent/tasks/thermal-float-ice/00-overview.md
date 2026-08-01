# Sandfall Float Temps + Ice Cold Source — Master Plan

## Problem Statement

Ice no longer freezes water — a regression that surfaced after commit `ce4be67`
(the `thermal-conservation-fix`). **Measured:** an ice block placed next to water
→ over the next steps the **ice count 12 → 9 while the water count 20 → 23**
(ice *melts*, no water freezes). The thermal system is now correct and
energy-conserving, but that correctness *exposed* that **ice was never a real
cold source** — the old non-conservative diffusion bug had been artificially
freezing water by annihilating heat at material boundaries; once that was fixed,
the freeze mechanism that relied on it stopped working.

Two compounding root causes, both confirmed by read-only prototyping:

1. **`int16` rounding stall.** `diffuse_temps` rounds to the nearest int each
   step (`np.rint(...).astype(np.int16)`, `thermal.py:156`). A water cell next
   to a mildly-cold ice cell cools only ~0.5°C/step, which **rounds back up** —
   the cell *sticks* at ~+6°C and can never reach the `<= 0` freeze threshold.
   (Heat sources still work because fire/lava are extreme 800–1500°C with large
   per-step deltas that clear rounding; mild cold cannot.)
2. **Ice is only −5°C and melts at `> 0°C`.** Even with float precision, a −5°C
   ice cell warms above 0 and melts (~7 steps) before the adjacent 20°C water
   cools to 0 — and the conservative diffusion with `CP_WATER = 4` transfers
   cold slowly. The `ce4be67` fix removed the old heat-destroying bug that had
   been *artificially* freezing water; fixing conservation revealed that ice was
   never strong enough to freeze anything on its own.

## Solution Summary

A **two-phase fix**, each independently verifiable:

- **Phase 01 — Float temps foundation.** Switch `Grid._temp` from `int16` to
  `float32` (`grid.py:84,94`), make `diffuse_temps` return `float32` by dropping
  the `np.rint(...).astype(np.int16)` (`thermal.py:156`), and update the
  type annotations (`get_temp -> float`, `set_temp(value: float)`, the `temp`
  property, `diffuse_temps`/`thermal_to_rgb` signatures). This removes the
  rounding stall so diffusion reaches thresholds precisely — a water cell cooling
  toward 0 actually crosses 0. Computation stays `float64` internally (only the
  stored/returned type is `float32`). This is the foundation; it does not by
  itself fix the freeze (ice is still only −5°C and still melts at `>0`).
- **Phase 02 — Ice as a persistent cold source.** Rework `update_ice`
  (`ice.py:25-29`) to (a) **re-assert a cold temp each step** —
  `if get_temp > ICE_COLD_TARGET: set_temp(ICE_COLD_TARGET)` where
  `ICE_COLD_TARGET ≈ −50` (a new module constant mirroring lava's
  `LAVA_SOLIDIFY_TEMP`) — so ice freezes water *via the thermal system*, exactly
  as fire re-asserts `burn_temp` (`fire.py:92-93`); and (b) **melt ONLY via
  direct fire/lava contact** (mirror `lava.py`'s reaction shape), **removing the
  old `if temp > melt_point: -> WATER` thermal-melt** that is incompatible with
  being a persistent cold source and was the thing preventing freezing. The
  water freeze branch (`water.py:56-59`) also sets the new ice's temp cold so the
  freeze front advances immediately (no 1-frame lag).

**Prototype validation (cite as the target behavior):** float temps + ice
re-asserting −50°C + new-ice-gets-cold spreads a freeze **1 → 3 → 5 → 9 cells
over 120 steps** (an ice cube growing in water) — the exact behavior that broke.

**Deliberate, temporary behavior change:** ice **no longer melts in ambient**
(warm water/air). This is incompatible with being a persistent cold source and
was the thing blocking the freeze. It is a deliberate interim model — see
**Out of Scope** and the BACKLOG for the realistic rework (revert ice to a
melt-at-`>0` non-source "frozen water" once colder cold-source elements exist).

## Phase List

| #  | Phase                                | Cx | Depends On | Parallelizable With |
|----|--------------------------------------|----|------------|---------------------|
| 01 | Float temps foundation (`_temp` → float32) | M  | —          | —                   |
| 02 | Ice as a persistent cold source      | M  | 01         | —                   |

## Dependency Map

```
01 (float temps) ──► 02 (ice cold source) ──► done
```

**Strictly sequential.** Phase 02's acceptance criterion (freeze *spreads*
through water) is only achievable on top of Phase 01's float precision: under
the current `int16` rounding, the water between two cold cells never reaches the
`<= 0` freeze threshold (it sticks at ~+6), so re-asserting −50 on ice would
still not propagate a freeze. The two phases are each individually green and
committable; Phase 01 is a correct, useful change on its own (precision + the
tightened conservation test) even before Phase 02 lands.

## Decision Log

All decisions below are **user-approved** and must not be re-litigated. The
phrasing "user-approved" is taken from the prompt that authorized this plan.

1. **`_temp` becomes `float32` (NOT `float64`).** Removes the `int16` rounding
   stall (root cause #1) with ample precision (~7 significant digits; the
   [−200, 3000] band and the ~0.5°C/step cold deltas resolve cleanly). `float64`
   storage was rejected as unnecessary: computation is already `float64` inside
   `diffuse_temps`, the storage cost is double for no behavior gain, and the
   rounding drain that justified `int16` is gone once storage is float.
   *(Supersedes the `thermal-conservation-fix/00` Decision Log #3 trade-off,
   which kept `int16` + round-to-nearest; that choice is now reversed because
   the rounding stall is the root cause of the freeze regression. The BACKLOG
   "float32 temp storage" cleanup item is thus consumed by this plan.)*
2. **Ice becomes a persistent cold source (mirrors fire's heat-source pattern).**
   Ice re-asserts `ICE_COLD_TARGET` each step exactly as `fire.py:92-93`
   re-asserts `_BURN_TEMP`. This is the mechanism that makes ice freeze water
   *through* the (now-conservative) thermal system rather than as a diffusion
   bug side-effect. `ICE_COLD_TARGET ≈ −50` (validated by prototype); it is a
   tunable knob for spread rate, NOT a physical temperature. *(Alternative
   considered: raise `ICE.temp_spawn` and keep melt-at-`>0` — rejected: a
   warmer-than-freezing source still melts before it freezes anything, and the
   melt-at-`>0` branch is logically incompatible with re-asserting cold.)*
3. **Ice melts ONLY via direct fire/lava contact (thermal-melt removed).** The
   `if temp > melt_point: -> WATER` branch (`ice.py:27-28`) is deleted. A cell
   that re-asserts `−50` every step can never exceed `melt_point` through
   diffusion, so the branch was dead weight *and* its existence is what blocked
   making ice cold enough to freeze. Direct fire/lava contact (the real-world
   way ice is destroyed quickly) replaces it, mirroring `lava.py:62-75`'s
   reaction shape. *(Accepted consequence, documented in Risks: ambient ice no
   longer melts — deliberate and temporary; the realistic rework is tracked in
   BACKLOG.)*
4. **`ICE_COLD_TARGET` lives as a module constant in `ice.py`** (mirrors
   `LAVA_SOLIDIFY_TEMP` at `lava.py:43`), imported by `water.py` for the
   new-ice-gets-cold write. NOT a new `Element` field and NOT in `config.py`:
   it is a *rule-level* tunable (like `LAVA_SOLIDIFY_TEMP` and `SMOKE_CHANCE`),
   not a material property. The sibling-rules import (`water → ice` for one
   constant) is one-way (ice imports only from `..elements`/`..grid`), so there
   is no import cycle.
5. **New ice gets cold immediately in the water rule.** The freeze branch
   (`water.py:56-59`) sets the freshly-frozen cell's temp to `ICE_COLD_TARGET`
   so the freeze front advances the *same* step rather than waiting a frame for
   the new ice's own rule to re-assert. Avoids a 1-frame stall at the front.

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | M  | A dtype swap (`int16` → `float32`) that is mechanically small but ripples through `_temp`/`temp`/`get_temp`/`set_temp` annotations and signatures in `grid.py` + `thermal.py`, plus a mandatory re-measurement of the conservation test tolerance (it was loose `±15` to allow int16 rounding drain; float should be near-zero), an `int16`-named test rename, the `dtype == np.int16` assertion in `test_grid.py`, and a mypy audit of `get_temp -> float` callers. Small surface, but the tolerance re-measurement and the mypy ripple are the careful parts. |
| 02    | M  | A focused rule rewrite (`update_ice`: re-assert + fire/lava-contact melt, drop thermal-melt) + a one-line addition to `water.py`'s freeze branch + a dormant-wake *verification* (analysis says the existing `temp_changed` wake suffices, but a real integration test must confirm the freeze actually spreads — and if it stalls, ICE joins the FIRE/LAVA wake condition) + two new/reworked tests (a spreading-freeze integration test; rework `test_ice_melts_to_water` to fire/lava contact). The dormant-wake sufficiency is the unknown. |

## Risks & Unknowns

1. **mypy float/int ripple from `get_temp -> float`.** Audited at planning time:
   every `get_temp` caller in `src/sandfall/rules/` either compares directly
   (`get_temp(...) > melt_point`, etc. — `float > int` is fine in mypy) or binds
   to an *untyped* local (`t = grid.get_temp(...)` in `water.py:45` — infers
   `float`, fine). **No rule annotates a `get_temp` result as `int`**, so no rule
   logic change is needed for Phase 01. Tests may have `int`-annotated locals
   (audit `tests/`); fix only what mypy flags.
2. **The conservation test tolerance MUST be re-measured for float.** The current
   bound is `±15` (`test_thermal.py:162`), deliberately loose to absorb the int16
   round-to-nearest drain (~10/410). With float32 storage the face-flux still
   telescopes to zero in float64 computation and the only residual is the
   per-step `float32` cast (~1e-6 relative), so the measured drift should be
   **<< 1**. Do NOT keep the loose `±15`; set the real measured value (provisional
   bound `1.0`, tightened to the measured number — flag in the reflection if it
   exceeds `1.0`, which would indicate an unexpected issue).
3. **Dormant-wake sufficiency for a spreading freeze (Phase 02's unknown).** The
   four wake conditions (`simulation.py:159-170`) do NOT currently include ICE.
   Analysis (encode in Phase 02): the diffusion pre-pass runs WHOLE-GRID
   regardless of `active`, so cold from dormant ice still propagates into
   adjacent water; that water cools (temp changes → condition 2 wakes it → it is
   scanned → its freeze-check runs → it freezes); the freshly-frozen cell changed
   identity (condition 1 wakes it + neighbors) and re-asserts cold; meanwhile the
   *ice* cell itself warms slightly toward the warmer water (temp changes →
   condition 2 wakes it → re-assert runs). So the existing `temp_changed` wake
   *should* keep the front alive **without** adding ICE to condition 3. **BUT
   this is verified, not assumed:** the Phase 02 integration test (seed ice in
   water, step ~80–120, assert ice count grows) is the gate. If the freeze
   *stalls*, add `| (data == int(ElementId.ICE))` to the condition-3 dilate at
   `simulation.py:168-170` and pin the finding in the reflection.
4. **`test_ice_melts_to_water` (`test_phase.py:86-95`) WILL break in Phase 02.**
   It relies on the thermal-melt branch (`ICE at 5°C → WATER`) that Phase 02
   deletes. Phase 02 reworks it into a fire/lava-contact melt test. (Phase 01
   alone does NOT break it — float `get_temp` comparisons still hold.)
5. **Behavior change: ambient ice no longer melts.** Deliberate and temporary
   (Decision Log #3). Document it in the `ice.py` docstring so a future
   contributor does not "fix" it back before the realistic rework lands. The
   realistic end state is in BACKLOG.
6. **`ICE_COLD_TARGET` tuning affects spread rate.** `−50` is prototype-validated
   (1 → 9 cells / 120 steps). Colder → faster spread; warmer → slower. Tunable;
   pin `−50` as the starting value and note the knob in the docstring.
7. **Line numbers in this plan are current as of the
   `thermal-conservation-fix`-complete source** (verified at planning time by
   reading every file cited). The implementer must re-read each file before
   editing rather than blind-applying line numbers.

## Verification Philosophy (applies to both phases)

Each phase's `Verification Commands` block includes these six gates, and ALL
must exit zero before the phase is considered done:

```bash
uv run pytest tests/test_thermal.py tests/test_grid.py -v   # Phase 01 focused
uv run pytest tests/test_phase.py tests/test_fire.py -v     # Phase 02 focused
uv run python -c "import sandfall"
uv run pytest                                                # FULL suite -- regression guard
uv run ruff check .; uv run ruff format --check .; uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall                          # SDL smoke (fallback SDL_VIDEODRIVER=dummy)
```

After each phase, the implementer MUST write `0N-<phase>-reflection.md` in this
directory. Each phase is ONE atomic git commit. Do NOT write reflections during
planning — only after execution.

## Out of Scope (Future Work — DO NOT implement now)

- **Realistic thermal rework** (the user's stated future direction). Revert ice
  to a non-source "frozen water" that melts at `> 0°C` (thermodynamically
  realistic), and add **colder-than-freezing cold-source elements** so that
  freezing water requires a colder-than-freezing source: **dry ice** (~−78°C,
  sublimates) and **liquid nitrogen** (~−196°C, evaporates). This is the
  Powder Toy / Sandboxels end state; the current persistent-cold-source ice is
  the interim. **Tracked as a new Tier 2 BACKLOG entry citing this plan.**
- **`float64` temp storage.** `float32` is enough (Decision Log #1); revisit
  only if precision issues appear at extreme temperatures.
- **A "cold source" element-category abstraction** (premature until multiple
  cold sources exist — only ice is one today).
- **Removing the `lava.py` steam-acceptance workaround** (still deferred from
  `thermal-conservation-fix`; out of scope here).

## Foundation Reference

This plan builds on the model fixed under `.agent/tasks/thermal-conservation-fix/`
(commit `ce4be67`). For architecture context, read:
- `.agent/tasks/thermal-conservation-fix/00-overview.md` — the conservative
  face-flux diffusion + heat-capacity model this plan's float change sits on top
  of (Decision Log #3 of that plan kept `int16`; this plan reverses it — see
  Decision Log #1 here).
- `.agent/tasks/thermal-conservation-fix/01-conservative-diffusion.md` — the
  exact `diffuse_temps` rewrite whose `np.rint(...).astype(np.int16)` return this
  plan's Phase 01 drops.
- `src/sandfall/grid.py`, `src/sandfall/thermal.py`, `src/sandfall/rules/ice.py`,
  `src/sandfall/rules/water.py`, `src/sandfall/rules/lava.py`,
  `src/sandfall/simulation.py`, `tests/test_thermal.py`, `tests/test_grid.py` —
  the exact code these phases edit. Re-read before editing; line numbers shift.

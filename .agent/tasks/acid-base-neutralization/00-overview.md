# Task Plan: Acid/Base Neutralization — quick steam-fix (Scope A)

> **Follow-on to** `new-elements/01-acid-base.md` (the phase that ADDED acid/base).
> Same domain, same voice. This is its behavior-fix ticket.

## Problem Statement

The acid+base neutralization (shipped in `new-elements/01`) is wrong in **two**
ways the user reported, both confirmed by measurement:

1. **It is not exothermic and produces no steam.** Today, acid+base adjacent
   just turns BOTH cells into WATER directly
   (`acid.py:88-91` / `base.py:91-94`: `grid.set(self, WATER);
   grid.set(neighbor, WATER)`). The user wants the reaction to be hot and to
   create **STEAM that then turns into water** (the realistic neutralization
   look — a hot gaseous puff, then condensation).

2. **It is nowhere near 1:1.** MEASURED: dropping ONE base cell into a 19-cell
   acid pool clears the ENTIRE pool (acid 19 → 0, water 0 → 11) within ~60
   steps. Root cause = the **dilute cascade**: neutralization produces WATER,
   and the acid `dilute` rule (`acid.py:96-98`: acid adjacent to WATER →
   probabilistically become WATER) fires on that product water, which makes
   more water, which dilutes more acid → the whole pool collapses to water
   from a single neutralization. (User quote: "a single base touches a pool of
   acid turns into water.")

User also noted two further items (DEFERRED — recorded in BACKLOG, not fixed
here): *"dilute acid does not dissolve anything; it's indistinguishable from
normal water"* and *"add a mixing heatmap."* Both require a per-cell
CONCENTRATION field (a thermal-scale chemistry layer); out of scope for this
fix — see Decision Log #2 (Scope B).

## Solution Summary

**User-approved Scope A ("quick steam-fix").** Change the neutralize branch in
BOTH `acid.py` and `base.py` so acid+base → **both become hot STEAM** (not
WATER), then let the existing steam rule condense that steam to WATER once it
cools.

Before (`acid.py:88-91`; `base.py:91-94` mirrors with `ACID`):

```python
if nb == ElementId.BASE:                 # base.py: if nb == ElementId.ACID:
    grid.set(x, y, ElementId.WATER)
    grid.set(nx, ny, ElementId.WATER)
    return None
```

After:

```python
if nb == ElementId.BASE:                 # base.py: if nb == ElementId.ACID:
    # Exothermic neutralization -> both become hot STEAM. The STEAM then
    # condenses to WATER via the steam rule (temp < condense_point -> WATER),
    # so the end state is still water but via a hot, gaseous intermediate.
    # Producing STEAM (not WATER) ALSO breaks the dilute cascade that used to
    # let one base clear a whole acid pool: the acid dilute rule fires only on
    # adjacent WATER, and STEAM is not WATER, so the surrounding acid is left
    # alone -> ~1:1 neutralization.
    grid.set(x, y, ElementId.STEAM)
    grid.set(nx, ny, ElementId.STEAM)
    grid.set_life(x, y, seed_steam_life())
    grid.set_life(nx, ny, seed_steam_life())
    grid.set_temp(x, y, NEUTRALIZE_TEMP)
    grid.set_temp(nx, ny, NEUTRALIZE_TEMP)
    return None
```

(`base.py` mirrors exactly: `if nb == ElementId.ACID:` → the identical STEAM
write.)

Supporting edits in each file:
- Add `seed_steam_life` to the `._common` import (`acid.py:37`, `base.py:39`
  currently import `seed_fire_life, seed_smoke_life`).
- Add `NEUTRALIZE_TEMP = 150` as a module constant in both files (alongside
  `DISSOLVE_CHANCE` / `DILUTE_CHANCE` / `DISSOLVE_SMOKE_CHANCE` at
  `acid.py:39-42` / `base.py:41-44`).

### Why the `set_life` + `set_temp` calls are MANDATORY (not belt-and-suspenders)

`Grid.set` updates ONLY the element id — it does **not** touch `life` or `temp`
(`grid.py:170-193`: *"This only updates the element id; the cell's life entry is
untouched"*). So after `grid.set(x, y, STEAM)` the cell still holds the **stale
acid values**: `life=0` (acid has no life) and `temp=AMBIENT_TEMP` (20). Left
that way:
- the steam rule (`steam.py:44-49`) sees `life <= 0` and **expires the cell to
  EMPTY** before it ever condenses; and
- even if life were seeded, `temp=20 < STEAM.condense_point (60)`
  (`elements.py:219`) → the steam rule (`steam.py:40-42`) **condenses it to
  WATER on the very next step** — no visible hot-steam phase at all.

So `seed_steam_life()` gives the steam a finite lifetime to rise/linger, and
`set_temp(NEUTRALIZE_TEMP)` (150, well above `condense_point` 60) is what keeps
it gaseous and hot long enough to be seen and to cool gradually. Both are
required for the intended behavior.

### Why it fixes BOTH reported points

- **Exothermic + steam→water.** STEAM at 150 °C is hot (shows on the `H` heat
  overlay; heat diffuses to neighbors via the existing thermal pass). The steam
  rule then condenses it to WATER once it cools below `condense_point` (60). So
  "creates steam that turns into water," via the existing path — no new code.
- **1:1 (cascade broken).** The `dilute` rule fires ONLY on adjacent WATER
  (`acid.py:96-98`: `if nb == ElementId.WATER ...`). STEAM ≠ WATER, so the
  surrounding acid pool no longer dilutes into the reaction product. One base
  neutralizes ~one acid cell; the steam rises away (open top) / condenses
  elsewhere; the pool persists. The headline regression test in Phase 01 proves
  it.

## Phase List

| # | Phase | Complexity | Depends On | Agent |
|---|-------|------------|------------|-------|
| 1 | Neutralize-to-steam (the branch edit in acid.py + base.py + tests, incl. the 1:1 pool-persists regression) | S | none | @implementer |

(One phase. The change is ~10 lines of rule code + 3 lines of import/constant,
mirrored across two files, plus test updates. Small and atomic.)

## Dependency Map

- Phase 1 depends on the already-shipped `new-elements/01` (acid/base exist,
  `seed_steam_life` exists in `_common.py:62`, the steam rule + its
  condense→WATER path exist in `steam.py:40-42`). No other in-flight work.
- Nothing else is in flight; this can run now.

## Decision Log

1. **Scope A (quick steam-fix), not Scope B (concentration system).** The user
   approved the minimal change: produce STEAM from neutralization and let the
   existing steam→water path finish the job. It fixes BOTH reported symptoms
   (no steam; not 1:1) for ~10 lines. Scope B (per-cell concentration field,
   diffusion-based mixing, dissolution-scaled-by-concentration, stoichiometric
   neutralization, a mixing heatmap) is a ~3-phase thermal-scale chemistry
   layer — genuinely deferred (see BACKLOG). Alternatives considered:
   - *Lower `DILUTE_CHANCE` / gate dilute on a "just-neutralized" flag.* Treats
     the cascade symptom, not the cause; leaves neutralization cold (no steam).
     Rejected — doesn't fix symptom #1.
   - *Produce one STEAM + one WATER (asymmetric).* Half-measure; still leaves a
     WATER cell adjacent to acid → local dilution. Rejected for cleanliness; the
     symmetric STEAM+STEAM write is also idempotent (Decision #3).

2. **Scope B (concentration/mixing) DEFERRED → BACKLOG.** Records the user's
   two deferred notes ("diluted acid indistinguishable from water" + "mixing
   heatmap"). It is the proper fix for dilution realism and is tracked as a
   Tier-2 entry citing this plan. Do NOT implement here.

3. **Symmetric STEAM+STEAM write keeps neutralization idempotent / scan-order
   safe.** Both rules perform the IDENTICAL write (self→STEAM, neighbor→STEAM,
   same life seed, same `NEUTRALIZE_TEMP`). Whichever rule scans first leaves
   both cells STEAM; the second rule then sees STEAM (a no-op for the
   neutralize check, which keys on BASE/ACID). Same property the WATER+WATER
   write had (`new-elements/01-acid-base-reflection.md:68-75`); preserved here.

4. **`NEUTRALIZE_TEMP = 150`, duplicated as a module constant in BOTH files.**
   Mirrors how `DISSOLVE_CHANCE`/`DILUTE_CHANCE`/`DISSOLVE_SMOKE_CHANCE` are
   already duplicated across `acid.py` and `base.py` (the reflection at
   `new-elements/01-acid-base-reflection.md:42-46` pins this "each rule file
   owns its knobs" convention). 150 is a starting value: hot (> ambient steam
   `temp_spawn` 120 at `elements.py:218`, well above `condense_point` 60), so
   the steam visibly persists before condensing. Pin the final tuned value in
   the reflection. If acid/base ever need different neutralization heats, the
   constants are independent.

5. **Reuse `seed_steam_life()`, do not invent a new lifetime.** Steam is a
   finite gas; `_common.py:62-72` already canonicalizes its lifetime window
   (80–160 steps) for both the lava+water reaction and the brush. Going through
   it keeps reaction-spawned and painted steam identical (the same contract
   `seed_*_life` exists to enforce).

6. **No `grid.set` semantics change.** The fix works *with* `set`'s
   "element-id-only" contract by explicitly calling `set_life` + `set_temp`
   after it (see the mandatory-calls note above). We do NOT modify `grid.py`.

## Estimated Complexity

- Phase 1: **S** — ~10 lines of rule code × 2 files + import/constant + test
  updates + one new regression test. All within the acid/base domain; no enum,
  LUT, config, or registry changes.

## Risks & Unknowns

- **Trapped steam (edge case, accepted).** If the neutralized steam CANNOT rise
  (a sealed box above the reaction), it condenses in place near the acid →
  WATER → local dilution of the immediately-adjacent acid. This is the same
  "cascade" resurfacing, but only in sealed containers and only locally (one or
  two cells, not the whole pool). Acceptable; document in the reflection. The
  1:1 regression test uses an OPEN top so steam escapes — that is the realistic
  case.
- **`NEUTRALIZE_TEMP` tuning.** 150 is a first guess (hot, > condense_point 60,
  > ambient steam spawn 120). If the steam condenses too fast (barely visible)
  or lingers too long (floods the scene), bump it. Pin final in reflection.
- **Behavior change to neutralization → existing tests must flip.** The old
  `test_acid_base_neutralize_both_become_water` (`tests/test_acid_base.py:164-178`)
  asserts WATER on both cells. It flips to STEAM. This is NOT a weakening — the
  spec changed (acid+base → STEAM, then steam → WATER via the existing rule).
- **"Neutralized steam condenses to WATER" test is empirical.** How fast 150 °C
  steam cools below 60 (via diffusion to ambient neighbors, conductivity 0.25)
  is not pre-computed; the condense test (Phase 01) traps the steam under a
  solid cap so it reliably cools in place rather than escaping the grid, and
  the step count is verified at implementation time.

## Verification Philosophy

Every gate must exit zero. The headline proof is the **1:1 pool-persists
regression test** (Phase 01): one base cell dropped into a ~19-cell acid pool,
after 60–120 steps, MOST of the acid REMAINS (assert acid count ≥ ~10; the old
behavior cleared it to 0). That single test is what demonstrates the cascade is
broken. The flipped neutralize test (both cells → STEAM) proves the exothermic
half. The full suite (205+ tests) is the regression guard that nothing else
broke. The SDL smoke is the human check that a dropped base produces a small
steam puff (not the whole pool clearing).

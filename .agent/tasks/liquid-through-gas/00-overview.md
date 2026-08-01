# Task Plan: Liquid/Powder through Gas — the complement of gas buoyancy

> **Small physics fix**, the symmetric twin of the just-shipped
> `gas-buoyancy/` plan. Same domain/voice. A single behavior-correctness
> ticket for the `can_displace` predicate.

## Problem Statement

Liquids (WATER / LAVA / ACID / BASE / OIL) and powders (SAND / GUNPOWDER)
cannot move **into a gas cell**. `can_displace` (`rules/_common.py:40-52`)
returns True only for EMPTY or a strictly-lighter **LIQUID** — gases are not
displacable:

```python
# rules/_common.py:48-52 (current)
if target_id == ElementId.EMPTY:
    return True
src = ELEMENTS[src_id]
target = ELEMENTS[ElementId(target_id)]
return target.phase == Phase.LIQUID and target.density < src.density
```

So a column of WATER beside / above a column of STEAM (or SMOKE / FIRE) just
sits there — the water cannot enter the steam cell. User report:

> *"I can create a wall of steam and it blocks flowing water. Water should
> flow through it (while still allowing the steam to rise through the
> water)."*

This is the **missing complement** of the buoyancy fix that just shipped
(`is_riseable` at `_common.py:55-63`: a GAS rises through a LIQUID). The two
directions should be **symmetric**: the denser phase displaces the lighter
one in BOTH directions — gas rises through liquid (done) **AND** liquid /
powder flows through gas (this fix). With only `is_riseable`, the gas can
leave the liquid but the liquid cannot enter the gas, so a steam wall is a
one-way valve that still traps water on the wrong side.

## Solution Summary

Extend `can_displace` with one additive clause: a **LIQUID or POWDER** `src`
may displace a **GAS** `target`. Minimal change to `_common.py:48-52`:

```python
if target_id == ElementId.EMPTY:
    return True
src = ELEMENTS[src_id]
target = ELEMENTS[ElementId(target_id)]
# (existing) a denser liquid/powder sinks through a strictly-lighter liquid.
if target.phase == Phase.LIQUID and target.density < src.density:
    return True
# (NEW) a liquid or powder flows through a gas -- the complement of
# is_riseable (gas rises through liquid). E.g. water flows through a steam
# wall; sand falls through steam. EMPTY is Phase.GAS but is already caught by
# the first check, so this only reaches FIRE / SMOKE / STEAM.
if target.phase == Phase.GAS and src.phase in (Phase.LIQUID, Phase.POWDER):
    return True
return False
```

Plus a docstring correction (the current docstring claims *"Solids, gases,
and same/higher-density liquids are not displacable"* — gases are now
displacable by liquids/powders) and the matching module-docstring bullet
touch-up. (`Phase` is already imported at `_common.py:30` — no new import.)

### Why it is safe / what the behavior looks like

- **Water beside a steam wall** now displaces it sideways (flows through);
  **water above steam** falls through it (down). The displaced gas is pushed
  to the water's old cell, then continues to rise next frame via
  `is_riseable` buoyancy. Both directions coexist: denser phase down/in,
  lighter phase up.
- **Same clause lets SAND / GUNPOWDER fall through gases**, and
  **LAVA / ACID / BASE / OIL flow through gases** — consistent (any denser
  phase through any gas). Generic over `Phase`, not water-specific (mirrors
  Decision #4 of the buoyancy plan).
- **EMPTY is `Phase.GAS`** but is already caught by the first
  `if target_id == EMPTY` check, so the new clause only ever reaches
  **FIRE / SMOKE / STEAM** — no change to EMPTY handling.
- **Symmetry with `is_riseable` is now complete.** For a gas/liquid pair the
  swap is reached from whichever side the scan visits first: bottom→top scan
  (`simulation.py:131`) visits the lower cell first, so a gas below a liquid
  rises into it (`is_riseable`); a liquid below a gas sinks into it
  (`can_displace`). Either path produces the identical swap — the two
  predicates agree on the outcome, so there is no order-dependent conflict.
- **Dormancy**: a liquid/powder moving into a gas is a swap (movement) → the
  existing `moved` / `id_changed` wake conditions fire → no `simulation.py`
  change.
- **The swap carries temp + life correctly** (`_common.swap` → `Grid.move`,
  the raw 3-array element swap), so a steam cell keeps its heat/life when it
  is shoved aside, and a water cell keeps its temp when it flows through.

### Edge case (documented, not a blocker)

The same clause also lets a liquid **displace FIRE** (a GAS): water shoves
fire aside rather than dousing it, because there is **no fire+water
extinguish mechanic yet**. This is acceptable for v1 and is recorded under
Out of Scope (a real extinguish is a separate feature). An optional test
locks the CURRENT shove behavior so a later extinguish feature changes it
deliberately; the test is optional because the FIRE-cell heat can boil an
adjacent water cell mid-step (diffusion pre-pass), making the assertion
fragile without careful temp isolation.

## Phase List

| # | Phase | Complexity | Depends On | Agent |
|---|-------|------------|------------|-------|
| 1 | Liquid/powder displaces gas (`_common.can_displace` clause + docstrings + tests, incl. repurposing one now-conflicted buoyancy test) | S | none | @implementer |

(One phase. The change is one additive `if` clause + a `return True` in
`_common.py`, two docstring touch-ups in the same file, a few new tests in
the existing `test_gas_buoyancy.py` (reusing its `_warm_all` / `_WARM`
helpers), and a repurpose of one existing drift test whose water-flanks now
shove the steam. Small and atomic.)

## Dependency Map

- Phase 1 depends on the already-shipped buoyancy helper `is_riseable`
  (`_common.py:55-63`) and its `_LIQUID_IDS` frozenset (`_common.py:33-37`),
  the gas rules (`steam.py` / `smoke.py`), `can_displace` itself
  (`_common.py:40-52`), and `elements.py` (`Phase` membership: GAS = EMPTY /
  FIRE / SMOKE / STEAM; LIQUID = WATER / LAVA / ACID / BASE / OIL; POWDER =
  SAND / GUNPOWDER). No other in-flight work.
- Nothing else is in flight; this can run now.

## Decision Log

1. **One additive clause in `can_displace`, not a new helper.** The buoyancy
   fix added a *separate* `is_riseable` helper because the gas rise steps
   needed a self-contained predicate to drop into `steam.py` / `smoke.py`.
   Here the call sites already go through `can_displace` (water / sand /
   lava / acid / base / oil / gunpowder — every liquid and powder rule), so
   extending `can_displace` is the single seam that fixes all of them at
   once. Adding a parallel `_can_flow_through_gas` helper and re-routing
   every rule through it would duplicate `can_displace`'s job for no gain.
   Alternatives considered:
   - *A new shared helper.* Rejected — `can_displace` is already the
     "may a cell move into another" predicate; the gas case belongs inside
     it alongside the EMPTY and lighter-liquid cases.

2. **LIQUID or POWDER through GAS; exclude SOLID and GAS sources.** A solid
   does not move (no rule calls `can_displace` for it), and a gas displacing
   another gas is gas-gas mixing — explicitly out of scope for v1 (mirrors
   the buoyancy plan's Decision #1 / Out of Scope). The clause guards with
   `src.phase in (Phase.LIQUID, Phase.POWDER)` so a notional solid/gas
   source returns False by construction.

3. **No density comparison for the gas case.** Every liquid (lightest OIL
   0.8) and every powder (1.5) is denser than every gas (heaviest FIRE 0.1),
   so any denser phase sinks/flows through any gas unconditionally — a plain
   phase check suffices. This deliberately differs from the
   lighter-LIQUID case (which DOES compare densities, e.g. water 1.0 through
   oil 0.8). Mirrors buoyancy plan Decision #4.

4. **EMPTY caught first, not by the gas clause.** EMPTY is `Phase.GAS`, so
   the gas clause *would* match EMPTY if reached — but the first
   `if target_id == ElementId.EMPTY: return True` short-circuits before it.
   This keeps EMPTY handling byte-identical (no behavioral change to any
   existing fall/flow path that targets EMPTY) and means the new clause only
   ever evaluates FIRE / SMOKE / STEAM. Called out in the code comment.

5. **Repurpose `test_drift_does_not_go_sideways_through_liquid` to flank
   with STONE, not WATER.** Trace analysis (bottom→top scan,
   `simulation.py:131`) shows this existing test BREAKS under the fix: the
   flanking WATER cells shove the boxed STEAM sideways
   (`can_displace(WATER, STEAM)` becomes True), so the steam no longer
   "stays put." That shove is the *new correct* liquid-through-gas behavior,
   not drift. The test's actual invariant — **drift is EMPTY-only** — holds
   for any non-EMPTY target identically (drift does not distinguish liquid
   from solid), so flanking with STONE preserves the drift lock without
   colliding with the new shove behavior. The shove itself is covered by the
   NEW tests. Alternatives considered:
   - *Keep water flanks, assert the shove.* Rejected as the drift test — it
     would no longer test drift; the shove belongs in its own named test.

## Estimated Complexity

- Phase 1: **S** — one `if … return True` clause + restructured final
  `return` in `can_displace`, two docstring touch-ups in `_common.py`, three
  new tests (water-through-steam sideways, water-through-steam down,
  sand-through-steam) + one optional fire-edge test in the existing
  `test_gas_buoyancy.py`, and a repurpose of one existing drift test. No
  enum, LUT, config, registry, rule-file, or `simulation.py` changes.

## Risks & Unknowns

- **One existing test breaks by design** —
  `test_drift_does_not_go_sideways_through_liquid`
  (`tests/test_gas_buoyancy.py:172-202`): its water-flank cells shove the
  boxed steam once gases become displacable (verified by trace against the
  bottom→top scan order). Phase 1 repurposes it to stone flanks (Decision
  #5). This is the ONLY expected break; the implementer confirms the rest of
  `test_gas_buoyancy.py` stays green by trace + run.
- **Other buoyancy tests stay green** (verified by trace): the bottom→top
  scan visits the lower gas before the liquid above it, so a gas below a
  liquid rises via `is_riseable` and the liquid-above never gets a chance to
  shove it; the outcome is identical pre- and post-fix. Flag
  `test_steam_rises_to_surface_of_water_pool` (multi-step) for an explicit
  run in the reflection.
- **Fire-displacement edge** — water shoves FIRE aside (no extinguish yet).
  Documented in the reflection; an optional test locks the current behavior.
  Not a blocker.
- **Perf**: negligible — one extra `if` (a phase-int compare) in
  `can_displace`, which is already a hot-path predicate.
- **Symmetry / order-independence**: for a gas/liquid pair both predicates
  produce the same swap, so scan order and per-row x-randomization cannot
  produce a conflicting result. The three new tests are asserted to be
  robust to both (seeded, but the outcome holds unseeded).

## Verification Philosophy

Every gate must exit zero. The headline proofs are the three new
single-step tests in Phase 1: **water flows through a steam wall sideways**,
**water falls through steam**, and **sand falls through steam** — each a
literal one-swap assertion (denser phase enters the gas's old cell, gas is
pushed to the source's old cell). The **buoyancy regression** is locked by
the existing `test_steam_rises_through_water` / `test_smoke_rises_through_water`
/ `test_steam_rises_through_oil`, which MUST stay green unchanged. The full
suite is the regression guard (no other test relied on gases being
impassable — confirmed by trace). The SDL smoke is the human check that a
steam wall no longer dams flowing water.

## Out of Scope

- **Fire + water extinguish mechanic.** Water should *douse* fire (consume
  it), not merely shove it aside. Separate feature; recorded here. The
  optional fire-edge test in Phase 1 locks the CURRENT shove behavior so the
  future extinguish changes it deliberately.
- **Gas-gas displacement** (steam displacing smoke, or a gas shoving another
  gas). Not modeled in v1; the clause's `src.phase in (LIQUID, POWDER)`
  guard returns False for gas sources by construction.
- **Solids displacing gases.** Solids do not move (no rule calls
  `can_displace` for a SOLID source), so this is N/A; the guard excludes it
  anyway.

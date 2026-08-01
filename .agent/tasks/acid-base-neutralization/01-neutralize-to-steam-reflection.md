# Reflection — Phase 01: Neutralize-to-steam (+ dilute-cascade fix)

> **Status: COMPLETE.** All six verification gates green. No git operations
> performed (changes left unstaged per the task's hard constraints).

## Summary of what shipped

The acid+base neutralization now produces **hot STEAM** (not WATER), and the
**autocatalytic `dilute` step was removed entirely** from both rules. Together
these deliver the user's two goals: exothermic neutralization (visible steam →
water) and ~1:1 stoichiometry (one base no longer clears a whole acid pool).

Final measured result (the headline): **ONE base dropped into a 20-cell acid
pool → ACID stays at 19/20 after 100 steps**, stable across 8 seeds. Pre-fix
this was 0 (the whole pool collapsed to water).

## What was difficult / unexpected (read this before touching acid/base again)

This phase took **three iterations** to land, because the original plan's
central premise was empirically wrong. Recording the full chain so the next
agent doesn't repeat it:

### Iteration 1 — neutralize → STEAM only (the plan as written)
Implemented exactly per spec: acid+base → both STEAM @150°C, seeded life,
`set_temp`. The neutralization itself worked (verified: ACID 20→19 at step 1,
STEAM appears at 150°C). **But the headline 1:1 test failed (acid 20→0).**

Root cause (measured, indexing-agnostic via `get_temp`): the reaction produces
one steam cell **inside the pool** (the former acid cell is surrounded by acid).
That steam cooled **150→29°C in a single step** (thermal diffusion into the
20°C acid neighbors), already below `condense_point` (60) → condensed to WATER
next to the pool → re-ignited the dilute cascade → ACID 19→0 by step 40.

The plan's premise — *"STEAM ≠ WATER breaks the cascade (dilute fires only on
adjacent WATER)"* — is true **instantaneously** but **false over time**, because
STEAM→WATER locally. The plan only anticipated this for *sealed containers*;
in reality it occurs whenever the reaction is below the pool surface, and the
former-acid cell is necessarily surrounded by acid, so no geometry sidesteps
it. **Bumping `NEUTRALIZE_TEMP` (150→2000) did not help** — the steam always
eventually condenses, and condensation near the pool always reseeds the
cascade. I stopped and reported rather than weakening the test.

### Iteration 2 — dilute → EMPTY (user-approved Scope-A addition)
User approved changing the dilute outcome from WATER to EMPTY (absorbed, no new
water → cascade can't propagate). **Improved acid_after 0→2, still < 10.**

Root cause: the EMPTY fix killed the *autocatalytic explosion* (WATER count
stayed constant at 2 — no new water spawned), but those 2 water cells
**persisted and crawled** through the pool, dissolving acid at ~8%/step/contact
(`DILUTE_CHANCE`): 19→2 over 100 steps across all seeds. The water wasn't
rising out fast enough; it sat in-pool and dissolved a trail.

### Iteration 3 — remove the dilute branch entirely (user's stated fallback)
User pre-authorized this fallback: "remove the dilute branch entirely (acid+
water coexist with no reaction — acid sinks through water by density)."
Applied. **This landed 1:1: acid 20→19.** With no dilute rule there is no
cascade, full stop. The lone water cell from condensed steam simply rises out
of the pool (lighter, 1.0 < 1.2) and the pool is left intact.

**Lesson:** the dilute rule was the actual source of the pool-clearing, not the
neutralization product. The plan located the symptom (WATER product) but not
the cause (autocatalytic dilute). Fixing the cause directly was necessary and
sufficient.

## Final tuned values / decisions

- **`NEUTRALIZE_TEMP = 150`** — held (not bumped). 150 is irrelevant to the 1:1
  outcome now that dilute is gone; it only governs how hot/visible the steam
  puff is. 150 is well above `condense_point` (60) and ambient steam
  `temp_spawn` (120), giving a brief visible puff before condensing. Fine.
- **1:1 floor tightened `>= 10` → `>= 15`.** Measured post-fix is a rock-stable
  **19/20** across 8 seeds (only the single acid cell touching the base
  neutralizes). The plan explicitly authorized this tightening
  (`01-neutralize-to-steam.md:230-233`); 15 leaves a 4-cell margin while still
  failing loudly on any regression toward the cascade.
- **`DILUTE_CHANCE` constant removed** from both files (the branch is gone, so
  the constant was dead code; keeping it would have been misleading and the
  monkeypatch test referenced it). Precedence renumbered 5-step → 4-step
  (Burn / Neutralize / Dissolve / Flow) in both module docstrings and inline
  comments. A "There is intentionally NO dilute step" paragraph was added to
  each module docstring recording *why*, so a future agent doesn't re-add it
  blindly.
- **Condense test:** STONE-cap layout (3-cell cap one row above the reaction)
  + **400 steps** reliably produces WATER from the neutralized steam. Passed.
  The cap traps the steam so it cools in place rather than escaping; without it
  the steam would rise out of the 3×6 grid and expire to EMPTY, making the
  condensation non-deterministic to assert on.
- **20-seed scan-order loop** still passes (idempotency held after WATER→STEAM:
  both rules perform the identical STEAM write, so whichever scans first wins).

## Test surface (tests/test_acid_base.py)

- `test_acid_base_neutralize_both_become_water` → **renamed/flipped** to
  `..._both_become_steam`: asserts STEAM on both cells, `temp == 150`, `life > 0`.
- `test_one_base_does_not_clear_whole_acid_pool` — **NEW headline regression**
  (1:1). acid_after >= 15 (measured 19).
- `test_neutralized_steam_condenses_to_water` — **NEW** (steam → WATER via the
  existing steam rule, STONE cap, 400 steps).
- `test_acid_dilutes_into_water` → **renamed/flipped** to
  `test_acid_does_not_dilute_into_water`: asserts acid+water coexist (acid
  count == 1, water count == 1; positions may swap via the density flow).
  Flipped *twice* during this phase (WATER → EMPTY → coexist) as the fix
  iterated.

Net test count: **205 → 207** (flipped 2 existing + added 2 new; the suite
only adds, no removals).

## Scope B (DEFERRED — still in BACKLOG)

The user's two deferred notes remain out of scope and are unchanged by this
phase:

- *"diluted acid is indistinguishable from normal water"* — now **moot** in the
  short term, because there is no longer a dilute step (acid+water just
  coexist). A future Scope-B concentration system would reintroduce realistic
  dilution (concentration-scaled, diffusion-based, non-cascading) properly;
  until then the cleanest behavior is no reaction.
- *"add a mixing heatmap"* — requires the per-cell concentration field; tracked
  in BACKLOG, not implemented here.

## Six-gate results (all green)

| # | Gate | Result |
|---|------|--------|
| 1 | `uv run pytest tests/test_acid_base.py -v` | ✅ 21 passed |
| 2 | `uv run python -c "import sandfall; ... NEUTRALIZE_TEMP==150; no DILUTE_CHANCE"` | ✅ OK |
| 3 | `uv run pytest` (full) | ✅ 207 passed |
| 4 | `uv run ruff check .` | ✅ All checks passed |
| 5 | `uv run ruff format --check .` | ✅ 52 files already formatted |
| 6 | `uv run mypy src` | ✅ no issues found in 28 files |
| + | `SANDFALL_FRAMES=60 uv run sandfall` (headless, `SDL_VIDEODRIVER=dummy`) | ✅ exit 0 |

## Files changed (exactly these three)

- `src/sandfall/rules/acid.py`
- `src/sandfall/rules/base.py`
- `tests/test_acid_base.py`

(`ruff format` wrapped the `._common` import across multiple lines — the spec's
single-line form exceeded the 88-col limit once `seed_steam_life` was added.
Mechanical, not a deviation.)

## Suggestions for future work

- If realistic dilution is ever wanted back, do NOT restore the autocatalytic
  `acid + WATER → WATER` form. Use Scope B (concentration field) so dilution is
  stoichiometric and concentration-scaled, or at minimum make the water cell
  itself get consumed on contact (so it can't crawl). The crawl problem
  (iteration 2) is the trap to avoid.
- The neutralize→STEAM write is symmetric/idempotent but produces steam one
  cell *inside* any pool it occurs in. If a visible rising plume is desired
  (rather than a brief in-place puff that condenses fast), consider warming a
  small neighborhood or seeding the steam at a higher temp — but that's
  cosmetic, not functional, and `NEUTRALIZE_TEMP=150` is acceptable for v1.

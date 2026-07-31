# Sandfall Thermal Conservation Fix — Master Plan

## Problem Statement

The thermal model shipped under `.agent/tasks/sandfall-temperature/` has **three
compounding bugs in `thermal.diffuse_temps`** (`src/sandfall/thermal.py:65-101`)
that, together, make heat and cold annihilate at material boundaries and make
hot cells equilibrate far too fast. The user-visible symptoms that surfaced this
were "lava cools down too quickly" and "ice spreads cold very far." All three
bugs were empirically isolated with standalone prototypes; the numbers below are
the measured reproductions.

1. **Non-conservative diffusion (the worst one).** The current update
   (`thermal.py:76, 98`):
   ```python
   new = temp + rate * cond[cell] * (left+right+up+down - 4*temp)
   ```
   weights each cell's move toward its neighbors by the cell's **OWN**
   conductivity. When two adjacent materials have different conductivity, the
   flux leaving the hot cell is NOT the flux entering the cold cell, so total
   heat is not conserved. **Measured:**
   - A single FIRE cell (cond 0.50) in air **lost 897 of 1380 heat units over
     60 steps.**
   - A 3-cell ICE block at −5° in a 25-cell row **drained total heat from 425
     to 0** (a conserved average would be ~17°). Heat and cold are annihilated
     at material boundaries — exactly the "ice spreads cold very far" symptom.

2. **`int16` truncation drains heat.** `diffuse_temps` casts the float result to
   `int16` with truncation-toward-zero (`thermal.py:101`), which biases every
   cell toward 0 every step. **Measured:** even a uniform-air field lost 219 of
   1380 over 60 steps; once the conservative fix (#1) is applied, truncation is
   what drives the ice scenario 410→0. Fix: round-to-nearest (`np.rint`) —
   measured drain drops to ~10/410. (Float storage was ~1/410 but unnecessary;
   `int16` storage is kept.)

3. **No heat capacity (thermal inertia).** There is no concept of thermal mass.
   A lava cell equilibrates with cold air at ~326°/step and solidifies (~700°)
   in ~3 steps, so lava has no persistence; dually, water heats instantly. Fix:
   a per-material **heat capacity** that divides the temperature change (high cp
   = changes slowly = thermally massive).

## Solution Summary

A **single focused fix phase** that rewrites `diffuse_temps` to a
**conservative face-flux discretization** with per-cell heat capacity and
round-to-nearest, and threads a `cp_lut` (mirroring the existing `cond_lut`)
through the one caller and the tests. No new phases, no new elements, no new
mechanics — this is a correctness repair of the existing thermal field.

- **Phase 01 — Conservative diffusion + heat capacity.** Rewrite
  `diffuse_temps(temp, ids, cond_lut, rate)` →
  `diffuse_temps(temp, ids, cond_lut, cp_lut, rate)` to a face-flux form: face
  conductivity is the arithmetic mean of the two cells sharing each face; net
  heat into each cell sums signed face fluxes (which telescope to zero →
  conservation); the temperature change is `div / cp` (heat capacity → thermal
  inertia); result is `np.rint`-rounded (NOT truncated) to `int16`. Add a
  `heat_capacity: float = 1.0` field to `Element` (defaulted so existing entries
  still construct), a `CP_*` constant block in `config.py` mirroring `COND_*`,
  and a `build_heat_capacity_lut()` in `thermal.py` mirroring
  `build_conductivity_lut()`. Cache `self._cp_lut` in `Simulation.__init__`
  alongside `self._cond_lut`; pass both to `diffuse_temps` in `Simulation.step`.
  Update the existing diffusion-math tests for the new formula and ADD the key
  regression guard `test_diffusion_conserves_total_heat`. **This is the only
  phase.**

**Prototype validation results (cite these as the target behavior):**
- **Conservation:** 3 ice @ −5 in 25×1 air: heat 410 → 400 over 60 steps (vs
  410 → 0 today).
- **Lava persistence:** a pinned lava cell (cp=5) solidifies at step ~27 (cp=3
  → ~14, cp=1 → ~4). **Recommend cp=5 for lava.**
- **Ice cold localized:** a 3×3 ice block in 21×21 air cools only ~4-5 cells
  around it after 40 steps (far field stays at ambient), vs the whole grid
  collapsing to 0 today.

## Phase List

| #  | Phase                                            | Cx | Depends On | Parallelizable With |
|----|--------------------------------------------------|----|------------|---------------------|
| 01 | Conservative diffusion + heat capacity (the fix) | M  | —          | —                   |

## Dependency Map

```
01 (conservative diffusion + heat capacity) ──► done
```

Single phase — no parallelization question. The change touches the conductivity
LUT, the cp LUT, the diffusion kernel, the one caller, and the diffusion tests
in one coherent atomic commit because the signature change
(`+cp_lut` parameter) and the formula change must land together or the build
breaks. Splitting would create a non-compiling intermediate state.

## Decision Log

All decisions below are **user-approved** and must not be re-litigated. The
phrasing "user-approved" is taken from the prompt that authorized this plan.

1. **Core fix only — defer the ambient thermostat (Newton's-law-of-cooling
   drift toward `AMBIENT_TEMP`).** The user was offered an ambient drift term
   and declined. The grid stays a **closed, insulated, energy-conserving**
   system: walls are insulators (no edge flux), and there is no term pulling
   cells toward ambient. Do NOT add ambient drift. *(Accepted consequence,
   documented in Risks: because the walls are insulated, fire's per-step
   burn-temp re-assertion injects heat that will slowly accumulate over a very
   long session — the ambient thermostat is the documented future mitigation.)*
2. **Lava `cp` ≈ 5 ("Persistent cp~5").** Per-material heat capacity values:
   LAVA 5.0, WATER 4.0, ICE 2.0, STONE 2.0, SAND 1.5, WOOD 1.5, PLANT 1.5,
   GLASS 1.5, FIRE 0.5, SMOKE 0.5, STEAM 0.5, EMPTY (air) 1.0. Rationale:
   water/stone/lava have high thermal mass (change slowly); gases
   (fire/smoke/steam) have low mass (change fast); air is the 1.0 baseline.
   These give the measured "lava solidifies at ~step 27" persistence the user
   asked for.
3. **Round-to-nearest (`np.rint`), keep `int16` storage.** Fixes the
   truncation-toward-zero drain (bug #2) without paying for `float32`/`float64`
   storage. Measured drain drops from ~219/1380 (trunc) to ~10/410 (rint);
   float storage was ~1/410 but is unnecessary. *(Alternative considered: store
   `_temp` as `float32` — rejected: the rest of the grid is integer
   (`uint8` ids/life), the clip band fits `int16`, and the hot path stays
   integer-storage; round-to-nearest already makes the drain negligible.)*
4. **Leave the `lava.py` steam-acceptance workaround in place.** That workaround
   (`rules/lava.py:1-20` docstring + the STEAM-neighbor branch, commit
   `d65c4ab`) exists because at LAVA's 1500 spawn-temp the OLD diffusion
   pre-boiled an adjacent water cell to steam before the LAVA rule ran. With
   WATER `cp=4`, the adjacent water now heats slowly (no one-step pre-boil), so
   the workaround becomes **redundant**. **Do NOT remove it in this fix** —
   minimize blast radius; it is a harmless belt-and-suspenders safety net. Note
   its new redundancy in the Phase 01 reflection for a future cleanup.
5. **Face-flux (finite-volume) discretization, arithmetic-mean face
   conductivity.** Each interior face carries a signed flux `k_face * rate *
   (t_left − t_right)` where `k_face = (k_left + k_right) / 2`. Net heat into a
   cell sums its four signed face fluxes; this sum telescopes to exactly zero
   over the grid, so `sum(cp * temp)` is conserved up to rounding/clip. Chosen
   over the alternative (harmonic-mean face conductivity, the physically
   "correct" series-resistor form) because arithmetic mean is simpler, is what
   the validated prototype used, and the prototype numbers above are what we are
   pinning as the target. *(Alternative considered: harmonic mean — rejected for
   this fix: changes the calibrated numbers; can be revisited if an insulator
   sandwich turns out to leak too fast in play.)*
6. **Heat capacity lives in `config.CP_*` AND on `Element.heat_capacity`.**
   Mirrors the existing `COND_*` / `Element.conductivity` split exactly: the LUT
   builder reads `config.CP_*` (one place to tune); `Element.heat_capacity`
   (default 1.0) is the registry datum a contributor edits when adding a
   material. The `Element` field is **defaulted** so every existing `ELEMENTS`
   entry still constructs without spelling it out.

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | M  | One numerically-careful kernel rewrite (face-flux + cp + rint) + a new `Element` field rippling through a frozen dataclass + a new `CP_*` config block + a new `build_heat_capacity_lut` mirroring the conductivity one + a one-line caller change + a one-line `__init__` cache + a signature change rippling to all diffusion tests + one new conservation regression test + one new LUT test. Small surface area, but the numerics are subtle and the conservation test is the whole point. |

## Risks & Unknowns

1. **Stability bound CHANGES.** The old explicit stencil was stable when
   `rate * max(cond) <= 0.25` (documented at `config.py:91-93`,
   `thermal.py:82-83`, and the test at `tests/test_thermal.py:59-68`). The new
   face-flux form reduces to standard explicit diffusion with coefficient
   `rate * k / cp`, so the stability bound is **`rate * max(cond) / min(cp) <=
   0.25`**. With the chosen defaults: `0.20 * 0.50 (FIRE) / 0.5 (FIRE/SMOKE/STEAM)
   = 0.20 <= 0.25` — comfortable. This is the tightest cell (highest cond AND
   lowest cp coincide on FIRE). The old bound and its stale comment + the old
   `test_no_overshoot_at_stability_bound` test MUST be replaced (see Phase 01).
2. **Behavior ripples in existing fire/lava tests (re-verify, do NOT
   pre-emptively change).**
   - `tests/test_fire.py:111-133` `test_fire_next_to_wood_eventually_ignites_it`
     — fire still heats wood via diffusion (conservatively now); may ignite at a
     different step but within the 400-step budget. Re-tune ONLY if it fails.
   - `tests/test_phase.py:171-204+`
     `test_lava_water_reaction_is_deterministic_across_scan_orders` — with
     WATER cp=4 the adjacent water no longer pre-boils in one step, so the LAVA
     rule's reaction fires cleanly. Re-verify it still passes at
     `LAVA.temp_spawn` (1500). (The `lava.py` steam-acceptance workaround
     remains as a safety net — see Decision Log #4.)
   - Lava solidify timing changes to ~27 steps for a single cell — this is the
     DESIRED improvement, not a regression.
3. **Long-term heat accumulation in a closed system.** Because the grid is
   insulated (no edge flux, no ambient drift — Decision Log #1), any ongoing
   heat source (fire re-asserts its burn_temp every step) injects net heat that
   cannot leave. Over a very long session the grid slowly warms. Accepted as a
   known consequence of "core fix only"; the ambient thermostat (Newton's law
   of cooling) is the documented future mitigation.
4. **`mypy` strict on the new cp LUT + the new `Element` field.** Annotate
   `build_heat_capacity_lut() -> npt.NDArray[np.float64]` (mirror the
   conductivity builder). The new `Element.heat_capacity: float = 1.0` field
   must come AFTER all existing defaulted fields in the dataclass (dataclass
   field-ordering rule: defaulted after non-defaulted) — placing it adjacent to
   `conductivity` (currently `elements.py:81`) is the natural spot and satisfies
   the ordering constraint since `conductivity` is already defaulted.
5. **The `cp` divisor must never be zero.** All chosen `CP_*` values are ≥ 0.5,
   and the default is 1.0, so `div / cp` is always finite. No guard needed, but
   the Phase 01 instructions add a one-line assertion-style comment that every
   `CP_*` is > 0 so a future contributor doesn't introduce a divide-by-zero.
6. **Line numbers in this plan are current as of the
   `sandfall-temperature`-complete source** (verified at planning time by
   reading every file cited). The implementer must re-read each file before
   editing rather than blind-applying line numbers — this fix edits the same
   files that may have drifted since.

## Verification Philosophy (applies to the phase)

The phase's `Verification Commands` block includes these six gates, and ALL must
exit zero before the phase is considered done:

```bash
uv run pytest tests/test_thermal.py -v            # phase-focused (incl. new conservation test)
uv run python -c "import sandfall"
uv run pytest                                     # full suite — re-verifies fire/phase/lava ripples
uv run ruff check .
uv run ruff format --check .
uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall                # SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy)
```

After the phase, the implementer MUST write
`01-conservative-diffusion-reflection.md` in this directory capturing: what was
difficult/unexpected, deviations from the plan + why, the re-verification
outcome of the fire/lava ripple tests (did they pass as-is, or need a re-tune,
and to what), the now-redundant `lava.py` workaround status, and anything fun
discovered. The phase is ONE atomic git commit.

## Out of Scope (Future Work — DO NOT plan now)

- **Ambient thermostat / Newton's-law-of-cooling drift toward `AMBIENT_TEMP`.**
  The user declined this; the grid stays a closed, insulated,
  energy-conserving system. Do NOT add ambient drift. (Mitigates Risk #3 if
  ever added later.)
- **Removing the `lava.py` steam-acceptance workaround** (`rules/lava.py:1-20`
  + STEAM-neighbor branch, commit `d65c4ab`). It is now redundant but harmless;
  leave it to minimize blast radius. Tracked for a future cleanup.
- **Harmonic-mean face conductivity** (physically "correct" series-resistor
  form for insulator sandwiches). Arithmetic mean is what the calibrated
  prototype used; revisit only if play shows insulators leaking too fast.
- **Changing `flammability` or any phase-transition thresholds** beyond what
  re-verification of the fire/lava ripple tests requires.
- **Per-element conductivity tuning.** The `COND_*` values are unchanged by
  this fix; only `CP_*` is new.

## Foundation Reference

This plan fixes a defect in the model built under
`.agent/tasks/sandfall-temperature/`. For architecture context, read:
- `.agent/tasks/sandfall-temperature/00-overview.md` — the original phase plan
  (the `_temp` array consistency contract, the diffusion pre-pass placement,
  the conductivity-LUT pattern this fix extends with a cp LUT).
- `.agent/tasks/sandfall-temperature/01-thermal-data-model.md` — the phase that
  introduced `diffuse_temps` and `build_conductivity_lut` (the exact functions
  this fix rewrites/mirrors).
- `src/sandfall/thermal.py`, `src/sandfall/elements.py`, `src/sandfall/config.py`,
  `src/sandfall/simulation.py`, `tests/test_thermal.py` — the exact code this
  fix edits. Re-read before editing; line numbers shift.

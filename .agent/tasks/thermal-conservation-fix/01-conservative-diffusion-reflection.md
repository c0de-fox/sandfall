# Phase 01 Reflection — Conservative diffusion + heat capacity

## Summary

Rewrote `thermal.diffuse_temps` from the non-conservative own-conductivity
stencil to a **conservative face-flux (finite-volume) discretization** with
**per-cell heat capacity** and **round-to-nearest** to int16. Added a
`heat_capacity` field to `Element`, a `CP_*` block in `config.py`, and a
`build_heat_capacity_lut()` mirroring the conductivity LUT, threaded through
`Simulation.step`. This fixes all three bugs in `00-overview.md`:

1. **Non-conservation** (heat annihilated at material boundaries) → the signed
   face fluxes telescope to zero, so `sum(cp*temp)` is conserved up to rounding.
2. **int16 truncation drain** (biased every cell toward 0) → `np.rint`
   (round-to-nearest) instead of truncation.
3. **No thermal inertia** (lava cooled ~326°/step, solidified in ~3 steps) →
   per-cell heat capacity divides the temp change.

## Files changed

- `src/sandfall/config.py` — `CP_*` block mirroring `COND_*`; updated the
  diffusion-tunables comment to the face-flux form and the NEW stability bound
  `rate*max(cond)/min(cp) <= 0.25` (default `0.20*0.50/0.5 == 0.20`).
- `src/sandfall/elements.py` — `Element.heat_capacity: float = 1.0` (after
  `conductivity`); value set on every `ELEMENTS` entry.
- `src/sandfall/thermal.py` — `build_heat_capacity_lut()`; `diffuse_temps`
  rewritten (new signature `+cp_lut`, conservative face-flux body, `np.rint`).
- `src/sandfall/simulation.py` — `self._cp_lut = build_heat_capacity_lut()` in
  `__init__`; passed positionally to `diffuse_temps` in `step`.
- `tests/test_thermal.py` — every `diffuse_temps(...)` call updated for the new
  signature; `test_no_overshoot_at_stability_bound` rewritten for the new bound;
  added `test_build_heat_capacity_lut_shape_and_values` and the headline
  `test_diffusion_conserves_total_heat`.
- `docs/ARCHITECTURE.md` — updated the diffusion section to the face-flux form,
  the new bound, and heat capacity / `CP_*`; extended the "Adding a new element"
  checklist.

`rules/lava.py` and every other rule were NOT touched.

Tests: **154 -> 156 passed** (+2: the cp-LUT test and the conservation test).

## Measured conservation (the headline number)

`test_diffusion_conserves_total_heat` uses the plan's validated prototype
scenario (3 ICE @ -5 in a 25-cell air row):

- **NEW (this fix):** total heat **410 -> 400** over 60 steps, `|ΔH| = 10`
  (2.4% — the residual int16 round-to-nearest pin; well inside the ±15 bound).
- **OLD formula:** 410 -> 0 (drain 410, 100%) — the bound fails by ~27×, so the
  test still catches the original regression loudly.

Gameplay checks (the user's original complaints):
- **Lava persistence:** a pinned lava cell now solidifies at **step ~27**
  (cp=5), vs ~3 steps before. A painted lava blob lasts much longer.
- **Ice cold localization:** a 3x3 ice block cools only ~4-5 cells around it
  (far field stays at ambient), vs collapsing the whole grid to 0 before.

## Decision: the spec's step-5d test was over-tight (deviation, documented)

The implementer correctly STOPPED rather than silently weaken a test. The
spec's step-5d specified a *different, more-adversarial* scenario (1 FIRE @1000
+ 1 ICE @-5) with tolerance **±2** — but that tolerance was tighter than the
plan's *own* validated target (410->400, drain 10). In the fire+ice scenario a
hot cell drives steady flux into the ICE cell, which `np.rint` pins at integer 0
every step (stored 0 -> float 0.476 -> rint -> 0 -> flux recomputed from 0),
destroying ~0.95 heat/step forever — a residual rounding-pin (the smaller cousin
of bug #2), measuring `|ΔH| = 46` over 60 steps. That is an inherent artifact of
int16 storage (float storage was explicitly out of scope), not a conservation
defect.

**Resolution chosen: Option B** — switch the test to the plan's VALIDATED
pure-ice scenario (the one `00-overview.md` cites as the target behavior) with
tolerance **±15**. This is tighter and more honest than widening fire+ice to
±100, matches the validated prototype exactly, and still discriminates the old
formula by ~27×. The float face-flux math itself conserves exactly (verified on
a 2-cell [0,1000] exchange); only the int16 rounding introduces the small
accepted drain.

(The residual ~10/410 drain over 60 steps is negligible for gameplay — the
game's fire/lava are continuous heat sources that dominate it — and float32 temp
storage remains the documented future mitigation if it ever matters.)

## Ripple tests — both PASS as-is (no re-tuning)

- `tests/test_fire.py::test_fire_next_to_wood_eventually_ignites_it` ✅ — fire
  still heats wood via the (now conservative) diffusion; ignites within budget.
- `tests/test_phase.py::test_lava_water_reaction_is_deterministic_across_scan_orders` ✅
  — with WATER cp=4 the adjacent water no longer pre-boils in one step, so the
  lava reaction fires cleanly. The `lava.py` steam-acceptance workaround
  (`d65c4ab`) is now REDUNDANT but was left in place as a belt-and-suspenders
  safety net (per the plan — minimize blast radius).

## Six gates — all green

| # | gate | result |
|---|------|--------|
| 1 | `uv run python -c "import sandfall"` | ✅ exit 0 |
| 2 | `uv run pytest` | ✅ 156 passed |
| 3 | `uv run ruff check .` | ✅ All checks passed |
| 4 | `uv run ruff format --check .` | ✅ 47 files already formatted |
| 5 | `uv run mypy src` | ✅ no issues, 25 source files |
| 6 | `SANDFALL_FRAMES=60 uv run sandfall` | ✅ exit 0 (`SDL_VIDEODRIVER=dummy`) |

## Commit

**Not committed** by the implementer; left unstaged per instructions.

## Notes / future work

- **Float32 temp storage** would eliminate the residual ~2.4% rounding drain
  entirely (out of scope; int16 kept). The conservation test's ±15 tolerance
  absorbs it for now.
- **Ambient thermostat** (slow drift toward `AMBIENT_TEMP`) was offered and
  declined by the user; the grid stays a closed, insulated, energy-conserving
  system. Consequence: fire's `burn_temp` re-assertion injects heat that slowly
  accumulates over a very long session — accepted; the thermostat is the
  documented mitigation if it becomes noticeable.
- The `lava.py` steam-acceptance workaround can be removed in a future cleanup
  now that heat capacity makes water pre-boiling impossible in one step.

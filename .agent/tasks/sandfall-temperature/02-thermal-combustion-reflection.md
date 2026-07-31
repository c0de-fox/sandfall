# Phase 02 Reflection — Thermal combustion (fire = heat source; reactive ignition)

## Summary

Replaced fire's probabilistic per-neighbor spread with temperature-driven
combustion. A living FIRE cell now re-asserts its `burn_temp` (~800) each
step (it is a *heat source*); the Phase 01 diffusion pre-pass carries that
heat outward; and WOOD/PLANT ignite **themselves** (reactive rules) when
their own temp exceeds their `flashpoint`. `SPREAD_FACTOR` and the
neighbor-ignition loop are gone. Smoke spawn, fire's rise, and the
age/expire path are unchanged.

## Files changed

- `src/sandfall/rules/fire.py` — re-assert `>= burn_temp` each step; expire
  to `AMBIENT_TEMP`; **added the cling-to-fuel behavior** (see below);
  removed `SPREAD_FACTOR` + `_NEIGHBORS_8` ignition loop; kept
  `SMOKE_CHANCE` + smoke spawn + rise; docstring rewritten.
- `src/sandfall/rules/wood.py` — was a no-op; now reactive (ignite to FIRE
  when `get_temp > flashpoint`).
- `src/sandfall/rules/plant.py` — prepended the same thermal-ignition check
  (priority over growth); grow-near-water logic intact below it.
- `src/sandfall/elements.py` — comment-only tweak (`SPREAD_FACTOR` →
  "per-neighbor spread"). **No registry values changed**: the Phase 01
  tuning held as-is.
- `tests/test_fire.py` — replaced the probabilistic spread assertions with
  deterministic thermal ones (heat-source, ignite-above-flashpoint,
  no-ignite-below, end-to-end chaining, stone-never-ignites); kept the
  smoke + isolated-expiry tests.

Tests: **124 → 127 passed** (+3 net: removed 2 probabilistic spread tests,
added deterministic ones incl. plant ignition + below-flashpoint).

## The key deviation: fire must CLING to fuel (not in the plan)

The plan assumed diffusion alone would chain combustion. It does not, and
this was the one real surprise of the phase. Diagnosed empirically: with
fire's existing rise behavior, a fire cell next to a lone wood cell in open
air **rises away in 1-2 steps** (sidesteps via up-diagonals, then floats to
the top of the grid). The wood peaked at **54°C** and then *cooled* —
nowhere near the 300 flashpoint. No tuning of `burn_temp` / `flashpoint` /
`COND_EMPTY` / `rate` can fix this: the fire simply does not dwell long
enough for diffusion to move meaningful heat.

**Fix:** fire does not rise while it has a flammable (`flashpoint > 0`)
orthogonal neighbor — it **clings** to fuel, sustaining the heat source so
diffusion can raise the fuel to its flashpoint. Once the fuel ignites it
becomes FIRE (no longer flammable), so the fire then rises normally and the
front advances through the fuel. This matches real fire and every other
sand game's behavior, and it preserves the plan's "diffusion is the single
physical cause" design — clinging only keeps the source in place; it does
not ignite anything directly.

This is a real model addition (a new step in `update_fire` + the
`_has_flammable_neighbor` helper using the same 4-neighborhood as
diffusion, so "in reach" and "being heated" agree). Flagged here so Phase
03's lava/water transitions and the Phase 04 docs inherit it.

## Measured combustion-chain latency (tuning gate)

With the cling fix and **no value changes**, a single long-lived fire
(life 300, burn_temp 800) directly below a wood cell ignites the wood at
**step 112** (well within the 300-step fire life and the 400-step test
budget). Wood temp trajectory: 197 (step 20) → 250 (40) → 278 (80) → 294
(100) → ignites at flashpoint 300 (step 112).

## Final tuned values (pinned for Phase 03 / Phase 04 docs)

All unchanged from Phase 01 — no re-tuning was needed once the cling
behavior was added:

| Knob | Value | Where |
|---|---|---|
| `FIRE.burn_temp` | 800 | `ELEMENTS` (elements.py) |
| `FIRE.temp_spawn` | 800 | `ELEMENTS` |
| `WOOD.flashpoint` | 300 | `ELEMENTS` |
| `PLANT.flashpoint` | 250 | `ELEMENTS` |
| `DIFFUSION_RATE` | 0.20 | config.py |
| `COND_EMPTY` | 0.10 | config.py |

Stability invariant `rate * max(cond) = 0.20 * 0.50 = 0.10 ≤ 0.25` still
holds (Phase 01).

## SPREAD_FACTOR removal

`rg -n 'SPREAD_FACTOR' src tests` → exit 1 (zero references). The
`SMOKE_CHANCE` module attribute is retained so the smoke test's
`monkeypatch.setattr(fire_mod, "SMOKE_CHANCE", 1.0)` still works.

## Six gates — all green

| # | Gate | Result |
|---|------|--------|
| 1 | `uv run python -c "import sandfall"` | ✅ exit 0 |
| 2 | `uv run pytest` | ✅ 127 passed |
| 3 | `uv run ruff check .` | ✅ All checks passed |
| 4 | `uv run ruff format --check .` | ✅ 42 files already formatted |
| 5 | `uv run mypy src` | ✅ no issues, 21 files |
| 6 | `SANDFALL_FRAMES=60 uv run sandfall` | ✅ exit 0 (`SDL_VIDEODRIVER=dummy`) |

## Commit

**Not committed.** All changes left unstaged per instructions; the commit
decision is deferred to the user.

## Notes for Phase 03

- The reactive-ignition pattern (`flashpoint > 0 and get_temp > flashpoint`
  → become FIRE + seed life + set burn_temp) is now proven on two solids
  (wood, plant). Phase 03's phase transitions (water boil/freeze, sand
  melt, lava cool, steam condense) follow the same shape against
  `boil_point` / `freeze_point` / `melt_point` / `condense_point`.
- The cling mechanism is fire-specific; lava (Phase 03) is a liquid heat
  source that flows rather than rises, so it does not need an analog — but
  its heat transfer to adjacent water (the lava+water→steam+stone reaction)
  should be verified to chain within a step budget the same way.
- `_has_flammable_neighbor` lives in `fire.py`; if Phase 03 needs the same
  "is this cell flammable" predicate elsewhere, lift it to `_common.py`.

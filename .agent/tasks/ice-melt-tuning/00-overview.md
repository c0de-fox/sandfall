# Ice melt tuning: probabilistic melt (slow at ambient, instant near heat)

## Problem
Ice melts too fast at ambient temperature (~4 steps). Root cause: `ICE.temp_spawn
= 0` and `melt_point = 0`. Painted ice starts at exactly 0°C; ambient 20°C air
warms it above 0 within ~2 diffusion steps; and the melt rule (`if temp >
melt_point → WATER`) is **instant** — no thermal buffer, no latent heat of
fusion. So the ice crosses the threshold and vanishes in ~4 steps.

## Fix (user-approved: probabilistic melt)
Change the thermal melt in `rules/ice.py` from instant to **probabilistic**,
scaled by degrees above `melt_point`. Mirrors the probabilistic patterns already
used by combustion (wood/plant ignite probabilistically above flashpoint) and
acid dissolve.

```python
# --- in ice.py ---

import random                          # ADD (ice.py doesn't currently import it)

ICE_MELT_RATE = 0.003                  # ADD as a module constant (tunable)

# In update_ice, the thermal-melt branch:

# BEFORE (instant):
if grid.get_temp(x, y) > _ICE.melt_point:
    grid.set(x, y, ElementId.WATER)
    return None

# AFTER (probabilistic):
t = grid.get_temp(x, y)
if t > _ICE.melt_point:
    if random.random() < min(1.0, (t - _ICE.melt_point) * ICE_MELT_RATE):
        grid.set(x, y, ElementId.WATER)
        return None
```

**Effect at the default `ICE_MELT_RATE = 0.003`:**
- Ambient (~20°C above 0): prob = 20 × 0.003 = 0.06 → **~17 steps average**
  (was ~4). At 60 FPS that's ~0.3 seconds — the ice block visibly persists.
- Near fire/lava (~500°C above 0): prob = min(1.0, 1.5) = **instant**.
- Direct fire/lava contact melt (the fast-destroy path — FIRE neighbor → WATER,
  LAVA neighbor → STEAM) stays **unchanged** (instant, bypasses the probability).

## Files
- `src/sandfall/rules/ice.py` — add `import random`, add `ICE_MELT_RATE =
  0.003`, change the thermal-melt check to probabilistic (3 lines changed).
- `tests/test_phase.py` — `test_ice_melts_in_ambient`: the step budget (~40)
  should be fine (17-step average is well inside), but **seed `random`** for
  determinism so the test doesn't flake on an unlucky RNG streak. If flaky,
  bump to ~80 steps or `monkeypatch` `ICE_MELT_RATE` to 1.0 for a deterministic
  instant-melt test.

## Verification
```
uv run pytest tests/test_phase.py -v          # ice melts test + no regressions
uv run pytest                                  # FULL suite
uv run ruff check . && uv run ruff format --check . && uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall            # SDL smoke: paint ice, confirm ~1s persistence
```

## Context (for a future session picking this up)
- The thermal-realism rework (`.agent/tasks/thermal-realism/`) reverted ice to a
  realistic non-source that melts at >0°C. This tuning makes that melt gradual
  instead of instant, so painted ice persists visibly at room temperature before
  melting (gameplay feel). The fix is intentionally simple (probabilistic, one
  constant) rather than a full latent-heat model (which would need a per-cell
  life/melt-progress field + brush/freeze seeding — deferred).
- `ICE_MELT_RATE` is the single knob: lower = ice lasts longer at ambient;
  higher = melts faster. 0.003 is the starting value; tune after playtesting.

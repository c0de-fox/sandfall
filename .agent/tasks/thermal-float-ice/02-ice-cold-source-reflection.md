# Phase 02 Reflection — Ice as a persistent cold source

## Outcome

The freeze regression is **fixed**. An ice block placed in water now grows
(visibly) instead of melting. Built on top of Phase 01's float32 temps
(`c575ccb`), with **no** change to `simulation.py`'s wake conditions.

## Files changed

- `src/sandfall/rules/ice.py` — full rewrite: defines `ICE_COLD_TARGET = -50`
  (module constant, mirrors `LAVA_SOLIDIFY_TEMP`); `update_ice` now (a) re-asserts
  `ICE_COLD_TARGET` each step (the persistent-cold-source, mirroring fire's
  `burn_temp` re-assert) and (b) melts only via direct fire/lava contact
  (FIRE→WATER, LAVA→STEAM with warm `temp_spawn` + seeded life). The old
  `if temp > melt_point: -> WATER` thermal-melt branch is **deleted**. Module
  docstring explains the persistent-cold-source model + the temporary
  no-ambient-melt behavior.
- `src/sandfall/rules/water.py` — freeze branch now also `set_temp(x,y,
  ICE_COLD_TARGET)` so the freeze front advances the same step (no 1-frame lag).
  Imports `ICE_COLD_TARGET` from the sibling `ice` module; freeze docstring
  bullet updated.
- `tests/test_phase.py` — added the headline `test_ice_freeze_spreads_through_water`;
  reworked the deleted `test_ice_melts_to_water` into
  `test_ice_melts_to_water_via_fire_contact` + `test_ice_melts_to_steam_via_lava_contact`;
  added `test_ice_at_ambient_stays_ice` (pins the deliberate no-ambient-melt
  behavior change); updated `test_water_freezes_to_ice` to assert the new ice is
  seeded at `ICE_COLD_TARGET`. Module-level import of `ICE_COLD_TARGET` added.
- `docs/ARCHITECTURE.md` — updated two stale "ice melts above 0" claims (the
  `melt_point` field description + the "add an element" guide) to the
  persistent-cold-source + contact-melt model, with a pointer to the
  realistic-rework BACKLOG.

**Not touched** (per hard constraints): `grid.py`, `thermal.py`, `elements.py`,
`renderer.py`, `ui.py`, `brush.py`, `game.py`, float32 storage. `ICE.melt_point`
left declared in `elements.py` for the realistic-rework BACKLOG item (now unused
by the rule). **`simulation.py` unchanged** (see dormant-wake finding).

## `ICE_COLD_TARGET` shipped

**`-50`** — straight from the prototype-validated value, **no tuning needed**.
Recorded as a tunable knob in the `ice.py` docstring (colder → faster spread).
Mirrors the `LAVA_SOLIDIFY_TEMP` pattern exactly (a rule-level module constant,
not an `Element` field).

## Dormant-wake finding — the headline unknown

**The existing wake conditions are SUFFICIENT; `simulation.py` was NOT edited.**

The analysis in the overview held: the whole-grid diffusion pre-pass carries
cold from dormant ice into adjacent water → that water's temp changes → condition
2 (thermal wake, `grid._temp != temp_before`) wakes it → its freeze-check runs →
it freezes (Phase 01 float precision lets it actually cross 0) → the new ice's
identity changed → condition 1 (`id_changed` + dilate) wakes it + neighbors →
its rule re-asserts cold and the diffusion continues. The front stays alive
without ICE joining FIRE/LAVA in condition 3. Confirmed by the integration test
(`test_ice_freeze_spreads_through_water`) AND a real game-path diagnostic below.

## Measured freeze spread

**Headline test geometry** (`Grid(12,12)`, water in bottom 6 rows, 2×2 ice seed
at `(5..6, 7..8)`, `random.seed(0)`):

| steps | ice count |
|-------|-----------|
|   0   |    4 (seed) |
|  40   |    6 |
|  60   |   16 |
|  80   |   24 |
| 100   |   32 |
| 120   |   46 |
| 160   |   70 (≈ whole 72-cell pool) |

**Real game path** (`paint_brush(g, 20, 22, 3, ICE)` in a 40×30 grid with a
15-row water pool, `random.seed(1)`):

| steps | ice | water |
|-------|-----|-------|
|   0   |  29 |  571 |
|  20   |  37 |  563 |
|  40   |  49 |  551 |
|  60   |  77 |  523 |
|  80   | 101 |  499 |

The freeze spreads fast and far — comfortably more than the prototype's
1→3→5→9 (which was a single ice cell). The assertion is strict growth
(`ice_after > ice_before`), never an exact count, so RNG/`ICE_COLD_TARGET`
tuning drift won't make it brittle.

## Fire/lava melt behavior

- **FIRE neighbor → WATER** (no temp/life set; WATER is ambient by default).
- **LAVA neighbor → STEAM** with warm `_STEAM.temp_spawn` (120) + `seed_steam_life()`,
  mirroring `lava.py`'s water→steam reaction shape. LAVA checked before FIRE so
  the more dramatic reaction wins when both are adjacent (documented in the
  `ice.py` docstring as a judgment call — kept the spec's chosen order).
- Both pinned by tests (`test_ice_melts_to_water_via_fire_contact`,
  `test_ice_melts_to_steam_via_lava_contact`). The lava test also asserts the
  STEAM temp and seeded-life range.

## H overlay sanity (SDL smoke)

`SANDFALL_FRAMES=60 uv run sandfall` ran clean (EXIT=0, real SDL available — no
dummy fallback needed). Programmatic check of the overlay values in the
game-path run: every ice cell's temp is at/near `ICE_COLD_TARGET` — min exactly
`-50.0`, max `-49.9166` (a single diffusion tick's worth of warming on a
just-frozen or just-warmed cell that the next step's re-assert clamps back to
exactly `-50`). That transient is the expected persistent-cold-source behavior,
not a bug. Ice renders cold on the overlay.

## Tests: before → after

**175 → 178** (net +3): removed 1 (`test_ice_melts_to_water`), added 4
(`test_ice_freeze_spreads_through_water`, `test_ice_melts_to_water_via_fire_contact`,
`test_ice_melts_to_steam_via_lava_contact`, `test_ice_at_ambient_stays_ice`);
`test_water_freezes_to_ice` extended in place (not a count change).

## Six verification gates (all observed green)

1. `uv run pytest tests/test_phase.py tests/test_fire.py tests/test_thermal.py -v` — **44 passed** ✅
2. `uv run python -c "import sandfall"` — **OK** ✅ (also confirms no `water→ice` import cycle)
3. `uv run pytest` — **178 passed** ✅
4. `uv run ruff check .` — **All checks passed!** ✅
5. `uv run ruff format --check .` — **47 files already formatted** ✅
6. `uv run mypy src` — **Success: no issues found in 25 source files** ✅
7. `SANDFALL_FRAMES=60 uv run sandfall` — **EXIT=0** ✅

## Notes

- **No import cycle.** `ice.py` imports only `..elements` / `..grid` / `._common`;
  the `water → ice` import for `ICE_COLD_TARGET` is strictly one-way (ice never
  imports water). Confirmed by the `import sandfall` gate + explicit import of
  both modules.
- **`docs/ARCHITECTURE.md` did describe ice's melt rule** (two spots: the
  `melt_point` field description and the "add an element" guide, both said "ice
  melts above 0"). Both updated to the persistent-cold-source + contact-melt
  model with a BACKLOG pointer.
- **Closes the ice regression** (the `ce4be67`-era "ice no longer freezes water"
  bug). The deliberate, temporary behavior change (ambient ice no longer melts)
  is documented in the `ice.py` docstring + Decision Log #3 + here, with the
  realistic rework tracked in BACKLOG.

## Git

**No git operations performed.** Changes left unstaged per the task contract
(commit boundary is the human approval gate). HEAD still at `c575ccb`.

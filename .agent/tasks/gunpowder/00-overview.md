# Gunpowder + Explosion Mechanic — Master Plan

## Problem Statement

The sandfall game ships **15 elements** (`ElementId` EMPTY=0 … OIL=14: the v1
set, the temperature feature's STEAM/ICE/LAVA/GLASS, the acid/base pair, and
oil). The thermal model, the reactive-rule contract relaxation (transform own
cell in place, return `None`), the reactive `flashpoint` ignition path
(`rules/wood.py`), density-based displacement (`can_displace`), the reactive
neighbor side-effect write (`rules/lava.py`), the auto-resizing renderer/palette/
thermal LUTs, and the dormant-cell active-set optimization are all proven.
`.agent/tasks/BACKLOG.md:27-31` has tracked **"gunpowder (explosive)"** under
Tier 1 "More elements" since the original plan.

This plan adds **one new element + one new reusable mechanic**:

- **Gunpowder** (`ElementId.GUNPOWDER = 15`) — a dark POWDER (density ~1.5, like
  sand) that **flows like sand when left alone** and **detonates when heated**
  above a low `flashpoint` (~200). Fire, lava, or **another explosion's heat**
  sets it off → chain reactions for free.
- **The explosion (`blast.explode`)** — a reusable helper (`src/sandfall/rules/
  blast.py`) that models a blast as **heat burst + crater + scatter**: it raises
  the temperature of cells in the radius (distance falloff), destroys everything
  in the inner crater (no blast-resistant material — user choice), and pushes
  loose materials one cell outward (knockback). Future explosives (TNT, etc.)
  reuse it.

Gunpowder reuses mechanisms the codebase already has: the POWDER movement shape
(`rules/sand.py`), the reactive `flashpoint` thermal trigger (`rules/wood.py`:
`if get_temp > flashpoint: → FIRE`), the module-constant pattern
(`rules/lava.py`'s `LAVA_SOLIDIFY_TEMP`), the reactive side-effect write
(`rules/lava.py:67-75`), and the dormant-cell wake conditions (no new wake
condition is needed — see Risks #1). The only genuinely new code is the
`blast.explode` helper and its geometry.

## Solution Summary

A **single phase** (one atomic commit + reflection) that follows the documented
"Adding a new element" recipe (`docs/ARCHITECTURE.md:510-545`):
enum member → `ELEMENTS` entry → rule file(s) → `RULES` registration → tests,
plus the geometry ripple (thermal LUT row 15, `config.COND_GUNPOWDER`/
`CP_GUNPOWDER`, `MIN_WINDOW_W` recompute for the 18-item palette) and the
existing-test updates that hardcode palette counts.

- **Gunpowder.** `ElementId.GUNPOWDER = 15` (v1+ values 0–14 unchanged; new
  member 15). POWDER, density ~1.5 (like sand), `flashpoint` ~200, color dark
  gray/black. `burn_temp` is left at its default: on detonation the cell becomes
  `ElementId.FIRE`, whose rule re-asserts `_FIRE.burn_temp` (800) — the same
  shape as wood/plant/oil where the active heat comes from FIRE. The per-step
  rule (`rules/gunpowder.py`): **1)** **detonate** — if `get_temp > flashpoint`,
  call `blast.explode(grid, x, y)`, then overwrite the detonation cell with FIRE
  (seed life, set hot temp) and return `None`; **2)** otherwise **flow like a
  powder** (mirror `rules/sand.py` exactly: straight down, then down-diagonals
  randomized — sand has NO sideways step). Because detonation transforms the own
  cell in place (→ FIRE) and returns `None`, the moved-this-frame guard is
  unaffected (same reactive-rule relaxation as wood/lava).
- **The blast helper (`rules/blast.py`).** `explode(grid, x, y, radius=,
  crater=, heat=)` walks a **circular radius** (`dx*dx+dy*dy <= radius*radius`)
  **outer ring first** (so scatter pushes cells into already-processed outer
  cells, reducing double-move) and for each non-empty in-bounds cell applies, in
  order: **(a) heat burst** — `set_temp += heat * (1 - d/(radius+1))` (distance
  falloff); this is what chains gunpowder (other gunpowder in the radius heats
  past its flashpoint → detonates on its own scan/next frame), ignites flammables
  (wood/plant/oil → FIRE via their own flashpoint rules), and boils water
  (→ STEAM). **GUNPOWDER cells are then `continue`d** — they are heated only, NOT
  destroyed, so the chain propagates through the scan rather than via deep
  recursion (avoids stack blowup on huge piles). **(b) crater** (inner, `d <=
  crater`) — destroy everything (user chose "destroys everything": stone, glass,
  sand, wood, water, … all go); the very core (`d <= 1`) becomes FIRE with
  `CORE_FIRE_CHANCE` (~0.8, the fireball), the rest of the crater becomes EMPTY
  (or SMOKE with `CRATER_SMOKE_CHANCE` ~0.15 for visual). **(c) scatter** (outer)
  — loose materials (POWDER/LIQUID phase) are pushed one cell **outward** (away
  from the blast center) with `SCATTER_CHANCE` (~0.5) if the outward target is
  EMPTY. Module constants (`BLAST_RADIUS` ~4, `CRATER_RADIUS` ~2, `BLAST_HEAT`
  ~1200, `CORE_FIRE_CHANCE`, `CRATER_SMOKE_CHANCE`, `SCATTER_CHANCE`) mirror
  `rules/lava.py`'s `LAVA_SOLIDIFY_TEMP`.

The blast's writes are **side-effect writes** (direct `grid.set`/`set_temp`,
like `lava.py:67-75`'s water→STEAM), so `update_gunpowder` returns `None` after a
detonation. The dormant-cell wake catches every blasted cell via condition #1
(`id_changed`, dilated — `simulation.py:158-159`) and condition #2
(`temp_changed` — `simulation.py:163`), so the whole blast zone (and the chain)
stays active with **no wake-condition edit** (see Risks #1).

## Phase List

| #  | Phase                                        | Cx | Depends On | Parallelizable With |
|----|----------------------------------------------|----|------------|---------------------|
| 01 | Gunpowder + the reusable `blast.explode`     | M  | —          | —                   |

## Dependency Map

```
01 (gunpowder + blast) ──► done
```

A single phase. It is **not parallelizable** with anything because it mutates the
same shared core files every element pass touches (`elements.py`, `config.py`,
`thermal.py`, `rules/__init__.py`, plus the palette-count / `MIN_WINDOW_W`
tests). The `blast.py` helper and the `gunpowder.py` rule ship together so the
gunpowder rule can import `explode` and the tests can exercise both in one
coherent commit. (Splitting blast from gunpowder would leave an imported-but-
unused helper or an untested rule mid-flight.)

## Decision Log

All decisions below are **user-confirmed** and must not be re-litigated. The
phrasing "user-confirmed" is taken from the prompt that authorized this plan.

1. **Gunpowder is `ElementId.GUNPOWDER = 15`.** Existing values 0–14 are
   unchanged, so every LUT index the existing code relies on (renderer color
   LUT, conductivity LUT, heat-capacity LUT) stays stable; `uint8` holds up to
   255, so there is ample room. *(User-specified id.)*
2. **Gunpowder is a POWDER (density ~1.5, like sand).** It piles and falls
   exactly like sand via `can_displace` + `swap` when not ignited. *(User-
   confirmed phase/density.)*
3. **The trigger is thermal (`flashpoint` ~200), NOT a contact fuse.** Gunpowder
   detonates when its OWN temp exceeds its flashpoint — the exact same
   `if get_temp > flashpoint:` shape as `wood.py:26` / `oil.py`. This means fire,
   lava, AND **another explosion's heat burst** all set it off → chain reactions
   for free (no special chain wiring). A fuse/detonator element is explicitly
   Out of Scope. *(User-confirmed trigger model.)*
4. **The explosion model is "heat burst + crater + scatter" (user chose this
   over pure-destruction and over a pressure sim).** The heat burst chains
   gunpowder + ignites/melts via the EXISTING thermal thresholds (no new
   transition code); the crater destroys (user chose "destroys everything" — no
   blast-resistant material); the scatter approximates knockback by pushing loose
   materials one cell outward. A real Powder-Toy-style pressure/displacement sim
   is explicitly Out of Scope (the scatter is the chosen lighter alternative).
   *(User-confirmed model.)*
5. **The crater destroys EVERYTHING (no blast-resistant material).** Stone,
   glass, sand, wood, water, … all destroyed in the inner crater. The very core
   (`d <= 1`) becomes FIRE (the fireball); the rest → EMPTY (small SMOKE chance).
   EXCEPTION: GUNPOWDER in the radius is NOT destroyed here — it is only HEATED,
   so it chains via its own rule (destroying it would break the chain). A stray
   detonation can wreck a scene — that is the user's explicit choice (explosives
   are destructive); documented, not a bug. *(User-confirmed.)*
6. **The chain propagates via HEAT, not via recursion.** Gunpowder caught in a
   blast is heated past its flashpoint and detonates on its OWN later scan / next
   frame — it is not recursively `explode()`d from within `explode()`. This
   bounds stack depth to O(1) per blast regardless of pile size; the cascade
   unfolds over the scan/a few frames instead. **Do NOT cap chain depth — the
   cascade is the point.** *(User-confirmed model.)*
7. **The blast logic is a reusable helper, `rules/blast.py::explode`.**
   `gunpowder.py` calls it. Future explosives (TNT, bombs) reuse it by calling
   `explode` with different radius/heat constants. The helper is the only
   genuinely new code; gunpowder's own rule is the simple "detonate-or-flow"
   shape. *(User-confirmed reusability goal.)*
8. **Module-level tunables in `blast.py` mirror `rules/lava.py`'s
   `LAVA_SOLIDIFY_TEMP` pattern.** `BLAST_RADIUS` (~4), `CRATER_RADIUS` (~2),
   `BLAST_HEAT` (~1200 at center), `CORE_FIRE_CHANCE` (~0.8),
   `CRATER_SMOKE_CHANCE` (~0.15), `SCATTER_CHANCE` (~0.5). They are module
   globals read at call time (like `fire.py`'s `SMOKE_CHANCE`), so tests pin them
   deterministic via `monkeypatch.setattr(blast, "...", ...)`. *(User-confirmed
   constants + pin-final-in-reflection.)*
9. **Scatter only applies to loose materials (POWDER/LIQUID phase) and carries
   no life.** Sand/water/oil/acid/base (the POWDER/LIQUID set) get pushed one
   cell outward; solids/gases do not. Because loose materials have life 0
   always, the scatter's manual `set` (not `swap`) need not carry the `life`
   array — but it DOES carry `temp` (the pseudocode does
   `set_temp(tx,ty,get_temp(nx,ny))` explicitly). *(User-confirmed scatter
   model.)*
10. **`MIN_WINDOW_W` is recomputed for the wider palette.** 18 items (15 element
    swatches + Eraser + Brush-shape + Magnifier) → `18*24 + 17*4 + 12 + 2*8 =
    528` (132 cols). Exact `CELL_SIZE` multiple. The math is shown in the
    `config.py` comment, mirroring the existing comment (`config.py:71-79`).
11. **Tuning values are starting points; pin final values in the reflection.**
    `BLAST_RADIUS` / `CRATER_RADIUS` / `BLAST_HEAT` / the three chances /
    flashpoint / density / conductivity / heat-capacity are first-pass values
    tuned by eyeballing the SDL smoke. The implementer records the final tuned
    numbers in the phase reflection. *(User-confirmed.)*

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | M  | One new enum member + one `ELEMENTS` entry; ONE genuinely new module (`rules/blast.py` — the circular-radius heat/crater/scatter helper, the only non-recipe code) + one small rule file (`rules/gunpowder.py`: detonate-or-flow, mirroring `wood.py` + `sand.py`); thermal LUT row 15; one `MIN_WINDOW_W` recompute; the existing palette-count/min-width test updates; and a new test file covering detonation, chain-reaction, destroys-everything, heat-burst-ignites/boils, scatter, and stable-at-ambient. Mid-size: more than oil (a pure-recipe element), less than acid+base (two rule files + a cross-rule reaction). The blast geometry + its ring-ordering/double-move care is the interesting part. |

## Risks & Unknowns

1. **Dormant interaction (the headline risk).** A detonation is a large
   `id_changed` (crater cells → EMPTY/FIRE/SMOKE) AND `temp_changed` (heat
   burst) event over the whole blast radius. Wake condition #1 (`id_changed |
   moved`, dilated — `simulation.py:158-159`) + condition #2 (`temp_changed` —
   `simulation.py:163`) therefore wake the entire blast zone, including
   gunpowder cells that were only heated (their temp changed → condition #2).
   The analysis says **no wake-condition edit is needed** — gunpowder does NOT
   join FIRE/LAVA in condition #3 (`simulation.py:168-170`). **Verify with the
   chain-reaction integration test**: ignite one end of a gunpowder line/cluster
   and assert the whole chain detonates over a few steps (eventual-assertion
   style, mirroring `test_phase.py:83-116`'s freeze-spread test). If the chain
   stalls against dormant gunpowder, the fallback is adding `GUNPOWDER` to wake
   condition #3 — pin the finding in the reflection.
2. **Performance spike on a large detonation.** Each blast touches ~π·R² cells
   (R=4 → ~50 cells) in pure Python; a big gunpowder pile chain-explodes over a
   few frames, so several blasts fire per frame. Acceptable as a one-time burst
   (the dormant system keeps non-blast cells cheap), but a very large pile could
   hitch a frame. **Mitigation**: keep `BLAST_RADIUS` modest (~4). Note the
   observed worst-case in the reflection. (Do NOT cap chain depth — the cascade
   is the point, Decision #6.)
3. **Scatter double-move / ordering.** Scattering moves cells outward; if the
   scan visited inner cells after outer ones, an outward-pushed cell could land
   on a not-yet-processed cell and be moved again. The recommended pseudocode
   processes **outer ring first** (`for dist_ring in range(radius, -1, -1)`) so
   scatter pushes into already-processed cells. The implementer should verify
   cells do not teleport wildly (seeded test: scatter at `SCATTER_CHANCE=1.0`,
   assert each loose cell moved at most one cell outward). Pin the ring-order
   choice in the reflection.
4. **`BLAST_HEAT` vs the "sand → glass" melt assertion is in tension.** The user
   listed "sand near center → GLASS (melted)" as a desired heat-burst effect, but
   two facts work against it: (a) the crater **destroys** sand in the inner zone
   (`d <= CRATER_RADIUS`) rather than melting it; (b) at `BLAST_HEAT` ~1200 the
   outer-ring heat (`falloff` ~0.4–0.5 → +480–600°C) reaches only ~500–620°C,
   far below `SAND.melt_point` (1700). Reaching a melt at the crater edge needs
   `BLAST_HEAT` ≥ ~3360 (close to `TEMP_MAX` 3000). **The robust heat-burst
   proofs are wood→FIRE (`flashpoint` 300, reached at d≈3) and water→STEAM
   (`boil_point` 100, reached across the outer ring).** Include sand→GLASS ONLY
   if the implementer raises `BLAST_HEAT` well above ~1200 AND places the sand
   just outside the crater; otherwise drop it. Pin the decision (and any
   `BLAST_HEAT` bump) in the reflection.
5. **`MIN_WINDOW_W` bump shrinks the smallest window slightly.** 500 → 528.
   Documented math in the `config.py` comment; the existing
   `test_min_window_width_fits_full_palette_with_group_gap`
   (`test_config.py:93-123`) and `test_palette_resolves_phase03_elements_and_fits
   _min_window` (`test_ui.py:198-248`) hardcode the old 17-item math and MUST be
   updated.
6. **Diffusion numerical stability is preserved.** The stability bound is
   `rate * max(cond) / min(cp) <= 0.25` (`config.py:104-107`). The new
   conductivity (`COND_GUNPOWDER` ~0.15) is below the existing max (FIRE 0.50)
   and the new heat-capacity (`CP_GUNPOWDER` ~1.5) is above the existing min
   (FIRE/SMOKE/STEAM 0.5), so `0.20 * 0.50 / 0.5 == 0.20 <= 0.25` is unchanged.
   No new tunable needed.
7. **Acid/base dissolve gunpowder by default (minor cross-rule interaction).**
   Gunpowder is NOT in `ACID_RESIST` / `BASE_RESIST` (`rules/acid.py` /
   `rules/base.py`), so acid/base dissolve it harmlessly (→ EMPTY/SMOKE, no
   detonation — dissolving is not heating). This is acceptable for v1 and is the
   "default" of the existing recipe. If the implementer prefers gunpowder to
   resist acid (so it can be stored), they MAY add it to the resist frozensets —
   but that is optional; pin the choice in the reflection. (The blast, in turn,
   destroys acid/base in the crater like everything else — Decision #5.)
8. **"Destroys everything" is powerful.** A stray detonation can wreck a scene.
   That is the user's explicit choice (explosives are destructive); documented
   here and in the phase file, not treated as a bug. No blast-resistant material
   is added (Out of Scope).
9. **Line numbers in this plan are current as of the post-`new-elements/oil`
   source** (verified at planning time by reading every file cited). They WILL
   shift during implementation. Re-read each file before editing rather than
   blind-applying line numbers (same caveat as the prior plans' final risk).

## Documentation Updates

- **`docs/ARCHITECTURE.md`** — append `GUNPOWDER=15` to the `ElementId` member
  list (`ARCHITECTURE.md:248-257`, currently "...ACID=12, BASE=13, and the light
  flammable liquid OIL=14"). Optionally extend the "Adding a new element" recipe
  (`ARCHITECTURE.md:510-545`) with a one-line note that an explosive element's
  detonation is a side-effect write over a radius (the `blast.explode` pattern),
  mirroring how `lava.py`'s neighbor reaction is already documented.
- **`.agent/tasks/BACKLOG.md`** — strike **"gunpowder"** from the Tier 1 "More
  elements" line (`BACKLOG.md:27-31`, where acid/oil are already struck) and add
  a "Recently shipped" entry. Leave salt/metal/electricity.
- **`README.md`** — if it enumerates elements (Features table), add a GUNPOWDER
  row. (Check at implementation time.)

## Verification Philosophy

The phase's `Verification Commands` block MUST include these gates, and ALL must
exit zero before the phase may be considered done:

```bash
uv run pytest tests/test_gunpowder.py tests/test_phase.py -v  # new + regression
uv run python -c "...enum+registry sanity..."                 # ids stable + count grew
uv run pytest                                                  # FULL suite stays green
uv run ruff check . && uv run ruff format --check . && uv run mypy src
SANDFALL_FRAMES=60 uv run sandfall        # SDL smoke (fallback SDL_VIDEODRIVER=dummy)
```

After the phase, the implementer MUST write `01-gunpowder-blast-reflection.md`
in this directory capturing: what was difficult/unexpected, deviations from the
plan + why, the **final tuned values** (Decision #11), the dormant-interaction
finding (Risk #1), the `BLAST_HEAT`-vs-melt decision (Risk #4), and anything
fun. The phase is ONE atomic git commit.

## Out of Scope (Future Work — DO NOT plan now)

- **TNT / bombs / other explosives.** The `blast.explode` helper is reusable for
  them (a future TNT element just calls `explode` with a bigger radius/heat) —
  tracked separately.
- **A fuse / detonator element.** Gunpowder triggers purely via heat for now
  (Decision #3); a dedicated fuse/detonator is a future element.
- **Pressure-displacement blast.** The heavier Powder-Toy-style pressure sim; the
  scatter approximation is the chosen lighter alternative (Decision #4).
- **Blast-resistant materials.** User chose "destroys everything" (Decision #5);
  no material resists. A future "reinforced wall" that survives a blast would be
  a separate element + a resist check in `blast.py`.
- **More elements: salt, metal, electricity** — separate future passes; tracked
  in `BACKLOG.md:27-31`.

# Phase 01: Neutralize-to-steam (acid+base → hot STEAM, not WATER)

## Objective

Change the acid+base neutralize branch in BOTH `acid.py` and `base.py` so the
two cells become **hot STEAM** (seeded life, `NEUTRALIZE_TEMP`) instead of
WATER — making the reaction exothermic (visible hot steam that condenses to
water via the existing steam rule) AND breaking the dilute cascade that let a
single base clear an entire acid pool.

## Depends On

none — builds on the shipped `new-elements/01` (acid/base exist; `seed_steam_life`
exists at `_common.py:62`; the steam rule + its condense→WATER path exist at
`steam.py:40-42`).

## Can Parallelize With

none — single-phase task.

## Recommended Agent

@implementer — small, well-specified edit mirrored across two rule files, plus
test updates and one new regression test. Read the overview's "mandatory
`set_life`/`set_temp`" note before editing: those calls are required (not
optional) because `Grid.set` touches only the element id.

## Changes Required

- `src/sandfall/rules/acid.py` — add `seed_steam_life` to the `._common` import;
  add `NEUTRALIZE_TEMP = 150` module constant; rewrite the neutralize branch
  (BASE → STEAM).
- `src/sandfall/rules/base.py` — identical edit: add `seed_steam_life` to the
  `._common` import; add `NEUTRALIZE_TEMP = 150`; rewrite the neutralize branch
  (ACID → STEAM).
- `tests/test_acid_base.py` — flip the existing neutralize test to assert STEAM;
  add the 1:1 pool-persists regression test; add a neutralized-steam-condenses-
  to-WATER test. Update the module docstring's neutralize description.

> No changes to `elements.py`, `config.py`, `thermal.py`, `rules/__init__.py`,
> `grid.py`, or the renderer. STEAM, `seed_steam_life`, and the steam rule
> already exist. (Defensive: STEAM is already in `ACID_RESIST` / `BASE_RESIST`
> — `acid.py:58` / `base.py:61` — so neither dissolves its own product.)

## Implementation Instructions

### 1. `src/sandfall/rules/acid.py`

**1a. Add `seed_steam_life` to the `._common` import** (`acid.py:37`):

```python
from ._common import can_displace, seed_fire_life, seed_smoke_life, seed_steam_life, swap
```

**1b. Add the `NEUTRALIZE_TEMP` constant** in the tunables block
(`acid.py:39-42`):

```python
# Tunables (first-pass values; pin final tuned values in the reflection).
DISSOLVE_CHANCE = 0.5  # per-step chance to eat one dissolvable neighbor
DILUTE_CHANCE = 0.08  # per-step chance to dilute into adjacent water
DISSOLVE_SMOKE_CHANCE = 0.10  # chance a dissolved target emits SMOKE (else EMPTY)
NEUTRALIZE_TEMP = 150  # temp (°C) the acid+base -> STEAM reaction heats both cells to
```

**1c. Rewrite the neutralize branch** (`acid.py:86-91`). Before:

```python
        # 2. Neutralize: acid adjacent to BASE -> BOTH become WATER (side-effect
        #    write on the neighbor, idempotent across scan orders).
        if nb == ElementId.BASE:
            grid.set(x, y, ElementId.WATER)
            grid.set(nx, ny, ElementId.WATER)
            return None
```

After:

```python
        # 2. Neutralize: acid adjacent to BASE -> BOTH become hot STEAM. The
        #    STEAM then condenses to WATER via the steam rule (temp <
        #    condense_point -> WATER), so the end state is still water but via
        #    a hot, gaseous intermediate (exothermic). Producing STEAM (not
        #    WATER) ALSO breaks the dilute cascade that used to let one base
        #    clear a whole acid pool: the dilute rule below fires ONLY on
        #    adjacent WATER, and STEAM is not WATER, so the surrounding acid is
        #    left alone (~1:1). Idempotent across scan orders: the base rule
        #    performs the identical STEAM write, so whichever scans first wins.
        #    set_life/set_temp are MANDATORY: grid.set updates ONLY the element
        #    id (grid.py), so without them the cell keeps the stale acid life
        #    (0 -> steam expires) and temp (ambient 20 < condense_point 60 ->
        #    instant condense).
        if nb == ElementId.BASE:
            grid.set(x, y, ElementId.STEAM)
            grid.set(nx, ny, ElementId.STEAM)
            grid.set_life(x, y, seed_steam_life())
            grid.set_life(nx, ny, seed_steam_life())
            grid.set_temp(x, y, NEUTRALIZE_TEMP)
            grid.set_temp(nx, ny, NEUTRALIZE_TEMP)
            return None
```

**1d. Update the module docstring** (`acid.py:9-12`, the "Neutralize" bullet) so
it no longer claims "BOTH ... become WATER." Replace with: acid adjacent to
BASE → BOTH become hot STEAM (`NEUTRALIZE_TEMP`), which the steam rule then
condenses to WATER once it cools; idempotent (both rules perform the identical
STEAM write).

### 2. `src/sandfall/rules/base.py`

Mirror `acid.py` exactly, with the one expected substitution (the neutralize
check keys on `ACID`):

**2a. Add `seed_steam_life` to the `._common` import** (`base.py:39`):

```python
from ._common import can_displace, seed_fire_life, seed_smoke_life, seed_steam_life, swap
```

**2b. Add `NEUTRALIZE_TEMP = 150`** in the tunables block (`base.py:41-44`),
identical to acid's.

**2c. Rewrite the neutralize branch** (`base.py:89-94`). Before:

```python
        # 2. Neutralize: base adjacent to ACID -> BOTH become WATER (side-effect
        #    write on the neighbor, idempotent across scan orders).
        if nb == ElementId.ACID:
            grid.set(x, y, ElementId.WATER)
            grid.set(nx, ny, ElementId.WATER)
            return None
```

After (same body as acid's; only the `if` element differs):

```python
        # 2. Neutralize: base adjacent to ACID -> BOTH become hot STEAM (see
        #    acid.py for the full rationale). Mirrors the acid rule's identical
        #    STEAM write, so the scan order does not matter (idempotent).
        if nb == ElementId.ACID:
            grid.set(x, y, ElementId.STEAM)
            grid.set(nx, ny, ElementId.STEAM)
            grid.set_life(x, y, seed_steam_life())
            grid.set_life(nx, ny, seed_steam_life())
            grid.set_temp(x, y, NEUTRALIZE_TEMP)
            grid.set_temp(nx, ny, NEUTRALIZE_TEMP)
            return None
```

**2d. Update the module docstring** (`base.py:11-15`, the "Neutralize" bullet)
the same way as acid's.

### 3. `tests/test_acid_base.py`

**3a. Flip the existing neutralize test** (`tests/test_acid_base.py:164-178`,
`test_acid_base_neutralize_both_become_water`). Rename to
`test_acid_base_neutralize_both_become_steam` and assert STEAM on both cells
(the reaction now produces hot steam that later condenses — the WATER end-state
is covered separately in 3c). Keep the 20-seed scan-order loop (still
idempotent — both rules write the identical STEAM):

```python
def test_acid_base_neutralize_both_become_steam() -> None:
    """Acid adjacent to BASE -> BOTH become STEAM (hot, finite life), for any
    seed / scan order. The idempotent side-effect write (both rules set BOTH
    cells to STEAM at NEUTRALIZE_TEMP) is what makes the randomized scan order
    irrelevant. The STEAM later condenses to WATER via the steam rule (see
    test_neutralized_steam_condenses_to_water). Verified across 20 seeds."""
    import sandfall.rules.acid as acid

    for i in range(20):
        random.seed(i)
        g = Grid(2, 1)
        g.set(0, 0, ElementId.ACID)
        g.set(1, 0, ElementId.BASE)
        Simulation(g).step()
        assert g.get(0, 0) == ElementId.STEAM, f"seed={i}"
        assert g.get(1, 0) == ElementId.STEAM, f"seed={i}"
        # Reaction is exothermic: both cells heated to NEUTRALIZE_TEMP.
        assert g.get_temp(0, 0) == acid.NEUTRALIZE_TEMP, f"seed={i}"
        assert g.get_temp(1, 0) == acid.NEUTRALIZE_TEMP, f"seed={i}"
        # Steam has a finite life (seeded, not the stale acid life of 0).
        assert g.get_life(0, 0) > 0, f"seed={i}"
        assert g.get_life(1, 0) > 0, f"seed={i}"
```

**3b. Add the headline 1:1 regression test** (the proof the cascade is broken).
Drop ONE base cell into a ~19-cell acid pool with an OPEN top (so neutralized
steam can rise away and condense elsewhere, the realistic case — avoids the
trapped-steam edge). Step many times; assert MOST of the acid REMAINS (pre-fix
the dilute cascade cleared the pool to 0 within ~60 steps):

```python
def test_one_base_does_not_clear_whole_acid_pool() -> None:
    """HEADLINE REGRESSION: dropping ONE base into a ~19-cell acid pool must NOT
    clear the pool.

    Pre-fix: neutralization produced WATER, and the acid `dilute` rule (acid
    adjacent to WATER -> probabilistically become WATER) fired on that product
    water -> more water -> more dilution -> the WHOLE pool collapsed to water
    from a single base (measured: acid 19 -> 0 within ~60 steps).

    Post-fix: neutralization produces STEAM (not WATER). The dilute rule fires
    ONLY on adjacent WATER (acid.py: `if nb == ElementId.WATER ...`), and
    STEAM != WATER, so the surrounding acid is left alone. One base neutralizes
    ~one acid cell; the steam rises out of the open top and condenses elsewhere;
    the pool persists.

    The grid top is left EMPTY so steam can escape upward. (In a sealed box the
    steam would condense in place near the acid -> local dilution of 1-2 cells
    — the accepted edge case, NOT what this test exercises.)"""
    random.seed(0)
    g = Grid(10, 12)
    # A ~20-cell acid pool across rows 6-9, cols 1-5 (open top above it).
    for y in range(6, 10):
        for x in range(1, 6):
            g.set(x, y, ElementId.ACID)
    acid_before = int((g.array == int(ElementId.ACID)).sum())
    assert acid_before == 20
    # Drop ONE base cell just above the pool's surface.
    g.set(3, 5, ElementId.BASE)
    sim = Simulation(g)
    for _ in range(100):
        sim.step()
    acid_after = int((g.array == int(ElementId.ACID)).sum())
    # Pool persists: well above 10 of ~20 cells remain (pre-fix this was ~0).
    assert acid_after >= 10, (acid_before, acid_after)
```

> The `>= 10` floor is deliberately loose (the true post-fix count is ~18-19);
> it leaves headroom for scan-order jitter while still failing loudly on the
> pre-fix 0. If the measured post-fix count is consistently ~18-19, tighten to
> `>= 15` in the reflection.

**3c. Add the condenses-to-WATER test.** Trap the neutralized steam under a
solid cap so it cannot escape the grid; it cools in place via diffusion and the
steam rule condenses it to WATER (the existing path, no new code). Step enough
times for 150 °C to cool below `condense_point` (60); verify the step count at
implementation time and pin it:

```python
def test_neutralized_steam_condenses_to_water() -> None:
    """The STEAM produced by acid+base neutralization eventually condenses to
    WATER via the existing steam rule (temp < condense_point -> WATER). No new
    code: this just exercises the steam rule on the reaction product.

    A STONE cap above the reaction traps the steam so it cools IN PLACE (rather
    than rising out of the grid and expiring to EMPTY), guaranteeing the
    condensation happens in a known place we can assert on."""
    random.seed(0)
    g = Grid(3, 6)
    # STONE cap one row above the reaction so steam cannot escape upward.
    g.set(0, 1, ElementId.STONE)
    g.set(1, 1, ElementId.STONE)
    g.set(2, 1, ElementId.STONE)
    # The reaction pair at the bottom row.
    g.set(1, 2, ElementId.ACID)
    g.set(2, 2, ElementId.BASE)
    sim = Simulation(g)
    for _ in range(400):  # empirical: let 150C steam cool below 60 -> condense
        sim.step()
    water = int((g.array == int(ElementId.WATER)).sum())
    assert water >= 1  # at least one neutralized cell condensed back to water
```

> If the 400-step count is too short (steam still > 60 °C) or so long the steam
> expires to EMPTY before cooling, tune the cap layout / step count and pin in
   the reflection. The assertion is "WATER appears somewhere from the
   reaction," not an exact cell.

**3d. Update the module docstring** (`tests/test_acid_base.py:1-20`): the
"neutralize" half now describes acid+base → STEAM (then steam → WATER), and the
20-seed loop verifies the STEAM write is scan-order-safe. Add one line noting
the new 1:1 pool-persists regression and the condense test.

## Acceptance Criteria

- [ ] Neutralization turns BOTH cells (acid + base) into **hot STEAM**: seeded
      life (`seed_steam_life`), temp `NEUTRALIZE_TEMP` (150); no longer WATER.
      (acid.py + base.py branches match; flipped test passes.)
- [ ] **1:1 regression test passes**: ONE base cell dropped into a ~20-cell acid
      pool, after ~100 steps, MOST of the acid REMAINS (`acid_after >= 10`;
      pre-fix was ~0). This is the headline proof the dilute cascade is broken.
- [ ] Neutralized steam eventually **condenses to WATER** (the condense test
      asserts WATER appears after enough steps) — via the existing steam rule,
      no new steam-rule code.
- [ ] Neutralization is **scan-order safe / idempotent** (the 20-seed loop in
      the flipped test passes; both rules perform the identical STEAM write).
- [ ] Existing acid/base tests updated: the "acid+base → WATER" assertion is
      flipped to STEAM; the rest of `tests/test_acid_base.py` (dissolve /
      dilute / burn / smoke / density / dormant / LUT) is unchanged and green.
- [ ] `seed_steam_life` is imported in BOTH `acid.py` and `base.py`;
      `NEUTRALIZE_TEMP == 150` is defined in BOTH.
- [ ] Full suite stays green (205+ tests; this plan only flips + adds, no
      removals).
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused tests (the flipped neutralize + 1:1 regression + condense):
uv run pytest tests/test_acid_base.py -v

# Import sanity + the new constant exists in both rule modules:
uv run python -c "import sandfall; from sandfall.rules import acid, base; assert acid.NEUTRALIZE_TEMP == 150 == base.NEUTRALIZE_TEMP; print('neutralize-steam OK')"

# FULL suite -- regression guard (nothing else broke):
uv run pytest

# Lint + format + types:
uv run ruff check . && uv run ruff format --check . && uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
#   Manual check: drop ONE base cell into an acid pool. Expect a small steam
#   puff at the contact (visible on the H heat overlay) and the pool PERSISTING
#   -- NOT the whole pool collapsing to water as before.
```

All commands must exit zero. Do not proceed to the reflection/commit until all
six pass.

## Documentation Updates

- None required for production code. The two rule-file docstrings are updated
  in-place (steps 1d / 2d) — that is the only doc surface this change touches.
- `.agent/tasks/BACKLOG.md` — add the deferred Scope B entry
  ("Concentration/mixing system for acid-base") citing this plan. (Done as part
  of this planning pass, not the implementation.)

## Reflection & Commit

After implementation, write `01-neutralize-to-steam-reflection.md`. Include:
- the **final `NEUTRALIZE_TEMP`** value actually shipped (did 150 hold, or was
  it bumped for visible-but-not-lingering steam?);
- the **measured 1:1 post-fix acid count** (was `>= 10` left loose, or
  tightened to `>= 15`?);
- the **condense-test step count** that reliably produced WATER (and whether the
  STONE-cap layout was needed vs. an open grid);
- whether the **trapped-steam edge case** showed up in manual play (sealed
  containers) and how local it was;
- confirmation the 20-seed scan-order loop still passes (idempotency held after
  switching WATER→STEAM).

Then make ONE atomic git commit covering `acid.py`, `base.py`, and
`tests/test_acid_base.py`.

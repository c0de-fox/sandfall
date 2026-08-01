# Task Plan: Gas Buoyancy — gases (STEAM + SMOKE) rise through liquids

> **Small physics fix**, same domain/voice as `acid-base-neutralization/`. A
> single behavior-correctness ticket for the gas rise rules.

## Problem Statement

Gases (STEAM, SMOKE) currently rise **only into EMPTY cells** — the rise checks
hard-code `grid.get(...) == ElementId.EMPTY`:

- `steam.py:53` (straight up) and `steam.py:60` (up-diagonals).
- `smoke.py:36` (straight up) and `smoke.py:43` (up-diagonals).

So a gas **trapped under a liquid** (water / oil / acid / base / lava) just sits
there — it never swaps with the liquid above it. User report: *"steam should
float past water (and other liquids)."* Real gases are buoyant in liquids and
bubble up; the current rule makes gas pockets stagnate under any liquid surface,
which looks wrong.

(For completeness: the sideways **drift** steps — `steam.py:70` /
`smoke.py:53` — are correctly EMPTY-only and stay that way; buoyancy is an
upward force, not swimming sideways through liquid.)

## Solution Summary

Add one shared **buoyancy predicate** — `is_riseable(cell_id)` — to
`rules/_common.py`, then use it in the **rise** steps (straight-up +
up-diagonals) of BOTH `steam.py` and `smoke.py`. A gas may rise into EMPTY (open
air, as before) **or any LIQUID** (buoyancy — the gas swaps with the liquid
above it: gas up, liquid down). The sideways **drift** stays EMPTY-only.

`is_riseable` returns `True` for EMPTY or any LIQUID id; `False` for solids and
other gases (a gas does not displace stone or another gas). The liquid-id set is
precomputed once at module load (`_LIQUID_IDS` frozenset) so the per-cell rise
check is an O(1) set lookup.

### The helper (`rules/_common.py`)

```python
# Gases rise through liquids (buoyancy): a gas swaps with a LIQUID above it.
# Precomputed once (Phase is static) so the per-cell rise check is a set lookup.
_LIQUID_IDS: frozenset[int] = frozenset(
    int(e) for e in ElementId if ELEMENTS[e].phase == Phase.LIQUID
)


def is_riseable(cell_id: int) -> bool:
    """True if a gas may rise INTO the cell holding ``cell_id``.

    EMPTY (open air) or any LIQUID (buoyancy -- the gas swaps with the liquid,
    gas up / liquid down). Solids and other gases are NOT riseable (a gas does
    not displace stone or another gas). Used by the STEAM/SMOKE rise steps.
    """
    return cell_id == int(ElementId.EMPTY) or cell_id in _LIQUID_IDS
```

(`_common.py:25` already imports `ELEMENTS`, `ElementId`, `Phase` — no new
import needed.)

### The rise-step edits (`steam.py` + `smoke.py`)

In BOTH rules, the two rise checks change from `== ElementId.EMPTY` to
`is_riseable(grid.get(...))`. Example (steam straight-up, `steam.py:53`):

```python
# before: if y - 1 >= 0 and grid.get(x, y - 1) == ElementId.EMPTY:
if y - 1 >= 0 and is_riseable(grid.get(x, y - 1)):
    swap(grid, x, y, x, y - 1)
    return (x, y - 1)
```

The up-diagonal loop gets the identical treatment (`steam.py:60` / `smoke.py:43`).
The sideways **drift** loop is UNCHANGED — it stays `== ElementId.EMPTY`
(buoyancy is upward, not sideways). `is_riseable` is added to the `._common`
import in both files (`steam.py:28` / `smoke.py:19`).

### Why it is safe / what the behavior looks like

- **Steam under water** → swaps up (steam rises, water sinks) → bubbles to the
  surface → continues into air. Same for oil / acid / base / lava (all LIQUID).
- **The displaced liquid falls back via its own rule next frame** (`can_displace`
  lets it sink through EMPTY / lower-density liquid below). No new fall code.
- **The swap carries temp + life correctly** (`_common.swap` → `Grid.move`, the
  raw 3-array element swap — `steam.py`/`smoke.py` already route every move
  through it), so a hot steam keeps its heat as it rises and a water keeps its
  temp as it sinks.
- **Steam rising through cool water may condense mid-pool** (the condense check
  at `steam.py:40-42` runs BEFORE movement; diffusion cools the steam each step).
  This is realistic — a steam bubble in cold water condenses before surfacing —
  and is already handled by the existing condense path. Tests isolate buoyancy
  from condensation by setting a uniform warm temp (see Phase 01).
- **FIRE is unchanged** (EMPTY-only rise) per scope — rising through water would
  let fire survive underwater, which is odd without a fire+water extinguish
  mechanic (explicitly out of scope).
- **Dormancy**: gas-through-liquid is a swap (movement) → the existing
  `moved`/`id_changed` wake conditions fire → no `simulation.py` change.

## Phase List

| # | Phase | Complexity | Depends On | Agent |
|---|-------|------------|------------|-------|
| 1 | Gas rise through liquid (`_common.is_riseable` helper + steam.py/smoke.py rise-step edits + docstrings + tests) | S | none | @implementer |

(One phase. The change is ~1 helper + a precomputed frozenset in `_common.py`,
two `== EMPTY` → `is_riseable(...)` edits mirrored across `steam.py` and
`smoke.py` (rise steps only), docstring touch-ups, and a focused new test file.
Small and atomic.)

## Dependency Map

- Phase 1 depends on the already-shipped gas rules: `steam.py` (rise + condense +
  age), `smoke.py` (rise + age), `_common.py` (`swap`, the `ELEMENTS`/`Phase`
  imports), and `elements.py` (`Phase.LIQUID` membership — WATER / LAVA / ACID /
  BASE / OIL). No other in-flight work.
- Nothing else is in flight; this can run now.

## Decision Log

1. **Fix STEAM and SMOKE; exclude FIRE.** User-confirmed scope. Fire rising
   through water would let it survive underwater — odd without a fire+water
   extinguish mechanic. FIRE stays EMPTY-only until that mechanic exists (Out of
   Scope). Alternatives considered:
   - *Fix all three gases uniformly.* Rejected — underwater fire is visibly
     wrong and needs its own mechanic (extinguish) first; bundling it would
     expand scope into behavior the user did not ask for.

2. **Rise steps use buoyancy; sideways drift stays EMPTY-only.** Buoyancy is an
   upward force — a gas bubble rises through the liquid above it. Gases do not
   swim sideways through liquid (that would be lateral displacement, not
   buoyancy). So only the straight-up + up-diagonal **rise** checks gain the
   liquid case; the **drift** loop keeps its `== ElementId.EMPTY` guard. This is
   the physically correct split and keeps drift a cheap air-only shim.

3. **Shared `is_riseable` helper in `_common.py`, not inline checks per rule.**
   Centralizes the "what may a gas rise into" predicate (EMPTY or any LIQUID),
   avoids duplicating that logic across `steam.py` and `smoke.py`, and gives the
   condense/age tests + future gas rules one obvious place to reuse it. Mirrors
   how `can_displace` already centralizes the sinking predicate. Alternatives:
   - *Inline `== EMPTY or grid.get(...) in _LIQUID_IDS` in each rule.* Duplicates
     the set membership in two files; rejected for the same reason `can_displace`
     is shared.

4. **No density comparison needed (all gases are less dense than all liquids).**
   STEAM 0.04, SMOKE 0.05 (FIRE 0.1, EMPTY 0.0) vs the lightest liquid OIL 0.8 —
   every gas is less dense than every liquid, so any LIQUID is riseable and a
   plain phase check suffices. This deliberately differs from `can_displace`,
   which DOES compare densities (a denser liquid sinks through a lighter one,
   e.g. water 1.0 through oil 0.8); gases need no such comparison.

5. **Precompute `_LIQUID_IDS` once at module load.** `Phase` membership is
   static, so the frozenset is built once (at import) and the per-cell rise check
   is a single set-membership test. Gases are few per frame, but keeping the hot
   path O(1) matches the `_common.py` performance discipline established by
   `Grid.move` / the `can_displace`-LUT backlog item.

## Estimated Complexity

- Phase 1: **S** — 1 helper + 1 frozenset in `_common.py`, 2 mirrored
  `== EMPTY` → `is_riseable(...)` edits per gas rule (rise steps only), docstring
  touch-ups in 3 files, and one new focused test file. No enum, LUT, config,
  registry, or `simulation.py` changes.

## Risks & Unknowns

- **Existing tests**: any test that relied on steam/smoke being TRAPPED under a
  liquid would now fail. None expected — the existing gas tests exercise rising
  into EMPTY (still permitted by `is_riseable`) and condense/age on 1x1 grids
  (no liquid involved). Note in the reflection if any needed updating.
- **Perf**: negligible. Gases are few per frame, and `is_riseable` is a single
  frozenset lookup (vs the previous `==` int compare — same order of magnitude).
- **Steam-through-lava**: steam bubbles through lava too (LAVA is LIQUID). The
  swap carries the steam's OWN temp up (diffusion re-equilibrates after); there
  is no instant heat-transfer on pass-through, so a steam bubble does not
  instantly superheat from the lava it displaces. Slight unphysicality —
  acceptable approximation (a full convective heat transfer model is far out of
  scope).
- **Test isolation from condensation**: steam condenses below `condense_point`
  (60 °C). A steam cell set without an explicit warm temp defaults to ambient
  (20 °C) and condenses on step 1 — before it can rise. The buoyancy tests
  therefore set a uniform warm temp (> 60) across the steam + liquid column so
  the diffusion Laplacian is ~zero and the steam stays gaseous while rising
  (mirrors the `test_phase.py` 1x1 diffusion-no-op philosophy). Flagged in
  Phase 01's test instructions.

## Verification Philosophy

Every gate must exit zero. The headline proof is the **steam-rises-through-water
test** (Phase 01): a STEAM cell below a WATER cell, one step, assert the steam
moved UP into the water's cell and the water moved DOWN — the literal buoyancy
swap. The mirror smoke test, the reaches-surface test, the through-another-
liquid test, the does-NOT-rise-through-solid/gas test, and the drift-stays-air-
only test together lock down the full behavior envelope. The existing steam/smoke
tests stay green (they rise into EMPTY, which `is_riseable` still permits). The
full suite (217 tests) is the regression guard. The SDL smoke is the human check
that a steam pocket released under water bubbles up to the surface.

## Out of Scope

- **Fire rising through liquids.** Needs a fire+water extinguish mechanic first
  (otherwise fire survives underwater). Recorded here; do NOT implement.
- **Gas-gas displacement** (steam/smoke displacing each other). Not modeled in
  v1; `is_riseable` returns False for other gases by design.
- **Sideways buoyant drift through liquids.** Drift stays air-only by design
  (Decision #2); only the upward rise gains the liquid case.

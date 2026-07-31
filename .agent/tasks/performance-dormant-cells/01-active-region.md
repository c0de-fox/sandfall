# Phase 01: Dormant-cell (active-region) tracking

## Objective

Add a persistent boolean `_active` array to `Grid` and rewrite `Simulation.step`
to scan ONLY cells that are both `_active` AND non-empty (narrowing the prior
sparse `np.nonzero(data[y])[0]` to `np.nonzero(active[y] & (data[y] != 0))[0]`),
then rebuild `_active` each frame from four wake conditions so a settled pile goes
dormant (skipped) while everything that *can* move or react stays awake. The four
conditions are reasoned complete; **the entire existing test suite (159 tests) is
the headline regression guard** and MUST stay green. Five new tests pin the
dormancy/wake behavior.

## Depends On

none — single phase (the `_active` array, the `step` rewrite, the brush/migrate
marks, and the tests are mutually dependent and land together; see the overview's
Dependency Map).

## Can Parallelize With

nothing — single phase.

## Recommended Agent

@implementer — one coherent, behavior-preserving change across `grid.py` +
`simulation.py` + `tests/test_simulation.py`. Read `00-overview.md` first
(especially Decision Log #3-#10 and Risks #1, #5), then re-read
`src/sandfall/simulation.py`, `src/sandfall/grid.py`, and `src/sandfall/brush.py`
before editing. Do NOT be tempted to carry `grid._active` forward into
`active_next` (Decision Log #4) — that would make cells never sleep. Do NOT
sparsify the diffusion pass (Decision Log #12) — thermal wake depends on it.

## Changes Required

- `src/sandfall/grid.py` — add the `_active` bool array (declaration + `__init__`
  + a read-only `active` property); mark active on write in `set` (non-empty) and
  in `fill_circle` (each painted cell + 4-neighbors, both branches); carry the
  overlap in `migrate_grid`.
- `src/sandfall/simulation.py` — bootstrap `_active` in `__init__`; rewrite
  `step` to scan `active & non-empty` and rebuild `_active` from the four wake
  conditions; add the module-level `_dilate` helper. Diffusion pre-pass
  (`simulation.py:55`) is UNCHANGED.
- `src/sandfall/brush.py` — **NO change.** `paint_brush` already routes through
  `Grid.fill_circle` (`brush.py:48`), which now marks active. (Listed here so the
  implementer verifies rather than assumes.)
- `tests/test_simulation.py` — ADD five focused regression tests pinning the
  dormancy/wake behavior.

## Implementation Instructions

> Re-read `src/sandfall/grid.py` and `src/sandfall/simulation.py` before editing —
> line numbers below are current at planning time and may have drifted. This is one
> coherent change; no new dependencies, no signature changes to public methods
> (only a new read-only `Grid.active` property and a private `_active` array).

### 1. `src/sandfall/grid.py` — add the `_active` array + property

**1a. Module docstring.** Add a short fourth paragraph to the existing docstring
(`grid.py:1-19`, which already documents `_data` / `_life` / `_temp`) noting a
fourth parallel `bool` array `_active` carries the per-cell wake flag for the
dormant-cell optimization, that `Simulation.step` rebuilds it each frame from the
wake conditions, and that `set` / `fill_circle` OR marks into it between steps so
the brush and rule transforms wake the cells they touch. Mirror the tone of the
`temp` paragraph (`grid.py:11-18`).

**1b. Class attribute declaration** (`grid.py:42-46`). Add after `_temp`:

```python
    _active: npt.NDArray[np.bool_]
```

**1c. `__init__`** (`grid.py:48-55`). After the `_temp` line (`grid.py:55`), add:

```python
        self._active = np.zeros((height, width), dtype=np.bool_)
```

**1d. Read-only `active` property.** Add after the `temp` property (`grid.py:82-91`),
mirroring its docstring tone:

```python
    @property
    def active(self) -> npt.NDArray[np.bool_]:
        """Raw ``(height, width)`` bool view of the per-cell active (wake) flag.

        Intended read-only access (e.g. for tests and diagnostics). The
        simulation owns the writes: :class:`~sandfall.simulation.Simulation`
        rebuilds ``_active`` each frame from the four wake conditions (see its
        docstring), and :meth:`set` / :meth:`fill_circle` OR marks into it
        between steps so the brush and rule transforms wake the cells they
        touch. Mirrors the read-view pattern of :attr:`temp` / :attr:`life`.
        """
        return self._active
```

### 2. `src/sandfall/grid.py` — mark active on write

**2a. `Grid.set`** (`grid.py:108-119`). Currently:

```python
        if not self.in_bounds(x, y):
            return
        self._data[y, x] = int(element_id)
```

Replace the final assignment so a non-empty write also marks the cell active (and
avoid a double `int()` cast by binding `eid` once):

```python
        if not self.in_bounds(x, y):
            return
        eid = int(element_id)
        self._data[y, x] = eid
        # Wake the cell for the next scan: a non-empty write placed/transformed
        # it (brush via fill_circle, rule transform, or test placement). EMPTY
        # writes (erasing) do NOT mark active here -- fill_circle marks the
        # erased cell's neighborhood itself. (During the scan this mark is
        # redundant: id_changed already captures it and active_next overwrites
        # _active at end of step. It exists for between-steps placement.)
        if eid != int(ElementId.EMPTY):
            self._active[y, x] = True
```

**2b. `Grid.fill_circle`** (`grid.py:171-204`). Mark each painted cell AND its
orthogonal neighbors active, in BOTH the `radius == 0` branch and the disk loop.
This is the brush's only source of between-step wake; the +neighbors is what makes
**erasing** wake the cells beside/above the opened hole (erase writes EMPTY, which
`set` does not mark).

Add a small private helper near `fill_circle` (module-level or as a nested helper —
module-level is cleaner and testable):

```python
def _mark_active_disk(grid: Grid, cx: int, cy: int, radius: int) -> None:
    """OR the painted disk (cx, cy, radius) AND its 1-cell neighborhood into
    ``grid._active``.

    Painting new cells must wake them so they get scanned next frame; erasing
    must wake the cells beside/above the opened hole so they fall/flow into it.
    The +1 neighborhood is applied by dilating the disk mask once in the
    4-neighborhood. Bounds-clipped via slicing (writes past the edge are simply
    dropped, matching fill_circle's silent edge clipping).
    """
    x0 = max(0, cx - radius - 1)
    x1 = min(grid.width - 1, cx + radius + 1)
    y0 = max(0, cy - radius - 1)
    y1 = min(grid.height - 1, cy + radius + 1)
    if x0 > x1 or y0 > y1:
        return
    grid._active[y0 : y1 + 1, x0 : x1 + 1] = True
```

Then call `self._mark_active_disk(cx, cy, radius)` (or the module function) at the
end of BOTH branches of `fill_circle`:

- In the `radius == 0` branch (`grid.py:186-190`), before `return`:
  ```python
            self._mark_active_disk(cx, cy, 0)
            return
  ```
- At the end of the disk loop (`grid.py:204`, after the loops complete):
  ```python
        self._mark_active_disk(cx, cy, radius)
  ```

(The disk+1 bounding box is a conservative superset of the true disk⊕4-neighborhood;
a few extra edge cells woken is harmless — they go dormant next frame if nothing
happened. Keeping it a single slice write avoids a per-cell Python loop.)

### 3. `src/sandfall/grid.py` — carry `_active` through `migrate_grid`

**3.** `migrate_grid` (`grid.py:207-225`). After the `_temp` copy (`grid.py:225`),
add the `_active` overlap copy, mirroring the existing three:

```python
        new._active[:h, :w] = old._active[:h, :w]
```

Newly-exposed cells in a grown region keep their default (all-False from
`__init__`) — they are EMPTY, so inactive is correct. (On resize, `Game` constructs
a fresh `Simulation(new_grid)` at `game.py:219`, which re-runs the bootstrap in
step 5 below — conservative-correct; the migrated overlap is a subset and is
harmlessly overwritten.)

### 4. `src/sandfall/simulation.py` — add the `_dilate` helper

**4.** Add a module-level helper (after the imports, before `class Simulation`).
Zero-padded 4-neighborhood dilation via four shifted ORs against the ORIGINAL mask:

```python
def _dilate(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """Dilate ``mask`` by one cell in the 4-neighborhood (von Neumann).

    A cell in the result is True if it OR any of its up/down/left/right
    neighbors was True in ``mask``. Used to propagate wake signals: when a cell
    moves / changes / is a heat source, the cells that could be affected by
    that (resting on it, beside it, heated by it) must wake next frame.

    Four zero-padded shifted ORs against the ORIGINAL ``mask`` (so the shifts
    do not compound into a 2-cell dilation). O(H*W), one allocation.
    """
    out = mask.copy()
    out[:, :-1] |= mask[:, 1:]   # right neighbor  -> this cell
    out[:, 1:] |= mask[:, :-1]   # left neighbor   -> this cell
    out[:-1, :] |= mask[1:, :]   # below neighbor  -> this cell
    out[1:, :] |= mask[:-1, :]   # above neighbor  -> this cell
    return out
```

(`out` is written; `mask` is only read, so all four shifts see consistent original
values — no aliasing.)

### 5. `src/sandfall/simulation.py` — bootstrap `_active` in `__init__`

**5.** `Simulation.__init__` (`simulation.py:38-42`). After the LUT builds, seed
the active set so the FIRST step scans all non-empty cells (covers
`Grid(); set(...); Simulation(g); step()`):

```python
        self._cond_lut = build_conductivity_lut()
        self._cp_lut = build_heat_capacity_lut()
        # Bootstrap: no prior active set exists, so seed the first step with
        # "every non-empty cell is active". Combined with Grid.set marking active
        # on non-empty writes, mid-sim placement via set is also covered.
        grid._active[:] = grid._data != int(ElementId.EMPTY)
```

### 6. `src/sandfall/simulation.py` — rewrite `step`

**6.** Replace the body of `step` (`simulation.py:48-87`) — the diffusion call at
`simulation.py:55` stays, but its result handling changes (capture the pre-diffusion
reference for the thermal-wake mask). The scan loop narrows from
`np.nonzero(data[y])[0]` to `np.nonzero(active[y] & (data[y] != 0))[0]`, and a
wake-set rebuild is appended. Use this exact body:

```python
    def step(self) -> None:
        """Advance the simulation by exactly one frame."""
        grid = self._grid
        data = grid._data
        # Heat diffusion pre-pass: one vectorized op BEFORE the movement scan, so
        # every rule reads a freshly-diffused temperature. diffuse_temps returns a
        # NEW int16 array (does not mutate grid._temp in place), so keep the OLD
        # reference for the thermal-wake mask below (no copy needed).
        temp_before = grid._temp
        grid._temp = diffuse_temps(grid._temp, data, self._cond_lut, self._cp_lut)

        data_before = data.copy()  # for id_changed (cheap ~0.05 ms at 200x140)
        active = grid._active
        moved = np.zeros((grid.height, grid.width), dtype=np.bool_)

        # Movement scan: y-descending (bottom -> top) so a single grain falls at
        # most one cell per step (no teleporting). x direction randomized per row
        # to avoid left bias. DORMANT-CELL: only cells that are BOTH active AND
        # non-empty are visited -- a settled pile goes dormant (active=False) and
        # is skipped, while the movement front stays awake. All scan semantics
        # (y-descending, per-row random dir, moved guard, mid-scan empty re-check)
        # are UNCHANGED from the sparse scan -- only the x-index source narrows.
        for y in range(grid.height - 1, -1, -1):  # y-descending -- UNCHANGED
            xs = np.nonzero(active[y] & (data[y] != 0))[0]  # active & non-empty
            if xs.size == 0:
                continue  # no active non-empty cell this row -> skipped in one call
            if random.random() < 0.5:  # per-row random direction -- UNCHANGED
                xs = xs[::-1]
            for x in xs:
                x = int(x)  # numpy intp -> plain int (mypy + rule args)
                if moved[y, x]:
                    continue
                # Mid-scan re-check: a cell active at nonzero-time may have
                # emptied/transformed earlier in this scan. Re-read and skip.
                eid = int(data[y, x])
                if eid == int(ElementId.EMPTY):
                    continue
                fn = RULES.get(ElementId(eid))
                if fn is None:
                    continue
                dest = fn(grid, x, y)
                if dest is not None:
                    moved[dest[1], dest[0]] = True

        # Rebuild the active set for NEXT frame from the four wake conditions.
        # (1) Movement / identity-change wake: a cell that moved or changed, or is
        #     orthogonally adjacent to one (so eroding support / opening a hole
        #     wakes the cells above/beside to fall/flow).
        id_changed = data != data_before
        active_next = _dilate(id_changed | moved)
        # (2) Thermal wake: a cell whose temperature changed (via diffusion from a
        #     heat source, or a rule) must be rescanned -- phase transitions
        #     (water boil/freeze, wood ignite) check the cell's OWN temp.
        active_next |= grid._temp != temp_before
        # (3) Persistent heat sources: FIRE and LAVA re-assert burn_temp / react
        #     each step but may neither move nor change identity nor (if already
        #     at burn_temp) change temp. Keep them and their neighborhood awake
        #     so combustion chains and lava reactions proceed.
        active_next |= _dilate(
            (data == int(ElementId.FIRE)) | (data == int(ElementId.LAVA))
        )
        # (4) Brush-painted/erased cells were OR-ed into grid._active between
        #     steps (by Grid.fill_circle) and were scanned above. They are NOT
        #     carried into active_next unless the sim dynamics woke them via
        #     (1)/(2)/(3) -- which is correct. (Do NOT do `active_next |=
        #     grid._active`: that would let cells marked once stay active forever
        #     and never sleep.)
        grid._active = active_next
```

**Properties the implementer MUST verify are preserved (the whole correctness
argument):**

- **y-descending outer loop, per-row random direction, `moved` guard, mid-scan
  empty re-check** — all byte-for-byte unchanged from the sparse scan. The ONLY
  change to the scan is the `x`-index source: `np.nonzero(data[y])[0]` →
  `np.nonzero(active[y] & (data[y] != 0))[0]`. `active[y] & (data[y] != 0)`
  produces a bool array; `np.nonzero(...)[0]` returns its True indices (ascending),
  exactly as before but restricted to active cells.
- **RNG sequence is unchanged** — still exactly one `random.random()` per row for
  the direction flip. The same cells are dispatched in the same order *among the
  active ones*; dormant cells (which previously dispatched and returned "no move")
  are simply not dispatched. If a previously-passing randomized test now draws a
  different RNG stream, that is a bug — investigate before touching the test. (It
  should not happen: a dormant cell's rule, when skipped, draws no RNG, but neither
  did it produce a move, so downstream cells see the same grid state.)
- **`temp_before = grid._temp` is a reference, not a copy** — `diffuse_temps`
  returns a new array, so the old reference is intact (Decision Log #6). Verify by
  the existing `simulation.py:52-54` comment.
- **`grid._active = active_next` OVERWRITES** (not `|=`) — the consumption
  semantics that let cells sleep (Decision Log #4).

**7. Update the `Simulation` class docstring** (`simulation.py:16-36`). Replace the
sparse-scan paragraph (`simulation.py:25-29`) with one that describes the
dormant-cell scan: only cells that are BOTH `active` AND non-empty are visited;
`_active` is rebuilt each frame from the four wake conditions (movement/id-change +
dilation; thermal change; FIRE/LAVA + neighborhood; brush-painted); a cell firing
none of them goes dormant and is skipped. Note explicitly that the result is
identical to the old scan because dormant cells provably cannot move or react
(nothing in their world changed). Keep the existing sentences about y-descending,
per-row random direction, the `moved` guard, and the diffusion pre-pass.

### 7. `src/sandfall/brush.py` — verify NO change

`paint_brush` (`brush.py:27-76`) calls `grid.fill_circle(...)` at `brush.py:48` and
nothing else that mutates the grid's per-cell state. Since `fill_circle` now marks
active (step 2b), the brush automatically wakes the cells it paints/erases. **Do
not edit `brush.py`.** (The implementer should confirm this by re-reading it.)

### 8. `tests/test_simulation.py` — ADD five dormancy/wake regression tests

Append after the existing tests. Each seeds `random.seed(0)` via `_seed()`
(`tests/test_simulation.py:18-20`). Add `from sandfall.brush import paint_brush` to
the imports for the lava/fire placement (paint_brush sets the correct
`temp_spawn`/life; placing FIRE/LAVA via bare `grid.set` would start them at
AMBIENT temp / life 0 and they would solidify/expire instantly).

```python
def test_settled_pile_goes_dormant() -> None:
    """A settled, ambient-temperature sand pile collapses to a dormant active set.

    After settling, no grain moves, no temp changes (uniform ambient), and there
    are no heat sources -- so the wake set is provably empty and the whole pile
    is skipped next frame. Pins the headline dormancy win: the active set is the
    (tiny) movement front, NOT the whole pile.
    """
    _seed()
    width, height = 12, 10
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    n_grains = 6
    for y in range(0, n_grains):
        grid.set(width // 2, y, ElementId.SAND)  # column above the floor
    sim = Simulation(grid)

    sim.step()  # bootstrap made every non-empty cell active
    initial_active = int(grid.active.sum())
    assert initial_active > 0  # the pile was scanned this frame

    for _ in range(80):
        sim.step()  # let the pile fully settle

    # No sand lost; all grains supported from below.
    sand_mask = grid.array == int(ElementId.SAND)
    assert int(sand_mask.sum()) == n_grains
    for y in range(height - 1):
        for x in range(width):
            if sand_mask[y, x]:
                assert grid.get(x, y + 1) != int(ElementId.EMPTY), (x, y)
    # Settled + uniform ambient + no heat source => the active set is empty
    # (the movement front is zero). This is the dormancy guard.
    final_active = int(grid.active.sum())
    assert final_active == 0, final_active


def test_eroding_support_wakes_dormant_pile() -> None:
    """Erasing the floor under a dormant pile wakes it and the grains fall.

    Erasing is done via the brush path (fill_circle), which marks the erased
    cell's neighborhood active -- including the dormant grain directly above.
    Next step that grain is scanned, finds the cell below now empty, and falls.
    (Direct grid.set(x, y, EMPTY) between steps intentionally does NOT wake --
    only non-empty set marks active; erase-wake is fill_circle's job.)
    """
    _seed()
    width, height = 6, 8
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    grid.set(width // 2, height - 2, ElementId.SAND)  # grain resting on floor
    sim = Simulation(grid)

    for _ in range(10):
        sim.step()  # grain settled + dormant
    assert grid.get(width // 2, height - 2) == ElementId.SAND
    assert not grid.active[height - 2, width // 2]  # dormant

    # Erase the floor cell directly beneath the dormant grain (brush path).
    grid.fill_circle(width // 2, height - 1, 0, ElementId.EMPTY)
    sim.step()

    # The grain was woken and fell one row into the opened hole.
    assert grid.get(width // 2, height - 1) == ElementId.SAND
    assert grid.get(width // 2, height - 2) == ElementId.EMPTY


def test_dormant_water_next_to_lava_flashes_to_steam() -> None:
    """A dormant (trapped, unmoving) water cell still flashes to STEAM when lava
    arrives beside it. Lava is a persistent heat source (wake 3), so the lava
    cell stays scanned and its rule side-effects the adjacent water to steam
    (lava.py reaction). Dormancy must not starve the reaction.
    """
    _seed()
    width, height = 4, 3
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    grid.set(0, 1, ElementId.STONE)  # left wall
    grid.set(2, 1, ElementId.STONE)  # right wall (becomes lava later)
    grid.set(1, 1, ElementId.WATER)  # trapped water: cannot move
    sim = Simulation(grid)

    for _ in range(5):
        sim.step()  # water trapped -> dormant
    assert grid.get(1, 1) == ElementId.WATER
    assert not grid.active[1, 1]  # water dormant

    # Lava arrives beside the dormant water (paint_brush sets spawn_temp=1500).
    paint_brush(grid, 2, 1, 0, ElementId.LAVA)
    sim.step()

    # The lava reacted with the adjacent water: water -> STEAM, lava -> STONE.
    assert grid.get(1, 1) == ElementId.STEAM
    assert grid.get(2, 1) == ElementId.STONE


def test_dormant_wood_next_to_fire_ignites() -> None:
    """A dormant (static) wood cell next to fire ignites to FIRE.

    Wood ignites when its OWN temp exceeds flashpoint (wood.py), so the wood
    cell MUST be scanned. Fire is a persistent heat source (wake 3) and clings
    to flammable neighbors (fire.py), so the wood stays awake across steps,
    heats via diffusion, and ignites. Pins that dormancy does not pin a cell
    that a heat source is actively heating.
    """
    _seed()
    width, height = 5, 4
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    grid.set(1, height - 2, ElementId.WOOD)  # static wood
    sim = Simulation(grid)

    for _ in range(5):
        sim.step()  # wood is static -> dormant
    assert grid.get(1, height - 2) == ElementId.WOOD
    assert not grid.active[height - 2, 1]  # wood dormant

    # Fire appears directly beside the dormant wood (paint_brush seeds fire life).
    paint_brush(grid, 2, height - 2, 0, ElementId.FIRE)

    # Fire clings to the flammable wood and heats it; once the wood's temp
    # crosses flashpoint it ignites. Detect the moment of ignition (the cell
    # becomes FIRE); robust to the fire later rising away.
    ignited = False
    for _ in range(60):
        sim.step()
        if grid.get(1, height - 2) == ElementId.FIRE:
            ignited = True
            break
    assert ignited, "dormant wood next to fire never ignited"


def test_painting_into_dormant_region_wakes_it() -> None:
    """Painting a cell into a dormant (empty) region wakes it so it is scanned.

    After a pile settles and the scene goes dormant, painting a single sand
    grain high above must mark it active (fill_circle) so the next step scans
    and drops it -- dormancy must not pin freshly painted cells.
    """
    _seed()
    width, height = 8, 8
    grid = Grid(width=width, height=height)
    for x in range(width):
        grid.set(x, height - 1, ElementId.STONE)  # floor
    for y in range(0, 2):
        grid.set(width // 2, y, ElementId.SAND)  # small pile
    sim = Simulation(grid)

    for _ in range(40):
        sim.step()  # pile settles -> dormant
    assert int((grid.array == int(ElementId.SAND)).sum()) == 2

    # Paint one sand grain at the top of the dormant region.
    grid.fill_circle(width // 2, 0, 0, ElementId.SAND)
    assert grid.active[0, width // 2]  # the brush woke it
    sim.step()

    # The painted grain was scanned and fell one row (dormancy did not pin it).
    assert grid.get(width // 2, 0) == ElementId.EMPTY
    assert grid.get(width // 2, 1) == ElementId.SAND
```

Notes for the implementer:
- All five are deterministic given `_seed()` (seed 0); the active-count assertion in
  `test_settled_pile_goes_dormant` is NOT a timing assertion (Decision Log #14) —
  it is a deterministic state check and is allowed. For a uniform-ambient settled
  pile with no heat sources the active set is provably empty (`final_active == 0`).
  If a future change introduces non-uniform spawn temps that leave a residual
  gradient, relax to `final_active < n_grains // 2` and document WHY in the
  reflection — do not silently loosen it.
- `test_dormant_water_next_to_lava_flashes_to_steam` relies on `paint_brush`
  setting LAVA's `temp_spawn=1500` so it does not instantly solidify
  (`LAVA_SOLIDIFY_TEMP == 700`). Placing lava via bare `grid.set` would start it at
  AMBIENT and it would turn to STONE before reacting.
- `test_dormant_wood_next_to_fire_ignites` detects ignition within a 60-step cap;
  fire clings to flammable wood (`fire.py:112`), so ignition is assured. If the cap
  proves insufficient on a slow host, WIDEN it (document the re-tune) — do not
  weaken the `ignited` assertion.

## Acceptance Criteria

- [ ] `Grid` has an `_active: NDArray[bool_]` array (shape `(H, W)`, init all
      `False`) declared and allocated in `__init__`; a read-only `active`
      property exposes it (mirroring `temp`/`life`).
- [ ] `Grid.set` marks `_active[y, x] = True` on non-empty writes (and only
      non-empty); `Grid.fill_circle` marks each painted cell AND its 4-neighbors
      active in BOTH the `radius == 0` branch and the disk loop.
- [ ] `migrate_grid` copies the `_active` overlap (alongside `_data`/`_life`/
      `_temp`).
- [ ] `Simulation.__init__` bootstraps `grid._active[:] = (grid._data != EMPTY)`.
- [ ] `Simulation.step` scans `np.nonzero(active[y] & (data[y] != 0))[0]` per row;
      the y-descending outer loop, the per-row `random.random() < 0.5` direction
      flip, the `moved` guard, and the mid-scan empty re-check are all preserved.
- [ ] `Simulation.step` rebuilds `_active` at end of step from the four wake
      conditions: `_dilate(id_changed | moved)`, `grid._temp != temp_before`,
      `_dilate((data==FIRE)|(data==LAVA))`, with `grid._active = active_next`
      (OVERWRITE, not `|=`). The diffusion pre-pass is UNCHANGED (still
      whole-grid); `temp_before` is the pre-diffusion reference (no copy).
- [ ] The module-level `_dilate(mask)` helper is present and correct (4-neighborhood,
      reads original mask, accumulates into `out`).
- [ ] **The entire existing test suite (159 tests) stays green** — the headline
      correctness guard. In particular all sand/water/fire/lava/steam/ice/glass/
      thermal physics tests pass unchanged.
- [ ] `test_settled_pile_goes_dormant` passes (active set collapses to 0).
- [ ] `test_eroding_support_wakes_dormant_pile` passes.
- [ ] `test_dormant_water_next_to_lava_flashes_to_steam` passes.
- [ ] `test_dormant_wood_next_to_fire_ignites` passes.
- [ ] `test_painting_into_dormant_region_wakes_it` passes.
- [ ] **No timing assertions** are added anywhere; perf is MEASURED and reported in
      the reflection.
- [ ] All six verification gates exit zero.

## Verification Commands

```bash
# Phase-focused (the five new dormancy/wake tests + the existing physics tests):
uv run pytest tests/test_simulation.py -v

# Import smoke:
uv run python -c "import sandfall"

# FULL suite -- the headline regression guard (159 tests; fire/lava/steam/ice/
# glass/thermal physics all ripple through the new scan):
uv run pytest

# Lint / format / types:
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# SDL smoke (headless fallback: SDL_VIDEODRIVER=dummy):
SANDFALL_FRAMES=60 uv run sandfall
```

All commands must exit zero. Do NOT proceed until the FULL suite is green. If a
previously-passing test fails, a wake condition was missed — fix the wake logic in
`step` (or the active-marking in `set`/`fill_circle`), do NOT weaken the test.

## Documentation Updates

- The `Simulation` class docstring is updated as part of the code change (step 7) —
  it is the source of truth for scan + wake semantics.
- The `Grid` module docstring gets a fourth paragraph noting the `_active` array
  (step 1a).
- `docs/ARCHITECTURE.md` — if it describes the scan as visiting every non-empty
  cell, update it to note the dormant-cell (active-region) scan and the four wake
  conditions, and that the result is identical to the old scan (dormant cells
  provably cannot move or react). If it does not describe the scan at that level,
  leave it. Note whichever you find in the reflection.

## Reflection & Commit

After implementation, write `01-active-region-reflection.md` in this directory.
**Specifically include:**

- The measured before/after `Simulation.step` time on (a) the settled 7,326-sand
  pile (the headline: was 72.9 ms — report the actual after), (b) an empty 200×140
  grid (should be ~2.6-3 ms; report actual), and (c) a ~59%-busy grid (confirms
  the `set` active-mark did not regress busy scenes — Risk #5; report actual
  before/after). Cite the measurement method (e.g. `timeit` over N frames via a
  one-off script under `/tmp/opencode/`).
- Confirmation that the full suite (159 tests) stayed green and that NO existing
  test needed an RNG-stream re-tune (if one did, explain why and what changed —
  the scan must NOT change the number/order of `random.*` draws among active
  cells).
- The actual measured active-set size on the settled pile after settling
  (`final_active`) — should be 0.
- Whether the `set` active-marking caused any measurable busy-scene regression,
  and if it was dropped (Decision Log #9 / Risk #5), with the rationale and
  confirmation that the full suite still passed afterward.
- Whether `docs/ARCHITECTURE.md` described the scan and was updated.
- Anything difficult/unexpected, deviations from this plan + why, and anything
  fun discovered (e.g. the measured mask-rebuild overhead vs the ~69 ms saved).

Then make ONE atomic git commit covering all changes in this phase.

"""Tests for the pure temperature-diffusion module (Phase 01).

``diffuse_temps`` is the per-frame heat pre-pass run before the movement
scan. These tests pin its numerical behavior headlessly (no pygame): heat
flows hot→cold, low-conductivity materials transfer slowly, a uniform field
is an equilibrium, the conservative face-flux stencil does not overshoot at
the ``rate*max(cond)/min(cp)==0.25`` stability bound, results clip to the
``[TEMP_MIN, TEMP_MAX]`` band, total heat ``sum(cp*temp)`` is conserved over
many steps, and the input array is never mutated. With float32 temp storage
(Phase 01 of thermal-float-ice) a cell cooling toward 0 actually crosses 0
(the headline ``test_diffusion_reaches_threshold_precisely``), which the old
int16 + round-to-nearest storage could not.
"""

from __future__ import annotations

import numpy as np

from sandfall.config import AMBIENT_TEMP, HEAT_VIZ_COLD, HEAT_VIZ_HOT, TEMP_MAX
from sandfall.elements import ElementId
from sandfall.thermal import (
    build_colorbar_gradient,
    build_conductivity_lut,
    build_heat_capacity_lut,
    diffuse_temps,
    thermal_to_rgb,
)


def test_heat_flows_hot_to_cold() -> None:
    # One hot cell in a uniform-conductivity field warms its neighbors next step.
    temp = np.full((3, 3), AMBIENT_TEMP, dtype=np.float32)
    temp[1, 1] = 1000
    ids = np.full((3, 3), int(ElementId.EMPTY), dtype=np.uint8)  # COND_EMPTY
    lut = build_conductivity_lut()
    cp_lut = build_heat_capacity_lut()
    out = diffuse_temps(temp, ids, lut, cp_lut, rate=0.2)
    # Center cooled; the 4 orthogonal neighbors warmed above ambient.
    assert out[1, 1] < 1000
    for y, x in [(0, 1), (2, 1), (1, 0), (1, 2)]:
        assert out[y, x] > AMBIENT_TEMP, (y, x, out[y, x])
    # Corners are NOT 4-neighbors of center -> unchanged at ambient.
    for y, x in [(0, 0), (0, 2), (2, 0), (2, 2)]:
        assert out[y, x] == AMBIENT_TEMP, (y, x, out[y, x])


def test_low_conductivity_transfers_slowly() -> None:
    # An insulator (STONE, low cond) moves less heat than a conductor (EMPTY).
    base = np.zeros((1, 3), dtype=np.float32)
    base[0, 0] = 0
    base[0, 1] = 1000
    base[0, 2] = 0
    lut = build_conductivity_lut()
    cp_lut = build_heat_capacity_lut()
    ids_stone = np.full((1, 3), int(ElementId.STONE), dtype=np.uint8)
    ids_empty = np.full((1, 3), int(ElementId.EMPTY), dtype=np.uint8)
    out_stone = diffuse_temps(base.copy(), ids_stone, lut, cp_lut, rate=0.2)
    out_empty = diffuse_temps(base.copy(), ids_empty, lut, cp_lut, rate=0.2)
    # The middle cell cooled more (transferred more) under the higher conductor.
    assert out_empty[0, 1] < out_stone[0, 1]


def test_uniform_field_is_equilibrium() -> None:
    # A uniform-temperature field does not change.
    temp = np.full((5, 5), 300, dtype=np.float32)
    ids = np.full((5, 5), int(ElementId.SAND), dtype=np.uint8)
    out = diffuse_temps(
        temp, ids, build_conductivity_lut(), build_heat_capacity_lut(), rate=0.2
    )
    assert np.array_equal(out, temp)


def test_no_overshoot_at_stability_bound() -> None:
    # The NEW stability bound is rate*max(cond)/min(cp) <= 0.25. At the bound,
    # a 0/1000 pair cannot swing past [0, 1000]. Use uniform cp (air, CP_EMPTY)
    # so the test isolates the cond/cp ratio; drive rate so the bound is hit
    # exactly: rate = 0.25 * cp / cond.
    temp = np.zeros((1, 2), dtype=np.float32)
    temp[0, 1] = 1000
    ids = np.zeros((1, 2), dtype=np.uint8)  # EMPTY
    lut = build_conductivity_lut()
    cp_lut = build_heat_capacity_lut()
    cond = lut[int(ElementId.EMPTY)]
    cp = cp_lut[int(ElementId.EMPTY)]
    out = diffuse_temps(temp, ids, lut, cp_lut, rate=0.25 * cp / cond)
    assert float(out.min()) >= 0.0
    assert float(out.max()) <= 1000.0


def test_clips_to_band() -> None:
    # The clip to [TEMP_MIN, TEMP_MAX] applies on the float32 result (no int16
    # band anymore). A uniform-max field diffusing among itself at rate=1.0
    # cannot exceed TEMP_MAX.
    temp = np.full((2, 2), TEMP_MAX, dtype=np.float32)
    ids = np.full((2, 2), int(ElementId.FIRE), dtype=np.uint8)
    out = diffuse_temps(
        temp, ids, build_conductivity_lut(), build_heat_capacity_lut(), rate=1.0
    )
    assert float(out.max()) <= float(TEMP_MAX)


def test_diffuse_returns_new_array_does_not_mutate_input() -> None:
    temp = np.full((3, 3), AMBIENT_TEMP, dtype=np.float32)
    temp[1, 1] = 800
    ids = np.full((3, 3), int(ElementId.EMPTY), dtype=np.uint8)
    before = temp.copy()
    diffuse_temps(
        temp, ids, build_conductivity_lut(), build_heat_capacity_lut(), rate=0.2
    )
    assert np.array_equal(temp, before)  # input untouched


def test_build_conductivity_lut_shape_and_values() -> None:
    # The LUT mirrors build_color_lut: shape (len(ElementId),) float64,
    # indexed by element id. Pin a few representative values.
    from sandfall.config import COND_EMPTY, COND_FIRE, COND_STONE

    lut = build_conductivity_lut()
    assert lut.shape == (len(ElementId),)
    assert lut.dtype == np.float64
    assert lut[int(ElementId.EMPTY)] == COND_EMPTY
    assert lut[int(ElementId.FIRE)] == COND_FIRE
    assert lut[int(ElementId.STONE)] == COND_STONE
    # Every registered element has a row (unmapped ids stay 0.0; Phase 03
    # adds the new ids' rows).
    for eid in ElementId:
        assert 0.0 <= lut[int(eid)] <= 1.0


def test_build_heat_capacity_lut_shape_and_values() -> None:
    # Mirrors the conductivity LUT test: shape (len(ElementId),) float64,
    # indexed by element id. Pin a few representative values incl. LAVA=5.0
    # (the high-thermal-mass case driving the "lava persists" behavior).
    from sandfall.config import CP_EMPTY, CP_FIRE, CP_LAVA, CP_STONE

    lut = build_heat_capacity_lut()
    assert lut.shape == (len(ElementId),)
    assert lut.dtype == np.float64
    assert lut[int(ElementId.EMPTY)] == CP_EMPTY
    assert lut[int(ElementId.FIRE)] == CP_FIRE
    assert lut[int(ElementId.STONE)] == CP_STONE
    assert lut[int(ElementId.LAVA)] == CP_LAVA
    # Every registered element has cp > 0 (diffusion divides by cp).
    for eid in ElementId:
        assert lut[int(eid)] > 0.0


def test_diffusion_conserves_total_heat() -> None:
    # The regression guard for the whole fix. Uses the plan's VALIDATED
    # prototype scenario (3 ICE @ -5 in 25x1 air): the OLD own-conductivity
    # stencil drained this 410 -> 0 (the "ice spreads cold far" symptom); the
    # conservative face-flux form conserves it (measured max |drift| over 60
    # steps ~= 4e-5, the residual float32 cast error in sum(cp*temp) -- there
    # is no int16 round-to-nearest drain anymore). This bound fails loudly on
    # the old formula (drain 410 vs the ~4e-5 here).
    lut = build_conductivity_lut()
    cp_lut = build_heat_capacity_lut()
    temp = np.full((1, 25), AMBIENT_TEMP, dtype=np.float32)
    ids = np.full((1, 25), int(ElementId.EMPTY), dtype=np.uint8)
    for col in (11, 12, 13):  # 3-cell ICE block at -5 in a 25-cell air row
        temp[0, col] = -5
        ids[0, col] = int(ElementId.ICE)
    heat0 = float((cp_lut[ids] * temp.astype(np.float64)).sum())
    for _ in range(60):
        temp = diffuse_temps(temp, ids, lut, cp_lut)  # default rate
        heat = float((cp_lut[ids] * temp.astype(np.float64)).sum())
        # Total heat stays within 0.001 (measured max drift ~4e-5; the bound is
        # ~23x that for platform/BLAS jitter). The OLD formula drained 410 -> 0,
        # so this bound fails loudly on it.
        assert abs(heat - heat0) <= 0.001, (heat0, heat)


def test_diffusion_reaches_threshold_precisely() -> None:
    # The headline float-temps test: a warm cell cooled by a very cold FIXED
    # source must drop ACROSS the 0 freeze threshold within a bounded step
    # count. Under the old int16 + np.rint storage, a cell whose per-step
    # cooling fell below 0.5C rounded back up and it stuck just above 0
    # forever (the freeze-regression root cause #1). With float32 storage the
    # cell's temp accumulates sub-degree deltas and drops monotonically past 0.
    lut = build_conductivity_lut()
    cp_lut = build_heat_capacity_lut()
    # 1x10 row of EMPTY air; cell 0 is a pinned cold source at -200 (TEMP_MIN,
    # the coldest a source can be), the rest start at 20 (AMBIENT). All EMPTY so
    # conductivity/cp are uniform (COND_EMPTY=0.1, CP_EMPTY=1.0 -> effective
    # diffusion coefficient D = rate*cond/cp = 0.2*0.1/1.0 = 0.02). We do NOT
    # call any rule here -- this tests the diffusion kernel alone, so "pinned"
    # means we re-set cell 0 each step to model a persistent source, exactly as
    # ice will in Phase 02.
    #
    # We watch cell 3 (not the far cell 9). Measured crossing steps under the
    # two storage models (200-step budget, D=0.02):
    #   float32: cell 3 crosses <=0 at step ~75 (cell 9 would need ~552).
    #   int16:   cell 3 NEVER crosses -- it stalls at exactly +2.0 (the
    #            per-step delta drops below 0.5C and rounds away), which is the
    #            textbook near-threshold rounding stall (root cause #1).
    # Cell 3 is the sharpest discriminator: it is the farthest cell int16 can
    # cool before its rounding pins it just above the freeze threshold, so it
    # exercises the sub-0.5C/step accumulation that ONLY float storage allows.
    # (The far cell 9 cannot cross within any reasonable budget even with the
    # float fix -- -200 is TEMP_MIN so the source cannot be made colder, and
    # D=0.02 means a 9-hop cool-to-0 takes ~552 steps; cell 3 within the
    # <=200-step budget is the right probe.)
    temp = np.full((1, 10), 20.0, dtype=np.float32)
    ids = np.full((1, 10), int(ElementId.EMPTY), dtype=np.uint8)
    temp[0, 0] = -200.0
    crossed = False
    for _ in range(200):
        temp = diffuse_temps(temp, ids, lut, cp_lut)
        temp[0, 0] = -200.0  # re-pin the cold source each step
        if temp[0, 3] <= 0.0:
            crossed = True
            break
    assert crossed, temp[0, 3]  # cell 3 cooled below 0 -- int16 stalls it at +2.0


# --- Heat-overlay gradient (Phase 04) ---------------------------------------
# thermal_to_rgb is a pure numpy map from the float32 temp field to an
# (H, W, 3) uint8 image (blue -> cyan -> neutral -> yellow -> red). These
# tests pin its contract headlessly: shape/dtype, the cold/blue vs hot/red
# ordering, saturation without overflow outside the display band, and that
# ambient reads as a truly neutral gray (the gradient's design pivot).


def test_thermal_to_rgb_shape_and_dtype() -> None:
    temp = np.full((4, 5), 20, dtype=np.float32)
    rgb = thermal_to_rgb(temp)
    assert rgb.shape == (4, 5, 3)
    assert rgb.dtype == np.uint8


def test_thermal_to_rgb_hot_is_redder_than_cold() -> None:
    cold = np.full((1, 1), HEAT_VIZ_COLD, dtype=np.float32)
    hot = np.full((1, 1), HEAT_VIZ_HOT, dtype=np.float32)
    rc = thermal_to_rgb(cold)[0, 0]
    rh = thermal_to_rgb(hot)[0, 0]
    assert rh[0] > rc[0]  # hot has more red
    assert rc[2] > rh[2]  # cold has more blue


def test_thermal_to_rgb_saturates_outside_band() -> None:
    # Clamped to the display band before coloring -> cells at/above
    # HEAT_VIZ_HOT produce identical colors (no uint8 overflow).
    at_band = thermal_to_rgb(np.array([[HEAT_VIZ_HOT]], dtype=np.float32))[0, 0]
    above = thermal_to_rgb(np.array([[HEAT_VIZ_HOT + 5000]], dtype=np.float32))[0, 0]
    below = thermal_to_rgb(np.array([[HEAT_VIZ_COLD - 5000]], dtype=np.float32))[0, 0]
    at_cold = thermal_to_rgb(np.array([[HEAT_VIZ_COLD]], dtype=np.float32))[0, 0]
    assert tuple(at_band) == tuple(above)
    assert tuple(at_cold) == tuple(below)


def test_thermal_to_rgb_ambient_is_neutral() -> None:
    rgb = thermal_to_rgb(np.full((1, 1), AMBIENT_TEMP, dtype=np.float32))[0, 0]
    # Neutral: no channel maxed out (not pure red/blue)...
    assert rgb[0] < 250 and rgb[2] < 250
    # ...and the gradient is pivoted on ambient, so all three channels are
    # exactly equal there (a true flat gray, not merely 'no channel maxed').
    assert rgb[0] == rgb[1] == rgb[2]


def test_thermal_to_rgb_monotone_red_and_blue() -> None:
    # Sweeping cold -> hot, red must not decrease and blue must not increase
    # (a monotone-ish ramp). Sample every 20 degrees across the band.
    temps = np.arange(HEAT_VIZ_COLD, HEAT_VIZ_HOT + 1, 20, dtype=np.float32).reshape(
        1, -1
    )
    rgb = thermal_to_rgb(temps)[0]
    red = rgb[:, 0].astype(int)
    blue = rgb[:, 2].astype(int)
    assert np.all(np.diff(red) >= 0)
    assert np.all(np.diff(blue) <= 0)


# --- Colorbar gradient (Phase 02) -------------------------------------------
# build_colorbar_gradient reuses thermal_to_rgb on a 1-D temp ramp so the H-mode
# legend is an EXACT mirror of the per-cell heat coloring (no second gradient
# definition to drift). Headlessly pinned: shape/dtype, the hot/cold endpoints
# match thermal_to_rgb, and a mid-bar sample near ambient reads as neutral gray.


def test_build_colorbar_gradient_shape_and_endpoints() -> None:
    """The colorbar gradient is (height, 3) uint8; row 0 is the HOT endpoint
    color (matching thermal_to_rgb(HEAT_VIZ_HOT)); the last row is the COLD
    endpoint color (matching thermal_to_rgb(HEAT_VIZ_COLD))."""
    grad = build_colorbar_gradient(50)
    assert grad.shape == (50, 3)
    assert grad.dtype == np.uint8
    # Row 0 == thermal_to_rgb(HEAT_VIZ_HOT); last row == thermal_to_rgb(HEAT_VIZ_COLD).
    hot = thermal_to_rgb(np.array([[HEAT_VIZ_HOT]], dtype=np.float32))[0, 0]
    cold = thermal_to_rgb(np.array([[HEAT_VIZ_COLD]], dtype=np.float32))[0, 0]
    assert tuple(grad[0]) == tuple(hot)
    assert tuple(grad[-1]) == tuple(cold)


def test_build_colorbar_gradient_ambient_is_neutral() -> None:
    """A row near the ambient temperature reads as approximately neutral gray
    (all channels close, no channel strongly saturated). With HEAT_VIZ_HOT well
    above ambient, the neutral point sits near the cold end of the bar, not at
    the geometric middle."""
    grad = build_colorbar_gradient(1000)
    span = HEAT_VIZ_HOT - HEAT_VIZ_COLD
    idx = int(round((HEAT_VIZ_HOT - AMBIENT_TEMP) / span * (1000 - 1)))
    rgb = grad[idx]
    # Near-neutral: R and B channels close (not strongly red or blue).
    assert abs(int(rgb[0]) - int(rgb[2])) < 15, (rgb[0], rgb[2])
    assert rgb[0] < 250 and rgb[2] < 250

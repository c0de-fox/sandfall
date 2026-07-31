"""Tests for the pure temperature-diffusion module (Phase 01).

``diffuse_temps`` is the per-frame heat pre-pass run before the movement
scan. These tests pin its numerical behavior headlessly (no pygame): heat
flows hot→cold, low-conductivity materials transfer slowly, a uniform field
is an equilibrium, the explicit stencil does not overshoot at the
``rate*cond==0.25`` stability bound, results clip to the int16 band, and the
input array is never mutated.
"""

from __future__ import annotations

import numpy as np

from sandfall.config import AMBIENT_TEMP, HEAT_VIZ_COLD, HEAT_VIZ_HOT, TEMP_MAX
from sandfall.elements import ElementId
from sandfall.thermal import build_conductivity_lut, diffuse_temps, thermal_to_rgb


def test_heat_flows_hot_to_cold() -> None:
    # One hot cell in a uniform-conductivity field warms its neighbors next step.
    temp = np.full((3, 3), AMBIENT_TEMP, dtype=np.int16)
    temp[1, 1] = 1000
    ids = np.full((3, 3), int(ElementId.EMPTY), dtype=np.uint8)  # COND_EMPTY
    lut = build_conductivity_lut()
    out = diffuse_temps(temp, ids, lut, rate=0.2)
    # Center cooled; the 4 orthogonal neighbors warmed above ambient.
    assert out[1, 1] < 1000
    for y, x in [(0, 1), (2, 1), (1, 0), (1, 2)]:
        assert out[y, x] > AMBIENT_TEMP, (y, x, out[y, x])
    # Corners are NOT 4-neighbors of center -> unchanged at ambient.
    for y, x in [(0, 0), (0, 2), (2, 0), (2, 2)]:
        assert out[y, x] == AMBIENT_TEMP, (y, x, out[y, x])


def test_low_conductivity_transfers_slowly() -> None:
    # An insulator (STONE, low cond) moves less heat than a conductor (EMPTY).
    base = np.zeros((1, 3), dtype=np.int16)
    base[0, 0] = 0
    base[0, 1] = 1000
    base[0, 2] = 0
    lut = build_conductivity_lut()
    ids_stone = np.full((1, 3), int(ElementId.STONE), dtype=np.uint8)
    ids_empty = np.full((1, 3), int(ElementId.EMPTY), dtype=np.uint8)
    out_stone = diffuse_temps(base.copy(), ids_stone, lut, rate=0.2)
    out_empty = diffuse_temps(base.copy(), ids_empty, lut, rate=0.2)
    # The middle cell cooled more (transferred more) under the higher conductor.
    assert out_empty[0, 1] < out_stone[0, 1]


def test_uniform_field_is_equilibrium() -> None:
    # A uniform-temperature field does not change.
    temp = np.full((5, 5), 300, dtype=np.int16)
    ids = np.full((5, 5), int(ElementId.SAND), dtype=np.uint8)
    out = diffuse_temps(temp, ids, build_conductivity_lut(), rate=0.2)
    assert np.array_equal(out, temp)


def test_no_overshoot_at_stability_bound() -> None:
    # rate*cond == 0.25 (the stability limit) must not overshoot the neighbor
    # mean: a 0/1000 pair cannot swing past [0, 1000].
    temp = np.zeros((1, 2), dtype=np.int16)
    temp[0, 1] = 1000
    ids = np.zeros((1, 2), dtype=np.uint8)  # EMPTY
    lut = build_conductivity_lut()
    out = diffuse_temps(temp, ids, lut, rate=0.25 / lut[int(ElementId.EMPTY)])
    assert int(out.min()) >= 0
    assert int(out.max()) <= 1000


def test_clips_to_int16_band() -> None:
    temp = np.full((2, 2), TEMP_MAX, dtype=np.int16)
    ids = np.full((2, 2), int(ElementId.FIRE), dtype=np.uint8)
    out = diffuse_temps(temp, ids, build_conductivity_lut(), rate=1.0)
    assert int(out.max()) <= TEMP_MAX


def test_diffuse_returns_new_array_does_not_mutate_input() -> None:
    temp = np.full((3, 3), AMBIENT_TEMP, dtype=np.int16)
    temp[1, 1] = 800
    ids = np.full((3, 3), int(ElementId.EMPTY), dtype=np.uint8)
    before = temp.copy()
    diffuse_temps(temp, ids, build_conductivity_lut(), rate=0.2)
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


# --- Heat-overlay gradient (Phase 04) ---------------------------------------
# thermal_to_rgb is a pure numpy map from the int16 temp field to an
# (H, W, 3) uint8 image (blue -> cyan -> neutral -> yellow -> red). These
# tests pin its contract headlessly: shape/dtype, the cold/blue vs hot/red
# ordering, saturation without overflow outside the display band, and that
# ambient reads as a truly neutral gray (the gradient's design pivot).


def test_thermal_to_rgb_shape_and_dtype() -> None:
    temp = np.full((4, 5), 20, dtype=np.int16)
    rgb = thermal_to_rgb(temp)
    assert rgb.shape == (4, 5, 3)
    assert rgb.dtype == np.uint8


def test_thermal_to_rgb_hot_is_redder_than_cold() -> None:
    cold = np.full((1, 1), HEAT_VIZ_COLD, dtype=np.int16)
    hot = np.full((1, 1), HEAT_VIZ_HOT, dtype=np.int16)
    rc = thermal_to_rgb(cold)[0, 0]
    rh = thermal_to_rgb(hot)[0, 0]
    assert rh[0] > rc[0]  # hot has more red
    assert rc[2] > rh[2]  # cold has more blue


def test_thermal_to_rgb_saturates_outside_band() -> None:
    # Clamped to the display band before coloring -> cells at/above
    # HEAT_VIZ_HOT produce identical colors (no uint8 overflow).
    at_band = thermal_to_rgb(np.array([[HEAT_VIZ_HOT]], dtype=np.int16))[0, 0]
    above = thermal_to_rgb(np.array([[HEAT_VIZ_HOT + 5000]], dtype=np.int16))[0, 0]
    below = thermal_to_rgb(np.array([[HEAT_VIZ_COLD - 5000]], dtype=np.int16))[0, 0]
    at_cold = thermal_to_rgb(np.array([[HEAT_VIZ_COLD]], dtype=np.int16))[0, 0]
    assert tuple(at_band) == tuple(above)
    assert tuple(at_cold) == tuple(below)


def test_thermal_to_rgb_ambient_is_neutral() -> None:
    rgb = thermal_to_rgb(np.full((1, 1), AMBIENT_TEMP, dtype=np.int16))[0, 0]
    # Neutral: no channel maxed out (not pure red/blue)...
    assert rgb[0] < 250 and rgb[2] < 250
    # ...and the gradient is pivoted on ambient, so all three channels are
    # exactly equal there (a true flat gray, not merely 'no channel maxed').
    assert rgb[0] == rgb[1] == rgb[2]


def test_thermal_to_rgb_monotone_red_and_blue() -> None:
    # Sweeping cold -> hot, red must not decrease and blue must not increase
    # (a monotone-ish ramp). Sample every 20 degrees across the band.
    temps = np.arange(HEAT_VIZ_COLD, HEAT_VIZ_HOT + 1, 20, dtype=np.int16).reshape(
        1, -1
    )
    rgb = thermal_to_rgb(temps)[0]
    red = rgb[:, 0].astype(int)
    blue = rgb[:, 2].astype(int)
    assert np.all(np.diff(red) >= 0)
    assert np.all(np.diff(blue) <= 0)

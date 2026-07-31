"""Temperature field diffusion + visualization (Phase 01/04).

Pure numpy module: no pygame import, so the diffusion math and the heat->RGB
mapping are unit-testable headlessly. ``diffuse_temps`` is the per-frame heat
pre-pass run by :class:`sandfall.simulation.Simulation` BEFORE the movement
scan; ``build_conductivity_lut`` mirrors :func:`sandfall.renderer.build_color_lut`
to turn the per-material ``COND_*`` scalars into an id-indexed LUT;
``thermal_to_rgb`` maps the int16 temp field to an ``(H, W, 3)`` uint8 image
for the heat-overlay render path (:meth:`sandfall.renderer.Renderer.render_heat`).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .config import (
    COND_EMPTY,
    COND_FIRE,
    COND_GLASS,
    COND_ICE,
    COND_LAVA,
    COND_PLANT,
    COND_SAND,
    COND_SMOKE,
    COND_STEAM,
    COND_STONE,
    COND_WATER,
    COND_WOOD,
    DIFFUSION_RATE,
    HEAT_VIZ_COLD,
    HEAT_VIZ_HOT,
    TEMP_MAX,
    TEMP_MIN,
)
from .elements import AMBIENT_TEMP, ElementId


def build_conductivity_lut() -> npt.NDArray[np.float64]:
    """Build the element-id -> conductivity LUT (mirrors build_color_lut).

    The returned array has shape ``(len(ElementId),)`` and dtype ``float64``;
    row ``int(eid)`` is that material's heat conductivity. Indexed by the
    grid's id array to get a per-cell conductivity field for
    :func:`diffuse_temps`. Sized from ``len(ElementId)`` so it grows
    automatically when Phase 03 adds new element ids.
    """
    lut = np.zeros(len(ElementId), dtype=np.float64)
    lut[int(ElementId.EMPTY)] = COND_EMPTY
    lut[int(ElementId.SAND)] = COND_SAND
    lut[int(ElementId.WATER)] = COND_WATER
    lut[int(ElementId.STONE)] = COND_STONE
    lut[int(ElementId.WOOD)] = COND_WOOD
    lut[int(ElementId.FIRE)] = COND_FIRE
    lut[int(ElementId.SMOKE)] = COND_SMOKE
    lut[int(ElementId.PLANT)] = COND_PLANT
    # Phase 03 new materials (rows 8..11).
    lut[int(ElementId.STEAM)] = COND_STEAM
    lut[int(ElementId.ICE)] = COND_ICE
    lut[int(ElementId.LAVA)] = COND_LAVA
    lut[int(ElementId.GLASS)] = COND_GLASS
    return lut


def diffuse_temps(
    temp: npt.NDArray[np.int16],
    ids: npt.NDArray[np.uint8],
    cond_lut: npt.NDArray[np.float64],
    rate: float = DIFFUSION_RATE,
) -> npt.NDArray[np.int16]:
    """Advance the temperature field one diffusion step. Returns a NEW array.

    Each cell moves toward the 4-neighborhood average weighted by its OWN
    conductivity::

        new = temp + rate * cond[cell] * (left+right+up+down - 4*temp)

    Boundaries are edge-padded (replicate) so the grid walls act as insulators
    (no heat flux across the edge). Computation is done in float64 to avoid
    int16 overflow in the Laplacian (4*temp up to 4*TEMP_MAX), then the result
    is clipped to ``[TEMP_MIN, TEMP_MAX]`` and cast back to int16. The explicit
    stencil is stable when ``rate * max(cond) <= 0.25``; the defaults
    (0.20 * 0.50 == 0.10) sit well inside that bound. Pure / pygame-free ->
    unit-tested headlessly. Does NOT mutate ``temp`` in place; the caller
    (:meth:`Simulation.step`) assigns the result back.
    """
    # Edge-pad so neighbor sums at the border use the border cell itself
    # (insulated walls: no heat crosses the grid edge).
    padded = np.pad(temp, pad_width=1, mode="edge").astype(np.float64)
    left = padded[1:-1, 0:-2]
    right = padded[1:-1, 2:]
    up = padded[0:-2, 1:-1]
    down = padded[2:, 1:-1]
    neighbor_sum = left + right + up + down

    cond = cond_lut[ids]  # per-cell conductivity, shape (H, W) float64
    t = temp.astype(np.float64)
    delta = rate * cond * (neighbor_sum - 4.0 * t)
    new_temp = t + delta
    np.clip(new_temp, TEMP_MIN, TEMP_MAX, out=new_temp)
    return new_temp.astype(np.int16)


# --- Heat-overlay gradient (Phase 04) ---------------------------------------
# The ramp is a 3-stop piecewise lerp on EACH side of ambient:
#   cold side (cold in [0,1]):  neutral -> cyan (0.5) -> deep blue (1)
#   hot  side (hot  in [0,1]):  neutral -> yellow (0.5) -> red (1)
# AMBIENT_TEMP is the shared 0 pivot of both halves, so a cell exactly at
# ambient colors as a flat neutral gray on every channel (true neutrality,
# not just 'no channel maxed'). The band [HEAT_VIZ_COLD, HEAT_VIZ_HOT] is
# asymmetric around ambient because the interesting hot range (fire ~800,
# lava ~1500) is far wider than the cold range.
# The ambient neutral value: a dim gray that reads as 'nothing happening'
# but is visibly lighter than BG_COLOR so ambient cells don't disappear.
_NEUTRAL_BASE = 40.0
# Cold-side stops (R stays at _NEUTRAL_BASE throughout -> not listed).
_CYAN = (40.0, 215.0, 215.0)
_BLUE = (40.0, 40.0, 255.0)
# Hot-side stops (B stays at _NEUTRAL_BASE throughout -> not listed).
_YELLOW = (235.0, 210.0, 40.0)
_RED = (255.0, 40.0, 40.0)


def _lerp3(
    x: npt.NDArray[np.float64], v0: float, vm: float, v1: float
) -> npt.NDArray[np.float64]:
    """Piecewise-linear 3-stop interpolation: ``v0`` at x=0, ``vm`` at x=0.5,
    ``v1`` at x=1.

    ``x`` is assumed already clipped to ``[0, 1]``. Two linear segments meet
    at the midpoint; equivalent to a smooth cold->cyan->blue or
    neutral->yellow->red ramp. Kept module-private: only
    :func:`thermal_to_rgb` uses it.
    """
    low = v0 + (vm - v0) * np.clip(x * 2.0, 0.0, 1.0)  # segment 0 -> 0.5
    high = vm + (v1 - vm) * np.clip((x - 0.5) * 2.0, 0.0, 1.0)  # segment 0.5 -> 1
    return np.where(x <= 0.5, low, high)


def thermal_to_rgb(temp: npt.NDArray[np.int16]) -> npt.NDArray[np.uint8]:
    """Map a temperature field to an ``(H, W, 3)`` uint8 RGB image.

    Gradient (cold -> hot): deep blue -> cyan -> neutral gray (ambient) ->
    yellow -> red. The temp range is clamped to ``[HEAT_VIZ_COLD,
    HEAT_VIZ_HOT]`` so the full color span covers the interesting
    temperatures; out-of-band cells saturate to the endpoint color (the clip
    happens BEFORE coloring, so there is no uint8 overflow).
    ``AMBIENT_TEMP`` is the neutral pivot of the ramp on BOTH sides, so an
    all-ambient scene reads as a flat 'no thermal activity' gray rather than
    a tinted one.

    Pure / pygame-free -> unit-tested headlessly. Output layout matches
    :func:`sandfall.renderer.grid_to_rgb` (row-major ``(H, W, 3)``) so the
    renderer transposes it onto the surface the same way.
    """
    lo = float(HEAT_VIZ_COLD)
    hi = float(HEAT_VIZ_HOT)
    amb = float(AMBIENT_TEMP)
    # Clip to the display band FIRST so out-of-band cells saturate cleanly.
    t = np.clip(temp.astype(np.float64), lo, hi)
    # Normalize each side so AMBIENT is the shared 0 pivot of both halves:
    #   cold in [0,1]: 0 at ambient (or warmer), 1 at HEAT_VIZ_COLD
    #   hot  in [0,1]: 0 at ambient (or cooler), 1 at HEAT_VIZ_HOT
    # The two are mutually exclusive away from ambient (one of (amb-t),(t-amb)
    # is <= 0 and clips to 0), so a cell colors from at most one side at once.
    cold = np.clip((amb - t) / (amb - lo), 0.0, 1.0)
    hot = np.clip((t - amb) / (hi - amb), 0.0, 1.0)

    h, w = temp.shape
    rgb = np.empty((h, w, 3), dtype=np.float64)
    # Red channel: only the hot side contributes (cold leaves it at neutral).
    rgb[..., 0] = _lerp3(hot, _NEUTRAL_BASE, _YELLOW[0], _RED[0])
    # Blue channel: only the cold side contributes (hot leaves it at neutral).
    rgb[..., 2] = _lerp3(cold, _NEUTRAL_BASE, _CYAN[2], _BLUE[2])
    # Green channel: BOTH sides hump through it (cyan on cold, yellow on hot).
    # cold and hot are mutually exclusive away from ambient, so max == sum here;
    # max is used for explicit safety.
    rgb[..., 1] = np.maximum(
        _lerp3(cold, _NEUTRAL_BASE, _CYAN[1], _BLUE[1]),
        _lerp3(hot, _NEUTRAL_BASE, _YELLOW[1], _RED[1]),
    )
    np.clip(rgb, 0.0, 255.0, out=rgb)
    return rgb.astype(np.uint8)

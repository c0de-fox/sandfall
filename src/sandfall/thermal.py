"""Temperature field diffusion + visualization (Phase 01/04).

Pure numpy module: no pygame import, so the diffusion math and the heat->RGB
mapping are unit-testable headlessly. ``diffuse_temps`` is the per-frame heat
pre-pass run by :class:`sandfall.simulation.Simulation` BEFORE the movement
scan; ``build_conductivity_lut`` mirrors :func:`sandfall.renderer.build_color_lut`
to turn the per-material ``COND_*`` scalars into an id-indexed LUT.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from .config import (
    COND_EMPTY,
    COND_FIRE,
    COND_PLANT,
    COND_SAND,
    COND_SMOKE,
    COND_STONE,
    COND_WATER,
    COND_WOOD,
    DIFFUSION_RATE,
    TEMP_MAX,
    TEMP_MIN,
)
from .elements import ElementId


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

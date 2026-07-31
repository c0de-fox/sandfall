"""Glass (SOLID) update rule.

Glass is static: it never moves and never transforms. It is made only by
SAND melting (see :mod:`sandfall.rules.sand`), and once formed it is inert
for the rest of the run. Registered as an explicit no-op so the ``RULES``
registry enumerates every element (mirrors :mod:`sandfall.rules.stone`):
``Simulation.step`` would skip an unregistered element via ``RULES.get``, but
the explicit no-op documents "static" intent and keeps the registry-count
assertion in the phase-03 verification gate honest.
"""

from __future__ import annotations

from ..grid import Grid


def update_glass(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Glass is a static solid. Made by SAND melting; does nothing on its own."""
    return None

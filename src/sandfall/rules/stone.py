"""Stone (SOLID) update rule.

Stone is static: it never moves. Registered as an explicit no-op so the
``RULES`` registry enumerates every element (the simulation loop would
silently skip an unregistered element via ``RULES.get``, but registering
the no-op makes "static" intent explicit and keeps the registry count
assertion in the phase-03 verification gate honest).
"""

from __future__ import annotations

from ..grid import Grid


def update_stone(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Stone never moves."""
    return None

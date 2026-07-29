"""Wood (SOLID) update rule.

Wood is static: it never moves. Its flammability is a *property* on the
``ELEMENTS`` entry (``flammability = 0.25``); the FIRE rule reads that
property to decide whether to ignite a wooden neighbor. This rule itself
does nothing — it exists only to declare wood static in the registry.
"""

from __future__ import annotations

from ..grid import Grid


def update_wood(grid: Grid, x: int, y: int) -> tuple[int, int] | None:
    """Wood never moves; burning is driven by the FIRE rule."""
    return None

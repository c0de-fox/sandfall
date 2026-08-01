#!/usr/bin/env python
"""Generate README screenshots for sandfall.

Initializes pygame headless (SDL_VIDEODRIVER=dummy), builds several pre-configured
scenes, steps the simulation, and saves 800x560 PNGs to ``docs/screenshots/``.

Usage::

    SDL_VIDEODRIVER=dummy uv run python tools/screenshot.py

Re-run after any visual change to regenerate screenshots.
"""

from __future__ import annotations

import os
import random
import sys

os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

# Ensure src/ is on the path when running as a script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sandfall.brush import paint_brush
from sandfall.config import CELL_SIZE, GRID_HEIGHT, GRID_WIDTH
from sandfall.elements import ELEMENTS, ElementId
from sandfall.grid import Grid
from sandfall.renderer import Renderer
from sandfall.simulation import Simulation

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "docs", "screenshots")
W, H = GRID_WIDTH, GRID_HEIGHT  # 200 x 140
OUT_W, OUT_H = W * CELL_SIZE, H * CELL_SIZE  # 800 x 560


def _fill_rect(grid: Grid, x0: int, y0: int, x1: int, y1: int, eid: ElementId) -> None:
    """Fill a rectangular region with one element via paint_brush (sets temp/life)."""
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            paint_brush(grid, x, y, 0, eid)


def _wall(grid: Grid, x0: int, y0: int, x1: int, y1: int) -> None:
    """Place a stone wall."""
    for y in range(max(0, y0), min(H, y1)):
        for x in range(max(0, x0), min(W, x1)):
            grid.set(x, y, ElementId.STONE)


def _save(surface: pygame.Surface, name: str) -> None:
    path = os.path.join(OUTPUT_DIR, f"{name}.png")
    pygame.image.save(surface, path)
    print(f"  saved {path}")


def render_elemental(renderer: Renderer) -> pygame.Surface:
    """All 17 elements in a 6x3 grid of stone-walled blocks."""
    grid = Grid(W, H)
    elements = [e for e in ElementId if e != ElementId.EMPTY]
    cols, rows = 6, 3
    bw = W // cols
    bh = H // rows
    gap = 2
    for i, eid in enumerate(elements):
        cx, cy = i % cols, i // cols
        x0 = cx * bw + gap
        y0 = cy * bh + gap
        _fill_rect(grid, x0, y0, x0 + bw - gap, y0 + bh - gap, eid)
    # No stepping — static color display.
    return renderer.render(grid)


def render_volcano(renderer: Renderer) -> pygame.Surface:
    """Lava pool + sand layer + fire/smoke. Shows glass formation."""
    random.seed(42)
    grid = Grid(W, H)
    _wall(grid, 0, 0, 1, H)  # left wall
    _wall(grid, W - 1, 0, W, H)  # right wall
    _wall(grid, 0, H - 1, W, H)  # floor
    # Lava pool bottom.
    _fill_rect(grid, 2, H - 12, W - 2, H - 1, ElementId.LAVA)
    # Sand layer above lava.
    _fill_rect(grid, 2, H - 20, W - 2, H - 12, ElementId.SAND)
    # Some fire on top of the sand.
    for x in range(60, 140, 8):
        paint_brush(grid, x, H - 22, 2, ElementId.FIRE)
    sim = Simulation(grid)
    for _ in range(100):
        sim.step()
    return renderer.render(grid)


def render_water_cycle(renderer: Renderer) -> pygame.Surface:
    """Water pool with dry ice (freezing) on one side, fire (boiling) on the other."""
    random.seed(7)
    grid = Grid(W, H)
    _wall(grid, 0, 0, 1, H)
    _wall(grid, W - 1, 0, W, H)
    _wall(grid, 0, H - 1, W, H)
    # Water pool.
    _fill_rect(grid, 2, H - 20, W - 2, H - 1, ElementId.WATER)
    # Dry ice block on the left (freezes water).
    _fill_rect(grid, 2, H - 20, 20, H - 10, ElementId.DRY_ICE)
    # Fire on the right (boils water).
    for x in range(160, 195, 6):
        paint_brush(grid, x, H - 22, 2, ElementId.FIRE)
    sim = Simulation(grid)
    for _ in range(120):
        sim.step()
    return renderer.render(grid)


def render_oil_fire(renderer: Renderer) -> pygame.Surface:
    """Oil slick on water, ignited at one end."""
    random.seed(3)
    grid = Grid(W, H)
    _wall(grid, 0, 0, 1, H)
    _wall(grid, W - 1, 0, W, H)
    _wall(grid, 0, H - 1, W, H)
    # Water pool.
    _fill_rect(grid, 2, H - 15, W - 2, H - 1, ElementId.WATER)
    # Oil on top (floats).
    _fill_rect(grid, 2, H - 18, W - 2, H - 15, ElementId.OIL)
    # Ignite left end.
    for x in range(4, 20, 4):
        paint_brush(grid, x, H - 19, 2, ElementId.FIRE)
    sim = Simulation(grid)
    for _ in range(60):
        sim.step()
    return renderer.render(grid)


def render_explosion(renderer: Renderer) -> None:
    """Gunpowder pile mid-detonation."""
    random.seed(99)
    grid = Grid(W, H)
    _wall(grid, 0, 0, 1, H)
    _wall(grid, W - 1, 0, W, H)
    _wall(grid, 0, H - 1, W, H)
    # Sand floor context.
    _fill_rect(grid, 2, H - 10, W - 2, H - 1, ElementId.SAND)
    # Gunpowder pile in the center.
    _fill_rect(grid, 80, H - 18, 120, H - 10, ElementId.GUNPOWDER)
    # Some wood nearby for visual context.
    _fill_rect(grid, 30, H - 15, 50, H - 10, ElementId.WOOD)
    _fill_rect(grid, 150, H - 15, 170, H - 10, ElementId.WOOD)
    sim = Simulation(grid)
    # Ignite the gunpowder.
    grid.set_temp(95, H - 16, 500.0)
    for _ in range(8):
        sim.step()
    return renderer.render(grid)


def render_acid_base(renderer: Renderer) -> pygame.Surface:
    """Acid eating a sand wall; base eating a glass wall; neutralization steam."""
    random.seed(11)
    grid = Grid(W, H)
    _wall(grid, 0, 0, 1, H)
    _wall(grid, W - 1, 0, W, H)
    _wall(grid, 0, H - 1, W, H)
    # Sand wall in the left half (acid eats from the left).
    _fill_rect(grid, 2, H - 25, 60, H - 1, ElementId.SAND)
    # Acid pool to the left of the sand wall.
    _fill_rect(grid, 2, H - 10, 60, H - 1, ElementId.ACID)  # overwrites some sand
    _fill_rect(grid, 2, H - 25, 5, H - 1, ElementId.ACID)
    # Glass wall in the right half (base eats from the right).
    _fill_rect(grid, 140, H - 25, W - 2, H - 1, ElementId.GLASS)
    # Base pool to the right of the glass wall.
    _fill_rect(grid, W - 8, H - 25, W - 2, H - 1, ElementId.BASE)
    _fill_rect(grid, 140, H - 25, 145, H - 1, ElementId.BASE)  # overwrites some glass
    sim = Simulation(grid)
    for _ in range(120):
        sim.step()
    return renderer.render(grid)


def render_heat_overlay(renderer: Renderer) -> pygame.Surface:
    """Volcano scene rendered in heat-overlay mode (temperature colors)."""
    random.seed(42)
    grid = Grid(W, H)
    _wall(grid, 0, 0, 1, H)
    _wall(grid, W - 1, 0, W, H)
    _wall(grid, 0, H - 1, W, H)
    _fill_rect(grid, 2, H - 12, W - 2, H - 1, ElementId.LAVA)
    _fill_rect(grid, 2, H - 20, W - 2, H - 12, ElementId.SAND)
    for x in range(60, 140, 8):
        paint_brush(grid, x, H - 22, 2, ElementId.FIRE)
    sim = Simulation(grid)
    for _ in range(100):
        sim.step()
    return renderer.render_heat(grid)


SCENES = [
    ("elemental", render_elemental),
    ("volcano", render_volcano),
    ("water_cycle", render_water_cycle),
    ("oil_fire", render_oil_fire),
    ("explosion", render_explosion),
    ("acid_base", render_acid_base),
    ("heat_overlay", render_heat_overlay),
]


def main() -> int:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pygame.init()
    renderer = Renderer()
    for name, fn in SCENES:
        print(f"Rendering {name}...")
        small = fn(renderer)
        scaled = pygame.transform.scale(small, (OUT_W, OUT_H))
        _save(scaled, name)
    pygame.quit()
    print(f"\nDone — {len(SCENES)} screenshots in {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

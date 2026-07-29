"""Pure pause/step state machine for the game loop.

The :class:`LoopController` decides whether the simulation should advance on a
given frame. It is deliberately pygame-free so its transitions can be unit
tested headlessly. The :class:`~sandfall.game.Game` owns one instance, feeds
it input events (``toggle_pause`` on SPACE, ``request_step`` on N while
paused), and asks ``consume_step`` once per frame to decide whether to call
``Simulation.step``.

Behavior:

* While **not** paused, ``consume_step`` returns ``True`` every frame (the sim
  runs continuously).
* While **paused**, ``consume_step`` returns ``False`` by default (the sim is
  frozen), but returns ``True`` for exactly one frame after ``request_step``
  is called (single-stepping).
* ``request_step`` while not paused is a no-op (the sim is already running).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class LoopController:
    """Pause/single-step state for the main loop."""

    paused: bool = False
    _step_once: bool = False

    def toggle_pause(self) -> None:
        """Flip the paused flag (bound to SPACE)."""
        self.paused = not self.paused

    def request_step(self) -> None:
        """Request exactly one sim step on the next ``consume_step`` call.

        Only meaningful while paused; while running it is a no-op (the sim is
        already stepping every frame). Bound to the N key.
        """
        if self.paused:
            self._step_once = True

    def consume_step(self) -> bool:
        """Return whether the sim should advance on this frame, clearing a pending step.

        Returns ``True`` every frame while running, ``True`` for exactly one
        frame after a step is requested while paused, and ``False`` otherwise.
        A pending single-step request is dropped if the sim is un-paused before
        it fires (the continuous run already advanced the sim, so a stale
        request must not surprise the user after a later re-pause).
        """
        if not self.paused:
            self._step_once = False
            return True
        if self._step_once:
            self._step_once = False
            return True
        return False

"""Headless tests for the pause/step state machine.

:class:`LoopController` is the pure decision box the :class:`Game` consults each
frame: it returns whether the simulation should advance. These tests pin its
state transitions without spinning up pygame or the real loop.
"""

from __future__ import annotations

from sandfall.control import LoopController


def test_initial_state_runs_continuously() -> None:
    loop = LoopController()

    assert loop.paused is False
    # While running, every frame steps.
    assert loop.consume_step() is True
    assert loop.consume_step() is True


def test_toggle_pause_freezes_the_sim() -> None:
    loop = LoopController()

    loop.toggle_pause()

    assert loop.paused is True
    assert loop.consume_step() is False
    assert loop.consume_step() is False


def test_toggle_pause_is_reversible() -> None:
    loop = LoopController()

    loop.toggle_pause()
    assert loop.paused is True
    loop.toggle_pause()
    assert loop.paused is False
    assert loop.consume_step() is True


def test_request_step_advances_exactly_one_frame_while_paused() -> None:
    loop = LoopController()
    loop.toggle_pause()
    assert loop.consume_step() is False  # frozen

    loop.request_step()
    assert loop.consume_step() is True  # the one requested step
    assert loop.consume_step() is False  # frozen again
    assert loop.consume_step() is False


def test_request_step_while_running_is_a_noop() -> None:
    """Requesting a step while not paused does not queue extra steps."""
    loop = LoopController()

    loop.request_step()
    # Still just "running" — every frame steps; no extra queued behavior.
    assert loop.consume_step() is True
    assert loop.consume_step() is True


def test_multiple_step_requests_collapse_to_one_step() -> None:
    """Repeated N presses before the frame ticks produce a single advance."""
    loop = LoopController()
    loop.toggle_pause()

    loop.request_step()
    loop.request_step()
    loop.request_step()

    assert loop.consume_step() is True  # one step consumed
    assert loop.consume_step() is False  # no further steps queued


def test_step_request_does_not_persist_across_pause_cycles() -> None:
    loop = LoopController()
    loop.toggle_pause()
    loop.request_step()
    # Un-pause before the step was consumed; running dominates anyway.
    loop.toggle_pause()
    assert loop.consume_step() is True
    # Re-pause: the old request must not have leaked through.
    loop.toggle_pause()
    assert loop.consume_step() is False

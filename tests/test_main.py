"""Tests for the entry-point helper :func:`sandfall.__main__._prefer_x11_video_driver`.

The interactive resize itself needs a real display, but the SDL-driver
*preference* is pure env/platform logic and is worth pinning down so a future
change does not silently stop preferring X11 on Linux (which is what makes
VIDEORESIZE-based resizing work on Wayland sessions).
"""

import os
import sys

import pytest

from sandfall.__main__ import _prefer_x11_video_driver


def test_prefers_x11_when_unset_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDL_VIDEODRIVER", raising=False)
    if not sys.platform.startswith("linux"):
        pytest.skip("X11 preference only applies on Linux")
    _prefer_x11_video_driver()
    assert os.environ["SDL_VIDEODRIVER"] == "x11"


def test_respects_existing_video_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    # An explicit export (e.g. SDL_VIDEODRIVER=dummy for headless runs, or a
    # user's deliberate choice) must never be overridden.
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    _prefer_x11_video_driver()
    assert os.environ["SDL_VIDEODRIVER"] == "dummy"


def test_no_op_off_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SDL_VIDEODRIVER", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    _prefer_x11_video_driver()
    assert "SDL_VIDEODRIVER" not in os.environ

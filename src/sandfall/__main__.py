"""Entry point for the ``sandfall`` console script."""

import os
import sys

__all__ = ["main"]


def _prefer_x11_video_driver() -> None:
    """Prefer the X11 SDL video driver on Linux.

    pygame (SDL2) handles an interactive window resize by re-calling
    ``display.set_mode`` on each ``VIDEORESIZE`` event (see
    :meth:`sandfall.game.Game._handle_resize`). On a Wayland session that
    fights the compositor: the compositor configures a new size, the app
    acknowledges it via ``set_mode``, and the window flickers / snaps back
    instead of resizing (fullscreen still works because it is a state toggle,
    not a size request). The X11 driver runs via XWayland on Wayland desktops
    and resizes the classic way, which ``set_mode``-on-resize works correctly
    with. XWayland is universally available on Linux desktops.

    An explicit ``SDL_VIDEODRIVER`` export is honored (the user / a parent
    process can opt out). Must run before ``pygame.display`` is initialized,
    hence the call at the top of :func:`main`.
    """
    if sys.platform.startswith("linux") and "SDL_VIDEODRIVER" not in os.environ:
        os.environ["SDL_VIDEODRIVER"] = "x11"


def main() -> int:
    """Run the sandfall game.

    The ``Game`` import is lazy so that merely importing this module (e.g.
    from tests, where there may be no display) does not pull in pygame or open
    a window.

    An absolute import is used (rather than ``from .game import Game``) so the
    module also works as a PyInstaller entry script: when PyInstaller runs this
    file as the top-level ``__main__`` it has no parent package, so a relative
    import would fail. Absolute imports resolve correctly in all three
    contexts (``python -m sandfall``, the ``sandfall`` console script, and the
    frozen one-file binary).
    """
    _prefer_x11_video_driver()
    from sandfall.game import Game

    return Game().run()


if __name__ == "__main__":
    raise SystemExit(main())

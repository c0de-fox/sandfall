"""Entry point for the ``sandfall`` console script."""

__all__ = ["main"]


def main() -> int:
    """Run the sandfall game.

    The ``Game`` import is lazy so that merely importing this module (e.g.
    from tests, where there may be no display) does not pull in pygame or open
    a window.
    """
    from .game import Game

    return Game().run()


if __name__ == "__main__":
    raise SystemExit(main())

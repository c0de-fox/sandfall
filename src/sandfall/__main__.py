"""Entry point for the ``sandfall`` console script."""

__all__ = ["main"]


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
    from sandfall.game import Game

    return Game().run()


if __name__ == "__main__":
    raise SystemExit(main())

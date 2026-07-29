"""Entry point for the ``sandfall`` console script.

The ``Game`` import is intentionally lazy (deferred inside :func:`main`) so
that merely importing this module (e.g. from a test, where there may be no
display) does not pull in pygame or open a window. An absolute import
(``from sandfall.game import Game``) is used rather than a relative one so
this module also works as a PyInstaller entry script: when PyInstaller runs
this file as the top-level ``__main__`` it has no parent package, so a
relative import would fail. Absolute imports resolve correctly in all three
contexts (``python -m sandfall``, the ``sandfall`` console script, and the
frozen one-file binary).
"""

__all__ = ["main"]


def main() -> int:
    """Run the sandfall game."""
    from sandfall.game import Game

    return Game().run()


if __name__ == "__main__":
    raise SystemExit(main())

"""Package-level smoke tests: imports succeed and the CLI entry is wired up.

These were the original Phase 01 sanity tests; they previously lived in
``tests/test_smoke.py`` but were relocated to avoid a filename collision
with the Phase 03 SMOKE-element physics tests.

Phase 04 made ``main()`` open a real pygame window, so we no longer call it
directly here (that would hang in a headless environment). Instead we assert
it is callable and that merely importing the entry module does NOT import
pygame (lazy-import contract). The full run-loop is exercised separately via
the ``SANDFALL_FRAMES`` env-var seam (see the Phase 04 verification commands).
"""


def test_package_imports() -> None:
    import sandfall

    assert sandfall.__version__


def test_main_is_callable_and_lazy() -> None:
    import sys

    # The Game import is deferred inside main(): importing the entry module
    # must not load ``sandfall.game`` (which would pull in pygame and, when
    # main() is actually called, open a window). We check the mechanism here;
    # the stricter "pygame absent from a clean interpreter" assertion is run
    # separately as a phase-04 gate (``uv run python -c "import sandfall;
    # assert 'pygame' not in sys.modules"``).
    from sandfall import __main__ as entry

    assert callable(entry.main)
    assert "sandfall.game" not in sys.modules

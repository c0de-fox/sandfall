"""Package-level smoke tests: imports succeed and the CLI entry returns 0.

These were the original Phase 01 sanity tests; they previously lived in
``tests/test_smoke.py`` but were relocated to avoid a filename collision
with the Phase 03 SMOKE-element physics tests.
"""


def test_package_imports() -> None:
    import sandfall

    assert sandfall.__version__


def test_main_returns_zero() -> None:
    from sandfall.__main__ import main

    assert main() == 0

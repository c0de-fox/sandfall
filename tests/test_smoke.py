"""Smoke test: the package imports and the entry stub returns 0."""


def test_package_imports() -> None:
    import sandfall

    assert sandfall.__version__


def test_main_returns_zero() -> None:
    from sandfall.__main__ import main

    assert main() == 0

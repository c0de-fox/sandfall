"""Static checks on the PyInstaller spec.

These do NOT run PyInstaller (far too slow for the normal test loop); they
just assert the spec file exists and is configured for a one-file build.
The actual binary build is a separate ``uv run pyinstaller`` step.
"""

from pathlib import Path


def test_spec_file_exists() -> None:
    assert Path("sandfall.spec").is_file()


def test_spec_is_onefile() -> None:
    text = Path("sandfall.spec").read_text()
    # one-file == EXE collects binaries+datas directly; NO COLLECT block
    # (a COLLECT block would make this a --onedir build instead).
    assert "COLLECT(" not in text
    assert 'name="sandfall"' in text or "name='sandfall'" in text


def test_spec_uses_entry_point() -> None:
    text = Path("sandfall.spec").read_text()
    # entry must be the console-script target's __main__
    assert "src/sandfall/__main__.py" in text


def test_spec_collects_pygame_and_numpy() -> None:
    text = Path("sandfall.spec").read_text()
    # belt-and-suspenders: pulls data + binaries + hidden imports for both
    assert 'collect_all("pygame")' in text
    assert 'collect_all("numpy")' in text


def test_spec_release_mode_suppresses_console_and_traceback() -> None:
    """Release builds must not attach a console window or pop a traceback
    dialog (SECURITY.md / audit finding L2, CWE-209). Dev builds keep both
    visible so startup tracebacks are easy to see while iterating.

    The ``console`` and ``disable_windowed_traceback`` EXE() options are
    driven by the ``SANDFALL_RELEASE`` env var (a release binary is produced
    with ``SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec``) so a release
    build never needs the spec edited by hand. This test guards against an
    accidental regression to a hardcoded ``console=True`` debug build.
    """
    text = Path("sandfall.spec").read_text()
    compact = text.replace(" ", "")

    # The env-var mechanism must be present.
    assert "SANDFALL_RELEASE" in text
    # No hardcoded console literal anywhere in the spec.
    assert "console=True" not in text
    assert "console=False" not in text
    # Both EXE() options must reference the derived variables, not literals.
    assert "console=console" in compact
    assert "disable_windowed_traceback=disable_windowed_traceback" in compact

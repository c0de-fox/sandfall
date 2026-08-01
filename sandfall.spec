# sandfall.spec
# PyInstaller spec for the sandfall single-file build (Linux / Windows / macOS).
#
# Build with:  uv run pyinstaller sandfall.spec --noconfirm
# Output:      dist/sandfall   (single self-contained executable, --onefile)
#
# Notes:
#   - This is a ONE-FILE spec: the EXE() is built directly from
#     PYZ + a.scripts + a.binaries + a.datas. There is intentionally no
#     COLLECT block -- adding one would turn this into a --onedir build
#     (a directory of loose files) instead of a single executable.
#   - console / disable_windowed_traceback are driven by the SANDFALL_RELEASE
#     env var (see the release block below): dev builds attach a console so
#     any startup traceback is visible on stderr; release builds
#     (SANDFALL_RELEASE=1) detach it so no terminal window pops up and no
#     windowed-traceback dialog leaks internal paths. See SECURITY.md.
#   - block_cipher is intentionally omitted: PyInstaller >= 6.0 deprecated
#     it and passing cipher=... emits a DeprecationWarning. Omitting it is
#     the clean fix (we are not relying on bytecode encryption anyway).
#   - collect_all('pygame') / collect_all('numpy') is belt-and-suspenders:
#     it pulls in each package's data files, native binaries, AND hidden
#     imports in one call. pygame-ce (the dist name) imports as 'pygame',
#     so we collect under the 'pygame' import name.
#   - Analysis / PYZ / EXE below are NOT undefined -- PyInstaller injects
#     them (plus COLLECT, BUNDLE) into the spec's global namespace at build
#     time. ruff therefore reports F821 if invoked explicitly on this file
#     (`ruff check sandfall.spec`); the default `ruff check .` and
#     `ruff format --check .` gates skip `.spec` files automatically
#     (ruff's default include glob is *.py/*.pyi/*.ipynb), so this is
#     expected and harmless.

from PyInstaller.utils.hooks import collect_all

# Each collect_all() returns (datas, binaries, hiddenimports) for that package.
pg_datas, pg_binaries, pg_hidden = collect_all("pygame")
np_datas, np_binaries, np_hidden = collect_all("numpy")

# --- Release vs development build -------------------------------------------
# A RELEASE build must not attach a console window or pop a windowed-traceback
# dialog (both can leak internal file paths / tracebacks to end users -- see
# SECURITY.md and audit finding L2 / CWE-209). Build a release binary with:
#   SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm
# Dev builds (env unset) keep a console attached so startup tracebacks are
# visible on stderr while iterating on the build.
import os

_IS_RELEASE = os.environ.get("SANDFALL_RELEASE", "") == "1"
console = not _IS_RELEASE                 # dev: True | release: False
disable_windowed_traceback = _IS_RELEASE  # dev: False | release: True

a = Analysis(
    ["src/sandfall/__main__.py"],
    pathex=["src"],
    binaries=pg_binaries + np_binaries,
    datas=pg_datas + np_datas,
    hiddenimports=pg_hidden + np_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="sandfall",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,  # compress the single file; harmless no-op if UPX is absent
    upx_exclude=[],
    runtime_tmpdir=None,
    console=console,  # dev: True (tracebacks visible) | release: False
    disable_windowed_traceback=disable_windowed_traceback,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

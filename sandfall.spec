# sandfall.spec
# PyInstaller spec for the sandfall single-file Linux build.
#
# Build with:  uv run pyinstaller sandfall.spec --noconfirm
# Output:      dist/sandfall   (single self-contained executable, --onefile)
#
# Notes:
#   - This is a ONE-FILE spec: the EXE() is built directly from
#     PYZ + a.scripts + a.binaries + a.datas. There is intentionally no
#     COLLECT block -- adding one would turn this into a --onedir build
#     (a directory of loose files) instead of a single executable.
#   - console=True so any startup traceback is visible on stderr (helpful
#     while verifying the build). Flip to console=False for a release GUI
#     build on Linux (no terminal window pops up).
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
    console=True,  # flip to False for a release GUI build
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

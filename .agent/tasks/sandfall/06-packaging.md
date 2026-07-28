# Phase 06: PyInstaller Single-Binary Packaging (Linux)

## Objective

Produce a single self-contained Linux executable `dist/sandfall` (one file, no Python install required) via PyInstaller `--onefile`, using a tracked `sandfall.spec`. Document the build in `AGENTS.md`. This closes out the v1 vertical slice.

**Scope (binding — from the approved plan):** Linux `--onefile` only. Windows, macOS, and CI are **explicitly deferred** — do NOT add phases or work for them here; record them as future work.

## Depends On

Phase 04 (the game must run via `uv run sandfall` before packaging it). Phase 03 (elements) and Phase 05 (UI) make the binary actually interesting, but the packaging mechanism itself only needs a working `Game`/`main()`.

## Can Parallelize With

Phase 05 (UI). Disjoint files: this phase = `sandfall.spec` + `pyproject.toml` dev-dep + `AGENTS.md` build section; Phase 05 = `ui.py` + `game.py` + tests. Merge conflict risk ~zero (only `pyproject.toml` is shared; coordinate by adding `pyinstaller` to the dev group, which Phase 05 does not touch).

## Recommended Agent

@implementer

## Changes Required

- `pyproject.toml` — EDIT: add `pyinstaller` to the `dev` dependency group.
- `sandfall.spec` — NEW. PyInstaller spec, tracked in git (do NOT ignore `*.spec`).
- `.gitignore` — confirm `build/` and `dist/` are ignored (they are, from Phase 01) but `sandfall.spec` is NOT ignored.
- `AGENTS.md` — EDIT: add a `## Building` section documenting the Linux build.
- `tests/test_packaging.py` — NEW (optional). Asserts the spec file parses / key options are set. (Cannot assert the binary exists in normal test runs; that's a build-step concern.)

## Implementation Instructions

### Step 1: Add `pyinstaller` to dev deps

Edit `pyproject.toml` `[dependency-groups].dev` to include:

```toml
[dependency-groups]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
    "mypy>=1.11",
    "pyinstaller>=6.0",
]
```

Then `uv sync` to install it.

### Step 2: Create `sandfall.spec` (tracked)

PyInstaller spec for a `--onefile` Linux build. Start with `console=True` so the first build is debuggable (any startup errors print to the terminal); a later polish commit can flip to `console=False` once the binary is known-good.

```python
# sandfall.spec
# PyInstaller spec for the sandfall single-file Linux build.
# Build with:  uv run pyinstaller sandfall.spec
# Output:      dist/sandfall  (single self-contained executable)

from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# pygame-ce ships font data + native libs; collect them explicitly.
pygame_datas = collect_data_files("pygame")
pygame_ce_datas = collect_data_files("pygame_ce")

a = Analysis(
    ["src/sandfall/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=pygame_datas + pygame_ce_datas,
    hiddenimports=[
        "pygame",
        "pygame.font",
        "pygame.surfarray",
        "numpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

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
    upx=True,                       # compress the single file (UPX optional; remove if it causes issues)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                   # flip to False once the build is verified
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
```

> Note: with `--onefile` (single EXE collecting binaries+datas into the EXE call), there is NO `COLLECT(...)` step. The spec above already reflects that. Do not add a `COLLECT` block — that would produce a directory (`--onedir`), not a single file.

If `uv run pyinstaller sandfall.spec` complains about `pygame_ce` not being a package (the import name is `pygame`, the dist name is `pygame-ce`), drop the `pygame_ce_datas` line and rely on `pygame_datas` only. Document whichever works in the reflection.

### Step 3: Build

```bash
uv run pyinstaller sandfall.spec --clean --noconfirm
```

`--clean` clears PyInstaller cache; `--noconfirm` overwrites `dist/` without prompting. Output: `dist/sandfall` (a single executable).

### Step 4: Verify the binary

```bash
./dist/sandfall
```

**MANUAL**: the game window opens, paints/falls work, ESC quits, no "module not found" / traceback. If the window fails to open with a missing-module error, add the module to `hiddenimports` in the spec and rebuild.

### Step 5: Document in `AGENTS.md`

Append a new section:

```markdown
## Building (Linux)

Produces a single self-contained executable at `dist/sandfall`.

```bash
uv sync                       # ensures pyinstaller is installed (dev dep)
uv run pyinstaller sandfall.spec --clean --noconfirm
./dist/sandfall               # run it
```

The spec (`sandfall.spec`) is tracked in git; `build/` and `dist/` are gitignored.

### Platform status

- **Linux**: supported via the `sandfall.spec` above (`--onefile`).
- **Windows / macOS**: not yet supported (future work). Will need platform-specific specs + native build runners.
- **CI**: not yet configured (future work).
```

### Step 6: Optional `tests/test_packaging.py`

A lightweight, fast test that does NOT actually run PyInstaller (too slow for the normal test loop):

```python
"""Static checks on the PyInstaller spec."""

from pathlib import Path


def test_spec_file_exists() -> None:
    assert Path("sandfall.spec").is_file()


def test_spec_is_onefile() -> None:
    text = Path("sandfall.spec").read_text()
    # onefile == EXE collects binaries+datas (no COLLECT block)
    assert "COLLECT(" not in text
    assert "name=\"sandfall\"" in text or "name='sandfall'" in text
```

Run via `uv run pytest tests/test_packaging.py` (it will be picked up by the normal `uv run pytest` too — that's fine).

## Acceptance Criteria

- [ ] `pyinstaller>=6.0` is in the `dev` dependency group and `uv sync` succeeds.
- [ ] `sandfall.spec` exists, is tracked, and is configured for `--onefile` (no `COLLECT` block), entry `src/sandfall/__main__.py`, name `sandfall`.
- [ ] `uv run pyinstaller sandfall.spec --clean --noconfirm` exits zero.
- [ ] `dist/sandfall` exists and is a single file (`test -f dist/sandfall`).
- [ ] `./dist/sandfall` opens the game window and runs without a Python traceback (manual).
- [ ] `AGENTS.md` has a `## Building (Linux)` section with the exact build commands and a "Platform status" note marking Windows/mac/CI as future work.
- [ ] `.gitignore` ignores `dist/` and `build/` but NOT `sandfall.spec`.
- [ ] All five automated verification gates pass.

## Verification Commands

```bash
# Automated gates
uv run python -c "import sandfall; print('ok')"
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src

# Packaging-specific
uv run pyinstaller sandfall.spec --clean --noconfirm      # exit zero
test -f dist/sandfall && echo "binary present"            # exit zero
```

Manual:
```bash
./dist/sandfall    # window opens, plays, ESC quits, no traceback
```

ALL automated gates + the PyInstaller build + `test -f dist/sandfall` must exit zero. This completes v1.

## Documentation Updates

- `AGENTS.md` — `## Building (Linux)` + Platform status (in-phase, above).
- Write `.agent/tasks/sandfall/06-packaging-reflection.md`. Capture: which `hiddenimports`/`collect_data_files` were actually needed, whether `console=True`/`False` was settled on, the final binary size, whether UPX was kept, and the recommended next steps for Windows/mac (cross-compilation vs native runners) — for the future-work backlog.

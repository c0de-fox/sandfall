# Sand Falling Game

(WIP name)

## PROMPT

We are developing a sand falling game similar to "sand:box", atom craft, the powder toy, sandustry, etc (there are many of these kinds of games, these are just some examples)

I want to use pygame for this. This project should use uv to manage python and dependencies.

Create a build system that produces a single self-contained binary for each platform (windows and linux, mac is optional).

Use the agents that are available to you for your work. 
All work must be planned using the task manager agent.

## Commands

All commands run from the repo root.

- **Run the game:** `uv run sandfall`
- **Run tests:** `uv run pytest`
- **Lint:** `uv run ruff check .`
- **Format:** `uv run ruff format .`
- **Type-check:** `uv run mypy src`
- **Sync deps:** `uv sync`
- **Build single-file binary (Linux):** `uv run pyinstaller sandfall.spec --noconfirm`

Python and dependencies are managed by `uv`. The lockfile (`uv.lock`) is committed.

## Building

Produces a single self-contained executable at `dist/sandfall` (no Python
install required on the target machine).

```bash
uv sync                                    # ensures pyinstaller is installed (it's a dev dep)
uv run pyinstaller sandfall.spec --noconfirm
./dist/sandfall                            # run it
```

Notes:

- `sandfall.spec` is a hand-written PyInstaller spec, **tracked in git**.
  It is a `--onefile` build: the `EXE(...)` is built directly from
  `PYZ + a.scripts + a.binaries + a.datas`, with intentionally **no
  `COLLECT` block** (a `COLLECT` block would produce a `--onedir` output
  — a directory of loose files — instead of a single executable).
- `build/` and `dist/` are **gitignored**.
- The spec uses `collect_all('pygame')` and `collect_all('numpy')` to pull
  in each package's data files, native binaries, and hidden imports in one
  call (belt-and-suspenders). pygame-ce's dist name is `pygame-ce` but it
  imports as `pygame`, so collection uses the `pygame` import name.
- `console=True` is set in the spec so any startup traceback is visible on
  stderr (useful while verifying the build). Flip to `console=False` for a
  release GUI build on Linux so no terminal window pops up.
- UPX compression (`upx=True`) is enabled but is a harmless no-op when UPX
  is not installed on the build host.
- Typical binary size: ~50 MiB (mostly SDL + numpy native libs).

## Future Work

Cross-platform packaging has **shipped**:

- **Windows, Linux, and macOS single-file binaries** are built automatically
  by GitHub Actions. `.github/workflows/release.yml` runs
  `SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm` on
  `ubuntu-latest`, `windows-latest`, and `macos-latest` runners, renames each
  output to a distinct asset (`sandfall-linux-x86_64`,
  `sandfall-windows-x86_64.exe`, `sandfall-macos-arm64`), and attaches them
  to the release created by every `v*` tag. `.github/workflows/ci.yml` runs
  the Linux quality gate (ruff / mypy / pytest + a build-smoke) on every
  push and pull request. The `--onefile` `sandfall.spec` needed **only a
  header-comment refresh** — it was already portable (env-driven `console` +
  `collect_all`, PyInstaller auto-selects the bootloader). macOS ships as a
  **bare executable** (no `.app` bundle — a `BUNDLE`/`COLLECT` block would
  collide with the `--onefile` design).

The **only** remaining deferred packaging sub-item is:

- **Code-signing / notarization.** A Windows code-signing cert and a macOS
  Developer ID + `notarytool` need credentials the project does not yet have.
  Until then v1 ships **unsigned** binaries (Windows SmartScreen + macOS
  Gatekeeper "unidentified developer" warnings — documented as the v1
  caveat in the README). This is the natural place to apply signing once
  credentials exist.


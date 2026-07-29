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

Cross-platform packaging is **deferred** (out of scope for v1; tracked here
so it isn't forgotten):

- **Windows `.exe` and macOS `.app` builds.** PyInstaller cannot
  cross-compile: a Windows executable must be produced on Windows, a macOS
  app on macOS. The `sandfall.spec` should generalize cleanly (the only
  platform-specific lines are `console=` and the bootloader selection,
  which PyInstaller picks automatically), but it has only been validated
  on Linux x86-64 so far. Each platform will likely need its own
  `.spec` tweaks (icon, code-signing identity, `console=False` for GUI).
- **CI matrix (GitHub Actions).** Once the per-platform specs are drafted,
  a CI workflow should run `uv sync && uv run pyinstaller <spec>` on
  `windows-latest`, `macos-latest`, and `ubuntu-latest` runners and upload
  the resulting `dist/sandfall*` artifacts against each release tag. This
  is the natural place to also flip `console=False` and apply signing.


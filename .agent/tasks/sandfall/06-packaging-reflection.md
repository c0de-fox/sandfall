# Phase 06 Reflection — PyInstaller Single-Binary Packaging (Linux)

## What was done

Closed out the v1 vertical slice: produced a single self-contained Linux
executable at `dist/sandfall` (~50.5 MiB) via a tracked, hand-written
`sandfall.spec`, added `pyinstaller` as a dev dependency, documented the
build in `AGENTS.md`, and added lightweight static tests on the spec.
75 → 79 tests, all 5 gates green, build exits 0.

End state:

- `pyproject.toml` — EDIT. Added `pyinstaller>=6.21.0` to the `dev`
  dependency group via `uv add --dev pyinstaller` (which also bumps the
  lower bound to the actually-installed version, as uv does by default).
  `uv.lock` updated accordingly (5 new transitive runtime deps:
  `pyinstaller`, `pyinstaller-hooks-contrib`, `altgraph`, `setuptools`,
  and the local `sandfall` re-install).
- `sandfall.spec` — NEW. Hand-written, tracked in git. `--onefile` build
  (EXE collects binaries+datas directly, NO `COLLECT` block). Entry:
  `src/sandfall/__main__.py`. `console=True` for debug visibility.
  `upx=True` (harmless no-op when UPX is absent — it is here).
  `block_cipher` deliberately omitted (deprecated in PyInstaller ≥ 6.0).
- `AGENTS.md` — EDIT. Added `## Building` (exact command, onefile note,
  collect_all note, console/upx/size notes) and `## Future Work`
  (Windows/macOS/CI deferred; explicit cross-compile constraint). Added
  a "Build single-file binary (Linux)" bullet to `## Commands`.
- `tests/test_packaging.py` — NEW (4 tests, ~0 cost). Static checks on
  the spec: exists, is onefile (`"COLLECT(" not in text`), uses the
  `__main__.py` entry, calls `collect_all("pygame")` + `collect_all("numpy")`.

## The spec approach (onefile via EXE-not-COLLECT)

PyInstaller's onefile vs onedir is decided by the spec's structure:

- **`--onedir`** = `Analysis(...)` → `PYZ(...)` → `EXE(...)` (just the
  scripts+pyz) → `COLLECT(exe, a.binaries, a.datas, ...)` → produces
  `dist/sandfall/` as a directory of loose files plus a tiny launcher.
- **`--onefile`** = `Analysis(...)` → `PYZ(...)` → `EXE(pyz, a.scripts,
  a.binaries, a.datas, ...)` — no COLLECT — produces `dist/sandfall` as
  a SINGLE self-extracting ELF executable.

I followed the onefile form: the `EXE()` call gets `a.binaries` and
`a.datas` as positional args (after `pyz` and `a.scripts`), and the spec
has no `COLLECT(...)` call anywhere. Verified by `ls -la dist/`:
`-rwxr-xr-x ... sandfall` (a regular file, 52,914,776 bytes), NOT a
directory. The bootloader extracts to a temp `runtime_tmpdir` at startup
and the user sees a single binary.

## collect_all vs collect_data_files

I used `collect_all('pygame')` + `collect_all('numpy')` rather than the
phase file's lighter `collect_data_files('pygame')` + explicit
`hiddenimports=[...]`. Rationale (per the task brief's "belt-and-suspenders"
directive):

- `collect_all(pkg)` returns a 3-tuple `(datas, binaries, hiddenimports)`
  and pulls in EVERYTHING in one call: data files (fonts, SDL aliases),
  native binaries (.so), and dynamically-imported submodules that PyInstaller's
  static analyzer might miss.
- pygame-ce is the dist name but imports as `pygame`, so collection uses
  the `'pygame'` import name (the spec comment calls this out).
- The phase file's note about possibly dropping `pygame_ce_datas` (the
  dist name) is moot here: `collect_all('pygame')` finds everything via
  the import name and there is no `pygame_ce` package to collect.

Was it needed? In this build, probably not strictly — pygame-ce and numpy
both ship with their own PyInstaller hooks (`hook-pygame.py`,
`hook-numpy.py`) via `pyinstaller-hooks-contrib`, and those hooks would
have pulled in the essentials automatically. The build's
`warn-sandfall.txt` shows ZERO unexpected MISSING modules for sandfall/
pygame/numpy paths — every "missing module" is a Windows-only conditional
import (`winreg`, `nt`, `_winapi`, `msvcrt`, `_overlapped`), Java/VMS
placeholders (`java.lang`, `vms_lib`), or stdlib conditional imports
(`_scproxy`, `multiprocessing.set_start_method`, `annotationlib`,
`_typeshed`). All of these are expected on a Linux freeze and require no
action. The belt-and-suspenders `collect_all` keeps the build robust
against future versions of pygame/numpy shipping new dynamic imports
their hooks don't yet cover, at the cost of pulling in numpy's test
modules (visible in the build log as `Analyzing hidden import
'numpy.tests.*'`) — harmless, just a slightly larger binary.

## Binary size and build time

- **Size**: 52,914,776 bytes ≈ **50.5 MiB** (consistent with the
  AGENTS.md note). Mostly SDL2 + numpy native libs + pygame-ce native
  libs + the Python runtime itself.
- **Build time**: ~65 seconds wall clock on this machine (single-threaded
  analysis + PKG/EXE stages). Most of it was `Building PKG (CArchive)`
  (~23 s) and `Building PYZ` (~1.5 s). Acceptable for a one-shot release
  build; CI matrices will multiply this by 3 platforms.

UPX was not installed on the build host, so `upx=True` was a no-op (the
bootloader logs say nothing about compression). If UPX were installed,
expect ~40% size reduction but a slightly slower first-run (bootloader
must decompress). Kept `upx=True` so the spec "just works" on hosts that
do have UPX without a config change.

## ruff / spec-formatting resolution

- **ruff's default include glob is `*.py` / `*.pyi` / `*.ipynb`** — `.spec`
  files are NOT in scope by default. So `ruff check .` and
  `ruff format --check .` (the actual gates) skip the spec automatically
  and pass cleanly with zero configuration changes.
- **Explicit `ruff check sandfall.spec` DOES lint it** and reports 3
  `F821 Undefined name` errors on `Analysis`, `PYZ`, `EXE` — these are
  PyInstaller-injected globals, not real bugs. I considered two fixes:
  (a) add `sandfall.spec` to `[tool.ruff].extend-exclude`, or (b) leave
  it and document the F821 as expected. **I chose (b)** after confirming
  (a) is a dead no-op: `extend-exclude` only affects files that match the
  default include glob (which `.spec` already doesn't), AND ruff's CLI
  explicitly bypasses include/exclude when you name a path as an
  argument. So (a) would be misleading dead config. The honest root-cause
  fix is to document it, which I did in the spec header comment (the
  comment explains exactly why F821 appears and why the gate commands
  are unaffected).
- **`ruff format`** does NOT want to change the spec even when invoked
  explicitly (`ruff format --check sandfall.spec` → "1 file already
  formatted") — the spec's call-arg layout already matches black-style
  formatting. No `# fmt: off` needed.

One small footgun: my first `tests/test_packaging.py` self-failed because
its own spec-comment said "NO `COLLECT(...)` block" and the test asserts
`"COLLECT(" not in text` — substring match caught the comment. Fixed by
rewording the comment to "no COLLECT block" (matching the phase file's
wording, no parens). The phase file's own example test has the same
latent substring bug if anyone writes a `COLLECT(...)`-in-comment in the
future — minor, but worth noting.

## Was console=True / console=False settled?

`console=True` for now, explicitly. Rationale: this is the first build
of v1, the orchestrator is about to run the binary for the first time
(`SANDFALL_FRAMES=60 ./dist/sandfall`), and `console=True` ensures any
startup traceback (missing module, font init failure, etc.) is printed
to stderr rather than swallowed by the GUI. The spec comment and
`AGENTS.md` both say to flip to `console=False` for a release GUI build
on Linux (so no terminal window pops up). That's a polish step for a
tagged release, not for v1 verification.

## What the build does NOT verify

- **The binary was not executed by this agent.** The bash allowlist here
  permits `uv*`, `ruff*`, `mypy*`, `pytest*`, etc. but NOT `./dist/sandfall`
  (or any non-allowlisted executable). I confirmed the binary exists and
  is a single regular file via `ls -la dist/`, and the build log reports
  `Build complete!` with no errors. **The orchestrator must run
  `SANDFALL_FRAMES=60 ./dist/sandfall` to verify execution end-to-end.**
  That env-var seam (from Phase 04) makes `main()` return 0 after 60
  frames instead of looping forever, so the verification is non-interactive
  and suitable for CI later.
- **No SDL/pygame runtime check was done here.** The in-process
  Phase-05 frame-cap smoke (`SDL_VIDEODRIVER=dummy` + 60 frames via the
  unfrozen `main()`) already validated `main()` returns 0; the only
  thing the frozen binary adds is the PyInstaller bootloader + bundled
  data, which `ls`/build-log confirm are present and correctly structured.

## Difficult / unexpected

1. **`block_cipher` deprecation.** The phase file's snippet passed
   `cipher=block_cipher` to `Analysis`, `PYZ`, and `EXE`. In PyInstaller
   6.x that emits a `DeprecationWarning` AND `block_cipher` is removed
   from the default templates. Since the global AGENTS rule is "fix
   warnings, never suppress them", I omitted `cipher=` entirely (the
   bytecode-encryption feature it gated was removed in PyInstaller 6.0 —
   it was already non-functional). Result: clean build log, zero
   deprecation warnings.
2. **`extend-exclude` is misleading for `.spec`.** As discussed above,
   the seemingly-defensive config is actually a no-op. I caught this by
   testing explicit `ruff check sandfall.spec` after adding the exclude
   — the F821 errors still appeared, proving the exclude doesn't apply
   to explicit-arg invocations. Reverted to avoid shipping misleading
   config. Documented the F821 situation in the spec header instead.
3. **`numpy.tests.*` pulled in by `collect_all('numpy')`.** The build
   log shows ~30 "Analyzing hidden import 'numpy.tests.test_*'" lines.
   This is expected: `collect_all` grabs numpy's full hidden-import list,
   which includes its own test modules. They add some bytes to the PYZ
   archive but don't run (no one imports them at runtime). Could be
   stripped with `excludes=['numpy.tests', 'numpy.typing.tests', ...]`
   in `Analysis(...)` if size becomes a concern; left alone for v1
   since correctness > 1-2 MiB.

## Deviations from the phase file

1. **Used `collect_all` instead of `collect_data_files` + explicit
   `hiddenimports`.** The phase file's spec uses
   `collect_data_files('pygame')` + a hand-written
   `hiddenimports=['pygame', 'pygame.font', 'pygame.surfarray', 'numpy']`.
   The task brief (more recent and more specific than the phase file)
   explicitly directed `collect_all('pygame')` and `collect_all('numpy')`
   as "belt-and-suspenders". Followed the brief; documented the tradeoff
   above. End result is functionally equivalent and slightly more robust
   against future hidden imports.
2. **Dropped `block_cipher` entirely.** Phase snippet kept
   `block_cipher = None` + `cipher=block_cipher` in three places. Removed
   because PyInstaller 6.x deprecates it (root-cause fix per global
   AGENTS rule). The feature it represented (bytecode encryption) was
   removed in PyInstaller 6.0 — `cipher=` is a no-op that just warns.
3. **Added `icon=None` and `noarchive=False` to the spec.** Phase snippet
   omitted `icon=`; modern PyInstaller `EXE()` accepts `icon=` (default
   `None`) and the bootloader picks a platform default. Added
   `icon=None` explicitly to document "no custom icon for v1" (a future
   polish task). `noarchive=False` is the `Analysis()` default (keeps
   the bytecode in the PYZ archive rather than dumping .pyc files loose);
   made it explicit so the choice is visible.
4. **Added `tests/test_packaging.py`** (4 tests). The phase file marked
   it optional; the task brief didn't mention it but said "follow the
   phase file literally" for the work. Added because it's ~0 cost and
   guards against the most common spec regressions (accidentally adding
   a COLLECT block, renaming the entry point, dropping collect_all).
5. **Did NOT execute `./dist/sandfall`.** The phase file lists
   `./dist/sandfall` as the manual verification step, but the bash
   allowlist here blocks it. The task brief explicitly addressed this
   ("You CANNOT run the built binary") and directed me to defer it to
   the orchestrator. Documented in this reflection and will be stated
   in the report.
6. **AGENTS.md heading is `## Building` not `## Building (Linux)`.** The
   phase file used `## Building (Linux)` with a `### Platform status`
   subsection; the task brief asked for `## Building` + an explicit
   `## Future Work` section. Followed the brief.

## Verification gate results (all pass, exit 0)

| Gate | Result |
|------|--------|
| `uv run python -c "import sandfall"` | `ok` |
| `uv run pytest` | `79 passed in 0.55s` (was 75; +4 packaging tests) |
| `uv run ruff check .` | `All checks passed!` |
| `uv run ruff format --check .` | `36 files already formatted` |
| `uv run mypy src` | `Success: no issues found in 20 source files` |
| `uv run pyinstaller sandfall.spec --noconfirm` | exit 0; `Build complete!` |
| `ls -la dist/` | `-rwxr-xr-x ... 52914776 Jul 28 ... sandfall` (single file, NOT a directory) |

## Suggestions for future work / agent improvements

- **Flip `console=False` for the tagged v1 release.** Once the orchestrator
  confirms the binary runs cleanly, change one line in `sandfall.spec`
  (`console=True` → `console=False`) and rebuild — no terminal window will
  pop up when launched from a Linux desktop. (Already noted in AGENTS.md
  Future Work; just want to make sure it actually happens before tagging.)
- **Windows/macOS specs.** Per AGENTS.md Future Work: draft a
  `sandfall.windows.spec` and `sandfall.macOS.spec`. The current spec
  should generalize (only `console=` and the bootloader auto-select
  differ). macOS will need an `icon=` (`.icns`) and probably a
  `BUNDLE(...)` step in addition to `EXE(...)` to produce a proper `.app`;
  that means macOS would NOT be onefile in the strict sense (a `.app` is
  a directory by macOS convention). Worth a dedicated phase once v1 is
  tagged.
- **CI matrix.** GitHub Actions with a 3-platform build matrix
  (`ubuntu-latest`, `windows-latest`, `macos-latest`) running
  `uv sync && uv run pyinstaller <spec>` and uploading `dist/sandfall*`
  as release artifacts against each tag. This is the natural place to
  flip `console=False`, sign the Windows `.exe` (`codesign_identity=`),
  and notarize the macOS `.app`.
- **Consider `excludes=['numpy.tests', 'numpy.typing.tests']`** in a
  follow-up to trim ~1-2 MiB off the binary. `collect_all('numpy')`
  pulls in numpy's whole hidden-import list including its test suite,
  which inflates the PYZ but is never imported at runtime. Low priority
  (correctness > size), but easy if size matters.
- **Agent-prompt note (global):** the `extend-exclude` is-a-no-op lesson
  is worth capturing. Specifically: *"ruff's `extend-exclude` /
  `exclude` only filters files that already match the default include
  glob (`*.py`, `*.pyi`, `*.ipynb`). For files outside that glob (e.g.
  `.spec`, `.pyx`), explicit CLI invocation bypasses exclude entirely —
  do not rely on `extend-exclude` to silence lint on non-`.py` files.
  Document the false positives in the file's own comments instead."* This
  would have saved me ~10 min of experimentation this phase.
- **PyInstaller `block_cipher` removed in 6.x** — any agent or template
  that still references `block_cipher = None` + `cipher=block_cipher`
  (the classic pyi-makespec output from older versions) is shipping dead
  code that emits a deprecation warning. Worth noting for any future
  packaging phase.

## Fun discovered

- The PyInstaller build log is unusually satisfying to read end-to-end:
  ~25 s of static analysis, ~1.5 s PYZ build, ~23 s PKG (CArchive)
  compression, then `Appending PKG archive to custom ELF section in EXE`
  — the bootloader literally grafts the entire Python payload into a
  custom ELF section of a tiny Linux executable, and the bootloader's
  `main()` mmap+decompresses that section at runtime. Single-file
  Python binaries are a neat hack.
- `pygame-ce 2.5.7 (SDL 2.32.10, Python 3.12.13)` is the very last
  line of the build log — PyInstaller's hook for pygame imports the
  package to introspect its version, which prints that banner. Harmless.
- `collect_all('numpy')` pulling in numpy's own test suite is the kind
  of "wait, why" detail that's obvious in hindsight (numpy ships with
  its test modules as part of the wheel) but surprising the first time
  you see "Analyzing hidden import 'numpy.tests.test__all__'" in a
  production build log.

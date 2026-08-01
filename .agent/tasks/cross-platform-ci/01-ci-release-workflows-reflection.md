# Phase 01 Reflection — CI + Release Workflows, Spec Header Refresh, Doc Updates

## What was done

Implemented the single atomic Phase 01 of the `cross-platform-ci` plan. Six
files touched (no Python source changed):

- **`.github/workflows/ci.yml`** — **CREATED**. Linux (`ubuntu-latest`)
  quality gate on `push: branches: [main]` and `pull_request`. Steps:
  `actions/checkout@v4` → `astral-sh/setup-uv@v3` (`enable-cache: true`) →
  `uv sync` → `uv run ruff check .` → `uv run ruff format --check .` →
  `uv run mypy src` → `uv run pytest` → `uv run python -c "import sandfall"`
  → Linux build-smoke `SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec
  --noconfirm`. Verbatim from the phase file (no `python-version` input —
  `uv sync` honors `.python-version = 3.12` itself).
- **`.github/workflows/release.yml`** — **CREATED**. `push: tags: ['v*']` →
  3-OS matrix (`ubuntu-latest`, `windows-latest`, `macos-latest`),
  `runs-on: ${{ matrix.os }}`, `fail-fast: false`. Top-level
  `permissions: contents: write` (required by `action-gh-release`). Steps:
  checkout → setup-uv (`enable-cache`) → `uv sync` → **`shell: bash`** Build
  (`SANDFALL_RELEASE=1 ...`) → **`shell: bash`** Rename per-OS (maps
  `dist/sandfall`/`dist/sandfall.exe` → `sandfall-linux-x86_64` /
  `sandfall-windows-x86_64.exe` / `sandfall-macos-arm64` via `RUNNER_OS`) →
  `actions/upload-artifact@v4` (`if-no-files-found: error`) →
  `softprops/action-gh-release@v2` (`files: dist/sandfall-*`). All cross-OS
  steps use `shell: bash` so the Windows job (Git Bash) doesn't fall back to
  PowerShell and choke on the `VAR=cmd` env-prefix / `mv`.
- **`sandfall.spec`** — **EDITED line 2 only**: header comment
  "single-file Linux build" → "single-file build (Linux / Windows / macOS)".
  No logic change. `git diff --stat sandfall.spec` = `1 insertion(+), 1
  deletion(-)` exactly. The env-driven `console` block (`sandfall.spec:47-49`)
  and `collect_all('pygame')`/`collect_all('numpy')` (`sandfall.spec:35-36`)
  are why no logic change was needed — confirmed portable by the local
  build-smoke.
- **`README.md`** — **EDITED** (three edits per the plan):
  - 4c "Requirements" OS line → now says the game runs on Linux/Windows/macOS
    and release binaries are produced by CI on `v*` tags (link to the new
    subsection).
  - 4a New "### Cross-platform builds (CI)" subsection inserted between the
    Building Notes block and "## Project layout" — lists the three asset
    names, describes both workflows, restates the unchanged local Linux
    command, and includes the **Unsigned-binary caveat (v1)** blockquote
    (SmartScreen / Gatekeeper warning, `xattr` workaround, bare-executable
    note).
  - 4b "## Status" rewritten — no longer "Linux-only"; states v1 builds on
    all three OS via CI and that code-signing/notarization is the **only**
    remaining deferred packaging item.
- **`AGENTS.md`** — **EDITED** "## Future Work" — builds + CI matrix now
  described as **shipped** (points at `release.yml` + `ci.yml`; notes the
  `--onefile` spec needed only a header refresh; macOS is a bare executable,
  no `.app`); code-signing/notarization kept as the **only** remaining
  deferred sub-item (needs credentials). "## Building" left unchanged.
- **`.agent/tasks/BACKLOG.md`** — **no edit by me**. The task-manager had
  already moved "Cross-platform builds + CI" from Tier 2 into "Recently
  shipped" (with the `source:` line intact). Verified at implementation time:
  the Tier-2 section contains only Electricity / Ambient thermostat / Thermal
  realism / Concentration-mixing — no cross-platform entry remains.

## Local verification (all green — personally observed)

```
uv run --with pyyaml python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('.github/workflows/release.yml')); print('YAML OK')"
  → YAML OK

uv run ruff check .          → All checks passed!
uv run ruff format --check . → 55 files already formatted
uv run mypy src              → Success: no issues found in 30 source files
uv run pytest                → 217 passed in 1.83s
uv run python -c "import sandfall"  → (exit 0)

SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm
  → Build complete! ... dist/sandfall  (exit 0)

ls -la dist/  → -rwxr-xr-x ... 53121824 Aug  1 00:05 sandfall   (~50 MiB, as expected)

git diff --stat sandfall.spec  → 1 file changed, 1 insertion(+), 1 deletion(-)
```

`actionlint` is **not installed** on this host (`which actionlint` → not
found), so the local workflow-correctness check is the `yaml.safe_load` parse
for both files (passes). `pyyaml` is not a project dep, so the check was run
via `uv run --with pyyaml`.

## Cross-OS verification — PENDING A PUSH (could not verify locally)

Per Risk #1, **PyInstaller is not a cross-compiler** and the dev box is
Linux, so the Windows + macOS release builds can **only** be proven out by
pushing to GitHub. **I did not push** (the task said not to push unless
asked, and did not ask). The local gate proves: both YAML files are
well-formed, the spec still builds (Linux), and the quality gates are green
— it does **not** prove Windows/macOS build or that the per-platform rename
lands the asset names.

To finish acceptance, the user should:

1. **Push this commit to `main`** → confirm the **CI** workflow goes green
   in the Actions tab (this also exercises the Linux build-smoke on GitHub,
   catching any spec regression the local smoke didn't).
2. **Push a throwaway tag** to trigger the 3-OS Release matrix:
   ```bash
   git tag v0.0.0-ci-test && git push origin v0.0.0-ci-test
   ```
   → confirm all three `release.yml` jobs (`ubuntu`/`windows`/`macos`)
   build, upload their `sandfall-<os>` artifact, and attach
   `dist/sandfall-*` to the (draft) release. Then delete the throwaway tag
   and its release:
   ```bash
   git tag -d v0.0.0-ci-test && git push origin :refs/tags/v0.0.0-ci-test
   gh release delete v0.0.0-ci-test --yes   # if created
   ```
   Record the Actions-run URLs + per-OS outcomes back here once observed.

Expected per-OS asset names (from the rename step):
`sandfall-linux-x86_64`, `sandfall-windows-x86_64.exe`,
`sandfall-macos-arm64`. The Windows job must use `shell: bash` (encoded in
both the Build and Rename steps) — if the Windows job fails with something
PowerShell-ish, that's the first thing to check, but the YAML is correct.

## What was difficult / unexpected

- Nothing unexpected. The phase file gave literal YAML; both files were
  written verbatim and parsed on the first try.
- `pyyaml` is not in the venv and `actionlint` is not on the host, so the
  local workflow check was `uv run --with pyyaml python -c "yaml.safe_load..."`.
  This is the documented local-equivalent check (plan Risk #2 / Verification
  Philosophy), not a gap.
- `dist/` already contained a stray `sandfall-20260728-200634` from a prior
  build session (predates this work; `dist/` is gitignored so it's harmless
  and not part of any commit). The build-smoke produced the expected
  `dist/sandfall`.
- The README "Building → Notes" bullet still describing `console=True` as
  "currently set" was **intentionally left as-is** per phase step 5's
  explicit instruction (dev builds still attach a console; the new
  Cross-platform subsection documents `SANDFALL_RELEASE=1` for release). No
  scope creep.

## Deviations from the plan

None. All six edits implemented exactly as specified; no extra files, no
spec logic change, no game-code change. **No git operations were performed**
— changes are left unstaged per the task contract (no commit / stage / push
/ amend).

## Suggestions for future work / agent improvements

- When the first real `v*` release tag is cut, capture the per-OS binary
  sizes + Actions run URL back into this reflection (or a follow-up) — that
  closes the loop on Decision Log #7 (macOS arm64-only, Intel via Rosetta)
  and confirms the spec is genuinely cross-OS portable end-to-end.
- If the Windows or macOS job reports a missing hidden import / native dep
  on first push, the fix is a targeted addition to `sandfall.spec` (e.g. a
  `binaries=`/`hiddenimports=` append) — not anticipated here, since
  `collect_all` already belts-and-suspenders both pygame and numpy.
- Optional: install `actionlint` in the dev env (or as a CI pre-step) for a
  stronger local workflow-correctness signal than YAML-parse alone.

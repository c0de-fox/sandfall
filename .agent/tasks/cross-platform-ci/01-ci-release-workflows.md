# Phase 01: CI + Release Workflows, Spec Header Refresh, Doc Updates

## Objective

Stand up cross-platform packaging for sandfall in one atomic commit: a Linux
**quality-gate** workflow (`.github/workflows/ci.yml`) that runs lint/type/test
+ a Linux build-smoke on every push/PR, and a **3-OS release** workflow
(`.github/workflows/release.yml`) that builds Windows/Linux/macOS binaries on
`v*` tags and attaches distinct per-platform assets to the GitHub release.
Refresh the `sandfall.spec` header comment (Linux → Linux/Windows/macOS; no
logic change), and update `README.md` / `AGENTS.md` / `BACKLOG.md` to reflect
that cross-platform packaging is now **done** (code-signing/notarization remains
deferred).

## Depends On

none — single phase (the workflows, the spec header edit, and the doc edits
are one logical change; see the overview's Dependency Map).

## Can Parallelize With

nothing — single phase.

## Recommended Agent

@implementer — two new small config files (literal YAML below), a one-line
comment edit in `sandfall.spec`, and three doc edits. No Python source change,
no new deps, no signature changes. Read `00-overview.md` first (especially the
Decision Log #1-#9 and Risks #1-#7), then re-read `sandfall.spec`,
`README.md`, and `AGENTS.md` before editing (line numbers below are current at
planning time and may drift). The one subtlety is **`shell: bash` on the
cross-OS steps** (Windows defaults to PowerShell; the `VAR=cmd` env-prefix and
`mv` are bash-isms) — do not drop it.

## Changes Required

- `.github/workflows/ci.yml` — **CREATE**. Linux quality-gate workflow: push to
  `main` + pull_request → one `ubuntu-latest` job running the six gates plus a
  Linux build-smoke.
- `.github/workflows/release.yml` — **CREATE**. Release workflow: `v*` tag →
  3-OS matrix build, per-platform rename, artifact upload, and release attach.
  Declares `permissions: contents: write`.
- `sandfall.spec` — **EDIT** the header comment line 2 only
  ("single-file Linux build" → "single-file build (Linux / Windows / macOS)").
  No logic change.
- `README.md` — **EDIT**: add a "Cross-platform builds (CI)" subsection under
  "Building"; update the "Status" + "Requirements" lines that say Linux-only /
  future work.
- `AGENTS.md` — **EDIT**: move the "Windows/macOS builds + CI matrix" items in
  "Future Work" from deferred to done (point at the workflows); keep
  code-signing/notarization as the remaining deferred sub-item.
- `.agent/tasks/BACKLOG.md` — **EDIT**: mark the Tier-2 "Cross-platform builds
  + CI" item as shipped (move to "Recently shipped").

## Implementation Instructions

> Re-read `sandfall.spec`, `README.md`, and `AGENTS.md` before editing — line
> numbers below are current at planning time and may drift. This phase touches
> NO Python source; the risk is YAML correctness and cross-OS shell behavior,
> both addressed below.

### 1. CREATE `.github/workflows/ci.yml` — the quality gate (every push/PR)

Create the file with exactly this content:

```yaml
# Quality gate: lint, type-check, tests, import smoke, and a Linux build-smoke.
# Runs on every push to main and every pull request. OS-independent checks run
# on Linux only (cheap + sufficient); the cross-OS release build lives in
# release.yml and fires on version tags. The repo is PUBLIC, so Actions is free.

name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      # uv manages both uv and Python: `uv sync` reads .python-version (3.12)
      # and installs that interpreter itself, so no explicit python-version is
      # needed here. enable-cache caches the uv store / wheels for speed.
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - run: uv sync

      # --- Quality gates (all must pass) ---
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run mypy src
      - run: uv run pytest

      # --- Import smoke ---
      - run: uv run python -c "import sandfall"

      # --- Linux build-smoke (recommended; catches spec regressions on every
      #     push. ~30s and free on a public repo. If it ever proves flaky it
      #     can be dropped without touching the quality gate above.) ---
      - run: SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm
```

Notes for the implementer:
- Do **not** add an explicit `python-version` / `python-version-file` input to
  `setup-uv` — `uv sync` honors `.python-version` (= `3.12`) on its own. (If a
  future uv/setuptools-uv change makes that insufficient, add
  `python-version-file: .python-version` — but only then.)
- The build-smoke step is **recommended but optional** (Decision Log #3). Keep
  it; if it fails the gate for a spec reason that is genuine, fix the spec; if
  it fails for an environment reason, it may be gated behind a separate job.
- `ruff check .` / `ruff format --check .` skip `.spec` files automatically
  (ruff's default include is `*.py`/`*.pyi`/`*.ipynb`), so the spec header edit
  does not trip them.

### 2. CREATE `.github/workflows/release.yml` — the 3-OS release build (on tags)

Create the file with exactly this content:

```yaml
# Release builds: produce a single-file binary per OS on every version tag and
# attach it to the GitHub release the tag created. PyInstaller is NOT a
# cross-compiler, so each target OS builds on its own runner. The repo is
# PUBLIC, so the Windows (2x) and macOS (10x) billing multipliers do NOT apply
# (those only hit the private-repo 2,000-min free quota).

name: Release

on:
  push:
    tags:
      - 'v*'

# softprops/action-gh-release needs to write the release (upload assets).
permissions:
  contents: write

jobs:
  build:
    strategy:
      fail-fast: false   # one OS failing must not cancel the others
      matrix:
        os: [ubuntu-latest, windows-latest, macos-latest]
    runs-on: ${{ matrix.os }}

    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - run: uv sync

      # Release mode: SANDFALL_RELEASE=1 detaches the console window and
      # disables the windowed-traceback dialog (see sandfall.spec:47-49).
      # `shell: bash` is REQUIRED on Windows: the env-prefix syntax and `mv`
      # below are bash-isms and Windows defaults to PowerShell otherwise.
      - name: Build (release)
        shell: bash
        run: SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm

      # PyInstaller emits dist/sandfall (linux/mac) or dist/sandfall.exe
      # (windows). Rename to a distinct, self-describing asset per OS.
      # macos-latest is Apple Silicon (arm64); Intel Macs use Rosetta.
      - name: Rename per-platform asset
        shell: bash
        run: |
          if [ "$RUNNER_OS" = "Windows" ]; then
            mv dist/sandfall.exe dist/sandfall-windows-x86_64.exe
          elif [ "$RUNNER_OS" = "macOS" ]; then
            mv dist/sandfall dist/sandfall-macos-arm64
          else
            mv dist/sandfall dist/sandfall-linux-x86_64
          fi

      # Always upload the binary as a workflow artifact (downloadable from the
      # run even for a throwaway / non-release tag test).
      - uses: actions/upload-artifact@v4
        with:
          name: sandfall-${{ matrix.os }}
          path: dist/sandfall-*
          if-no-files-found: error

      # Attach the per-platform binary to the release the tag created.
      - uses: softprops/action-gh-release@v2
        with:
          files: dist/sandfall-*
```

Notes for the implementer:
- `RUNNER_OS` is one of `Linux` / `Windows` / `macOS` (predefined). The rename
  branch order handles all three.
- `if-no-files-found: error` makes a failed build/raname loud rather than
  silently uploading nothing.
- **Do NOT add a macOS `.app` / `BUNDLE` block** — it collides with the
  `--onefile` spec (Decision Log #5). v1 ships a bare executable on all OS.
- **Do NOT add code-signing steps** (Decision Log #6). Binaries ship unsigned;
  the UX-warning caveat is documented in the README edit (step 4).

### 3. EDIT `sandfall.spec` — header comment refresh only

`sandfall.spec:2` currently reads:

```
# PyInstaller spec for the sandfall single-file Linux build.
```

Change it to:

```
# PyInstaller spec for the sandfall single-file build (Linux / Windows / macOS).
```

That is the **only** spec edit. Rationale (encode in the reflection): the spec
is already portable — `console` / `disable_windowed_traceback` are env-driven
(`sandfall.spec:47-49`), `collect_all('pygame')`/`collect_all('numpy')` pull
per-platform native libs (`sandfall.spec:35-36`), and PyInstaller selects the
bootloader automatically. `name="sandfall"` is unchanged (`sandfall.spec:72`);
PyInstaller appends `.exe` on Windows, and the release workflow does the
per-platform renaming. `icon=None` stays (`sandfall.spec:84`).

### 4. EDIT `README.md` — docs

Re-read `README.md` first. Three edits:

**4a.** In the **"Building the single-file binary"** section
(`README.md:99`), add a new subsection **after** the existing Notes block
(ends ~`README.md:124`) and before "Project layout":

```markdown
### Cross-platform builds (CI)

Release binaries for **Windows, Linux, and macOS are produced automatically**
by GitHub Actions whenever a `v*` tag is pushed. A `v1.0.0` tag, for example,
publishes three assets to that tag's release:

- `sandfall-linux-x86_64`
- `sandfall-windows-x86_64.exe`
- `sandfall-macos-arm64` (Apple Silicon; Intel Macs run it via Rosetta 2)

The workflow (`.github/workflows/release.yml`) runs `uv sync && SANDFALL_RELEASE=1
uv run pyinstaller sandfall.spec --noconfirm` on `ubuntu-latest`,
`windows-latest`, and `macos-latest` runners. (PyInstaller cannot
cross-compile, so each binary is built on its own OS.) A separate Linux
workflow (`.github/workflows/ci.yml`) runs lint, type-check, and tests on
every push and pull request.

The local Linux build is unchanged:

```bash
SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm
```

> **Unsigned-binary caveat (v1).** Windows binaries will trigger SmartScreen
> and macOS binaries will trigger Gatekeeper's "unidentified developer"
> warning, because code-signing / notarization is deferred (it needs
> credentials the project does not yet have). On macOS, run
> `xattr -dr com.apple.quarantine /path/to/sandfall-macos-arm64` to clear the
> quarantine flag. macOS ships as a **bare executable** (no `.app` bundle).
```

**4b.** Update the **"Status"** section (`README.md:161-177`). It currently
opens "**v1 is complete and Linux-only.**" and lists cross-platform as
"deferred". Replace that framing: state that v1 builds on all three OS via CI,
that release binaries are attached to `v*` tags automatically (point at the
Cross-platform builds (CI) subsection above), and that the **only** remaining
deferred packaging item is code-signing/notarization (unsigned-binary caveat).
Remove/rewrite the "Windows `.exe` and macOS `.app` builds" and "CI matrix"
bullets that described them as future work — they are now done.

**4c.** Update the **"Requirements"** OS line (`README.md:77-79`), which
currently says "OS: Linux. Windows and macOS builds are future work." Change
it to reflect that the game runs anywhere pygame-ce does and that Windows /
Linux / macOS release binaries are produced by CI on `v*` tags.

### 5. EDIT `AGENTS.md` — docs

Re-read `AGENTS.md` first. The **"Future Work"** section (`AGENTS.md:60-76`)
currently lists two deferred items: "Windows `.exe` and macOS `.app` builds"
and "CI matrix (GitHub Actions)". Rewrite the section so that:

- The **builds + CI matrix are described as DONE** — a one-liner noting that
  `.github/workflows/ci.yml` runs the quality gate on every push/PR and
  `.github/workflows/release.yml` builds all three OS on `v*` tags. (The
  `--onefile` spec needed no logic change; macOS is a bare executable, not a
  `.app`.)
- The **only remaining deferred sub-item is code-signing / notarization**
  (Windows code-signing cert + macOS Developer ID/notarytool), which needs
  credentials — keep that as Future Work, and reference the unsigned-binary
  caveat.

Keep the **"Building"** section (`AGENTS.md:30-58`) as-is (the local Linux
build command is unchanged), except: if it describes `console=True` as the
current setting, leave it (dev builds still attach a console; `SANDFALL_RELEASE=1`
detaches it) — no change required there.

### 6. EDIT `.agent/tasks/BACKLOG.md` — mark shipped

Re-read `BACKLOG.md` first. The **Tier-2** entry "Cross-platform builds + CI"
(`BACKLOG.md:53-58`) moves to **"Recently shipped"** (`BACKLOG.md:11-21`).
Add a bullet under "Recently shipped" summarizing what shipped (3-OS release
build on `v*` tags via `release.yml`, Linux quality gate via `ci.yml`,
`--onefile` spec needed only a header refresh, signing deferred), and remove
the now-stale Tier-2 bullet. Keep its `source:` line intact in the shipped
bullet so the trail is preserved.

## Acceptance Criteria

- [ ] `.github/workflows/ci.yml` exists and is valid YAML; it triggers on
      `push` (branch `main`) and `pull_request`; it runs ONE `ubuntu-latest`
      job with the six gates (`ruff check`, `ruff format --check`, `mypy src`,
      `pytest`, `import sandfall`, and the Linux build-smoke
      `SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm`).
- [ ] `.github/workflows/release.yml` exists and is valid YAML; it triggers on
      `push: tags: ['v*']`; it has a `matrix.os = [ubuntu-latest,
      windows-latest, macos-latest]` with `runs-on: ${{ matrix.os }}`; it
      builds in release mode, renames the per-platform asset, uploads an
      artifact per OS, and attaches `dist/sandfall-*` to the release; it
      declares `permissions: contents: write`.
- [ ] Both release-build and rename steps (and the build step) use
      `shell: bash` (so Windows does not default to PowerShell).
- [ ] `sandfall.spec` header comment line 2 now reads "single-file build
      (Linux / Windows / macOS)"; **no other spec line changed** (diff is one
      line — the Linux build-smoke proves it still builds).
- [ ] `README.md` has a "Cross-platform builds (CI)" subsection (release
      binaries on `v*` tags; local Linux build unchanged; unsigned-binary +
      bare-executable + Rosetta caveats), and "Status"/"Requirements" no
      longer say Linux-only / future work.
- [ ] `AGENTS.md` "Future Work" marks the builds + CI matrix done (pointing at
      the workflows) and retains code-signing/notarization as the only
      deferred packaging sub-item.
- [ ] `BACKLOG.md` moved "Cross-platform builds + CI" from Tier 2 to
      "Recently shipped".
- [ ] **YAML validity**: both workflow files parse (`yaml.safe_load` succeeds).
      If `actionlint` is available, it passes; else the `yaml.safe_load` check
      is the local verification step (noted in the reflection).
- [ ] All local verification gates (below) exit zero.

## Verification Commands

```bash
# --- Quality gates (unchanged source → unchanged results) ---
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run python -c "import sandfall"

# --- Linux build-smoke (proves the spec header edit did not regress the build) ---
SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm

# --- YAML validity (the local equivalent of "do the workflows parse?") ---
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('ci.yml ok')"
uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml')); print('release.yml ok')"

# --- Optional: actionlint if installed on the host ---
#   actionlint .github/workflows/ci.yml .github/workflows/release.yml

# --- Spec edit is one line ---
git diff --stat sandfall.spec      # expect exactly 1 insertion / 1 deletion
```

All commands must exit zero. The **cross-OS release build has no local
equivalent** (Risk #1): Windows/macOS can ONLY be verified by pushing to
GitHub. The final acceptance gate for the release path is the Actions run:

1. Push this commit to `main` → confirm `ci.yml` goes **green** in the Actions
   tab (this also exercises the Linux build-smoke on GitHub).
2. Push a throwaway tag `v0.0.0-ci-test` → confirm all three `release.yml`
   jobs build, upload artifacts, and attach to the (draft) release. Then
   delete the throwaway tag and its release.

Record both Actions-run URLs and the per-OS outcomes in the reflection.

## Documentation Updates

- `README.md` — steps 4a/4b/4c (Cross-platform builds subsection; Status;
  Requirements).
- `AGENTS.md` — step 5 (Future Work: builds + CI done; signing deferred).
- `BACKLOG.md` — step 6 (move Tier-2 item to Recently shipped).
- The `sandfall.spec` header comment (step 3) is the source of truth for
  "this spec is cross-OS." No other doc change is required.

## Reflection & Commit

After implementation, write `01-ci-release-workflows-reflection.md` in this
directory. **Specifically include:**

- The **Actions-run outcomes** — the URL and green status of the `ci.yml` run
  on push, and the URL + per-OS build/upload/attach outcome of the
  `release.yml` run on the throwaway `v0.0.0-ci-test` tag (or whichever tag
  was used). This is the **authoritative** cross-OS verification (Risk #1).
- Confirmation that `sandfall.spec` needed **only the one-line header edit**
  and built clean on all three OS via the Actions run (Decision Log: the spec
  was already portable). If any OS needed a spec addition, name it and the
  fix.
- Confirmation that the two YAML files pass `yaml.safe_load` (and
  `actionlint` if you ran it), and that `ruff`/`mypy`/`pytest`/Linux
  build-smoke pass locally.
- Confirmation the per-platform asset names landed as expected
  (`sandfall-linux-x86_64`, `sandfall-windows-x86_64.exe`,
  `sandfall-macos-arm64`) and that the Windows job used `shell: bash`
  (Risk #3).
- Anything difficult/unexpected (e.g. a missing hidden import on a given OS,
  a setup-uv cache quirk, a macOS notarization prompt that did not occur
  because the binary is unsigned), deviations from this plan + why, and
  anything fun discovered (e.g. the final per-OS binary sizes, or how the
  free-tier billing showed up).

Then make ONE atomic git commit covering all changes in this phase (the two
workflow files, the spec header edit, the three doc edits, and the BACKLOG
update).

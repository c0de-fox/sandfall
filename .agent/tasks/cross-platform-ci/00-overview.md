# Sandfall — Cross-Platform Packaging + GitHub Actions CI — Master Plan

## Problem Statement

The game ships today as a **single-file Linux x86-64 binary** (`sandfall.spec`,
a hand-written PyInstaller `--onefile` spec). The founding brief asked for a
"single self-contained binary for each platform (Windows and Linux, Mac is
optional)", but cross-platform packaging has sat under **deferred Future Work**
since v1 — recorded in `AGENTS.md` "Future Work", `README.md` "Status", and the
`.agent/tasks/BACKLOG.md` Tier-2 entry. There is also **no CI** of any kind
today (`.github/` does not exist — confirmed at planning time): lint / type /
tests run only on the developer's Linux box.

Two facts drive the approach:

1. **PyInstaller is not a cross-compiler** (https://pyinstaller.org/). A Windows
   `.exe` must be produced on Windows and a macOS binary on macOS; a Linux host
   (Docker or bare) can only build Linux binaries. PyInstaller-under-Wine and
   Windows-containers-on-Linux both exist but are fragile for pygame's native
   SDL/numpy wheels and are not used. **Therefore each target OS must build on
   its own runner** — the standard, correct pattern is a per-OS build matrix.

2. **GitHub Actions is unlimited-free for this repo because it is PUBLIC.**
   Per https://docs.github.com/billing, public repositories get unlimited free
   minutes on all standard runners (`ubuntu-latest`, `windows-latest`,
   `macos-latest`). The 2× (Windows) / 10× (macOS) billing multipliers apply
   only to the **private**-repo 2,000-minute free quota — irrelevant here.
   Minutes are therefore NOT a constraint on the matrix.

The good news: **`sandfall.spec` is already essentially portable.** The only
platform-specific lines are `console=` / `disable_windowed_traceback=`, and
both are already driven by the `SANDFALL_RELEASE` env var (`sandfall.spec:47-49`)
so a release build detaches the console on every OS. `collect_all('pygame')` /
`collect_all('numpy')` (`sandfall.spec:35-36`) pull the per-platform native
libs for whatever OS runs the build, and PyInstaller selects the correct
bootloader automatically. **The spec needs essentially no logic change — only
a header-comment refresh** (it currently says "single-file Linux build",
`sandfall.spec:2`).

So the work is: stand up two GitHub Actions workflows (a Linux quality gate
on every push/PR, and a 3-OS release build on version tags), rename the
per-OS binary before upload so release assets are distinct, refresh the spec
header, and move the docs from "deferred" to "done".

**Evidence base (cited — read at planning time on the current source):**

| Fact                                                  | Where                                                                 |
|-------------------------------------------------------|-----------------------------------------------------------------------|
| `sandfall.spec` already portable (env-driven console) | `sandfall.spec:47-49`; `collect_all` at `sandfall.spec:35-36`.        |
| Spec header still says "Linux build"                  | `sandfall.spec:2`.                                                    |
| `name="sandfall"` (`.exe` auto-appended on Windows)   | `sandfall.spec:72`.                                                   |
| `icon=None` already                                   | `sandfall.spec:84`.                                                   |
| Dev deps include `pyinstaller>=6.21.0`                | `pyproject.toml:24`.                                                  |
| `requires-python = ">=3.12"`; `.python-version = 3.12`| `pyproject.toml:6`; `.python-version:1`.                              |
| `sandfall` console script entry exists                | `pyproject.toml:13`.                                                  |
| No `.github/` exists yet (no CI at all)               | `ls .github` → no files (glob `**/.github/**` empty).                 |
| `build/` + `dist/` gitignored                         | `.gitignore:8-9`.                                                     |
| Cross-platform listed as DEFERRED                     | `AGENTS.md:60-76`; `README.md:161-177`; `BACKLOG.md:53-58` (Tier 2).  |

## Solution Summary

**One atomic phase, four deliverables (user-confirmed scope; do not re-litigate).**

1. **`.github/workflows/ci.yml` — the quality gate (every push/PR).** A single
   `ubuntu-latest` job: checkout, `astral-sh/setup-uv@v3` (with `enable-cache`),
   `uv sync` (uv reads `.python-version = 3.12` itself), then the six gates —
   `ruff check`, `ruff format --check`, `mypy src`, `pytest`, an `import
   sandfall` smoke — plus a recommended Linux **build-smoke**
   (`SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm`) that
   catches spec regressions on every push (~30 s, free on a public repo).
2. **`.github/workflows/release.yml — the 3-OS release build (on `v*` tags).**
   A `matrix.os = [ubuntu-latest, windows-latest, macos-latest]` job: checkout,
   setup-uv, `uv sync`, `SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec
   --noconfirm`. A bash rename step maps PyInstaller's output
   (`dist/sandfall` / `dist/sandfall.exe`) to distinct asset names
   (`sandfall-linux-x86_64`, `sandfall-windows-x86_64.exe`,
   `sandfall-macos-arm64` — `macos-latest` is Apple Silicon). Each OS uploads
   its binary via `actions/upload-artifact@v4`; `softprops/action-gh-release@v2`
   attaches `dist/sandfall-*` to the release the tag created. The job declares
   `permissions: contents: write`.
3. **`sandfall.spec` — header refresh only.** Line 2 "single-file Linux build"
   → "single-file build (Linux / Windows / macOS)". **No logic change** — the
   env-driven `console` block + `collect_all` already make it portable.
   `name="sandfall"` is unchanged (PyInstaller appends `.exe` on Windows; the
   release workflow does the per-platform renaming).
4. **Docs.** `README.md` gets a "Cross-platform builds (CI)" subsection under
   "Building" (release binaries produced automatically on `v*` tags; local
   Linux build unchanged; macOS ships **unsigned** as a **bare executable** —
   Gatekeeper caveat, Intel-Mac-needs-Rosetta note) and the "Status"/
   "Requirements" lines that say "Linux-only" / "future work" are updated.
   `AGENTS.md` "Future Work" moves the build + CI items to **done** (pointing
   at the workflows), keeping **code-signing / notarization** as the remaining
   deferred sub-item. `BACKLOG.md` marks the Tier-2 "Cross-platform builds + CI"
   item **shipped**.

## Phase List

| #  | Phase                                                                    | Cx | Depends On | Parallelizable With |
|----|-------------------------------------------------------------------------|----|------------|---------------------|
| 01 | CI + release workflows, spec header refresh, doc updates (atomic commit)| S  | —          | — (single phase)    |

## Dependency Map

```
01 (workflows + spec header + docs) ──► done
```

Single phase. The two workflows, the spec header edit, and the doc updates are
all part of the same logical change ("stand up cross-platform packaging") and
land in **one atomic commit**. The doc edits reference the workflows by path,
so the workflows and docs must ship together to avoid stale/stale-pointing
docs. Nothing downstream of this plan depends on it.

## Decision Log

All decisions follow directly from the user-confirmed scope (public repo →
3-OS matrix; test-on-Linux quality gate; release builds on tags; signing
deferred; macOS bare executable, no `.app`). Do not re-litigate without new
information.

1. **Release matrix = all three OS** (`ubuntu` / `windows` / `macos`), not the
   "windows + linux minimum." The founding brief said "windows + linux minimum;
   mac optional," but the repo is **public** so Actions is free on all three
   standard runners (Fact #2). The user opted into all three. *(Alternative
   considered: windows+linux only — rejected: macOS is free here and the spec
   is already portable, so there is no cost reason to defer it.)*
2. **CI quality gate runs on Linux only (every push/PR); the 3-OS build is
   separate (release tags only).** Tests/lint/types are OS-independent, so a
   single Linux job is the correct, cheap quality gate. Running the full 3-OS
   *build* on every push would burn minutes for no signal (the spec doesn't
   change per-PR in a way the Linux build-smoke wouldn't already catch).
   *(Alternative considered: 3-OS on every push — rejected: cost-free here but
   slow and noisy; the Linux build-smoke in ci.yml already guards the spec on
   every push.)*
3. **`ci.yml` includes a Linux build-smoke step** (`SANDFALL_RELEASE=1 uv run
   pyinstaller ...`). It is the *only* local-verifiable signal that the spec
   still builds, and it runs automatically on every push/PR at ~free cost. It
   is **recommended but optional** — if it proves flaky it can be dropped
   without touching the quality gate.
4. **Release assets are renamed per-platform before upload.** PyInstaller emits
   `dist/sandfall` (linux/mac) and `dist/sandfall.exe` (windows); a bash rename
   step produces `sandfall-<os>-<arch>[.exe]` so a release's `files:` glob
   attaches three distinct, self-describing binaries. *(Alternative considered:
   upload the raw `sandfall`/`sandfall.exe` and let the OS be implicit —
   rejected: ambiguous assets, especially linux-vs-mac which are both bare
   `sandfall` with no extension.)*
5. **macOS ships as a bare executable (no `.app` bundle).** A `.app` would
   require `--onedir` + a `BUNDLE(...)` block, which **collides with the
   `--onefile` design** (the spec intentionally has no `COLLECT`/`BUNDLE` —
   see `sandfall.spec:8-11`). For v1, `--onefile` on all three OS is the
   consistent, simplest path. *(Alternative considered: macOS `.app` —
   rejected: breaks the single-file model and is out of scope for v1.)*
6. **Code-signing / notarization is DEFERRED.** Signing needs credentials (a
   Windows code-signing cert and a macOS Developer ID + notarytool) the project
   does not have. v1 ships **unsigned** binaries; the known consequence
   (Windows SmartScreen + macOS Gatekeeper "unidentified developer" warnings)
   is **documented** as the v1 caveat. *(No alternative until credentials
   exist.)*
7. **macOS asset is `arm64`-only.** `macos-latest` is Apple Silicon (M-series).
   Intel Macs run it via Rosetta 2 — documented. *(Alternative considered:
   also build on a `macos-13` Intel runner — rejected: doubles macOS build
   time; Rosetta is acceptable for v1 and Intel-Mac share is small and
   shrinking.)*
8. **Manual version tags for v1; no auto-versioning.** `release.yml` fires on
   `push: tags: ['v*']`; a maintainer pushes a tag by hand. Bumping the version
   string into the tag/spec/build automatically is deferred. *(Alternative
   considered: tag-from-pyproject or release-please — rejected: scope creep;
   manual tags are fine while release cadence is low.)*
9. **No `act` requirement.** Local Actions pre-flight via `act` is optional and
   not part of the deliverable; the plan's local verification gate is "both
   YAML files parse + the Linux build/tests pass locally" (see Risks — the
   Windows/macOS builds can ONLY be verified on GitHub).

## Estimated Complexity

| Phase | Cx | Why |
|-------|----|-----|
| 01    | S  | Two new (small, self-contained) workflow files, a one-line spec header comment refresh, and three doc edits. No Python/source-code logic changes, no new dependencies, no signature changes. The risk is in getting the workflow YAML correct and in the fact that Windows/macOS can only be verified on GitHub — both addressed by literal YAML in the phase file and an explicit Risks note. |

## Risks & Unknowns

1. **Windows/macOS builds CANNOT be verified locally** (the dev box is Linux;
   PyInstaller does not cross-compile — Fact #1). **The only real verification
   of the 3-OS release build is pushing to GitHub.** Encode this prominently:
   - `ci.yml` runs on push → confirm it goes **green** in the Actions tab.
   - `release.yml` runs on a `v*` tag → push a throwaway tag
     (e.g. `v0.0.0-ci-test`) and confirm all three OS jobs build + upload +
     attach to the (draft) release. The Phase 01 reflection records the
     Actions-run URLs / outcomes. Delete the throwaway tag/release afterward.
   - The **local** gate is: both YAML files parse, and the Linux build + tests
     pass (`uv run pytest` && `SANDFALL_RELEASE=1 uv run pyinstaller
     sandfall.spec --noconfirm`). That proves the spec still builds and the
     YAML is well-formed; it does NOT prove Windows/macOS build.
2. **YAML correctness.** A typo or wrong action input name fails the whole job
   at runtime. Mitigation: the phase file gives literal YAML; the local check
   is `python -c "import yaml; yaml.safe_load(open(p))"` for both files, plus
   `actionlint` if available (note in the phase if it is not).
3. **Bash on Windows.** The `SANDFALL_RELEASE=1 <cmd>` env-prefix syntax and
   `mv` are bash-isms. The Windows runner ships Git Bash, so every cross-OS
   step uses `shell: bash` explicitly. Without `shell: bash`, the Windows job
   would default to PowerShell and the `VAR=cmd` form would fail.
4. **Unsigned-binary UX warnings.** Windows SmartScreen and macOS Gatekeeper
   will warn end users of an unsigned binary. This is the **known v1 caveat**
   (Decision Log #6) — documented, not fixed.
5. **`macos-latest` is arm64.** The resulting binary is Apple-Silicon-native;
   Intel Macs need Rosetta 2 — documented. If `macos-latest` ever flips back
   or to a different arch, the rename step's `macos-arm64` suffix should be
   revisited (it is a string in the workflow, not auto-detected).
6. **Spec portability is asserted, not yet proven cross-OS.** The spec *should*
   build clean on Windows/macOS (env-driven console + `collect_all`), but the
   first real proof is the GitHub run. If a per-OS hidden import or native
   dependency is missing, the fix is a targeted addition to the spec — recorded
   in the reflection, not assumed here.
7. **`softprops/action-gh-release@v2` attaches to the release that the tag
   created.** This requires the tag to be a release tag and `permissions:
   contents: write` (set at the top of `release.yml`). If the tag does not map
   to a release, the action creates one. Confirmed behavior of v2.

## Verification Philosophy

The phase's `Verification Commands` block runs these **local** gates (ALL must
exit zero before the phase is considered *locally* done):

```bash
uv run pytest                                      # tests still pass (unchanged source)
uv run ruff check .                                # lint
uv run ruff format --check .                       # format
uv run mypy src                                    # types
uv run python -c "import sandfall"                 # import smoke
SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm   # Linux build-smoke
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"      # ci.yml YAML valid
python -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))" # release.yml YAML valid
# (optional, if installed) actionlint .github/workflows/*.yml
```

**The cross-OS release build has no local equivalent** (Risk #1). The final
acceptance gate for the release path is the GitHub Actions run itself: push
the commit → watch `ci.yml` go green; push `v0.0.0-ci-test` → watch all three
`release.yml` jobs build and upload. The Phase 01 reflection records those run
URLs and outcomes as the authoritative evidence.

## Out of Scope (Future Work — DO NOT plan now)

- **Code-signing / notarization** (a Windows code-signing cert + a macOS
  Developer ID and `notarytool`). Needs credentials; deferred. Tracked to
  remain in `AGENTS.md` "Future Work" as the surviving deferred sub-item.
- **macOS `.app` bundle** (would need `--onedir` + `BUNDLE`; collides with the
  `--onefile` spec design — `sandfall.spec:8-11`).
- **A per-platform app icon** (`icon=None` stays; `sandfall.spec:84`).
- **Auto-versioning** (bumping the version into the tag/spec/build). Manual
  `v*` tags for v1 (Decision Log #8).
- **`act`** (local Actions runner) as a required pre-flight. Optional.
- **UPX compression on CI.** `upx=True` is already a no-op when UPX is absent
  (`sandfall.spec:76`); installing UPX on the runners to shrink the binary is a
  future nicety, not a v1 requirement.

## Foundation Reference

This plan closes the deferred item that has lived in three places since v1:
- `AGENTS.md:60-76` — "Future Work" (builds + CI matrix).
- `README.md:161-177` — "Status" (Linux-only; cross-platform deferred).
- `.agent/tasks/BACKLOG.md:53-58` — Tier-2 "Cross-platform builds + CI".

For the build context the implementer should read (re-read before editing —
line numbers drift):
- `sandfall.spec` — the already-portable `--onefile` spec; the only edit is
  the header comment at `sandfall.spec:2`. The env-driven `console` block at
  `sandfall.spec:47-49` and `collect_all` at `sandfall.spec:35-36` are why no
  logic change is needed.
- `pyproject.toml` — `requires-python`/dev deps (`pyproject.toml:6,24`) and the
  `sandfall` console script (`pyproject.toml:13`).
- `.python-version` — uv reads `3.12` from here; no explicit Python-version
  input is needed in the workflows.
- `.gitignore:8-9` — `build/` and `dist/` ignored (CI artifacts are uploaded,
  not committed).

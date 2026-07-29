# Security Policy

## Threat model

**sandfall is an offline, single-player desktop game.** Its attack surface is
intentionally tiny, and the following are **structurally absent** (verified by
audit, see "Audit history" below):

- No network code — no HTTP server, no client requests, no sockets.
- No authentication, authorization, sessions, or cookies.
- No database and no persistent storage of user data.
- No file I/O on user-supplied paths. The only `os.environ` access reads a
  single optional integer (`SANDFALL_FRAMES`) used as a test/debug seam.
- No deserialization of untrusted data (no `pickle`/`marshal`/`yaml.load`).
- No subprocess or shell execution (`subprocess`, `os.system`, `shell=True`).
- No dynamic code execution (`eval`, `exec`, `compile`).
- No cryptography (and therefore no custom/weak crypto or hardcoded keys).

The only user input is mouse + keyboard, which feeds a fixed-size in-memory
numpy grid. Every grid accessor is bounds-checked (out-of-bounds reads raise
`IndexError`; out-of-bounds writes are a silent no-op; `fill_circle` clamps its
iteration box). There is no path from input to an unchecked array index or to a
dangerous sink.

`random` (Mersenne Twister) is used for game mechanics only — never for
tokens, IDs, keys, or any security-sensitive purpose.

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes (current development line) |

Older versions are not maintained.

## Reporting a vulnerability

There is no dedicated security contact or private reporting channel set up for
this project yet. If you find a security issue, please open an issue on the
project's issue tracker describing it, or contact the maintainer through
whichever channel the repository is hosted on.

If a private reporting channel (e.g. GitHub's "Report a vulnerability" /
`security advisories`, or a published email) is added later, it will be
documented here.

## Dependency posture

- All dependencies are pinned by the committed **`uv.lock`**, so installs are
  reproducible. Runtime dependencies: `pygame-ce` and `numpy`.
- The manifest uses **lower-bound version specifiers with upper bounds**
  (e.g. `pygame-ce>=2.5,<3`, `numpy>=2.0,<3`) to prevent a silent major-version
  jump when the lockfile is regenerated.
- The application never loads images, arrays, or any data from disk or network
  (no `pygame.image.load`, no `numpy.load`/`memmap`/`fromfile`), which closes
  the historical image/array-parser CVE exposure paths in its dependencies.
- Automated CVE scanning (`pip-audit` against `uv.lock`) is **not yet** wired
  into CI (CI itself is future work — see `AGENTS.md` → Future Work). When CI
  exists, `pip-audit` should run on every change and on a schedule.

## Release build hardening

A **release** binary must not leak internal information to end users. The
PyInstaller spec (`sandfall.spec`) drives its console/traceback settings from
the `SANDFALL_RELEASE` environment variable:

```bash
# Development build (default): console attached, tracebacks visible on stderr.
uv run pyinstaller sandfall.spec --noconfirm

# Release build: no console window, no windowed-traceback dialog.
SANDFALL_RELEASE=1 uv run pyinstaller sandfall.spec --noconfirm
```

The test suite guards against an accidental regression to a debug-configured
release (see `tests/test_packaging.py`).

## Distributable binary integrity

The Linux single-file binary produced by `sandfall.spec` is **not code-signed**.
Tampering protection for distributed binaries (Authenticode signing for Windows,
Developer-ID signing + notarization for macOS, SHA-256 checksums / Sigstore for
Linux) is deferred to the cross-platform release pipeline tracked in
`AGENTS.md` → Future Work. Until then, obtain binaries only from a trusted
source and verify checksums where published.

## Audit history

- **2026-07** — Initial security audit (manual; no automated scanners were
  available in the environment). Result: **LOW risk**, 0 Critical/High/Medium,
  3 Low findings (all addressed here or tracked as future release-engineering
  work), 0 hardcoded secrets. See the audit report in the project history.

# Phase 01: Project Scaffolding

## Objective

Stand up a working Python project managed by `uv`: install uv, create the `src/sandfall/` layout, pin Python 3.12, add runtime + dev dependencies, configure ruff/mypy/pytest, add a `sandfall` console-script entry, a trivial passing test, a correct `.gitignore`, and update `AGENTS.md` with the canonical command list. No game logic yet.

## Depends On

None. This is the foundation.

## Can Parallelize With

None. Everything downstream needs the project to exist.

## Recommended Agent

@implementer

## Changes Required

### Step 0 — Install `uv` (it is NOT currently installed)

Run the official installer (curl), then verify. If `uv` is already present on the machine (check `command -v uv`), skip installation but still verify the version.

Files: none (this is environmental).

### Create / modify

- `/home/c0de/dev/sand-falling-game/pyproject.toml` — created via `uv init`, then edited to match the spec below.
- `/home/c0de/dev/sand-falling-game/src/sandfall/__init__.py` — package marker; may expose `__version__`.
- `/home/c0de/dev/sand-falling-game/src/sandfall/__main__.py` — minimal `main()` stub returning `0`.
- `/home/c0de/dev/sand-falling-game/tests/__init__.py` — empty package marker.
- `/home/c0de/dev/sand-falling-game/tests/test_smoke.py` — one trivial passing test.
- `/home/c0de/dev/sand-falling-game/.gitignore` — see exact contents below.
- `/home/c0de/dev/sand-falling-game/.python-version` — created by uv (`3.12`); leave it.
- `/home/c0de/dev/sand-falling-game/uv.lock` — created by `uv sync`; TRACK it.
- `/home/c0de/dev/sand-falling-game/AGENTS.md` — append a `## Commands` section.
- `/home/c0de/dev/sand-falling-game/README.md` — optional minimal one; only if `uv init` created it, otherwise skip. Do NOT create docs proactively.

## Implementation Instructions

### Step 0: Install uv

```bash
# only if `command -v uv` returns nothing
curl -LsSf https://astral.sh/uv/install.sh | sh
# reload shell env or: source $HOME/.local/bin/env  (path the installer prints)
uv --version    # MUST succeed
```

If the curl install is blocked by environment policy, fall back to `pipx install uv` or `pip install --user uv`. Do NOT proceed until `uv --version` works.

### Step 1: Initialize the project

From the repo root `/home/c0de/dev/sand-falling-game`:

```bash
uv init --name sandfall --python 3.12 --lib
```

`--lib` produces a `src/sandfall/` package layout. Verify with `ls` that `src/sandfall/__init__.py` exists. If `uv init` instead created a flat layout, delete and re-run with the correct flag, or manually `mkdir -p src/sandfall` and move files. The end state MUST have `src/sandfall/__init__.py`.

### Step 2: Edit `pyproject.toml` to match this spec EXACTLY (merge; do not duplicate keys)

```toml
[project]
name = "sandfall"
version = "0.1.0"
description = "A falling-sand sandbox game built with pygame-ce."
requires-python = ">=3.12"
dependencies = [
    "pygame-ce>=2.5",
    "numpy>=2.0",
]

[project.scripts]
sandfall = "sandfall.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "ruff>=0.6",
    "mypy>=1.11",
]

[tool.hatch.build.targets.wheel]
packages = ["src/sandfall"]

[tool.ruff]
line-length = 88
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]

[tool.mypy]
python_version = "3.12"
strict = true
packages = ["sandfall"]
mypy_path = "src"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

Notes:
- `pyinstaller` is **deliberately NOT added here** — it enters in Phase 06 to keep Phase 01 minimal (per approved plan).
- If `uv init --lib` already wrote a different `[build-system]` (e.g. with `uv_build`), keep whichever backend produced a working `src/` layout; the important parts are `name`, `requires-python`, `dependencies`, `[project.scripts]`, and the `[tool.*]` tables.

### Step 3: Add deps & sync

```bash
uv sync
```

This creates `uv.lock` and `.venv/`. `uv.lock` MUST be committed (it is tracked). `.venv/` MUST be ignored (it is, via `.gitignore`).

### Step 4: Source files

`src/sandfall/__init__.py`:
```python
"""Sandfall — a falling-sand sandbox game."""

__version__ = "0.1.0"
```

`src/sandfall/__main__.py`:
```python
"""Entry point for the ``sandfall`` console script."""

__all__ = ["main"]


def main() -> int:
    """Run the sandfall game.

    Currently a stub; wired up in Phase 04.
    """
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`tests/__init__.py`: empty file (or a one-line docstring).

`tests/test_smoke.py`:
```python
"""Smoke test: the package imports and the entry stub returns 0."""


def test_package_imports() -> None:
    import sandfall

    assert sandfall.__version__


def test_main_returns_zero() -> None:
    from sandfall.__main__ import main

    assert main() == 0
```

### Step 5: `.gitignore` (exact contents)

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so

# Packaging / builds
build/
dist/
.eggs/
*.egg-info/
*.egg

# Virtual envs
.venv/
env/
venv/

# Tool caches
.mypy_cache/
.ruff_cache/
.pytest_cache/
.coverage
htmlcov/

# OS / editors
.DS_Store
.idea/
.vscode/
*.swp

# NOTE: uv.lock is TRACKED on purpose (reproducible installs).
# NOTE: *.spec is TRACKED on purpose (PyInstaller spec is source, phase 06).
```

Do NOT add `uv.lock`, `*.spec`, or `src/` to the ignore list.

### Step 6: Update `AGENTS.md`

Append (do not rewrite) a new section to `/home/c0de/dev/sand-falling-game/AGENTS.md`:

```markdown
## Commands

All commands run from the repo root.

- **Run the game:** `uv run sandfall`
- **Run tests:** `uv run pytest`
- **Lint:** `uv run ruff check .`
- **Format:** `uv run ruff format .`
- **Type-check:** `uv run mypy src`
- **Sync deps:** `uv sync`

Python and dependencies are managed by `uv`. The lockfile (`uv.lock`) is committed.
```

Leave the existing `## PROMPT` section intact.

### Step 7: First logical commits

Per global git-hygiene rules, split into logical commits, e.g.:
1. `chore: scaffold sandfall project with uv` — pyproject, src stubs, tests, .gitignore, uv.lock, .python-version.
2. `docs: add commands section to AGENTS.md`.

(Commits are at the implementer's discretion but must NOT bundle unrelated changes.)

## Acceptance Criteria

- [ ] `command -v uv` returns a path and `uv --version` prints a version.
- [ ] `pyproject.toml` exists with `name = "sandfall"`, `requires-python = ">=3.12"`, `pygame-ce` and `numpy` in `dependencies`, a `sandfall` console script, and working `[tool.ruff]` / `[tool.mypy]` / `[tool.pytest.ini_options]` tables.
- [ ] `src/sandfall/__init__.py` and `src/sandfall/__main__.py` exist; `src/sandfall/__main__.py` has a `main() -> int` returning `0`.
- [ ] `tests/test_smoke.py` exists with at least two passing tests.
- [ ] `uv.lock` exists and is tracked (NOT in `.gitignore`).
- [ ] `.gitignore` ignores `__pycache__/`, `.venv/`, `dist/`, `build/`, caches — and does NOT ignore `uv.lock` or `*.spec`.
- [ ] `AGENTS.md` has a `## Commands` section with all six canonical commands.
- [ ] `uv run sandfall` runs without error and exits cleanly (prints nothing; returns 0).
- [ ] `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src` all exit zero.

## Verification Commands

Run these from the repo root. ALL must exit zero.

```bash
# Build / import smoke
uv run python -c "import sandfall; print(sandfall.__version__)"

# Entry point runs
uv run sandfall; echo "exit=$?"

# Tests
uv run pytest

# Lint
uv run ruff check .

# Format check (does NOT rewrite)
uv run ruff format --check .

# Type-check (strict on the sandfall package)
uv run mypy src
```

Do NOT proceed to Phase 02 until every command above exits zero.

## Documentation Updates

- `AGENTS.md` — `## Commands` section (in-phase, above).
- After completing the phase, write `.agent/tasks/sandfall/01-scaffolding-reflection.md`.

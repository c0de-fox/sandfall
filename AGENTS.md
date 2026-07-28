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

Python and dependencies are managed by `uv`. The lockfile (`uv.lock`) is committed.


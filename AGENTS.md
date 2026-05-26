# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## Project

MCP server demo app — a Python MCP server exposing a post-sale delivery management domain (accounts → projects → milestones → tasks) over streamable HTTP. Implements all three MCP primitives: Tools, Resource, and Prompt.

**Specs:**
- `docs/spec.md` — feature and demo spec; the authoritative source for what gets built and why
- `docs/engineering_spec.md` — implementation spec; the primary reference during implementation (file layout, schema, queries, contracts, test cases)
- `docs/tasks.md` — implementation task list and progress tracker; update task status as work progresses; commit and push when a task reaches `complete` before starting the next

## Stack

- **Python** with `uv` for package/environment management
- **fastmcp** — MCP server framework (streamable HTTP transport, `/mcp` endpoint)
- **SQLite** — data layer via stdlib `sqlite3`; database at `data/delivery.db` (override with `DB_PATH` env var); gitignored — run `uv run python seed.py` before starting the server
- **httpx** — HTTP client used in `demo.py`'s raw MCP client
- **Ruff** for linting and formatting
- **pytest** for testing

## Key files

```
mcp_demo_server.py  MCP server — tools, resource, prompt, health endpoint (port 8000)
db.py           Database module — connection factory and all query functions
demo.py         Demo runner — MCP client, agent subprocess, judge loop
demo.sh         Single entry point for running the full demo
stop.sh         Stop the running MCP server (reads .server.pid)
seed.py         Seed script — populates data/delivery.db; not application code
```

## Common commands

```bash
uv sync                                            # install dependencies
uv run python seed.py                              # seed the database
uv run python mcp_demo_server.py                   # start MCP server (port 8000)
./stop.sh                                          # stop the MCP server cleanly
./demo.sh                                          # run the full demo end-to-end
uv run ruff check .                                # lint
uv run ruff format .                               # format
uv run pytest                                      # run all tests
uv run pytest tests/path/to/test.py::test_name    # run a single test
```

## Testing

Tests are written as each module is implemented — not deferred to the end. A module is not complete until its tests are written and pass. Test cases for each module are defined in `docs/engineering_spec.md` alongside the module they cover.

All tests use in-memory SQLite (`":memory:"`). The `conftest.py` fixtures (`db_conn`, `seeded_db_conn`) provide isolated connections; tool, resource, and prompt handler tests monkeypatch `db.get_connection` to use the fixture connection rather than the real database path.

## Python environment

All Python must be invoked inside the project `.venv` to keep any `pip install`s isolated from the global environment. Use `uv run` (which activates `.venv` automatically) or invoke `.venv/bin/python` directly.

Never use the system `python` or `python3` binary directly.

## Git practices

**Staging:** Always stage files explicitly by name — never `git add .` or `git add -A`. This prevents accidentally committing unintended files (secrets, build artifacts, scratch work). Stage only the files that belong to the current task.

**Commit scope:** Each commit should correspond to exactly one completed task from `docs/tasks.md`. Do not bundle multiple tasks into one commit, and do not split a single task across multiple commits. Update the task status in `docs/tasks.md` and include that file in the same commit as the task's code.

**Commit messages:** Use the imperative mood and a concise subject line (50 characters or fewer). The subject should state what the commit does, not what you did. Lead with the task number and a short description of what was added or changed:

```
Task 2: add database module and query tests
Task 5: add get_task tool handler
```

Do not pad messages with filler phrases ("initial implementation of", "adds support for"). Do not describe the how — the diff already shows that. If the why is non-obvious and not captured in a spec, add a blank line after the subject and a brief body.

**No force-push, no amend after push:** Once a commit is pushed, do not rewrite it. If a mistake was made, fix it in a new commit.

**Check before committing:** Run `git diff --staged` before committing to verify only the intended changes are staged. Run `uv run ruff check .` and `uv run pytest` to confirm the code is clean before the commit lands.

**`.gitignore` is authoritative:** Do not commit files that `.gitignore` excludes. If a needed file is being ignored unexpectedly, fix `.gitignore` rather than using `git add -f`.

## Ephemeral scripting

`scratch.py` in the project root is reserved for one-off scripting tasks — exploration, data inspection, quick experiments. When you need to run a throwaway script, write it to `scratch.py` and execute it with `.venv/bin/python scratch.py`. Do not inline such code as multi-line shell commands in the Bash tool. `scratch.py` is not part of the production codebase and is excluded from version control.

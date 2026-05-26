# Implementation Tasks
*Delivery Manager MCP Server*

Derived from `engineering_spec.md`. Each task bundles code and test work; status reflects the combined state. A task is not complete until all tests pass. Completed tasks are committed and pushed before the next task begins.  At the beginning of any task, verify that the previous task was actually committed.

**Statuses:** `pending` · `in-progress` · `code-complete` · `in-testing` · `complete`

---

### 1. Project scaffold — `complete`

`pyproject.toml` with runtime and dev dependencies (`fastmcp`, `httpx`, `pytest`, `ruff`). `data/` and `tests/` directories.

---

### 2. Database — `complete`

`db.py`: connection factory, all query functions.  
`tests/conftest.py`: `db_conn` and `seeded_db_conn` fixtures.  
`tests/test_db.py`: all query function tests.

---

### 3. Server scaffold — `complete`

`server.py`: `FastMCP` app instance, HTTP transport on port 8000, `GET /health` route.  
`tests/test_server.py`: health endpoint test.

---

### 4. `get_account_status` tool — `complete`

`server.py`: `get_account_status` handler.  
`tests/test_tools.py`: `get_account_status` tests.

---

### 5. `get_task` tool — `pending`

`server.py`: `get_task` handler.  
`tests/test_tools.py`: `get_task` tests.

---

### 6. `update_task_status` tool — `pending`

`server.py`: `update_task_status` handler with full cascade logic.  
`tests/test_tools.py`: all `update_task_status` tests (precondition, task-not-found, demo path, milestone-advanced, full cascade).

---

### 7. `accounts://all` resource — `pending`

`server.py`: resource handler.  
`tests/test_resource.py`: resource tests.

---

### 8. `assess-account` prompt — `pending`

`server.py`: prompt handler.  
`tests/test_prompt.py`: prompt tests.

---

### 9. Configuration files — `pending`

`.mcp.json`: Claude Code MCP server registration.  
`.claude-code-version`: pinned Claude Code CLI version.

---

### 10. `demo.py` — `pending`

MCP client (`initialize`, `read_resource`, `get_prompt`, `call_get_task`), display functions, agent runner, judge loop, main sequence.  
`tests/test_demo.py`: `verify_update` and data extraction tests.

---

### 11. `demo.sh` — `pending`

Entry point: Claude Code version check and install, `uv sync`, server start, health poll, demo run, EXIT trap.

---

### 12. End-to-end validation — `pending`

Write `seed.py` and run `uv run python seed.py` to populate `data/delivery.db`. Then run `./demo.sh` and confirm: resource display, agent tool calls, judge verification, and before/after delta.

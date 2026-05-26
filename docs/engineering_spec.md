# Engineering Spec
*Delivery Manager MCP Server*

Implementation detail for the features defined in `spec.md`. Covers file layout, database schema and queries, module responsibilities, tool/resource/prompt contracts, MCP client protocol, and configuration. No source code.

---

## File Layout

```
mcp-demo/
├── server.py              # MCP server — tools, resource, prompt, health endpoint
├── db.py                  # Database module — connection, all query functions
├── demo.py                # Demo runner — MCP client, agent subprocess, judge loop
├── demo.sh                # Entry point — version check, server lifecycle, runs demo.py
├── seed.py                # Seed script — not application code, excluded from this spec
├── .mcp.json              # Claude Code MCP server registration
├── .claude-code-version   # Pinned Claude Code CLI version
├── pyproject.toml         # Python project config and dependencies
└── tests/
    ├── conftest.py        # Shared fixtures — in-memory DB, test data, monkeypatching
    ├── test_db.py         # db.py query function tests
    ├── test_tools.py      # Tool handler tests
    ├── test_resource.py   # Resource handler tests
    ├── test_prompt.py     # Prompt handler tests
    ├── test_server.py     # Health endpoint test
    └── test_demo.py       # Demo module unit tests
```

---

## Test Fixtures — `tests/conftest.py`

Two function-scoped pytest fixtures, shared across all test modules.

**`db_conn`** — yields an in-memory SQLite connection (`":memory:"`) with the full schema (DDL from the Database section) applied and foreign keys enabled. No data inserted. Used by `test_db.py`, which inserts only the rows each test requires.

**`seeded_db_conn`** — extends `db_conn` with test data mirroring the spec.md seed data:
- Acme Corp (`active`), project `active`, Milestone 1 `complete`, Milestone 2 `in_progress` with 2 `complete` tasks and 1 `open` task
- Globex Inc (`at_risk`), project `at_risk`, Milestone 1 `complete`, Milestone 2 `in_progress` with 1 `complete` task, 1 `blocked` task (`updated_at` set 14 days in the past), 1 `invalid` task

Used by `test_tools.py`, `test_resource.py`, and `test_prompt.py`. These tests monkeypatch `db.get_connection` to return the fixture connection, isolating handlers from the real database path.

---

## Database

### Schema

```sql
CREATE TABLE accounts (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('active', 'at_risk')),
    updated_at TEXT NOT NULL
);

CREATE TABLE projects (
    id         TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    name       TEXT NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('active', 'at_risk', 'complete')),
    updated_at TEXT NOT NULL
);

CREATE TABLE milestones (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id),
    name       TEXT NOT NULL,
    "order"    INTEGER NOT NULL,
    status     TEXT NOT NULL CHECK (status IN ('not_started', 'in_progress', 'complete')),
    updated_at TEXT NOT NULL
);

CREATE TABLE tasks (
    id           TEXT PRIMARY KEY,
    milestone_id TEXT NOT NULL REFERENCES milestones(id),
    title        TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('open', 'in_progress', 'pending_customer', 'blocked', 'complete', 'invalid')),
    owner        TEXT,
    blocker      TEXT,
    updated_at   TEXT NOT NULL
);
```

All `updated_at` values are ISO 8601 UTC strings (`YYYY-MM-DDTHH:MM:SSZ`).

### Indexes

```sql
CREATE INDEX idx_projects_account_id   ON projects(account_id);
CREATE INDEX idx_milestones_project_id ON milestones(project_id);
CREATE INDEX idx_tasks_milestone_id    ON tasks(milestone_id);
```

### Database location

Path: `data/delivery.db` relative to the project root. `db.py` accepts an override via the `DB_PATH` environment variable.

---

## Database Module — `db.py`

Provides a single connection factory and one function per distinct query. No ORM. The connection uses `row_factory = sqlite3.Row` so callers can access columns by name.

### Connection

`get_connection()` — opens and returns a `sqlite3.Connection` to the configured database path. Foreign key enforcement enabled on every connection (`PRAGMA foreign_keys = ON`).

### Query functions

**`fetch_account(conn, account_id)`**
```sql
SELECT id, name, status, updated_at
FROM accounts
WHERE id = ?
```
Returns one row or `None`.

**`fetch_active_project(conn, account_id)`**
```sql
SELECT id, name, status
FROM projects
WHERE account_id = ? AND status != 'complete'
LIMIT 1
```
Returns one row or `None`.

**`fetch_current_milestone(conn, project_id)`**

Two queries in priority order:
1. In-progress milestone:
```sql
SELECT id, name, status
FROM milestones
WHERE project_id = ? AND status = 'in_progress'
LIMIT 1
```
2. If none, lowest-order not-started milestone:
```sql
SELECT id, name, status
FROM milestones
WHERE project_id = ? AND status = 'not_started'
ORDER BY "order" ASC
LIMIT 1
```
Returns one row or `None`.

**`fetch_tasks_for_milestone(conn, milestone_id)`**
```sql
SELECT id, title, status, owner, blocker, updated_at
FROM tasks
WHERE milestone_id = ?
ORDER BY rowid
```
Returns all rows (may be empty list).

**`fetch_task(conn, task_id)`**
```sql
SELECT id, title, status, owner, blocker, updated_at
FROM tasks
WHERE id = ?
```
Returns one row or `None`.

**`update_task(conn, task_id, new_status, now)`**
```sql
UPDATE tasks
SET status = ?, updated_at = ?
WHERE id = ?
```
`now` is an ISO 8601 UTC string generated at call time.

**`fetch_incomplete_tasks_for_milestone(conn, milestone_id)`**
```sql
SELECT id, title, status, blocker
FROM tasks
WHERE milestone_id = ? AND status != 'complete'
ORDER BY rowid
```
Returns all non-complete rows. The caller determines whether the milestone is complete by checking if this result is empty.

**`fetch_milestone_for_task(conn, task_id)`**
```sql
SELECT m.id, m.project_id, m.name, m.status
FROM milestones m
JOIN tasks t ON t.milestone_id = m.id
WHERE t.id = ?
```
Returns one row.

**`complete_milestone(conn, milestone_id, now)`**
```sql
UPDATE milestones
SET status = 'complete', updated_at = ?
WHERE id = ?
```

**`fetch_incomplete_milestones_for_project(conn, project_id)`**
```sql
SELECT id, name, status
FROM milestones
WHERE project_id = ? AND status != 'complete'
ORDER BY "order"
```

**`fetch_project_for_milestone(conn, milestone_id)`**
```sql
SELECT p.id, p.account_id, p.name, p.status
FROM projects p
JOIN milestones m ON m.project_id = p.id
WHERE m.id = ?
```
Returns one row.

**`complete_project(conn, project_id, now)`**
```sql
UPDATE projects
SET status = 'complete', updated_at = ?
WHERE id = ?
```

**`clear_account_at_risk(conn, account_id, now)`**
```sql
UPDATE accounts
SET status = 'active', updated_at = ?
WHERE id = ? AND status = 'at_risk'
```

**`fetch_all_accounts_with_context(conn)`**

Executed as four queries composed in application code (not a single join) to keep the mapping logic clear:
1. All accounts ordered by name.
2. For each account: active project (`status != 'complete'`).
3. For each project: current milestone (same priority logic as `fetch_current_milestone`).
4. For each milestone: all tasks (same as `fetch_tasks_for_milestone`).

Returns a list of account dicts with nested project → milestone → tasks structure.

### Tests — `tests/test_db.py`

Fixture: `db_conn`. Each test inserts only the rows it needs.

**`fetch_account`**
- Returns the correct row for a known `account_id`
- Returns `None` for an unknown `account_id`

**`fetch_active_project`**
- Returns a project row for an account with a non-complete project
- Returns `None` when the account's only project has `status = 'complete'`

**`fetch_current_milestone`**
- Returns the `in_progress` milestone when one exists
- Returns `in_progress` over `not_started` when both exist in the same project
- Returns the lowest-`order` `not_started` milestone when no `in_progress` milestone exists
- Returns `None` when all milestones for the project are `complete`

**`fetch_tasks_for_milestone`**
- Returns all tasks in rowid order for a milestone with tasks
- Returns an empty list for a milestone with no tasks

**`fetch_task`**
- Returns the full row for a known `task_id`
- Returns `None` for an unknown `task_id`

**`update_task`**
- `status` and `updated_at` change to the supplied values; all other columns are unchanged

**`fetch_incomplete_tasks_for_milestone`**
- Excludes tasks with `status = 'complete'`
- Includes tasks with `status = 'invalid'`
- Returns an empty list when all tasks in the milestone are `complete`

**`fetch_milestone_for_task`**
- Returns the milestone row including `id` and `project_id` for a known task

**`complete_milestone`**
- Sets `status` to `complete` and updates `updated_at`; other columns unchanged

**`fetch_incomplete_milestones_for_project`**
- Excludes milestones with `status = 'complete'`
- Results are ordered ascending by `"order"`

**`fetch_project_for_milestone`**
- Returns the project row including `id` and `account_id` for a known milestone

**`complete_project`**
- Sets `status` to `complete` and updates `updated_at`; other columns unchanged

**`clear_account_at_risk`**
- Sets an `at_risk` account's `status` to `active` and updates `updated_at`
- Does not modify an account already in `active` status

**`fetch_all_accounts_with_context`**
- Returns one entry per account, ordered by name
- Each entry contains the correct nested project → milestone → tasks structure
- An account with no non-complete project has `project: null`
- A project with no current milestone has `milestone: null`
- A milestone with no tasks has `tasks: []`
- A complete project is not included in any account's entry

---

## Server Module — `server.py`

### Framework and transport

`FastMCP` app instance, HTTP transport. Listens on `0.0.0.0:8000`. The `/mcp` endpoint is managed by fastmcp. A separate `GET /health` route returns `{"status": "ok"}` with HTTP 200 — this is the readiness probe used by `demo.sh`.

The health route is added to the underlying ASGI app that fastmcp exposes. Implementation detail: fastmcp's HTTP transport wraps a Starlette app; additional routes can be mounted on it.

### Database connection

One connection per request, opened and closed within each handler. `db.get_connection()` is called at the top of each tool, resource, and prompt handler.

### Tool registration

Three tools registered with `@mcp.tool()`:

- `get_account_status(account_id: str)` — see Tool Contracts below
- `get_task(task_id: str)` — see Tool Contracts below
- `update_task_status(task_id: str, new_status: str)` — see Tool Contracts below

### Resource registration

One resource registered with `@mcp.resource("accounts://all")`:

Handler calls `db.fetch_all_accounts_with_context()` and returns the structured result. See Resource Contract below.

### Prompt registration

One prompt registered with `@mcp.prompt(name="assess-account")`:

The handler function may use any valid Python name; the MCP-exposed name is `assess-account` (hyphen), set via the explicit `name` parameter. See Prompt Contract below.

### Tests — `tests/test_server.py`

Fixture: Starlette `TestClient` wrapping the FastMCP ASGI app.

- `GET /health` returns HTTP 200 with JSON body `{"status": "ok"}`

---

## Tool Contracts

All return values are plain dicts serialized by fastmcp. Error responses include `"error": true` and a `"code"` string. Success responses never include an `"error"` key.

### `get_account_status(account_id)`

**Logic:**
1. Fetch account by `account_id`. If not found: return error.
2. Fetch active project for account. If not found: return error.
3. Fetch current milestone for project. If not found: return error.
4. Fetch all tasks for milestone.
5. Return assembled result.

**Success response:**
```json
{
  "account":   { "id": "…", "name": "…", "status": "…", "updated_at": "…" },
  "project":   { "id": "…", "name": "…", "status": "…" },
  "milestone": { "id": "…", "name": "…", "status": "…" },
  "tasks": [
    { "id": "…", "title": "…", "status": "…", "owner": "…", "blocker": "…", "updated_at": "…" }
  ]
}
```

**Error responses:**
```json
{ "error": true, "code": "ACCOUNT_NOT_FOUND",   "reason": "No account with id '…'" }
{ "error": true, "code": "NO_ACTIVE_PROJECT",   "reason": "…" }
{ "error": true, "code": "NO_CURRENT_MILESTONE","reason": "…" }
```

#### Tests — `tests/test_tools.py`

Fixture: `seeded_db_conn` monkeypatched into `db.get_connection`.

- Returns the correct nested structure (account, project, milestone, tasks) for a known account
- All task fields are present: `id`, `title`, `status`, `owner`, `blocker`, `updated_at`
- Returns `ACCOUNT_NOT_FOUND` for an unknown `account_id`
- Returns `NO_ACTIVE_PROJECT` when the account's only project is `complete`
- Returns `NO_CURRENT_MILESTONE` when all milestones in the active project are `complete`

---

### `get_task(task_id)`

**Logic:**
1. Fetch task by `task_id`. If not found: return error.
2. Return task record.

**Success response:**
```json
{ "id": "…", "title": "…", "status": "…", "owner": "…", "blocker": "…", "updated_at": "…" }
```

**Error response:**
```json
{ "error": true, "code": "TASK_NOT_FOUND", "reason": "No task with id '…'" }
```

#### Tests — `tests/test_tools.py`

Fixture: `seeded_db_conn` monkeypatched into `db.get_connection`.

- Returns the full task record for a known `task_id`
- Returns `TASK_NOT_FOUND` for an unknown `task_id`

---

### `update_task_status(task_id, new_status)`

**Valid status values:** `open`, `in_progress`, `pending_customer`, `blocked`, `complete`, `invalid`

**Logic:**

*Precondition check (no DB writes if this fails):*
1. If `new_status` is not in the valid set: return `INVALID_STATUS` error with `current_status` from a `fetch_task` call.

*On passing precondition:*
1. Fetch task to confirm existence. If not found: return `TASK_NOT_FOUND` error.
2. Call `update_task(task_id, new_status, now)`.
3. Call `fetch_milestone_for_task(task_id)` to get `milestone_id` and `project_id`.
4. Call `fetch_incomplete_tasks_for_milestone(milestone_id)`.
5. If any incomplete tasks remain: return task-updated result with blocking tasks list.
6. Call `complete_milestone(milestone_id, now)`.
7. Call `fetch_project_for_milestone(milestone_id)` to get `account_id` (project_id is already known from step 3).
8. Call `fetch_incomplete_milestones_for_project(project_id)`.
9. If any incomplete milestones remain: return milestone-advanced result with remaining milestones list.
10. Call `complete_project(project_id, now)`.
11. Call `clear_account_at_risk(account_id, now)`.
12. Return full cascade result.

All steps 1–12 execute within a single transaction on a single connection, opened at the start of the handler and committed before returning. This ensures that reads at steps 4 and 8 see the uncommitted writes from steps 2 and 6 respectively (SQLite guarantees a connection sees its own transaction's writes). If any write fails, roll back and return a `WRITE_FAILED` error.

**Error responses:**
```json
{ "error": true, "code": "INVALID_STATUS",  "reason": "…", "current_status": "…" }
{ "error": true, "code": "TASK_NOT_FOUND",  "reason": "…" }
{ "error": true, "code": "WRITE_FAILED",    "reason": "…" }
```

**Task updated, milestone not complete:**
```json
{
  "task_updated":       { "id": "…", "new_status": "…" },
  "milestone_advanced": false,
  "blocking_tasks": [
    { "id": "…", "title": "…", "status": "…", "blocker": "…" }
  ]
}
```

**Milestone advanced, project not complete:**
```json
{
  "task_updated":         { "id": "…", "new_status": "…" },
  "milestone_advanced":   true,
  "milestone":            { "id": "…", "name": "…", "status": "complete" },
  "project_complete":     false,
  "remaining_milestones": [{ "id": "…", "name": "…", "status": "…" }]
}
```

**Full cascade (project and account updated):**
```json
{
  "task_updated":          { "id": "…", "new_status": "…" },
  "milestone_advanced":    true,
  "milestone":             { "id": "…", "name": "…", "status": "complete" },
  "project_complete":      true,
  "project":               { "id": "…", "name": "…", "status": "complete" },
  "account_status_updated":true,
  "account":               { "id": "…", "name": "…", "status": "active" }
}
```

#### Tests — `tests/test_tools.py`

Fixture: `seeded_db_conn` monkeypatched into `db.get_connection`. Each test that mutates data uses a fresh fixture connection.

**Precondition:**
- Returns `INVALID_STATUS` (with `current_status`) when `new_status` is not in the valid set
- The task's `status` in the database is unchanged after an `INVALID_STATUS` response

**Task not found:**
- Returns `TASK_NOT_FOUND` for an unknown `task_id` with a valid `new_status`

**Task updated, milestone not complete (demo path):**
- Task `status` and `updated_at` are updated in the database
- Response has `milestone_advanced: false`
- `blocking_tasks` includes the `invalid`-status task
- `blocking_tasks` does not include the `complete`-status task

**Milestone advanced, project not complete:**

The seeded accounts cannot reach the milestone-advanced-but-not-complete path: Acme has only two milestones (completing M2 also completes the project); Globex's M2 has an `invalid` task that prevents all-tasks-complete. This test uses `db_conn` with its own minimal data: one account, one project, two `not_started` milestones with one task each. The test updates M1's task to `complete`.

- Milestone M1 `status` becomes `complete`
- Response has `milestone_advanced: true` and a `remaining_milestones` list containing M2

**Full cascade:**

The seeded accounts cannot reach the full cascade path: Globex's milestone is blocked by an `invalid` task; Acme's account is already `active`. This test uses `db_conn` with its own minimal data: one `at_risk` account, one `at_risk` project, one `in_progress` milestone, one `open` task. The test updates that task to `complete`.

- Project `status` becomes `complete`
- Account `status` changes from `at_risk` to `active`
- Response contains `project_complete: true` and `account_status_updated: true`

---

## Resource Contract — `accounts://all`

**URI:** `accounts://all`

**Logic:** Calls `db.fetch_all_accounts_with_context()` and returns the result directly.

**Response shape:**
```json
[
  {
    "id": "…", "name": "…", "status": "…", "updated_at": "…",
    "project": {
      "name": "…", "status": "…",
      "milestone": {
        "name": "…", "status": "…",
        "tasks": [
          { "id": "…", "title": "…", "status": "…", "owner": "…", "blocker": "…", "updated_at": "…" }
        ]
      }
    }
  }
]
```

If an account has no active project, `"project"` is `null`. If a project has no current milestone, `"milestone"` is `null`. If a milestone has no tasks, `"tasks"` is `[]`.

### Tests — `tests/test_resource.py`

Fixture: `seeded_db_conn` monkeypatched into `db.get_connection`.

- Returns a list containing both test accounts
- Accounts are ordered by name (Acme Corp before Globex Inc)
- Account entries contain `id`, `name`, `status`, `updated_at`
- Project entries contain `name` and `status`
- Milestone entries contain `name` and `status`
- Task entries contain `id`, `title`, `status`, `owner`, `blocker`, `updated_at`
- Globex Milestone 2 tasks include the `blocked`, `complete`, and `invalid` tasks

---

## Prompt Contract — `assess-account`

**Argument:** `account_id: str`

**Logic:**
1. Call `get_account_status(account_id)` internally (direct function call, not MCP round-trip). If it returns an error, raise so fastmcp surfaces the failure.
2. Filter `tasks` to only those with `status == 'blocked'`. All other tasks (including `invalid`) are excluded from the briefing.
3. For each blocked task: compute `days_blocked` as the number of whole days between `updated_at` and the current UTC time.
4. Construct a filled user-role message with two sections:

**Briefing section** contains:
- Account name and status
- Project name and status
- Current milestone name and status
- Blocked task list only: id, title, status, owner, blocker, days_blocked

**Decision framing section** instructs the model to:
- Determine the appropriate action for the blocked task: nudge the customer, escalate, or place on hold — model's judgment
- Call `update_task_status(task_id, chosen_status)` to execute the action, where the prompt text specifies which `new_status` value corresponds to each action

**Constraint:** Every action choice offered in the decision framing must map to a `new_status` value that is not `blocked`. The judge loop verifies the agent acted by comparing the post-run task status against `baseline_status = 'blocked'` — if the model calls `update_task_status` with `new_status = 'blocked'` (a no-op on an already-blocked task), the status is unchanged and the judge incorrectly treats the run as a failure. The prompt text must not offer any action that resolves to `blocked`.

**Return value:** A single MCP `PromptMessage` with role `user` and the filled text as content.

### Tests — `tests/test_prompt.py`

Fixture: `seeded_db_conn` monkeypatched into `db.get_connection`.

- Returns a `PromptMessage` with `role = "user"`
- The message text contains the account name, project name, and milestone name
- Only the `blocked` task appears in the task list; `complete`, `invalid`, and `open` tasks are absent
- `days_blocked` is present and reflects the number of whole days since the blocked task's `updated_at` (which is set 14 days in the past in the fixture)
- Raises an error when called with an unknown `account_id`

---

## Demo Module — `demo.py`

### MCP client

All MCP communication is raw `httpx` POST requests to `http://localhost:8000/mcp`. JSON-RPC 2.0 envelope. The `Mcp-Session-Id` header is captured from the `initialize` response and passed on all subsequent requests.

Request ID is an incrementing integer per session.

#### `initialize()`
```json
{
  "jsonrpc": "2.0", "id": 1, "method": "initialize",
  "params": {
    "protocolVersion": "2025-03-26",
    "capabilities": {},
    "clientInfo": { "name": "demo", "version": "0.1" }
  }
}
```
Captures `Mcp-Session-Id` from response headers. Sends `notifications/initialized` after.

#### `read_resource(uri)`
```json
{ "jsonrpc": "2.0", "id": N, "method": "resources/read", "params": { "uri": "accounts://all" } }
```
Returns the `contents` array from the response.

#### `get_prompt(name, arguments)`
```json
{ "jsonrpc": "2.0", "id": N, "method": "prompts/get", "params": { "name": "assess-account", "arguments": { "account_id": "…" } } }
```
Returns the `messages` array. The first message's `content.text` is the filled prompt.

#### `call_get_task(task_id)`
```json
{ "jsonrpc": "2.0", "id": N, "method": "tools/call", "params": { "name": "get_task", "arguments": { "task_id": "…" } } }
```
Returns the parsed tool result content.

### Display functions

**`display_accounts(resource_data)`** — formats and prints the full account/task dataset to stdout. Structured text output: one block per account, indented project → milestone → task lines. Status values printed inline. Intended to be human-readable at a glance, not JSON.

**`display_delta(before_data, after_data)`** — prints only changed fields between two `accounts://all` responses (specifically task status changes). Highlights the blocked→pending_customer transition.

### Agent runner

**`run_claude_p(prompt_text, session_uuid)`**

Invokes as a subprocess:
```
claude -p --session-id {session_uuid} --output-format json "{prompt_text}"
```
Streams stdout in real time (tool calls visible as they happen). Returns the full JSON output on completion.

**`run_claude_p_resume(session_uuid, message)`**

Invokes as a subprocess:
```
claude -p --resume {session_uuid} --output-format json "{message}"
```
Same streaming behavior.

### Judge loop

**`verify_update(task_id, baseline_status)`**

Calls `call_get_task(task_id)` and compares the returned `status` against `baseline_status`. Returns `True` if status has changed, `False` if unchanged.

### Main sequence

```
1. initialize() → capture session_id

2. data = read_resource("accounts://all")
   display_accounts(data)
   Extract from resource data:
     globex_id           = id of account with name == 'Globex Inc'
     blocked_task_id     = id of task with status == 'blocked' in Globex Milestone 2
     baseline_status     = 'blocked'

3. messages = get_prompt("assess-account", {account_id: globex_id})
   filled_prompt = messages[0].content.text

4. session_uuid = str(uuid.uuid4())
   run_claude_p(filled_prompt, session_uuid)  ← streams live

5. changed = verify_update(blocked_task_id, baseline_status)
   if not changed:
     go to 5a
   else:
     go to 6

5a. retry_message = (
      "Verification: task {blocked_task_id} status is still '{baseline_status}' — "
      "update_task_status was not called or did not succeed. "
      "Current status from get_task: '{current_status}'. "
      "Please call update_task_status now with the appropriate action."
    )
    run_claude_p_resume(session_uuid, retry_message)  ← streams live
    verify_update(blocked_task_id, baseline_status)   ← final check, result printed only

6. after_data = read_resource("accounts://all")
   display_delta(data, after_data)
   display_accounts(after_data)
```

### Globex account ID

`demo.py` identifies Globex by name from the `accounts://all` response (the name "Globex Inc" is fixed in seed data). It does not hardcode an ID. This keeps demo.py resilient to seed script variations.

### Tests — `tests/test_demo.py`

**`verify_update`:**

`verify_update` calls `call_get_task` internally, which makes an httpx request. Tests mock `call_get_task` to return a controlled status value without a live server.

- Returns `True` when the mocked `call_get_task` returns a status that differs from `baseline_status`
- Returns `False` when the mocked `call_get_task` returns a status equal to `baseline_status`

**Data extraction from resource response:**

Tests use inline data (a Python dict matching the resource response shape). No server or fixture required.

- `globex_id` is correctly identified as the `id` of the account with `name == "Globex Inc"`
- `blocked_task_id` is correctly identified as the `id` of the task with `status == "blocked"` within Globex's current milestone

---

## Shell Script — `demo.sh`

```
1.  if ! command -v claude; then
      print: "Claude Code CLI not found. Install from https://claude.ai/code"
      exit 1

2.  VERSION=$(cat .claude-code-version)

3.  claude install $VERSION

4.  uv sync

5.  uv run python server.py &
    SERVER_PID=$!

6.  trap "kill $SERVER_PID 2>/dev/null" EXIT

7.  for i in 1..10:
      if GET http://localhost:8000/health returns 200: break
      sleep 1
    if not ready: print timeout error, exit 1

8.  uv run python demo.py
```

---

## Configuration Files

### `.mcp.json`

Registers the running server with Claude Code CLI so `claude -p` has tool access when launched from the project directory.

```json
{
  "mcpServers": {
    "delivery-manager": {
      "type": "http",
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### `.claude-code-version`

Plain text file, one line: the pinned Claude Code CLI version string.

Example: `1.2.3`

---

## Dependencies — `pyproject.toml`

**Runtime:**
- `fastmcp` — MCP server framework with HTTP transport
- `httpx` — HTTP client for demo.py's MCP calls

**Dev:**
- `pytest` — test runner
- `ruff` — linter and formatter

Python version: `>=3.11`

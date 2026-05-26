# Feature & Demo Spec
*Delivery Manager MCP Server*

This document captures implementation decisions and demo design agreed during planning. It is the working spec for Claude Code. The project definition is in `delivery_manager_mcp_project_def.md`.

---

## Scope

All three MCP primitives, minimal implementation:

| Primitive | Implementation |
|-----------|---------------|
| Resource | `accounts://all` — full account/project/milestone/task dataset |
| Tools | `get_account_status` (compound read), `get_task` (single-row read), `update_task_status` (flow tool) |
| Prompt | `assess-account(account_id)` — embeds rich status server-side, frames the decision |

**Explicitly out of scope:** auth, multi-tenancy, pagination, full CRUD, schema validation hardening.

---

## Transport

Streamable HTTP via `fastmcp` HTTP transport, `/mcp` endpoint. Recommended over SSE for all new projects as of MCP spec 2025-03-26. Both `claude -p` and the demo script connect as MCP clients via POST requests to `/mcp`.

---

## Data Model

```
Account      id, name, status, updated_at
Project      id, account_id, name, status, updated_at
Milestone    id, project_id, name, order, status, updated_at
Task         id, milestone_id, title, status, owner, blocker, updated_at
```

**Task statuses:** `open`, `in_progress`, `pending_customer`, `blocked`, `complete`, `invalid`

The `invalid` status represents a task in an unresolvable state requiring admin intervention. It blocks milestone advancement and is correctly ignored by the prompt logic — the model does not attempt to update it.

**Milestone statuses:** `not_started`, `in_progress`, `complete`

**Account statuses:** `active`, `at_risk`

**Project statuses:** `active`, `at_risk`, `complete`

---

## Seed Data

**Account A — Acme Corp (`active`)**
- Project: "Acme Onboarding" (`active`)
- Milestone 1: `complete`
- Milestone 2 (current, `in_progress`): 2 tasks `complete`, 1 task `open` and unblocked

**Account B — Globex Inc (`at_risk`)**
- Project: "Globex Onboarding" (`at_risk`)
- Milestone 1: `complete`
- Milestone 2 (current, `in_progress`): 1 task `complete`, 1 task `blocked` (customer document not submitted, `updated_at` set 14 days in the past), 1 task `invalid`

---

## Tools

### `get_account_status(account_id)`
Compound read. Returns account name and status, active project name and status, current milestone name and status, all tasks for the current milestone (id, title, status, owner, blocker, updated_at). Used internally by the prompt handler; also available for the model to call directly.

### `get_task(task_id)`
Single-row read. Returns the full task record (id, title, status, owner, blocker, updated_at). Used by the demo script's judge loop for post-run verification; also available to the model.

### `update_task_status(task_id, new_status)`
Flow tool. Encodes the full domain logic for task completion and milestone advancement — the model decides *when* to call it and *which action* to take; the tool executes the cascade deterministically.

Precondition check (before any mutation):
- Reject if `new_status` is not a recognised status value
- Return structured error with `code`, `reason`, `current_status` — do not mutate

On passing the precondition:
1. Update `tasks.status` and `tasks.updated_at`
2. Check if all tasks in the milestone are now `complete`
3. If not: return structured result with task update confirmed and list of remaining blocking tasks (id, title, status, blocker) — stop here
4. If all complete: mark milestone `complete`
5. Check if all milestones in the project are now `complete`
6. If not: return result with milestone advanced, remaining milestones listed — stop here
7. If all complete: mark project `complete`, update account status `at_risk` → `active`
8. Return result with full cascade outcome

The gate failing in the demo is intentional: after the blocked task is marked `pending_customer`, the `invalid` task still prevents milestone advancement. The tool correctly reports this; the model reports it in its conclusion.

---

## Resource

**URI:** `accounts://all`

Returns the full dataset for all accounts: for each account, its id, name, status, updated_at, and active project (name, status, current milestone name and status, and all tasks for the current milestone with id, title, status, owner, blocker, updated_at).

The resource returns the full DB result rather than a compressed summary — since this is not injected directly into model context there is no token cost to returning everything. The complete task records enable the demo script to extract task IDs and baseline statuses for the judge loop without a separate tool call.

This is the host-controlled view — the host fetches and presents it; the model does not drive this fetch. In a production host it would auto-inject based on page context. In the demo script it is the opening and closing display.

---

## Prompt Template

**Name:** `assess-account`
**Argument:** `account_id`

Server-side handler calls `get_account_status` internally and returns a filled message containing:

1. **Briefing:** account name, project, current milestone status, list of actionable blocked tasks list with statuses, days since last update on the blocked task
2. **Decision framing:** determine whether the appropriate action for the blocked task is to nudge the customer, escalate, or place on hold, then call `update_task_status` to execute it. Tasks with status `invalid` are omitted from the briefing.

The only judgment call is which action to take on the blocked task. The `invalid` task is explicitly excluded from the prompt.

**Implementation constraint:** Every action choice offered in the decision framing must map to a `new_status` that is not `blocked`. The judge loop verifies the agent acted by checking that the task status changed from its baseline value of `blocked` — any action that resolves to `blocked` is indistinguishable from no action and will cause the judge to treat the run as a failure.

---

## Demo Script

`demo.py` is the demo runner and the MCP host for the resource and prompt primitives. `claude -p` is the MCP host for the tool primitives during the agent loop.

### MCP client

Raw `httpx` POST requests to `/mcp`. No SDK. The server returns an `Mcp-Session-Id` response header on `initialize` which is passed on all subsequent requests. The entire client is a handful of `httpx` calls.

### Judge loop

After `claude -p` completes, the demo script verifies that `update_task_status` was actually called by checking the DB state directly via `get_task`. Comparison is against the baseline status cached from the resource response in step 2 (Script sequence, below) — not against a timestamp (too fragile across latency sources).

The session ID for the `claude -p` call is a UUID generated by `demo.py` and passed via `--session-id`. This makes the retry deterministic: if verification fails, the retry uses `--resume {uuid}` to continue the same session, leveraging the existing prompt cache rather than starting cold.

The retry message contains the verification result — the cached baseline status and the current `get_task` value — not a replay of the model's previous text output. Max one retry.

### Script sequence

```
1. POST /mcp  initialize

2. POST /mcp  resources/read("accounts://all")
              → display full account/task data
              → cache blocked task: {id, baseline_status} from Globex Milestone 2

3. POST /mcp  prompts/get("assess-account", {account_id: globex_id})
              → server returns filled briefing

4. Generate session_uuid
   subprocess  claude -p --session-id {session_uuid}
                         --output-format json
                         "{filled_prompt}"
              → tool call visible in real time:
                  update_task_status(blocked_task, pending_customer)
                      cascade: invalid task still blocking → milestone stays
              → agent concludes: nudge sent, milestone blocked by invalid task,
                recommends admin review

5. POST /mcp  get_task(cached_blocked_task_id)
              → if status == baseline_status: verification failed → go to 5a
              → if status != baseline_status: verification passed → go to 6

5a. subprocess  claude -p --resume {session_uuid}
                          --output-format json
                          "Verification: task {id} status is still
                          '{baseline_status}' — update_task_status was not
                          called or did not succeed. Please call it now with
                          the appropriate action."
              → repeat step 5 (max one retry)

6. POST /mcp  resources/read("accounts://all")
              → display updated dataset; blocked→pending_customer delta visible
```

### Shell script

`demo.sh` is the single entry point for running the demo. It:

1. Checks that `claude` is on PATH — exits with a clear error message if not found (README installation instructions are the fix)
2. Reads the pinned version from `.claude-code-version`
3. Runs `claude install {version}` to ensure the correct version is active
4. Runs `uv sync` to ensure Python dependencies are installed
5. Starts `uv run python mcp_demo_server.py` in the background
6. Polls the server health endpoint until ready (timeout after 10 seconds)
7. Runs `uv run python demo.py`
8. Traps EXIT to kill the background server process

### Claude Code config

`.mcp.json` in the project root registers the running server so `claude -p` has tool access when launched from the project directory. The pinned Claude Code version is stored in `.claude-code-version`; `demo.sh` enforces it. The README lists Claude Code CLI as a prerequisite with installation instructions.

---

## Implementation Order

1. Streamable HTTP server scaffold (`fastmcp` HTTP transport, health check endpoint)
2. SQLite schema + seed script
3. `get_account_status` tool
4. `get_task` tool
5. `update_task_status` flow tool
6. `accounts://all` resource
7. `assess-account` prompt template
8. `.mcp.json` Claude Code config + `.claude-code-version`
9. `demo.py` — httpx client + subprocess + judge loop
10. `demo.sh` — version check, server lifecycle, single entry point
11. End-to-end demo run and validation

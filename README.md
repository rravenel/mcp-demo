# Delivery Manager MCP Server

A focused demonstration of all three MCP (Model Context Protocol) primitives — Tools, Resources, and Prompts — implemented in a post-sale delivery management domain. The domain (accounts → projects → milestones → tasks) mirrors the architecture pattern used by Salesforce ISV agent platforms.

This is a deliberate demonstration, not a general-purpose application. Auth, multi-tenancy, pagination, and full CRUD are intentionally absent. Every feature exists to illustrate a specific MCP server pattern in a coherent agentic loop.

---

## Prerequisites

- **Claude Code CLI** — required to drive the agent loop. Install from [claude.ai/code](https://claude.ai/code) or via:
  ```bash
  npm install -g @anthropic-ai/claude-code
  ```
- **uv** — Python package manager. Install from [docs.astral.sh/uv](https://docs.astral.sh/uv).

---

## Running the demo

**First run — seed the database:**
```bash
uv run python seed.py
```

This creates `data/delivery.db` with the demo accounts, projects, milestones, and tasks. Only needed once (or to reset state between runs).

**Run the demo:**
```bash
./demo.sh
```

The script checks for Claude Code CLI, pins the correct version, installs Python dependencies, starts the MCP server, runs the demo, and shuts everything down on exit.

**Stop the server early** (if you interrupt the demo mid-run):
```bash
./stop.sh
```

---

## What the demo shows

The demo focuses on **Globex Inc**, an at-risk account with a stalled onboarding milestone. One task is blocked waiting on a customer document submission; a second task is in an invalid state requiring admin intervention.

The demo sequence:

1. **Resource fetch** — `demo.py` calls `accounts://all` and displays the full account/task dataset. This is the host-controlled resource primitive: the script is the MCP host, fetching and presenting data before the agent session begins.

2. **Prompt fetch** — `demo.py` calls the `assess-account` prompt template with Globex's account ID. The server-side handler calls `get_account_status` internally and returns a filled briefing: milestone status, actionable blocked tasks, days since last update.

3. **Agent loop** — `claude -p` receives the filled prompt and calls `update_task_status` to mark the blocked task as `pending_customer` (nudge action). The flow tool executes the cascade: task updated, milestone check runs, the `invalid` task prevents milestone advancement, structured result returned. The agent concludes: nudge sent, milestone blocked by invalid task, recommends admin review.

4. **Verification** — `demo.py` calls `get_task` to confirm the status change. If the update didn't happen, the session is resumed (leveraging prompt cache) with the verification result, and the agent retries.

5. **Final resource fetch** — `accounts://all` is fetched again. The blocked→pending_customer delta is visible in the output.

---

## MCP primitives demonstrated

| Primitive | Implementation | Pattern |
|-----------|---------------|---------|
| **Resource** | `accounts://all` | Host-controlled fetch; the script drives this, not the model. In production, a host app would auto-inject based on page context. |
| **Tools** | `get_account_status`, `get_task`, `update_task_status` | Model-callable functions with typed schemas. `update_task_status` is a flow tool: one callable surface encoding multi-step domain logic with gate conditions. |
| **Prompt** | `assess-account(account_id)` | User-invoked template; server-side handler embeds live data and frames the decision. The model's only judgment call is which action to take. |

### The flow tool pattern

`update_task_status` does more than update a row. After the task write, it checks milestone completion, conditionally marks the milestone complete, checks project completion, and conditionally updates account status — all in one deterministic cascade. The model decides *when* to call it; the tool decides *what the business process means*.

This is the Salesforce ISV architecture pattern: domain expertise encoded as a callable unit, not distributed across model reasoning steps.

### The invalid task

The `invalid` task on Globex's milestone can't be resolved by the agent — it requires admin intervention. The prompt explicitly excludes it; the model correctly ignores it. It remains in the milestone and prevents advancement. The tool reports this accurately; the agent surfaces it in its conclusion.

This demonstrates that the system correctly identifies and communicates constraints rather than silently failing or unconditionally succeeding.

---

## Stack

- Python, `fastmcp` (streamable HTTP transport)
- SQLite (no external database)
- `httpx` for the demo script's MCP client (raw POST requests — no SDK)
- Claude Code CLI for the agent loop

---

## Design documents

The `docs/` directory contains the full design and implementation record for this project.

| File | Purpose |
|------|---------|
| `docs/delivery_manager_mcp_project_def.md` | Original project definition and brief — context, motivation, and design decisions |
| `docs/spec.md` | Feature and demo spec — authoritative source for what is built and why |
| `docs/engineering_spec.md` | Implementation spec — file layout, schema, query contracts, tool/resource/prompt contracts, test cases |
| `docs/tasks.md` | Implementation task list and progress tracker |

---

## Future revisions

- **Multiple task updates per session**: The `assess-account` prompt returns a single briefing scoped to one blocked task. Full support for accounts with multiple actionable tasks would require the prompt endpoint to return a list of prompts — one per blocked task — so the agent can act on each independently.
- **Conditional updates**: In a production assessment loop, the agent might evaluate a task and decide no action is warranted — leaving it unchanged. The demo is designed to always produce an update call (the blocked task is clearly actionable), so this path is not exercised here.
- **Auth and multi-tenancy**: Out of scope by design; would be the next layer for a production deployment.
- **Pagination**: The resource returns the full dataset; pagination would be needed at scale.

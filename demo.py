import json
import subprocess
import uuid

import httpx

from config import CLAUDE_MODEL, MCP_PORT

MCP_URL = f"http://localhost:{MCP_PORT}/mcp"

_session_id: str | None = None
_request_counter = 0


def _next_id() -> int:
    global _request_counter
    _request_counter += 1
    return _request_counter


_BASE_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _post(payload: dict) -> dict:
    headers = dict(_BASE_HEADERS)
    if _session_id:
        headers["Mcp-Session-Id"] = _session_id
    response = httpx.post(MCP_URL, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    if not response.content:
        return {}
    content_type = response.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        for line in response.text.splitlines():
            if line.startswith("data:"):
                return json.loads(line[5:].strip())
        return {}
    return response.json()


def initialize() -> None:
    global _session_id
    payload = {
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "demo", "version": "0.1"},
        },
    }
    response = httpx.post(MCP_URL, json=payload, headers=_BASE_HEADERS, timeout=30)
    response.raise_for_status()
    _session_id = response.headers.get("Mcp-Session-Id")

    _post(
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
    )


def read_resource(uri: str) -> list:
    result = _post(
        {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "resources/read",
            "params": {"uri": uri},
        }
    )
    return result["result"]["contents"]


def get_prompt(name: str, arguments: dict) -> list:
    result = _post(
        {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "prompts/get",
            "params": {"name": name, "arguments": arguments},
        }
    )
    return result["result"]["messages"]


def call_get_task(task_id: str) -> dict:
    result = _post(
        {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/call",
            "params": {"name": "get_task", "arguments": {"task_id": task_id}},
        }
    )
    content = result["result"]["content"]
    if isinstance(content, list):
        return json.loads(content[0]["text"])
    return json.loads(content)


# ---------------------------------------------------------------------------
# Display functions
# ---------------------------------------------------------------------------


def display_accounts(resource_data: list) -> None:
    print("\n=== Account Overview ===")
    for item in resource_data:
        raw = item.get("text") or item
        if isinstance(raw, str):
            raw = json.loads(raw)
        accounts = raw if isinstance(raw, list) else [raw]
        for acct in accounts:
            print(f"\nAccount: {acct['name']} [{acct['status']}]")
            proj = acct.get("project")
            if not proj:
                print("  No active project")
                continue
            print(f"  Project: {proj['name']} [{proj['status']}]")
            ms = proj.get("milestone")
            if not ms:
                print("    No current milestone")
                continue
            print(f"  Milestone: {ms['name']} [{ms['status']}]")
            for task in ms.get("tasks", []):
                blocker = f" | blocker: {task['blocker']}" if task.get("blocker") else ""
                owner = f" | owner: {task['owner']}" if task.get("owner") else ""
                print(f"    - [{task['status']}] {task['title']}{owner}{blocker}")


def _parse_accounts(resource_data: list) -> list:
    result = []
    for item in resource_data:
        raw = item.get("text") or item
        if isinstance(raw, str):
            raw = json.loads(raw)
        if isinstance(raw, list):
            result.extend(raw)
        else:
            result.append(raw)
    return result


def display_delta(before_data: list, after_data: list) -> None:
    print("\n=== Result ===")
    before_tasks: dict[str, str] = {}
    after_tasks: dict[str, str] = {}

    def _collect(data: list, store: dict) -> None:
        for acct in _parse_accounts(data):
            proj = acct.get("project")
            if not proj:
                continue
            ms = proj.get("milestone")
            if not ms:
                continue
            for t in ms.get("tasks", []):
                store[t["id"]] = t["status"]

    _collect(before_data, before_tasks)
    _collect(after_data, after_tasks)

    changed = False
    for task_id, before_status in before_tasks.items():
        after_status = after_tasks.get(task_id, before_status)
        if before_status != after_status:
            print(f"\nTask {task_id}: {before_status} → {after_status}")
            changed = True
    if not changed:
        print("  (no task status changes detected)")


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------


def _run_claude(cmd: list[str]) -> dict:
    final_event: dict | None = None
    lines: list[str] = []

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for raw in proc.stdout:
        raw = raw.rstrip()
        if not raw:
            continue
        lines.append(raw)
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            continue

        etype = event.get("type")

        if etype == "system" and event.get("subtype") == "init":
            for srv in event.get("mcp_servers", []):
                print(f"  MCP: {srv.get('name')} ({srv.get('status', 'unknown')})")

        elif etype == "assistant":
            content = event.get("message", {}).get("content", [])
            texts = [b["text"] for b in content if b.get("type") == "text" and b.get("text")]
            calls = [b for b in content if b.get("type") == "tool_use"]
            if texts or calls:
                print("\n  [Assistant]")
            if texts:
                print(texts[0].replace("\n", "\n  "))
            for c in calls:
                print(f"    → {c['name']}({json.dumps(c.get('input', {}))})")

        elif etype == "user":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "tool_result":
                    rc = block.get("content", "")
                    if isinstance(rc, list):
                        rc = rc[0].get("text", "") if rc else ""
                    print(f"\n  [Tool]\n    ← {rc}")

        elif etype == "result":
            final_event = event

    proc.wait()

    if not final_event:
        print("".join(lines))
        return {"result": "(no result text)", "num_turns": 0, "cost": 0.0, "usage": {}}

    return {
        "result": final_event.get("result", "(no result text)"),
        "num_turns": final_event.get("num_turns", "?"),
        "cost": final_event.get("total_cost_usd", 0),
        "usage": final_event.get("usage", {}),
    }


def run_claude_p(prompt_text: str, session_uuid: str) -> dict:
    cmd = [
        "claude",
        "-p",
        "--model",
        CLAUDE_MODEL,
        "--session-id",
        session_uuid,
        "--verbose",
        "--output-format",
        "stream-json",
        prompt_text,
    ]
    return _run_claude(cmd)


def run_claude_p_resume(session_uuid: str, message: str) -> dict:
    cmd = [
        "claude",
        "-p",
        "--model",
        CLAUDE_MODEL,
        "--resume",
        session_uuid,
        "--verbose",
        "--output-format",
        "stream-json",
        message,
    ]
    return _run_claude(cmd)


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------


def verify_update(task_id: str, baseline_status: str) -> bool:
    task = call_get_task(task_id)
    return task["status"] != baseline_status


# ---------------------------------------------------------------------------
# Main sequence
# ---------------------------------------------------------------------------


def _print_summary(run_data: dict) -> None:
    usage = run_data.get("usage", {})
    inp = usage.get("input_tokens", 0)
    cache_r = usage.get("cache_read_input_tokens", 0)
    cache_w = usage.get("cache_creation_input_tokens", 0)
    out = usage.get("output_tokens", 0)
    print("\nUsage:")
    print(f"  cost: ${run_data.get('cost', 0):.4f}")
    print(
        f"  tokens: {inp:,} input + {cache_r:,} cache_read + {cache_w:,} cache_write + {out:,} output"
    )


def main() -> None:
    print(f"Connecting to MCP server at {MCP_URL}...")
    initialize()

    print("\nReading accounts resource...")
    data = read_resource("accounts://all")
    display_accounts(data)

    accounts = _parse_accounts(data)
    globex = next(a for a in accounts if a["name"] == "Globex Inc")
    globex_id = globex["id"]

    tasks = globex["project"]["milestone"]["tasks"]
    blocked_task = next(t for t in tasks if t["status"] == "blocked")
    blocked_task_id = blocked_task["id"]
    baseline_status = "blocked"

    print("\n=== MCP Prompt ===")
    messages = get_prompt("assess-account", {"account_id": globex_id})
    filled_prompt = messages[0]["content"]["text"]
    print(f"\n{filled_prompt}")

    session_uuid = str(uuid.uuid4())
    print("\n=== Agent ===")
    print(f"\nRunning agent (session: {session_uuid})...")
    run_data = run_claude_p(filled_prompt, session_uuid)
    _print_summary(run_data)

    after_data = read_resource("accounts://all")
    display_delta(data, after_data)
    changed = verify_update(blocked_task_id, baseline_status)
    print(f"\nVerification: {'PASSED' if changed else 'FAILED'}")

    if not changed:
        current = call_get_task(blocked_task_id)["status"]
        retry_message = (
            f"Verification: task {blocked_task_id} status is still '{baseline_status}' — "
            f"update_task_status was not called or did not succeed. "
            f"Current status from get_task: '{current}'. "
            f"Please call update_task_status now with the appropriate action."
        )
        print("\n=== MCP Prompt ===")
        print(f"\n{retry_message}")
        print("\n=== Agent ===")
        print(f"\nRunning agent (session: {session_uuid}, resume)...")
        retry_data = run_claude_p_resume(session_uuid, retry_message)
        _print_summary(retry_data)
        after_data = read_resource("accounts://all")
        display_delta(data, after_data)
        changed = verify_update(blocked_task_id, baseline_status)
        print(f"\nVerification: {'PASSED' if changed else 'FAILED'}")

    display_accounts(after_data)


if __name__ == "__main__":
    main()

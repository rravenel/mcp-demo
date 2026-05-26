import json
import subprocess
import uuid

import httpx

MCP_URL = "http://localhost:8000/mcp"

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

    _post({
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    })


def read_resource(uri: str) -> list:
    result = _post({
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": "resources/read",
        "params": {"uri": uri},
    })
    return result["result"]["contents"]


def get_prompt(name: str, arguments: dict) -> list:
    result = _post({
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": "prompts/get",
        "params": {"name": name, "arguments": arguments},
    })
    return result["result"]["messages"]


def call_get_task(task_id: str) -> dict:
    result = _post({
        "jsonrpc": "2.0",
        "id": _next_id(),
        "method": "tools/call",
        "params": {"name": "get_task", "arguments": {"task_id": task_id}},
    })
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
    print("\n=== Changes ===")
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
            print(f"  Task {task_id}: {before_status} → {after_status}")
            changed = True
    if not changed:
        print("  (no task status changes detected)")


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------


def _run_claude(cmd: list[str]) -> str:
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    raw = proc.stdout.read()
    proc.wait()
    try:
        data = json.loads(raw)
        result_text = data.get("result", "(no result text)")
        turns = data.get("num_turns", "?")
        cost = data.get("total_cost_usd", 0)
        print(f"{result_text}\n")
        print(f"  turns: {turns}  |  cost: ${cost:.4f}")
    except (json.JSONDecodeError, KeyError):
        print(raw)
    return raw


def run_claude_p(prompt_text: str, session_uuid: str) -> str:
    cmd = ["claude", "-p", "--session-id", session_uuid, "--output-format", "json", prompt_text]
    return _run_claude(cmd)


def run_claude_p_resume(session_uuid: str, message: str) -> str:
    cmd = ["claude", "-p", "--resume", session_uuid, "--output-format", "json", message]
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


def main() -> None:
    print("Initializing MCP session...")
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

    print(f"\nFetching prompt for account: {globex_id}")
    messages = get_prompt("assess-account", {"account_id": globex_id})
    filled_prompt = messages[0]["content"]["text"]

    session_uuid = str(uuid.uuid4())
    print(f"\nRunning agent (session: {session_uuid})...\n")
    run_claude_p(filled_prompt, session_uuid)

    changed = verify_update(blocked_task_id, baseline_status)
    if not changed:
        current = call_get_task(blocked_task_id)["status"]
        retry_message = (
            f"Verification: task {blocked_task_id} status is still '{baseline_status}' — "
            f"update_task_status was not called or did not succeed. "
            f"Current status from get_task: '{current}'. "
            f"Please call update_task_status now with the appropriate action."
        )
        print("\nAgent did not update task — retrying...\n")
        run_claude_p_resume(session_uuid, retry_message)
        changed = verify_update(blocked_task_id, baseline_status)
        print(f"\nFinal verification: {'PASSED' if changed else 'FAILED'}")
    else:
        print("\nVerification: PASSED")

    after_data = read_resource("accounts://all")
    display_delta(data, after_data)
    display_accounts(after_data)


if __name__ == "__main__":
    main()

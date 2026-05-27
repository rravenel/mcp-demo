import json

import anthropic
import httpx

from config import MCP_PORT

_MODEL = "claude-haiku-4-5-20251001"
_INPUT_COST_PER_M = 1.00   # USD per million tokens, May 2026
_OUTPUT_COST_PER_M = 5.00  # USD per million tokens, May 2026
_client = anthropic.Anthropic()

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


def initialize() -> str:
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

    server_name = "unknown"
    if response.content:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    data = json.loads(line[5:].strip())
                    server_name = (
                        data.get("result", {}).get("serverInfo", {}).get("name", "unknown")
                    )
                    break
        else:
            data = response.json()
            server_name = data.get("result", {}).get("serverInfo", {}).get("name", "unknown")

    _post({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
    return server_name


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


def list_tools() -> list[dict]:
    result = _post({"jsonrpc": "2.0", "id": _next_id(), "method": "tools/list", "params": {}})
    tools = []
    for t in result["result"]["tools"]:
        tools.append({
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t["inputSchema"],
        })
    return tools


def list_resources() -> list[str]:
    result = _post(
        {"jsonrpc": "2.0", "id": _next_id(), "method": "resources/list", "params": {}}
    )
    return [r["uri"] for r in result["result"]["resources"]]


def list_prompts() -> list[str]:
    result = _post(
        {"jsonrpc": "2.0", "id": _next_id(), "method": "prompts/list", "params": {}}
    )
    return [p["name"] for p in result["result"]["prompts"]]


def call_tool(name: str, arguments: dict) -> str:
    result = _post(
        {
            "jsonrpc": "2.0",
            "id": _next_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    content = result["result"]["content"]
    if isinstance(content, list):
        return content[0]["text"] if content else ""
    return str(content)


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


def _run_agent(messages: list, tools: list[dict]) -> dict:
    total_input, total_output = 0, 0

    while True:
        print("\n  [Assistant]")
        had_text = False
        with _client.messages.stream(
            model=_MODEL,
            max_tokens=1024,
            tools=tools,
            messages=messages,
        ) as stream:
            for chunk in stream.text_stream:
                print(chunk.replace("\n", "\n  "), end="", flush=True)
                had_text = True
            response = stream.get_final_message()

        total_input += response.usage.input_tokens
        total_output += response.usage.output_tokens

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            break

        if had_text:
            print()

        tool_results = []
        for tool_use in tool_uses:
            print(f"    → {tool_use.name}({json.dumps(tool_use.input)})")
            result_text = call_tool(tool_use.name, tool_use.input)
            print(f"\n  [Tool]\n    ← {result_text}")
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result_text,
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    cost = (
        (total_input / 1_000_000) * _INPUT_COST_PER_M
        + (total_output / 1_000_000) * _OUTPUT_COST_PER_M
    )
    return {
        "cost": cost,
        "usage": {"input_tokens": total_input, "output_tokens": total_output},
        "messages": messages,
    }


def run_agent(prompt_text: str, tools: list[dict]) -> dict:
    messages = [{"role": "user", "content": prompt_text}]
    return _run_agent(messages, tools)


def run_agent_resume(message: str, tools: list[dict], prior_messages: list) -> dict:
    messages = prior_messages + [{"role": "user", "content": message}]
    return _run_agent(messages, tools)


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
    out = usage.get("output_tokens", 0)
    print("\nUsage:")
    print(f"  cost (May 2026): ${run_data.get('cost', 0):.4f}")
    print(f"  tokens: {inp:,} input + {out:,} output")


def main() -> None:
    print(f"Connecting to MCP server at {MCP_URL}...")
    server_name = initialize()
    tools = list_tools()
    resources = list_resources()
    prompts = list_prompts()
    print(f"\nMCP: {server_name}")
    print(f"  Tools:     {', '.join(t['name'] for t in tools)}")
    print(f"  Resources: {', '.join(resources)}")
    print(f"  Prompts:   {', '.join(prompts)}")

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
    prompt_messages = get_prompt("assess-account", {"account_id": globex_id})
    filled_prompt = prompt_messages[0]["content"]["text"]
    print(f"\n{filled_prompt}")

    print("\n=== Agent ===")
    run_data = run_agent(filled_prompt, tools)

    after_data = read_resource("accounts://all")
    display_delta(data, after_data)
    changed = verify_update(blocked_task_id, baseline_status)
    print(f"\nVerification: {'PASSED' if changed else 'FAILED'}")
    _print_summary(run_data)

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
        retry_data = run_agent_resume(retry_message, tools, run_data["messages"])
        after_data = read_resource("accounts://all")
        display_delta(data, after_data)
        changed = verify_update(blocked_task_id, baseline_status)
        print(f"\nVerification: {'PASSED' if changed else 'FAILED'}")
        _print_summary(retry_data)

    display_accounts(after_data)


if __name__ == "__main__":
    main()

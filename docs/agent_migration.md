# Agent Migration: `claude -p` → Anthropic API

## Motivation

The current demo spawns `claude -p` as a subprocess. Claude Code injects its own ~30k-token
system prompt on every run — tool catalogs, internal instructions, MCP config. This dominates
token cost and obscures what's actually happening. Replacing the subprocess with direct Anthropic
API calls:

- Eliminates the ~30k token overhead (dominant cost driver)
- Removes the `mcp__delivery-manager__` tool prefix (a Claude Code artifact, not MCP)
- Gives us full control over the system prompt and message history
- Makes the demo story cleaner for a developer audience: MCP server + Anthropic API, no CLI wrapper

Model: `claude-haiku-4-5-20251001` — moved from `config.py` to `demo.py` as `_MODEL` by this migration.

---

## What Changes

### `pyproject.toml`
Add `anthropic` to dependencies.

### `config.py`
Remove `CLAUDE_MODEL` and the commented-out Sonnet line entirely. `config.py` is for operator
configuration only — the one value a demo runner might need to change is the port if 8000 is
already in use. After this change it contains only:

```python
MCP_PORT = 8000
```

### `demo.py`

**Remove entirely:**
- `run_claude_p()` and `run_claude_p_resume()` — subprocess wrappers
- `_run_claude()` — stream-json parser
- `import subprocess`, `import uuid`
- `session_uuid` generation and the `Running agent (session: ...)` print line in `main()`

**Add imports:**
- `import anthropic`
- `from config import` line becomes `from config import MCP_PORT` only — `CLAUDE_MODEL` is
  removed from config entirely (see above)

**Add module-level constants** (not config — baked-in implementation details):

```python
_MODEL = "claude-haiku-4-5-20251001"
_INPUT_COST_PER_M = 1.00   # USD per million tokens, May 2026
_OUTPUT_COST_PER_M = 5.00  # USD per million tokens, May 2026
```

The Anthropic client is also initialized at module level so it is not re-created on each call:

```python
_client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from environment
```

**Add:**

`list_tools()` — calls `tools/list` on the MCP server and returns tool definitions formatted
for the Anthropic API. MCP uses `inputSchema`; Anthropic uses `input_schema` — rename the key.

```python
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
```

`list_resources()` — calls `resources/list` and returns the URI for each resource (display only).

```python
def list_resources() -> list[str]:
    result = _post({"jsonrpc": "2.0", "id": _next_id(), "method": "resources/list", "params": {}})
    return [r["uri"] for r in result["result"]["resources"]]
```

`list_prompts()` — calls `prompts/list` and returns the name of each prompt (display only).

```python
def list_prompts() -> list[str]:
    result = _post({"jsonrpc": "2.0", "id": _next_id(), "method": "prompts/list", "params": {}})
    return [p["name"] for p in result["result"]["prompts"]]
```

`call_tool()` — executes a single MCP tool call and returns the result as a string.

```python
def call_tool(name: str, arguments: dict) -> str:
    result = _post({
        "jsonrpc": "2.0", "id": _next_id(), "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    })
    content = result["result"]["content"]
    if isinstance(content, list):
        return content[0]["text"] if content else ""
    return str(content)
```

`_run_agent()` — replaces `_run_claude()`. Takes a messages list and tool list; runs the
agentic loop via the Anthropic SDK's streaming interface. Prints `[Assistant]` / `[Tool]` blocks
as before. Returns `{cost, usage, messages}` where `messages` is the full accumulated history
for the retry path.

The loop:
1. Print `[Assistant]`, then call `_client.messages.stream()` with current messages, tools, and
   `max_tokens=1024`.
2. Print streamed text chunks as they arrive.
3. After the stream completes, inspect the final message for `tool_use` blocks.
4. If no tool use: break.
5. For each tool use: print `→ name(args)`, execute via `call_tool()`, print `[Tool] ← result`.
6. Append the assistant message and a `tool_result` user message to history; loop.

Accumulate `input_tokens` and `output_tokens` from `response.usage` across all loop iterations.
Compute estimated cost using the module-level constants:

```python
cost = (total_input / 1_000_000) * _INPUT_COST_PER_M \
     + (total_output / 1_000_000) * _OUTPUT_COST_PER_M
```

`run_agent()` — constructs the initial message list as
`[{"role": "user", "content": prompt_text}]` and calls `_run_agent()`.

`run_agent_resume()` — takes the prior `messages` list returned by the first run, appends the
retry message as a new user turn, and calls `_run_agent()`.

**Update `initialize()`:**

Return the server name from the MCP handshake. The initialize response body includes
`result.serverInfo.name` — parse it and return the string. Currently `initialize()` returns
`None`; change the return type to `str`.

**Update `main()`:**

- Immediately after `initialize()`, call all three discovery functions and print the server
  header:
  ```
  MCP: delivery-manager
    Tools:     get_account_status, get_task, update_task_status
    Resources: accounts://all
    Prompts:   assess-account
  ```
  Server name comes from `initialize()`'s return value. This replaces the single-line
  `MCP: delivery-manager (connected)` that Claude Code emitted from its `system/init` event,
  and surfaces all three primitives — showcasing the full MCP surface from our own client code.
- Pass the `tools` list (from `list_tools()`) into both agent calls.
- Replace `run_claude_p(filled_prompt, session_uuid)` with `run_agent(filled_prompt, tools)`.
- Capture the returned `messages` from the first run for the retry path.
- Replace `run_claude_p_resume(session_uuid, retry_message)` with
  `run_agent_resume(retry_message, tools, prior_messages)`.
- Update `_print_summary`: change the cost label to `est. cost (May 2026): $X.XXXX` and
  simplify the token line to `input + output` only (drop cache fields — caching is out of scope).
  This is the only change to `_print_summary`; the `{cost, usage}` dict shape is unchanged.

### `demo.sh`

Remove:
- `claude` PATH check and exit
- `claude install "$VERSION"` line
- `.mcp.json` generation block (only needed for Claude Code)

Add:
- Check that `ANTHROPIC_API_KEY` is set; exit with a clear error message if not.

Keep everything else: `uv sync`, server start, health poll, `uv run python demo.py`.

### `README.md`

- Remove Claude Code CLI as a prerequisite.
- Add `ANTHROPIC_API_KEY` as a prerequisite (environment variable, Anthropic console).
- Update the `config.py` description to state it controls the MCP server port only; remove any
  mention of model configuration.

### Files to remove from the repo
- `.claude-code-version` — only used by `demo.sh` to pin the Claude Code version

---

## What Stays the Same

- The MCP server (`mcp_demo_server.py`) is untouched.
- The `_post()` HTTP client and MCP session management are untouched.
- `display_accounts` and `display_delta` are untouched.
- The judge loop logic (`verify_update`, `call_get_task`) is untouched.
- The retry path structure (one retry with context message) is preserved — driven by message
  history instead of `--resume`.
- The `[Assistant]` / `[Tool]` output format is preserved.
- `test_demo.py` tests `verify_update` and `_parse_accounts` — both untouched, passes as-is.

---

## Agentic Loop Detail

```
messages = [{"role": "user", "content": prompt_text}]
total_input, total_output = 0, 0

loop:
    print "[Assistant]"
    stream response: model=_MODEL, max_tokens=1024, tools=tools, messages=messages
    print text chunks as they arrive

    total_input += response.usage.input_tokens
    total_output += response.usage.output_tokens

    tool_uses = [b for b in response.content if b.type == "tool_use"]
    if not tool_uses:
        break

    for each tool_use:
        print "→ name(args)"
        result = call_tool(tool_use.name, tool_use.input)
        print "[Tool] ← result"

    append {"role": "assistant", "content": response.content} to messages
    append {"role": "user", "content": [tool_result blocks]} to messages

cost = (total_input / 1_000_000) * _INPUT_COST_PER_M \
     + (total_output / 1_000_000) * _OUTPUT_COST_PER_M
return {cost, usage: {"input_tokens": total_input, "output_tokens": total_output}, messages}
```

The Anthropic SDK's streaming context manager (`_client.messages.stream()`) surfaces incremental
text via `text` events and exposes the complete final message (including `usage` and all content
blocks) via `.get_final_message()` after the stream closes. No manual JSON parsing.

---

## System Prompt

None required. The `assess-account` prompt template already contains the full briefing and
instructions. An empty or minimal system prompt keeps token count low and matches what we want
the demo to show: the MCP prompt template doing the work, not a wrapper system prompt.

---

## Expected Cost Impact

With `claude -p`:
- ~30k tokens system prompt + ~1-2k prompt + output ≈ ~32k input tokens per run
- At Haiku input pricing ($1.00/M): ~$0.032 input alone

With direct API:
- ~1-2k prompt + small tool schemas + output ≈ ~2-3k input tokens per run
- At Haiku input pricing ($1.00/M): ~$0.002 input alone
- Rough order-of-magnitude reduction in cost per run

#!/usr/bin/env bash
set -euo pipefail

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "ANTHROPIC_API_KEY is not set. Get your key at https://console.anthropic.com/"
    exit 1
fi

uv sync

MCP_PORT=$(uv run python -c "from config import MCP_PORT; print(MCP_PORT)")

uv run python seed.py

# Stop any server already running (previous demo run, manual start, etc.)
./stop.sh

uv run python mcp_demo_server.py >> .server.log 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > .server.pid

trap "kill $SERVER_PID 2>/dev/null; rm -f .server.pid" EXIT

for i in $(seq 1 10); do
    if curl -sf "http://localhost:${MCP_PORT}/health" >/dev/null 2>&1; then
        echo "MCP server ready — http://localhost:${MCP_PORT}/mcp (pid ${SERVER_PID})"
        break
    fi
    if [ "$i" -eq 10 ]; then
        echo "Server did not become ready after 10 seconds"
        exit 1
    fi
    sleep 1
done

uv run python demo.py

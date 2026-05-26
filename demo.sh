#!/usr/bin/env bash
set -euo pipefail

if ! command -v claude &>/dev/null; then
    echo "Claude Code CLI not found. Install from https://claude.ai/code"
    exit 1
fi

VERSION=$(cat .claude-code-version)
claude update "$VERSION"

uv sync

uv run python mcp_demo_server.py &
SERVER_PID=$!

trap "kill $SERVER_PID 2>/dev/null" EXIT

for i in $(seq 1 10); do
    if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
        break
    fi
    if [ "$i" -eq 10 ]; then
        echo "Server did not become ready after 10 seconds"
        exit 1
    fi
    sleep 1
done

uv run python demo.py

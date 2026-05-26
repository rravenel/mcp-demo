#!/usr/bin/env bash
set -euo pipefail

if ! command -v claude &>/dev/null; then
    echo "Claude Code CLI not found. Install from https://claude.ai/code"
    exit 1
fi

VERSION=$(cat .claude-code-version)
claude update "$VERSION"

uv sync

# Stop any server already running (previous demo run, manual start, etc.)
./stop.sh

uv run python mcp_demo_server.py >> .server.log 2>&1 &
SERVER_PID=$!
echo $SERVER_PID > .server.pid

trap "kill $SERVER_PID 2>/dev/null; rm -f .server.pid" EXIT

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

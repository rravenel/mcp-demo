#!/usr/bin/env bash
set -euo pipefail

PID_FILE=".server.pid"
MCP_PORT=$(uv run python -c "from config import MCP_PORT; print(MCP_PORT)" 2>/dev/null || echo 8000)

_kill_pid() {
    local pid=$1
    echo "Stopping server (pid $pid)..."
    kill "$pid"
    for i in $(seq 1 5); do
        if ! kill -0 "$pid" 2>/dev/null; then
            break
        fi
        sleep 1
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "Process did not exit cleanly — sending SIGKILL"
        kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    echo "Done"
}

# Primary path: use the pid file
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        _kill_pid "$PID"
        exit 0
    else
        echo "Stale pid file removed"
        rm -f "$PID_FILE"
    fi
fi

# Fallback: find whatever is listening on the configured port
PORT_PID=$(lsof -ti:"${MCP_PORT}" 2>/dev/null || true)
if [ -n "$PORT_PID" ]; then
    echo "No pid file found but port ${MCP_PORT} is in use — stopping process $PORT_PID"
    _kill_pid "$PORT_PID"
    exit 0
fi

echo "No server running"

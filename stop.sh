#!/usr/bin/env bash
set -euo pipefail

PID_FILE=".server.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "No .server.pid file found — server may not be running"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ! kill -0 "$PID" 2>/dev/null; then
    echo "Process $PID is not running (stale pid file)"
    rm -f "$PID_FILE"
    exit 0
fi

echo "Stopping server (pid $PID)..."
kill "$PID"

for i in $(seq 1 5); do
    if ! kill -0 "$PID" 2>/dev/null; then
        break
    fi
    sleep 1
done

if kill -0 "$PID" 2>/dev/null; then
    echo "Process did not exit cleanly — sending SIGKILL"
    kill -9 "$PID" 2>/dev/null || true
fi

rm -f "$PID_FILE"
echo "Done"

#!/bin/sh
PORT="${PORT:-8000}"
echo "=== Starting PowerSync on port $PORT ==="

if [ -f "venv/bin/uvicorn" ]; then
    UVICORN_CMD="venv/bin/uvicorn"
elif [ -f ".venv/bin/uvicorn" ]; then
    UVICORN_CMD=".venv/bin/uvicorn"
elif command -v uvicorn >/dev/null 2>&1; then
    UVICORN_CMD="uvicorn"
else
    UVICORN_CMD="python3 -m uvicorn"
fi

exec $UVICORN_CMD app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips='*'

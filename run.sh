#!/usr/bin/env bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt
fi

echo "=========================================================="
echo "⚡ PowerSync - AI Fitness Dashboard & Zwift Bridge"
echo "=========================================================="
echo "Starting local server at http://0.0.0.0:8000 (accessible on your Mac & local Wi-Fi) ..."
echo "Press Ctrl+C to stop."
echo ""

exec "$DIR/venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 --reload

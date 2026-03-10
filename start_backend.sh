#!/usr/bin/env bash
# Swasthya Sahayak AI - Backend Startup Script (Mac/Linux)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/backend"

# Virtual env
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$SCRIPT_DIR/venv"
fi
source "$SCRIPT_DIR/venv/bin/activate"

pip install -r requirements.txt -r requirements-azure.txt -q

# Load .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
    echo "Loaded .env"
fi

echo ""
echo "Starting Swasthya Sahayak backend on http://localhost:8080"
echo "Press Ctrl+C to stop."
echo ""

python -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload

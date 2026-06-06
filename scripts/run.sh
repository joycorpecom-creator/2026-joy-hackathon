#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

if [ ! -d .venv ]; then
    echo "Virtual environment not found. Run: ./setup.sh"
    exit 1
fi
if [ ! -f .env ]; then
    echo ".env not found. Run: ./setup.sh, then edit .env"
    exit 1
fi

source .venv/bin/activate
export PYTHONPATH="$DIR:${PYTHONPATH:-}"

echo "=== JOY-DNSE Mockup Studio ==="
echo "Starting server: http://127.0.0.1:8000"
echo "Press Ctrl+C to stop."
exec python main.py

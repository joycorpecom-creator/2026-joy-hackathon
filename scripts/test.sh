#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

if [ ! -d .venv ]; then
    echo "Virtual environment not found. Run: ./setup.sh"
    exit 1
fi
source .venv/bin/activate
export PYTHONPATH="$DIR:${PYTHONPATH:-}"

echo "Running syntax checks..."
python -m py_compile *.py agent_runtime/*.py

echo "Running tests..."
pytest -q

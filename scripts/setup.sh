#!/usr/bin/env bash
set -e
DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$DIR"

echo "=== JOY-DNSE Mockup Studio Setup ==="

# Python check
PYTHON=""
for cmd in python3 python3.10 python3.11; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done
if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.10+ is required but not found."
    echo "Install: sudo apt install python3 python3-venv python3-pip"
    exit 1
fi
echo "✓ Python: $($PYTHON --version)"

# Create venv
if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv .venv
    echo "✓ venv created"
fi
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt
echo "✓ dependencies installed"

# Copy .env if needed
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "⚠️  .env created from .env.example"
    echo "   Edit .env and set:"
    echo "     BURGERPRINTS_API_KEY=your_key"
    echo "     GEMINI_API_KEY=your_key"
    echo ""
    echo "   Then run: ./run.sh"
    exit 0
fi

echo "✓ .env found"
echo ""
echo "Setup complete. Run: ./run.sh"

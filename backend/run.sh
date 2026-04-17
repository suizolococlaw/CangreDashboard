#!/bin/bash

# CangreDashboard Backend Startup Script

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    echo "Python 3.10+ is required but was not found in PATH"
    exit 1
fi

echo "🦞 CangreDashboard - Backend Server"
echo "=================================="
echo "🐍 Using Python: $PYTHON_BIN"

if [ -d "venv" ]; then
    VENV_VER=$(venv/bin/python -c "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')" 2>/dev/null || echo "0.0")
    VENV_MAJOR=${VENV_VER%%.*}
    VENV_MINOR=${VENV_VER##*.}
    if [ "$VENV_MAJOR" -gt 3 ] || { [ "$VENV_MAJOR" -eq 3 ] && [ "$VENV_MINOR" -ge 14 ]; }; then
        echo "♻️ Recreating venv built with unsupported Python $VENV_VER"
        rm -rf venv
    fi
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    "$PYTHON_BIN" -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -q -r requirements.txt

# Set environment variables
export FLASK_APP=app.py
export FLASK_ENV=production
# Uncomment for debugging:
# export FLASK_DEBUG=True

# Run the app
echo "🚀 Starting backend server on http://127.0.0.1:5001"
echo "   Press Ctrl+C to stop"
echo ""
python app.py

#!/bin/bash

# YouTube Intelligence Development Server
# Hot reloading enabled for prompt and UI editing

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Use Python 3.12 from venv if available, fallback to system python3
if [ -f "$SCRIPT_DIR/venv_py312/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv_py312/bin/python3"
else
    PYTHON_CMD="python3"
fi

echo "🔥 Starting YouTube Intelligence Development Server..."
echo "📱 Hot reloading ENABLED - edit prompts and HTML files to see changes instantly!"
echo ""

# Check if port 5002 is available
if lsof -i :5002 > /dev/null 2>&1; then
    echo "⚠️  Port 5002 is already in use. Stopping existing process..."
    lsof -ti :5002 | xargs kill -9 2>/dev/null
    sleep 2
fi

# Start the development server
echo "🚀 Starting Flask development server on port 5002..."
"$PYTHON_CMD" app_dev.py


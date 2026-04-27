#!/bin/bash

# YouTube Intelligence Server Startup Script
# This script ensures the Flask app stays running

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Use Python 3.12 from venv if available, fallback to system python3
if [ -f "$SCRIPT_DIR/venv_py312/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv_py312/bin/python3"
else
    PYTHON_CMD="python3"
fi

echo "🚀 Starting YouTube Intelligence Server..."

# Function to start the server
start_server() {
    echo "📱 Starting Flask app on port 5001..."
    "$PYTHON_CMD" app.py
}

# Function to check if server is running
check_server() {
    curl -s http://localhost:5001/library > /dev/null 2>&1
    return $?
}

# Main loop
while true; do
    if ! check_server; then
        echo "⚠️  Server not responding, restarting..."
        start_server &
        sleep 5
    else
        echo "✅ Server is running on http://localhost:5001"
        sleep 30
    fi
done

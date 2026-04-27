#!/bin/bash

# Standalone server starter - can be called even when server is down
# This script starts the server without needing the API to be running

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Use Python 3.12 from venv if available, fallback to system python3
if [ -f "$SCRIPT_DIR/venv_py312/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv_py312/bin/python3"
else
    PYTHON_CMD="python3"
fi

LOG_FILE="$SCRIPT_DIR/logs/server.log"
mkdir -p logs

echo "🚀 Starting YouTube Intelligence Server..."
echo "$(date): Starting server via standalone script..." >> "$LOG_FILE"

# Check if already running
if lsof -i :5001 > /dev/null 2>&1; then
    echo "⚠️  Server is already running on port 5001"
    exit 0
fi

# Start the server using the keep-running script
"$SCRIPT_DIR/start_and_keep_running.sh" > /dev/null 2>&1 &

# Wait a moment
sleep 3

# Check if it started
if lsof -i :5001 > /dev/null 2>&1; then
    echo "✅ Server started successfully!"
    echo "📱 Access at: http://localhost:5001"
else
    echo "❌ Server failed to start. Check logs: $LOG_FILE"
    exit 1
fi









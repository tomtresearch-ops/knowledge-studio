#!/bin/bash

# Stop YouTube Intelligence Server

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PID_FILE="$SCRIPT_DIR/.server.pid"

echo "🛑 Stopping YouTube Intelligence Server..."

# Track if we successfully stopped anything
STOPPED_SOMETHING=false

# Kill the monitoring script if PID file exists
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if ps -p "$PID" > /dev/null 2>&1; then
        echo "Stopping monitoring process $PID..."
        kill "$PID" 2>/dev/null && STOPPED_SOMETHING=true
    fi
    rm -f "$PID_FILE"
fi

# Kill all related processes - updated to match Python 3.12 venv paths
# Try graceful kill first, then force kill
pkill -f "python.*app\.py" 2>/dev/null && STOPPED_SOMETHING=true
pkill -f "venv_py312.*app\.py" 2>/dev/null && STOPPED_SOMETHING=true
pkill -f "run_background\.py" 2>/dev/null && STOPPED_SOMETHING=true
pkill -f "venv_py312.*run_background" 2>/dev/null && STOPPED_SOMETHING=true
pkill -f "start_and_keep_running" 2>/dev/null && STOPPED_SOMETHING=true

# Wait a moment for graceful shutdown
sleep 1

# Force kill anything still on port 5001
PORT_PIDS=$(lsof -ti:5001 2>/dev/null)
if [ -n "$PORT_PIDS" ]; then
    echo "Force stopping processes on port 5001..."
    echo "$PORT_PIDS" | xargs kill -9 2>/dev/null && STOPPED_SOMETHING=true
fi

# Final cleanup - force kill any remaining Python processes matching our patterns
pkill -9 -f "python.*app\.py" 2>/dev/null
pkill -9 -f "venv_py312.*app\.py" 2>/dev/null
pkill -9 -f "run_background\.py" 2>/dev/null
pkill -9 -f "venv_py312.*run_background" 2>/dev/null

# Wait a moment
sleep 1

# Check if anything is still running
if lsof -i :5001 > /dev/null 2>&1; then
    echo "⚠️  Warning: Some processes still running on port 5001"
    echo "   Attempting final cleanup..."
    lsof -ti:5001 | xargs kill -9 2>/dev/null
    sleep 1
    if lsof -i :5001 > /dev/null 2>&1; then
        echo "❌ Could not stop all processes. You may need to manually kill them:"
        lsof -i :5001
        exit 1
    else
        echo "✅ Server stopped successfully (after force cleanup)"
        exit 0
    fi
else
    if [ "$STOPPED_SOMETHING" = true ]; then
        echo "✅ Server stopped successfully"
    else
        echo "ℹ️  No server processes were running"
    fi
    exit 0
fi


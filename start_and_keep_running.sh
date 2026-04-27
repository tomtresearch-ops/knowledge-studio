#!/bin/bash

# YouTube Intelligence - Start and Keep Running
# This script starts the app and automatically restarts it if it crashes

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Use Python 3.12 from venv if available, fallback to system python3
if [ -f "$SCRIPT_DIR/venv_py312/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv_py312/bin/python3"
else
    PYTHON_CMD="python3"
fi

PID_FILE="$SCRIPT_DIR/.server.pid"
LOG_FILE="$SCRIPT_DIR/logs/server.log"

# Create logs directory if it doesn't exist
mkdir -p logs

# Function to check if server is running
check_server() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            # Check if it's actually listening on port 5001
            if lsof -i :5001 > /dev/null 2>&1; then
                return 0
            fi
        fi
    fi
    return 1
}

# Function to start the server
start_server() {
    echo "$(date): Starting YouTube Intelligence Server..." >> "$LOG_FILE"
    
    # Kill any existing processes
    pkill -f "python.*app.py" 2>/dev/null
    
    # Start the server in background
    nohup "$PYTHON_CMD" app.py >> "$LOG_FILE" 2>&1 &
    SERVER_PID=$!
    
    # Save PID
    echo $SERVER_PID > "$PID_FILE"
    
    echo "$(date): Server started with PID $SERVER_PID" >> "$LOG_FILE"
    echo "Server started with PID: $SERVER_PID"
    
    # Wait a moment for server to start
    sleep 3
    
    # Verify it's running
    if check_server; then
        echo "✅ Server is running on http://localhost:5001"
        return 0
    else
        echo "❌ Server failed to start. Check logs: $LOG_FILE"
        return 1
    fi
}

# Function to stop the server
stop_server() {
    echo ""
    echo "🛑 Stopping server..."
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        kill "$PID" 2>/dev/null
        rm "$PID_FILE"
    fi
    pkill -f "python.*app.py" 2>/dev/null
    echo "✅ Server stopped"
    exit 0
}

# Set up signal handlers
trap stop_server INT TERM

# Start the server initially
start_server

# Main monitoring loop
while true; do
    sleep 10
    
    if ! check_server; then
        echo "$(date): Server not responding, restarting..." >> "$LOG_FILE"
        echo "⚠️  Server not responding, restarting..."
        start_server
    fi
done









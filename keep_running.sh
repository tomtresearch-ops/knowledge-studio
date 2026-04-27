#!/bin/bash

# Keep YouTube Intelligence Server Always Running
# This script ensures the server stays up and restarts if it crashes

echo "🚀 YouTube Intelligence - Always Running Mode"
echo "This will keep the server running until you stop it with Ctrl+C"
echo ""

# Function to check if server is running
check_server() {
    curl -s http://localhost:5001/api/status > /dev/null 2>&1
    return $?
}

# Function to start the server
start_server() {
    echo "📱 Starting YouTube Intelligence Server..."
    ./start_everything.sh &
    SERVER_PID=$!
    echo "Server started with PID: $SERVER_PID"
}

# Function to stop the server
stop_server() {
    echo ""
    echo "🛑 Stopping server..."
    pkill -f "python.*app.py"
    pkill -f "run_background.py"
    echo "✅ Server stopped"
    exit 0
}

# Set up signal handlers
trap stop_server INT TERM

# Start the server initially
start_server

# Wait a moment for startup
sleep 5

# Main monitoring loop
while true; do
    if ! check_server; then
        echo "⚠️  Server not responding, restarting..."
        pkill -f "python.*app.py"
        pkill -f "run_background.py"
        sleep 2
        start_server
        sleep 5
    else
        echo "✅ Server is running on http://localhost:5001"
        sleep 30
    fi
done



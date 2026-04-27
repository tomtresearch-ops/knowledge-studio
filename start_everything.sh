#!/bin/bash

# YouTube Intelligence - Complete System Launcher
# Starts both background processing and web interface

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Use Python 3.12 from venv if available, fallback to system python3
if [ -f "$SCRIPT_DIR/venv_py312/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv_py312/bin/python3"
else
    PYTHON_CMD="python3"
fi

echo "🚀 Starting YouTube Intelligence Complete System..."

# Function to check if a port is in use
check_port() {
    lsof -i :$1 > /dev/null 2>&1
    return $?
}

# Start background processing service
echo "📱 Starting background processing service..."
"$PYTHON_CMD" run_background.py &
BACKGROUND_PID=$!

# Wait a moment for background service to start
sleep 2

# Start web interface
echo "🌐 Starting web interface..."
"$PYTHON_CMD" app.py &
WEB_PID=$!

# Wait a moment for web service to start
sleep 3

# Check if services are running
if check_port 5001; then
    echo "✅ System is running!"
    echo "📱 Web interface: http://localhost:5001"
    echo "📱 Library: http://localhost:5001/library"
    echo ""
    echo "📸 Just drop screenshots into the 'screenshots/' folder"
    echo "🔄 Processing happens automatically in the background"
    echo ""
    echo "Press Ctrl+C to stop everything"
    
    # Wait for user interrupt
    trap "echo '🛑 Stopping system...'; kill $BACKGROUND_PID $WEB_PID 2>/dev/null; exit" INT
    wait
else
    echo "❌ Failed to start web interface"
    kill $BACKGROUND_PID 2>/dev/null
    exit 1
fi

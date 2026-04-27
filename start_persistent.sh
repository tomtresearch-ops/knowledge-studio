#!/bin/bash

# YouTube Intelligence - Persistent Background Service
# This runs the server in the background and keeps it running

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Use Python 3.12 from venv if available, fallback to system python3
if [ -f "$SCRIPT_DIR/venv_py312/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv_py312/bin/python3"
else
    PYTHON_CMD="python3"
fi

echo "🚀 Starting YouTube Intelligence as persistent background service..."

# Kill any existing processes
pkill -f "python.*app.py" 2>/dev/null
pkill -f "run_background.py" 2>/dev/null

# Start background processing service
echo "📱 Starting background processing service..."
nohup "$PYTHON_CMD" run_background.py > logs/background.log 2>&1 &
BACKGROUND_PID=$!

# Wait a moment for background service to start
sleep 2

# Start web interface
echo "🌐 Starting web interface..."
nohup "$PYTHON_CMD" app.py > logs/web.log 2>&1 &
WEB_PID=$!

# Wait a moment for web service to start
sleep 3

# Check if services are running
if curl -s http://localhost:5001/api/status > /dev/null 2>&1; then
    echo "✅ System is running in the background!"
    echo "📱 Web interface: http://localhost:5001"
    echo "📱 Library: http://localhost:5001/library"
    echo ""
    echo "Process IDs:"
    echo "  Background service: $BACKGROUND_PID"
    echo "  Web interface: $WEB_PID"
    echo ""
    echo "Logs are in the 'logs/' directory"
    echo "To stop: ./stop_server.sh"
    echo ""
    echo "The server will continue running even if you close this terminal!"
else
    echo "❌ Failed to start services"
    kill $BACKGROUND_PID $WEB_PID 2>/dev/null
    exit 1
fi



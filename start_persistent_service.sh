#!/bin/bash

# YouTube Intelligence - Persistent Service Manager
# This script manages the app as a launchd service

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PLIST_FILE="$SCRIPT_DIR/com.knowledgestudio.server.plist"
SERVICE_NAME="com.knowledgestudio.server"

echo "🚀 YouTube Intelligence - Persistent Service Manager"
echo ""

# Check if service is already loaded
if launchctl list | grep -q "$SERVICE_NAME"; then
    echo "⚠️  Service is already running"
    echo "   To restart: ./start_persistent_service.sh restart"
    echo "   To stop: ./start_persistent_service.sh stop"
    exit 0
fi

# Load the service
echo "📱 Loading service..."
launchctl load "$PLIST_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Service loaded successfully!"
    echo ""
    echo "📱 Web interface: http://localhost:5001"
    echo "📱 Library: http://localhost:5001/library"
    echo ""
    echo "The service will automatically restart if it crashes."
    echo "To stop: ./start_persistent_service.sh stop"
    echo "To restart: ./start_persistent_service.sh restart"
    echo ""
    echo "Logs:"
    echo "  Output: logs/launchd.out.log"
    echo "  Errors: logs/launchd.err.log"
else
    echo "❌ Failed to load service"
    exit 1
fi









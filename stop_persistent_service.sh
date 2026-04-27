#!/bin/bash

# Stop YouTube Intelligence Persistent Service

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PLIST_FILE="$SCRIPT_DIR/com.knowledgestudio.server.plist"
SERVICE_NAME="com.knowledgestudio.server"

echo "🛑 Stopping YouTube Intelligence service..."

# Unload the service
launchctl unload "$PLIST_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ Service stopped"
else
    echo "⚠️  Service may not have been running"
fi

# Also kill any remaining processes
pkill -f "python.*app.py" 2>/dev/null
pkill -f "run_background.py" 2>/dev/null

echo "✅ All processes stopped"









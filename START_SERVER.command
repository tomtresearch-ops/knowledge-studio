#!/bin/bash

# YouTube Intelligence Server - START
# Double-click this to start the server

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🚀 Starting YouTube Intelligence Server..."
echo "📱 Server will be available at: http://localhost:5001"
echo ""
echo "This will keep the server running and restart it if it crashes."
echo ""

./start_and_keep_running.sh
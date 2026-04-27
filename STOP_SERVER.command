#!/bin/bash

# YouTube Intelligence Server - STOP
# Double-click this to stop the server

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🛑 Stopping YouTube Intelligence Server..."
echo ""

./stop_server.sh

echo ""
echo "Press any key to close this window..."
read -n 1
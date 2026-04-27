#!/bin/bash

# Restart YouTube Intelligence Server
# This script stops the server, waits, then starts it again
# Must run completely independently to survive Flask being killed

# Disown this process immediately so it survives parent death
( 
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

LOG_FILE="$SCRIPT_DIR/logs/restart.log"
mkdir -p logs

echo "$(date): 🔄 Restarting YouTube Intelligence Server..." >> "$LOG_FILE"

# Stop the server (this will kill Flask, but this script continues)
"$SCRIPT_DIR/stop_server.sh" >> "$LOG_FILE" 2>&1

# Wait for server to fully stop
sleep 5

# Verify it's stopped
for attempt in {1..5}; do
    if ! lsof -i :5001 > /dev/null 2>&1; then
        echo "$(date): ✅ Server stopped" >> "$LOG_FILE"
        break
    fi
    sleep 1
done

# Start the server
echo "$(date): 🚀 Starting server..." >> "$LOG_FILE"
cd "$SCRIPT_DIR"
"$SCRIPT_DIR/start_and_keep_running.sh" >> "$LOG_FILE" 2>&1 &

# Wait for server to start
sleep 8

# Check if it started
for check in {1..5}; do
    if lsof -i :5001 > /dev/null 2>&1; then
        echo "$(date): ✅ Server restarted successfully" >> "$LOG_FILE"
        exit 0
    fi
    sleep 2
done

echo "$(date): ⚠️  Server restart may still be in progress" >> "$LOG_FILE"
) & disown


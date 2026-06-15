#!/bin/bash
# KS watchdog — restarts Flask app if port 5001 is unresponsive
LOG=~/knowledge-studio/logs/watchdog.log
APP_DIR=~/knowledge-studio
PYTHON=~/knowledge-studio/.venv/bin/python

if curl -sf --max-time 5 http://localhost:5001/ > /dev/null 2>&1; then
    exit 0
fi

echo "$(date): KS down — restarting" >> "$LOG"

# Kill any zombie app.py processes
pkill -f 'python.*app\.py' 2>/dev/null
sleep 2

# Start fresh
cd "$APP_DIR"
nohup "$PYTHON" app.py >> logs/ks.stdout.log 2>> logs/ks.stderr.log &
disown

sleep 5
if curl -sf --max-time 5 http://localhost:5001/ > /dev/null 2>&1; then
    echo "$(date): KS restarted OK (PID $!)" >> "$LOG"
else
    echo "$(date): KS restart FAILED" >> "$LOG"
fi

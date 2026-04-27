#!/bin/bash
cd "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence"
nohup ./start_and_keep_running.sh > /dev/null 2>&1 &
sleep 3
if lsof -i :5001 > /dev/null 2>&1; then
    osascript -e 'display notification "Server is running at http://localhost:5001" with title "Server Started"'
else
    osascript -e 'display notification "Server starting... may take a moment" with title "Server Starting"'
fi

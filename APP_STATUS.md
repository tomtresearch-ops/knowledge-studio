# YouTube Intelligence - App Status & Startup Guide

## Problem
The Flask app wasn't staying up persistently because:
1. The start scripts weren't properly monitoring and restarting the app
2. The app could crash and not restart automatically
3. No persistent background service was running

## Solution Created

### Option 1: Simple Persistent Script (Recommended)
**File:** `start_and_keep_running.sh`
- Starts the app and monitors it
- Automatically restarts if it crashes
- Runs in background with nohup
- Logs to `logs/server.log`

**To start:**
```bash
./start_and_keep_running.sh
```

**Or double-click:** `START_SERVER.command`

### Option 2: Launchd Service (Advanced)
**Files:** 
- `com.knowledgestudio.server.plist` - Launchd configuration
- `start_persistent_service.sh` - Service manager
- `stop_persistent_service.sh` - Stop service

**To start:**
```bash
./start_persistent_service.sh
```

**To stop:**
```bash
./stop_persistent_service.sh
```

## Current Status

Check if server is running:
```bash
lsof -i :5001
```

Check logs:
```bash
tail -f logs/server.log
```

Stop all processes:
```bash
./stop_server.sh
# or
pkill -f "python.*app.py"
```

## Quick Start

1. **Double-click:** `START_SERVER.command`
2. **Or run:** `./start_and_keep_running.sh`
3. **Access:** http://localhost:5001

The server will now stay running and automatically restart if it crashes!









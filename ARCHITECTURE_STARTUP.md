# Startup Architecture - Knowledge Studio

## Current State Analysis

You're right to ask - there ARE multiple overlapping startup mechanisms. Here's what exists:

### Existing Startup Mechanisms

1. **`start_and_keep_running.sh`** ✅ **RECOMMENDED**
   - Monitors server and auto-restarts if it crashes
   - Single script that handles everything
   - This is what the new launchd plist uses

2. **`start_persistent.sh`** ⚠️ **DEPRECATED**
   - Starts server but doesn't monitor/restart
   - Used by `Start YouTube Server.app`
   - Should be updated to use `start_and_keep_running.sh`

3. **`Start YouTube Server.app`** ⚠️ **NEEDS UPDATE**
   - Currently calls `start_persistent.sh` (no monitoring)
   - Should call `start_and_keep_running.sh` instead

4. **`com.knowledgestudio.server.plist`** ✅ **NEW - OPTIONAL**
   - macOS launchd service for auto-start on boot
   - Calls `start_and_keep_running.sh`
   - Only needed if you want auto-start on login

5. **Other scripts** (legacy/backup):
   - `start_everything.sh` - Old approach
   - `start_persistent_service.sh` - Old approach
   - `start_server.sh` - Basic start (no monitoring)
   - `keep_running.sh` - Old monitoring attempt

## Recommended Architecture

### Single Source of Truth: `start_and_keep_running.sh`

This script:
- ✅ Starts the server
- ✅ Monitors it every 10 seconds
- ✅ Auto-restarts if it crashes
- ✅ Handles PID tracking
- ✅ Logs everything

### How to Use It

**Option 1: Manual Start (Current)**
```bash
./start_and_keep_running.sh
```
- Starts server with monitoring
- Keeps running until you stop it
- Auto-restarts on crash

**Option 2: macOS App (Needs Update)**
- Double-click `Start YouTube Server.app`
- Currently broken - calls wrong script
- Should be updated to call `start_and_keep_running.sh`

**Option 3: Auto-Start on Boot (New)**
```bash
cp com.knowledgestudio.server.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.knowledgestudio.server.plist
```
- Starts automatically when you log in
- Uses `start_and_keep_running.sh` internally
- Auto-restarts on crash

**Option 4: Web UI (New)**
- Status indicator in header
- Start/Stop button
- Calls `start_and_keep_running.sh` via API

## What We Should Do

1. ✅ **Keep** `start_and_keep_running.sh` as the single source of truth
2. ⚠️ **Update** `Start YouTube Server.app` to call `start_and_keep_running.sh`
3. ✅ **Keep** `com.knowledgestudio.server.plist` as optional auto-start
4. 🗑️ **Archive** old scripts (move to backups or delete)
5. ✅ **Use** Web UI for manual control

## No Duplicates - Just Different Entry Points

All mechanisms now point to `start_and_keep_running.sh`:
- Manual: `./start_and_keep_running.sh`
- App: `Start YouTube Server.app` → `start_and_keep_running.sh` (needs update)
- Launchd: `com.knowledgestudio.server.plist` → `start_and_keep_running.sh`
- Web UI: API → `start_and_keep_running.sh`

## Next Steps

1. Update `Start YouTube Server.app` to use the monitoring script
2. Archive old startup scripts
3. Document which script to use









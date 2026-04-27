# Setting Up Persistent Server

## Quick Setup (One-Time)

To make Knowledge Studio start automatically and stay running:

### Option 1: macOS Launch Agent (Recommended - Auto-starts on boot)

```bash
# Copy the plist file to LaunchAgents directory
cp com.knowledgestudio.server.plist ~/Library/LaunchAgents/

# Load the service
launchctl load ~/Library/LaunchAgents/com.knowledgestudio.server.plist

# Start it now (optional)
launchctl start com.knowledgestudio.server
```

The server will now:
- ✅ Start automatically when you log in
- ✅ Restart automatically if it crashes
- ✅ Keep running in the background

### Option 2: Manual Start Script

If you prefer manual control, you can run:
```bash
./start_and_keep_running.sh
```

This will start the server and keep it running, restarting automatically if it crashes.

## Managing the Service

### Check Status
```bash
launchctl list | grep knowledgestudio
```

### Stop the Service
```bash
launchctl stop com.knowledgestudio.server
launchctl unload ~/Library/LaunchAgents/com.knowledgestudio.server.plist
```

### Start the Service
```bash
launchctl load ~/Library/LaunchAgents/com.knowledgestudio.server.plist
launchctl start com.knowledgestudio.server
```

## UI Controls

You can also control the server from the web interface:
- **Status Indicator**: Shows green (running) or red (stopped) in the header
- **Start/Stop Button**: Click to start or stop the server
- **Error Banner**: Automatically appears if the server goes down

The interface checks server status every 10 seconds and shows a warning banner if the server is down.









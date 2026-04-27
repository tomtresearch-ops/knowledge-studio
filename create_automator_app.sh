#!/bin/bash

# Create an Automator-based app that will definitely work

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🚀 Creating Automator-based app..."

# Create the app structure
mkdir -p "Start Server.app/Contents/MacOS"
mkdir -p "Start Server.app/Contents/Resources"

# Create an AppleScript that runs the start script
cat > "Start Server.app/Contents/Resources/start_server.scpt" << 'EOF'
on run
    set scriptPath to POSIX path of (path to me as alias) & "Contents/Resources/start_server.sh"
    do shell script "bash " & quoted form of scriptPath
    display notification "Server starting..." with title "YouTube Intelligence"
end run
EOF

# Create the shell script
cat > "Start Server.app/Contents/Resources/start_server.sh" << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
nohup ./start_and_keep_running.sh > /dev/null 2>&1 &
sleep 3
if lsof -i :5001 > /dev/null 2>&1; then
    osascript -e 'display notification "Server is running at http://localhost:5001" with title "Server Started"'
else
    osascript -e 'display notification "Server starting... may take a moment" with title "Server Starting"'
fi
EOF

chmod +x "Start Server.app/Contents/Resources/start_server.sh"

# Create a simple executable that runs the AppleScript
cat > "Start Server.app/Contents/MacOS/Start Server" << 'EOF'
#!/usr/bin/osascript
on run
    set scriptDir to POSIX path of (path to me as alias) & "../Resources/"
    set scriptPath to scriptDir & "start_server.sh"
    do shell script "bash " & quoted form of scriptPath
    display notification "Server starting..." with title "YouTube Intelligence"
end run
EOF

chmod +x "Start Server.app/Contents/MacOS/Start Server"

# Create Info.plist
cat > "Start Server.app/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Start Server</string>
    <key>CFBundleIdentifier</key>
    <string>com.knowledgestudio.startserver</string>
    <key>CFBundleName</key>
    <string>Start Server</string>
    <key>CFBundleVersion</key>
    <string>3.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.9</string>
</dict>
</plist>
EOF

echo "✅ Created Start Server.app"
echo ""
echo "🎯 Try this one - it uses AppleScript which macOS trusts more"
echo "   Drag 'Start Server.app' to your Dock"









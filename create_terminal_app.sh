#!/bin/bash

# Create an app that opens Terminal and runs the start command
# This is the most reliable method

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🚀 Creating Terminal-based app (most reliable)..."

mkdir -p "Start YouTube Server.app/Contents/MacOS"
mkdir -p "Start YouTube Server.app/Contents/Resources"

# Create AppleScript that opens Terminal and runs the command
cat > "Start YouTube Server.app/Contents/MacOS/Start YouTube Server" << EOF
#!/usr/bin/osascript
on run
    set scriptDir to "$SCRIPT_DIR"
    tell application "Terminal"
        activate
        do script "cd " & quoted form of scriptDir & " && ./start_and_keep_running.sh"
    end tell
    display notification "Starting server in Terminal..." with title "YouTube Intelligence"
end run
EOF

chmod +x "Start YouTube Server.app/Contents/MacOS/Start YouTube Server"

# Update Info.plist
cat > "Start YouTube Server.app/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Start YouTube Server</string>
    <key>CFBundleIdentifier</key>
    <string>com.knowledgestudio.startserver</string>
    <key>CFBundleName</key>
    <string>Start YouTube Server</string>
    <key>CFBundleVersion</key>
    <string>4.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.9</string>
</dict>
</plist>
EOF

echo "✅ Updated Start YouTube Server.app"
echo ""
echo "🎯 This version opens Terminal and runs the command there"
echo "   This is the most reliable method - macOS always allows Terminal apps"
echo ""
echo "💡 You'll see a Terminal window open when you click it"
echo "   The server will run in that window (you can minimize it)"









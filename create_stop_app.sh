#!/bin/bash

# Create/update the Stop Server app to work silently

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🛑 Creating/updating Stop Server app..."

mkdir -p "Stop YouTube Server.app/Contents/MacOS"
mkdir -p "Stop YouTube Server.app/Contents/Resources"

# Create AppleScript that runs stop_server.sh silently
cat > "Stop YouTube Server.app/Contents/MacOS/Stop YouTube Server" << 'EOF'
#!/usr/bin/osascript
on run
    set scriptDir to "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence"
    
    -- Run the stop script
    try
        do shell script "cd " & quoted form of scriptDir & " && ./stop_server.sh"
        
        -- Wait a moment and check if server stopped
        delay 2
        
        -- Check if server is stopped
        try
            do shell script "lsof -i :5001 > /dev/null 2>&1"
            display notification "Server may still be stopping. Check again in a moment." with title "Server Stopping"
        on error
            display notification "Server stopped successfully" with title "Server Stopped" sound name "Glass"
        end try
    on error errorMessage
        display notification "Error: " & errorMessage with title "Server Stop Failed" sound name "Basso"
    end try
end run
EOF

chmod +x "Stop YouTube Server.app/Contents/MacOS/Stop YouTube Server"

# Update Info.plist
cat > "Stop YouTube Server.app/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Stop YouTube Server</string>
    <key>CFBundleIdentifier</key>
    <string>com.knowledgestudio.stopserver</string>
    <key>CFBundleName</key>
    <string>Stop YouTube Server</string>
    <key>CFBundleVersion</key>
    <string>2.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.9</string>
</dict>
</plist>
EOF

echo "✅ Updated Stop YouTube Server.app"
echo ""
echo "🎯 This version:"
echo "   ✅ Runs silently (no Terminal window)"
echo "   ✅ Shows notifications for feedback"
echo "   ✅ Should work without Terminal automation permission"
echo ""
echo "💡 Remove and re-add to Dock to use the updated version"









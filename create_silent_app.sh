#!/bin/bash

# Create a silent version that shows notifications but no Terminal window
# This should work without the Terminal automation permission

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🚀 Creating silent app with notifications..."

mkdir -p "Start YouTube Server.app/Contents/MacOS"
mkdir -p "Start YouTube Server.app/Contents/Resources"

# Create AppleScript that runs directly without Terminal
cat > "Start YouTube Server.app/Contents/MacOS/Start YouTube Server" << 'EOF'
#!/usr/bin/osascript
on run
    set scriptDir to "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence"
    
    -- Show starting notification
    display notification "Starting YouTube Intelligence Server..." with title "Server Starting"
    
    -- Run the start script in background using do shell script
    -- This runs without Terminal window
    try
        do shell script "cd " & quoted form of scriptDir & " && nohup ./start_and_keep_running.sh > /dev/null 2>&1 &"
        
        -- Wait a moment and check if server started
        delay 4
        
        -- Check if server is running
        try
            do shell script "lsof -i :5001 > /dev/null 2>&1"
            display notification "Server is running at http://localhost:5001" with title "Server Started" sound name "Glass"
        on error
            display notification "Server may still be starting. Check http://localhost:5001 in a moment." with title "Server Starting"
        end try
    on error errorMessage
        display notification "Error: " & errorMessage with title "Server Start Failed" sound name "Basso"
    end try
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
    <string>5.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.9</string>
</dict>
</plist>
EOF

echo "✅ Created silent version"
echo ""
echo "🎯 This version:"
echo "   ✅ Runs silently (no Terminal window)"
echo "   ✅ Shows notifications for feedback"
echo "   ✅ Should work without Terminal automation permission"
echo ""
echo "💡 Try it - you'll get notifications but no Terminal window"









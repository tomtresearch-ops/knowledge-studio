#!/bin/bash

# Create updated Dock apps for YouTube Intelligence Server
# These will work with Python 3.12 and correct paths

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🚀 Creating/Updating Dock apps..."

# Create Start Server App
mkdir -p "Start YouTube Server.app/Contents/MacOS"
mkdir -p "Start YouTube Server.app/Contents/Resources"

cat > "Start YouTube Server.app/Contents/MacOS/Start YouTube Server" << EOF
#!/bin/bash
cd "$SCRIPT_DIR"
./start_and_keep_running.sh
EOF

chmod +x "Start YouTube Server.app/Contents/MacOS/Start YouTube Server"

# Create Info.plist for Start app
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
    <string>2.0</string>
    <key>CFBundleShortVersionString</key>
    <string>2.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.9</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

# Create Stop Server App
mkdir -p "Stop YouTube Server.app/Contents/MacOS"
mkdir -p "Stop YouTube Server.app/Contents/Resources"

cat > "Stop YouTube Server.app/Contents/MacOS/Stop YouTube Server" << 'EOF'
#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && cd ../.. && pwd )"
cd "$SCRIPT_DIR"
./stop_server.sh
sleep 2
EOF

chmod +x "Stop YouTube Server.app/Contents/MacOS/Stop YouTube Server"

# Create Info.plist for Stop app
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
    <key>CFBundleShortVersionString</key>
    <string>2.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.9</string>
    <key>LSUIElement</key>
    <false/>
</dict>
</plist>
EOF

echo ""
echo "✅ Created/Updated:"
echo "   📱 Start YouTube Server.app"
echo "   🛑 Stop YouTube Server.app"
echo ""
echo "🎯 To use:"
echo "   1. Drag 'Start YouTube Server.app' to your Dock"
echo "   2. Click it anytime to start the server (one click!)"
echo "   3. Optionally drag 'Stop YouTube Server.app' to Dock too"
echo ""
echo "💡 Tip: Right-click the Dock icon → Options → Keep in Dock"









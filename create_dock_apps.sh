#!/bin/bash

# Create proper .app bundles for the Dock

echo "🚀 Creating Dock-friendly apps..."

# Create Start Server App
mkdir -p "Start YouTube Server.app/Contents/MacOS"
mkdir -p "Start YouTube Server.app/Contents/Resources"

# Create a native shell script instead of copying the .command file
cat > "Start YouTube Server.app/Contents/MacOS/start_server" << 'EOF'
#!/bin/bash
cd "/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT"
echo "🚀 Starting YouTube Intelligence Server..."
echo "📱 Server will be available at: http://localhost:5001"
echo ""
./start_persistent.sh
EOF
chmod +x "Start YouTube Server.app/Contents/MacOS/start_server"

# Create Info.plist
cat > "Start YouTube Server.app/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>start_server</string>
    <key>CFBundleIdentifier</key>
    <string>com.youtubetools.startserver</string>
    <key>CFBundleName</key>
    <string>Start YouTube Server</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.9</string>
</dict>
</plist>
EOF

# Create Stop Server App
mkdir -p "Stop YouTube Server.app/Contents/MacOS"
mkdir -p "Stop YouTube Server.app/Contents/Resources"

# Create a native shell script instead of copying the .command file
cat > "Stop YouTube Server.app/Contents/MacOS/stop_server" << 'EOF'
#!/bin/bash
cd "/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT"
echo "🛑 Stopping YouTube Intelligence Server..."
echo ""
./stop_server.sh
echo ""
echo "Press any key to close this window..."
read -n 1
EOF
chmod +x "Stop YouTube Server.app/Contents/MacOS/stop_server"

# Create Info.plist
cat > "Stop YouTube Server.app/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>stop_server</string>
    <key>CFBundleIdentifier</key>
    <string>com.youtubetools.stopserver</string>
    <key>CFBundleName</key>
    <string>Stop YouTube Server</string>
    <key>CFBundleVersion</key>
    <string>1.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.9</string>
</dict>
</plist>
EOF

echo "✅ Created:"
echo "  - Start YouTube Server.app"
echo "  - Stop YouTube Server.app"
echo ""
echo "🎯 Now you can:"
echo "  1. Drag these .app files to your Dock"
echo "  2. Right-click → Get Info to add custom icons"
echo "  3. They'll look like proper apps in the Dock!"


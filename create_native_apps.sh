#!/bin/bash

echo "🚀 Creating native Apple Silicon app bundles..."

# Create Start Server App
mkdir -p "Start YouTube Server.app/Contents/MacOS"
mkdir -p "Start YouTube Server.app/Contents/Resources"

# Create the executable script with proper shebang
cat > "Start YouTube Server.app/Contents/MacOS/Start YouTube Server" << 'EOF'
#!/usr/bin/env bash
cd "/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT"
echo "🚀 Starting YouTube Intelligence Server..."
echo "📱 Server will be available at: http://localhost:5001"
echo ""
exec ./start_persistent.sh
EOF

chmod +x "Start YouTube Server.app/Contents/MacOS/Start YouTube Server"

# Create Info.plist with proper native settings
cat > "Start YouTube Server.app/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Start YouTube Server</string>
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
    <string>11.0</string>
    <key>LSArchitecturePriority</key>
    <array>
        <string>arm64</string>
    </array>
    <key>LSRequiresIPhoneOS</key>
    <false/>
</dict>
</plist>
EOF

# Create Stop Server App
mkdir -p "Stop YouTube Server.app/Contents/MacOS"
mkdir -p "Stop YouTube Server.app/Contents/Resources"

# Create the executable script with proper shebang
cat > "Stop YouTube Server.app/Contents/MacOS/Stop YouTube Server" << 'EOF'
#!/usr/bin/env bash
cd "/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT"
echo "🛑 Stopping YouTube Intelligence Server..."
echo ""
exec ./stop_server.sh
echo ""
echo "Press any key to close this window..."
read -n 1
EOF

chmod +x "Stop YouTube Server.app/Contents/MacOS/Stop YouTube Server"

# Create Info.plist with proper native settings
cat > "Stop YouTube Server.app/Contents/Info.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Stop YouTube Server</string>
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
    <string>11.0</string>
    <key>LSArchitecturePriority</key>
    <array>
        <string>arm64</string>
    </array>
    <key>LSRequiresIPhoneOS</key>
    <false/>
</dict>
</plist>
EOF

echo "✅ Created native Apple Silicon apps:"
echo "  - Start YouTube Server.app"
echo "  - Stop YouTube Server.app"
echo ""
echo "🎯 These should work without Rosetta!"














#!/bin/bash

# Apply custom icons to Start and Stop server apps

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🎨 Applying custom icons to apps..."

# Function to set icon for an app
set_app_icon() {
    local APP_NAME="$1"
    local ICON_FILE="$2"
    
    if [ ! -d "$APP_NAME.app" ]; then
        echo "⚠️  $APP_NAME.app not found, skipping..."
        return
    fi
    
    if [ ! -f "$ICON_FILE" ]; then
        echo "⚠️  Icon file $ICON_FILE not found, skipping..."
        return
    fi
    
    # Copy icon to app resources
    mkdir -p "$APP_NAME.app/Contents/Resources"
    cp "$ICON_FILE" "$APP_NAME.app/Contents/Resources/icon.png"
    
    # Update Info.plist to reference the icon
    if [ -f "$APP_NAME.app/Contents/Info.plist" ]; then
        # Check if CFBundleIconFile already exists
        if grep -q "CFBundleIconFile" "$APP_NAME.app/Contents/Info.plist"; then
            # Update existing entry
            sed -i '' 's|<key>CFBundleIconFile</key>.*|<key>CFBundleIconFile</key>\n    <string>icon.icns</string>|' "$APP_NAME.app/Contents/Info.plist" 2>/dev/null || \
            python3 << EOF
import plistlib
import sys

plist_path = "$APP_NAME.app/Contents/Info.plist"
with open(plist_path, 'rb') as f:
    plist = plistlib.load(f)

plist['CFBundleIconFile'] = 'icon.icns'

with open(plist_path, 'wb') as f:
    plistlib.dump(plist, f)
EOF
        else
            # Add before closing </dict>
            sed -i '' '/<\/dict>/i\
    <key>CFBundleIconFile</key>\
    <string>icon.icns</string>
' "$APP_NAME.app/Contents/Info.plist" 2>/dev/null || \
            python3 << EOF
import plistlib

plist_path = "$APP_NAME.app/Contents/Info.plist"
with open(plist_path, 'rb') as f:
    plist = plistlib.load(f)

plist['CFBundleIconFile'] = 'icon.icns'

with open(plist_path, 'wb') as f:
    plistlib.dump(plist, f)
EOF
        fi
    fi
    
    # Use sips to convert and set icon (macOS native method)
    if command -v sips > /dev/null 2>&1; then
        # Create iconset directory
        ICONSET_DIR="$APP_NAME.app/Contents/Resources/icon.iconset"
        mkdir -p "$ICONSET_DIR"
        
        # Generate all required icon sizes
        for size in 16 32 128 256 512 1024; do
            sips -z $size $size "$ICON_FILE" --out "$ICONSET_DIR/icon_${size}x${size}.png" > /dev/null 2>&1
            # Also create @2x versions
            sips -z $((size*2)) $((size*2)) "$ICON_FILE" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" > /dev/null 2>&1
        done
        
        # Create .icns file
        iconutil -c icns "$ICONSET_DIR" -o "$APP_NAME.app/Contents/Resources/icon.icns" 2>/dev/null
        
        # Set the icon using file attributes
        if [ -f "$APP_NAME.app/Contents/Resources/icon.icns" ]; then
            # Use Rez/DeRez or touch to trigger icon refresh
            touch "$APP_NAME.app"
            echo "✅ Applied icon to $APP_NAME.app"
        fi
    else
        echo "⚠️  sips not available, using basic icon file"
        touch "$APP_NAME.app"
    fi
}

# Apply icons
if [ -f "icons/start_server_icon.png" ]; then
    set_app_icon "Start YouTube Server" "icons/start_server_icon.png"
else
    echo "⚠️  Start server icon not found"
fi

if [ -f "icons/stop_server_icon.png" ]; then
    set_app_icon "Stop YouTube Server" "icons/stop_server_icon.png"
else
    echo "⚠️  Stop server icon not found"
fi

if [ -f "icons/restart_server_icon.png" ]; then
    set_app_icon "Restart YouTube Server" "icons/restart_server_icon.png"
else
    echo "⚠️  Restart server icon not found"
fi

echo ""
echo "✅ Icons applied!"
echo "💡 You may need to:"
echo "   1. Remove apps from Dock"
echo "   2. Re-add them to see the new icons"
echo "   3. Or restart Finder: killall Finder"


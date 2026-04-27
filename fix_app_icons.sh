#!/bin/bash

# Fix app icons using AppleScript with .icns files

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🎨 Setting app icons using .icns files..."

set_icon_applescript() {
    local APP_PATH="$1"
    local ICON_FILE="$2"
    
    if [ ! -d "$APP_PATH" ]; then
        echo "⚠️  $APP_PATH not found"
        return 1
    fi
    
    if [ ! -f "$ICON_FILE" ]; then
        echo "⚠️  Icon file $ICON_FILE not found"
        return 1
    fi
    
    # Convert to absolute paths
    APP_ABS=$(cd "$(dirname "$APP_PATH")" && pwd)/$(basename "$APP_PATH")
    ICON_ABS=$(cd "$(dirname "$ICON_FILE")" && pwd)/$(basename "$ICON_FILE")
    
    # Use AppleScript to set icon
    osascript << EOF
tell application "Finder"
    try
        set theApp to POSIX file "$APP_ABS" as alias
        set theIcon to POSIX file "$ICON_ABS" as alias
        set icon of theApp to theIcon
    on error errMsg
        return "Error: " & errMsg
    end try
end tell
EOF
    
    if [ $? -eq 0 ]; then
        echo "✅ Set icon for $(basename "$APP_PATH")"
        return 0
    else
        echo "❌ Failed to set icon for $(basename "$APP_PATH")"
        return 1
    fi
}

# Process each app using their .icns files
echo ""
echo "Processing Start YouTube Server..."
set_icon_applescript "Start YouTube Server.app" "Start YouTube Server.app/Contents/Resources/icon.icns"

echo ""
echo "Processing Stop YouTube Server..."
set_icon_applescript "Stop YouTube Server.app" "Stop YouTube Server.app/Contents/Resources/icon.icns"

echo ""
echo "Processing Restart YouTube Server..."
set_icon_applescript "Restart YouTube Server.app" "Restart YouTube Server.app/Contents/Resources/icon.icns"

echo ""
echo "🔄 Refreshing icon cache..."
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -kill -r -domain local -domain system -domain user 2>/dev/null

echo ""
echo "🔄 Restarting Dock and Finder..."
killall Dock 2>/dev/null
killall Finder 2>/dev/null

echo ""
echo "✅ Done! Icons should now appear."
echo "💡 Wait for Finder to restart, then check the apps in Finder."

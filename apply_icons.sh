#!/bin/bash

echo "🎨 Applying custom icons to command files..."

# Create temporary icon files from our PNGs
sips -s format icns icons/start_server_icon.png --out /tmp/start_icon.icns
sips -s format icns icons/stop_server_icon.png --out /tmp/stop_icon.icns

# Apply icons to the command files
sips -s format icns /tmp/start_icon.icns --out START_SERVER.command
sips -s format icns /tmp/stop_icon.icns --out STOP_SERVER.command

# Alternative method - copy the icon files directly
cp icons/start_server_icon.png START_SERVER.command/icon.png 2>/dev/null || echo "Icon method 1 failed"
cp icons/stop_server_icon.png STOP_SERVER.command/icon.png 2>/dev/null || echo "Icon method 2 failed"

echo "✅ Icons applied!"
echo ""
echo "📁 Your files are ready:"
echo "   - START_SERVER.command (Green play button)"
echo "   - STOP_SERVER.command (Red stop button)"
echo ""
echo "🚀 Drag these to your Dock - they should now show custom icons!"



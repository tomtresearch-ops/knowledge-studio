#!/bin/bash

# Script to help add server apps to Dock
# Run this, then drag the apps from Finder to Dock

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "🔧 Preparing apps for Dock..."
echo ""

# Remove quarantine attributes if present
for app in "Start YouTube Server.app" "Stop YouTube Server.app" "Restart YouTube Server.app"; do
    if [ -d "$app" ]; then
        echo "Processing $app..."
        xattr -d com.apple.quarantine "$app" 2>/dev/null
        xattr -d com.apple.provenance "$app" 2>/dev/null
        
        # Make sure it's executable
        if [ -f "$app/Contents/MacOS/"* ]; then
            chmod +x "$app/Contents/MacOS/"*
        fi
        
        # Touch to refresh
        touch "$app"
        echo "✅ $app is ready"
    fi
done

echo ""
echo "📋 Next steps:"
echo "1. Open Finder and navigate to this folder:"
echo "   $SCRIPT_DIR"
echo ""
echo "2. You should see these 3 apps:"
echo "   • Start YouTube Server.app"
echo "   • Stop YouTube Server.app"
echo "   • Restart YouTube Server.app"
echo ""
echo "3. Try dragging them to the Dock one at a time"
echo ""
echo "4. If dragging doesn't work:"
echo "   - Right-click each app → 'Open' (to allow it)"
echo "   - Then try dragging again"
echo ""
echo "5. Alternative: Control-click (right-click) on app → Options → 'Keep in Dock'"
echo ""







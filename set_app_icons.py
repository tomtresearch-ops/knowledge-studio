#!/usr/bin/env python3
"""
Set app icons using PyObjC (most reliable method on macOS)
"""

import os
import sys
from AppKit import NSWorkspace, NSImage

def set_app_icon(app_path, icon_path):
    """Set icon for an app bundle using PyObjC"""
    app_path = os.path.abspath(app_path)
    icon_path = os.path.abspath(icon_path)
    
    if not os.path.exists(app_path):
        print(f"❌ App not found: {app_path}")
        return False
    
    if not os.path.exists(icon_path):
        print(f"❌ Icon not found: {icon_path}")
        return False
    
    try:
        # Load the icon image
        icon_image = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if icon_image is None:
            print(f"❌ Failed to load icon: {icon_path}")
            return False
        
        # Set the icon using NSWorkspace
        workspace = NSWorkspace.sharedWorkspace()
        success = workspace.setIcon_forFile_options_(icon_image, app_path, 0)
        
        if success:
            print(f"✅ Set icon for {os.path.basename(app_path)}")
            return True
        else:
            print(f"❌ Failed to set icon for {os.path.basename(app_path)}")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    apps = [
        ("Start YouTube Server.app", "Start YouTube Server.app/Contents/Resources/icon.icns"),
        ("Stop YouTube Server.app", "Stop YouTube Server.app/Contents/Resources/icon.icns"),
        ("Restart YouTube Server.app", "Restart YouTube Server.app/Contents/Resources/icon.icns"),
    ]
    
    print("🎨 Setting app icons using PyObjC...\n")
    
    for app_name, icon_path in apps:
        print(f"Processing {app_name}...")
        set_app_icon(app_name, icon_path)
        print()
    
    print("✅ Done! Icons should now appear in Finder.")
    print("💡 If they don't show:")
    print("   1. Quit Finder (Cmd+Q)")
    print("   2. Reopen Finder")
    print("   3. Remove apps from Dock and re-add them")







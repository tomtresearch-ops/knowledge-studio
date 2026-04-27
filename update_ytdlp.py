#!/usr/bin/env python3
"""
Manual yt-dlp updater script
Run this to manually update yt-dlp to the latest version
"""

import subprocess
import sys

def update_ytdlp():
    """Update yt-dlp to the latest version"""
    print("🔍 Checking for yt-dlp updates...")
    
    try:
        # Check current version
        current_result = subprocess.run([sys.executable, '-c', 'import yt_dlp; print(yt_dlp.version.__version__)'], 
                                      capture_output=True, text=True)
        print(f"Current version: {current_result.stdout.strip()}")
        
        # Update yt-dlp
        print("📦 Updating yt-dlp...")
        update_result = subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade', 'yt-dlp'], 
                                     capture_output=True, text=True, timeout=120)
        
        if update_result.returncode == 0:
            print("✅ yt-dlp updated successfully!")
            
            # Check new version
            new_result = subprocess.run([sys.executable, '-c', 'import yt_dlp; print(yt_dlp.version.__version__)'], 
                                      capture_output=True, text=True)
            print(f"New version: {new_result.stdout.strip()}")
        else:
            print(f"❌ Update failed: {update_result.stderr}")
            
    except Exception as e:
        print(f"❌ Error updating yt-dlp: {e}")

if __name__ == "__main__":
    update_ytdlp()
















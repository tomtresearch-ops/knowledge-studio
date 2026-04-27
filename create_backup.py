#!/usr/bin/env python3
"""Create a backup of the current working state"""

import os
import shutil
from datetime import datetime

description = "cross_tab_window_tracking_channel_view_features_restart_button"
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = f"backups/{timestamp}_{description}"

print(f"🔄 Creating backup...")
print(f"📁 Backup location: {backup_dir}")

# Create backup directory
os.makedirs(backup_dir, exist_ok=True)

# Files to backup
files_to_backup = [
    "app.py",
    "youtube_processor.py", 
    "library.html",
    "channels.html",
    "debug.html",
    "interface.html",
    "stats.html",
    "youtube_intelligence.db"
]

# Copy files
print("📄 Copying core files...")
for file in files_to_backup:
    if os.path.exists(file):
        shutil.copy2(file, backup_dir)
        print(f"  ✓ {file}")
    else:
        print(f"  ⚠ {file} not found")

# Copy prompts directory
if os.path.exists("prompts"):
    print("📂 Copying prompts directory...")
    shutil.copytree("prompts", os.path.join(backup_dir, "prompts"), dirs_exist_ok=True)
    print(f"  ✓ prompts/")

# Create backup info
info_file = os.path.join(backup_dir, "BACKUP_INFO.txt")
with open(info_file, "w") as f:
    f.write(f"""YouTube Intelligence System Backup
Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Description: {description}

Files included:
- app.py (Flask backend)
- youtube_processor.py (Main processor)  
- library.html (Main UI)
- channels.html (Channels UI)
- debug.html, interface.html, stats.html (Supporting UI)
- youtube_intelligence.db (Database with all videos/summaries)
- prompts/ (All prompt templates)

Changes in this version:
- Cross-Tab Window Tracking:
  * localStorage heartbeat system for document windows
  * Document windows write heartbeat every 2.5 seconds
  * Library tabs read heartbeats to detect windows from other tabs
  * Automatic cleanup of stale entries (10 second timeout)
  * Combined window count display (local + cross-tab)
  * Real-time updates via storage events + polling fallback
- Channel View Document Window Features:
  * Added highlighting functionality (text selection → highlight button)
  * Added Copy Summary button
  * Added Quick Note button and modal
  * Full feature parity with library view document windows
- Server Restart Button:
  * Added Restart Server button in interface.html
  * Restart endpoint in app.py (stop then start)
  * Visual feedback during restart process
  * Polls for server to come back up
- Server Status Lock File Integration:
  * /api/server-status checks for Port Authority lock file
  * Browser start button checks starting status
  * Prevents race conditions between Port Authority and browser

To restore:
cp -r {backup_dir}/* .
python3 app.py
""")

print(f"\n✅ Backup completed successfully!")
print(f"📁 Location: {backup_dir}")
print(f"📊 Files backed up: {len(os.listdir(backup_dir))} items")




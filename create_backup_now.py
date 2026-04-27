#!/usr/bin/env python3
"""Create a backup of the current working state"""

import os
import shutil
from datetime import datetime

description = "article_processing_queue_tracking_duplicate_detection"
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
- Article processing improvements:
  * PDF support with pypdf library
  * Enhanced HTML content extraction with better selectors
  * Robust error handling and logging
  * Queue entry creation for article tracking (separate connection, non-blocking)
- Queue tracking fixes:
  * Articles now appear in Recent Processing sidebar
  * View Queue modal shows articles with 📄 icons
  * Refresh button works for Recent Processing
  * INSERT OR REPLACE for queue entries (handles duplicates gracefully)
- Duplicate detection for articles:
  * Checks for existing articles before processing
  * User confirmation dialog before reprocessing
  * force_reprocess flag to update existing articles
  * Prevents accidental overwrites
- Bookmarks feature (from Dec 17 backup):
  * Full implementation with expand/collapse
  * Highlights display in expanded bookmarks
  * 2-line card layout with domain-only URLs
- 3-prompt routing system (Interview, Tools/Workflows, Explainer)
- Enhanced YouTube bot detection bypass

NOTE: If article processing/queue tracking issues occur, the Dec 17 backup 
(20251217_001650_3_prompt_routing_bot_detection_bypass_removed_bookmarks) 
is the "gold standard" stable version with working bookmarks.

To restore:
cp -r {backup_dir}/* .
python3 app.py
""")

print(f"\n✅ Backup completed successfully!")
print(f"📁 Location: {backup_dir}")
print(f"📊 Files backed up: {len(os.listdir(backup_dir))} items")











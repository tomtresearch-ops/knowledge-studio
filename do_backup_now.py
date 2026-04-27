#!/usr/bin/env python3
import os
import shutil
from datetime import datetime

os.chdir('/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence')

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_dir = f"backups/{timestamp}_document_view_buttons_fixed_event_listeners"

print(f"Creating backup: {backup_dir}")
os.makedirs(backup_dir, exist_ok=True)

files_to_backup = [
    "app.py",
    "youtube_processor.py", 
    "library.html",
    "channels.html",
    "interface.html",
    "stats.html"
]

copied = []
for file in files_to_backup:
    if os.path.exists(file):
        shutil.copy2(file, backup_dir)
        copied.append(file)
        print(f"  ✓ {file}")

# Create backup info
with open(f"{backup_dir}/BACKUP_INFO.txt", "w") as f:
    f.write(f"""Document View Buttons Fixed - Event Listeners Implementation
Created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Files: {', '.join(copied)}

Changes:
- Document View Buttons Fixed (event listeners, syntax error fix)
- Transcript View Modal with search
- Highlight Button Fixes
""")

print(f"\n✅ Backup created: {backup_dir}")
print(f"📊 Files: {len(copied)}")

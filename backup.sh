#!/bin/bash
# YouTube Intelligence System - Quick Backup Script
# Usage: ./backup.sh [description]

# Get optional description from command line
DESCRIPTION=${1:-"working_state"}

# Create timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup directory name
BACKUP_DIR="backups/${TIMESTAMP}_${DESCRIPTION}"

echo "🔄 Creating backup..."
echo "📁 Backup location: $BACKUP_DIR"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Copy core files
echo "📄 Copying core files..."
cp app.py youtube_processor.py library.html debug.html interface.html stats.html youtube_intelligence.db "$BACKUP_DIR/"

# Copy prompts directory
echo "📂 Copying prompts directory..."
cp -r prompts "$BACKUP_DIR/"

# Create backup info file
echo "📝 Creating backup info..."
cat > "$BACKUP_DIR/BACKUP_INFO.txt" << EOF
YouTube Intelligence System Backup
Created: $(date)
Description: $DESCRIPTION

Files included:
- app.py (Flask backend)
- youtube_processor.py (Main processor)  
- library.html (Main UI)
- debug.html, interface.html, stats.html (Supporting UI)
- youtube_intelligence.db (Database with all videos/summaries)
- prompts/ (All prompt templates)

To restore:
cp -r $BACKUP_DIR/* .
python3 app.py
EOF

echo "✅ Backup completed successfully!"
echo "📁 Location: $BACKUP_DIR"
echo "📊 Files backed up: $(ls -1 "$BACKUP_DIR" | wc -l | tr -d ' ') items"
echo ""
echo "💡 To restore this backup later:"
echo "   cp -r $BACKUP_DIR/* ."
echo "   python3 app.py"

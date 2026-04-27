# Pre-Backup Test Checklist

## Critical Functionality Tests

### 1. Library Page
- [ ] Page loads without JavaScript errors
- [ ] Videos/articles display correctly
- [ ] Search and filters work
- [ ] Date display shows both published and processed dates

### 2. Document View
- [ ] Click "Doc View" button - opens in new window/tab
- [ ] "← Back to Library" button closes the window
- [ ] "✕ Close" button closes the window
- [ ] Text selection works (for highlighting)
- [ ] All action buttons work (Favorite, Quick Note, Copy Summary, View Video)

### 3. Modals
- [ ] Video summary modal opens and displays correctly
- [ ] Article summary modal opens and displays correctly
- [ ] "📝 Quick Note" button works in modals
- [ ] "⭐ Favorite" button works in modals
- [ ] "📋 Copy Summary" button works
- [ ] Close button works

### 4. Highlights Feature
- [ ] Can select text in document view
- [ ] Highlight button appears on selection
- [ ] Can save highlights with notes and tags
- [ ] Highlights appear in sidebar
- [ ] Can view highlights by category
- [ ] Can export highlights

### 5. Failed Videos Reprocessing
- [ ] Check the 4 previously failed videos
- [ ] They should now have proper summaries (not error messages)
- [ ] If still showing errors, they may need manual reprocessing

### 6. New Video Processing
- [ ] Drop a new screenshot/video URL
- [ ] Verify it processes with the new 5-minute timeout
- [ ] Summary generates successfully

## Quick Test Commands

```bash
# Check if background processor is running
ps aux | grep run_background

# Check recent logs
tail -20 logs/background.log

# Check database for failed videos
sqlite3 youtube_intelligence.db "SELECT COUNT(*) FROM videos WHERE ai_summary LIKE '%Summary generation error%'"
```

## If Everything Works
1. Create backup: `./backup.sh` or create timestamped backup folder
2. Document what was fixed in this version
3. Move forward with new features




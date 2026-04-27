# Mobile Knowledge Capture Setup

## Quick Setup Guide

### 1. Install Scriptable (iOS)
- Download **Scriptable** from the App Store (free)
- Open the app and tap the **+** button to create a new script

### 2. Add the Script
- Copy the contents of `knowledge_capture_scriptable.js`
- Paste into Scriptable
- Name it: **"Save to Knowledge Capture"**
- Tap the settings icon (sliders) → Enable **"Show in Share Sheet"**

### 3. Start the Watcher (Mac)
The watcher monitors your iCloud Drive folder and routes files to the right processing folders:

```bash
python3 scripts/icloud_to_screenshots_watcher.py \
  --source "~/Library/Mobile Documents/com~apple~CloudDocs/Knowledge Capture"
```

This will:
- Watch `Knowledge Capture` folder recursively
- Route images → `screenshots/` (YouTube processing)
- Route audio files → `audio_files/` (audio transcription)
- Route PDFs/text → `input/` (article processing)

### 4. Usage
1. Take a screenshot or save any file
2. Tap the thumbnail → **Share**
3. Tap **"Save to Knowledge Capture"** (your Scriptable script)
4. File syncs to iCloud → Mac watcher picks it up → Auto-processes!

## File Type Support

- **Images** (`.png`, `.jpg`, `.jpeg`, `.heic`, `.webp`) → YouTube screenshot processing
- **Audio** (`.m4a`, `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg`, `.m4b`) → Audio transcription + summary
- **PDFs** (`.pdf`) → Text extraction + article summary
- **Text** (`.txt`, `.md`) → Article processing

## Troubleshooting

- **Script not showing in Share Sheet**: Make sure "Show in Share Sheet" is enabled in Scriptable settings
- **Files not processing**: Check that the watcher is running and the Flask app is running
- **iCloud sync delay**: Files may take a few seconds to sync between devices






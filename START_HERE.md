# YouTube Intelligence System - Quick Start

## 🚀 How to Start the System

### Option 1: Complete System (Recommended)
```bash
./start_everything.sh
```
This starts both background processing AND web interface automatically.

### Option 2: Background Processing Only
```bash
./run_background.py
```
This runs the file monitoring and processing in the background (no web interface).

### Option 3: Web Interface Only
```bash
python3 app.py
```
This starts just the web interface (for viewing results).

## 📱 Access the System
- **Library**: http://localhost:5001/library
- **Interface**: http://localhost:5001

## 📸 How to Use
1. Drop screenshots into the `screenshots/` folder
2. The system will automatically process them
3. View results in the library at http://localhost:5001/library

## 🔧 What's Fixed
- ✅ No more duplicate entries
- ✅ Proper transcript extraction and storage
- ✅ Auto-restart functionality
- ✅ News roundup detection and routing
- ✅ Optimized prompts for different content types

## 🛑 To Stop
Press `Ctrl+C` in the terminal

## 📊 System Status
The system now:
- Prevents duplicate processing
- Stores clean transcripts (not raw JSON)
- Automatically detects content type (news/interview/genai_tools/crypto)
- Uses optimized prompts for each content type
- Handles errors gracefully

**The system should now work reliably without manual intervention!**

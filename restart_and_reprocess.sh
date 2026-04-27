#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Use Python 3.12 from venv if available, fallback to system python3
if [ -f "$SCRIPT_DIR/venv_py312/bin/python3" ]; then
    PYTHON_CMD="$SCRIPT_DIR/venv_py312/bin/python3"
else
    PYTHON_CMD="python3"
fi

echo "=== Stopping background processor ==="
pkill -f "run_background.py" 2>/dev/null
pkill -f "youtube_processor" 2>/dev/null
sleep 2

echo "=== Starting background processor ==="
nohup "$PYTHON_CMD" run_background.py > logs/background.log 2>&1 &
echo "Background processor started with PID: $!"

sleep 2

echo "=== Running reprocessing script ==="
"$PYTHON_CMD" reprocess_failed_videos.py

echo "=== Done ==="




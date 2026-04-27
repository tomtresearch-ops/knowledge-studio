#!/usr/bin/env python3
"""
Restart background processor and reprocess failed videos
"""

import os
import subprocess
import time
import sys

def main():
    print("=== Stopping background processor ===")
    try:
        subprocess.run(["pkill", "-f", "run_background.py"], check=False, capture_output=True)
        subprocess.run(["pkill", "-f", "youtube_processor"], check=False, capture_output=True)
        time.sleep(2)
        print("✓ Stopped any running processors")
    except Exception as e:
        print(f"Error stopping processors: {e}")

    print("\n=== Starting background processor ===")
    try:
        os.makedirs("logs", exist_ok=True)
        with open("logs/background.log", "a") as log_file:
            process = subprocess.Popen(
                [sys.executable, "run_background.py"],
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=os.getcwd()
            )
            print(f"✓ Background processor started with PID: {process.pid}")
            time.sleep(2)
    except Exception as e:
        print(f"Error starting processor: {e}")

    print("\n=== Running reprocessing script ===")
    try:
        from reprocess_failed_videos import reprocess_failed_videos
        reprocess_failed_videos()
    except Exception as e:
        print(f"Error running reprocessing: {e}")
        import traceback
        traceback.print_exc()

    print("\n=== Done ===")

if __name__ == "__main__":
    main()




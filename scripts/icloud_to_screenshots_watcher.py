#!/usr/bin/env python3
"""
Watch an iCloud Drive folder for new files and copy them into the app's
intake directories so they are picked up for processing.

Usage:
    python3 scripts/icloud_to_screenshots_watcher.py \
        --source "~/Library/Mobile Documents/com~apple~CloudDocs/Knowledge Capture" \
        --dest-screenshots "/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT/screenshots" \
        --dest-audio "/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT/audio_files" \
        --dest-articles "/Users/bossmdaddy/Desktop/screenshot-ai-claude rapid IT/input"

The script uses watchdog to monitor the source folder recursively for new files.
When a new file appears, it waits until the file is fully written, then copies it
to the appropriate destination based on file type.
"""

import argparse
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Set, Dict, Optional

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

IMAGE_EXTENSIONS: Set[str] = {'.png', '.jpg', '.jpeg', '.heic', '.webp'}
AUDIO_EXTENSIONS: Set[str] = {'.m4a', '.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4b'}
PDF_EXTENSIONS: Set[str] = {'.pdf'}
TEXT_EXTENSIONS: Set[str] = {'.txt', '.md'}

ALL_SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | PDF_EXTENSIONS | TEXT_EXTENSIONS


def get_file_type(path: Path) -> Optional[str]:
    """Determine file type based on extension. Returns 'image', 'audio', 'pdf', 'text', or None."""
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    elif ext in AUDIO_EXTENSIONS:
        return 'audio'
    elif ext in PDF_EXTENSIONS:
        return 'pdf'
    elif ext in TEXT_EXTENSIONS:
        return 'text'
    return None


def is_supported_file(path: Path) -> bool:
    return path.suffix.lower() in ALL_SUPPORTED_EXTENSIONS


def wait_for_complete_write(path: Path, timeout: float = 30.0, poll_interval: float = 0.5) -> bool:
    """
    Wait until the file stops growing or until timeout is reached.
    Returns True if the file appears stable, False otherwise.
    """
    deadline = time.time() + timeout
    previous_size = -1
    while time.time() < deadline:
        try:
            current_size = path.stat().st_size
        except FileNotFoundError:
            # File disappeared (maybe temporary). Wait briefly and retry.
            time.sleep(poll_interval)
            continue

        if current_size == previous_size and current_size > 0:
            return True

        previous_size = current_size
        time.sleep(poll_interval)

    return False


class KnowledgeCaptureHandler(FileSystemEventHandler):
    def __init__(self, destinations: Dict[str, Path]):
        self.destinations = destinations
        for dest in destinations.values():
            dest.mkdir(parents=True, exist_ok=True)

    def on_created(self, event: FileSystemEvent):
        if event.is_directory:
            return
        self._handle_path(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent):
        if event.is_directory:
            return
        self._handle_path(Path(event.dest_path))

    def _handle_path(self, path: Path):
        if not is_supported_file(path):
            return

        file_type = get_file_type(path)
        if not file_type:
            return

        # Map file types to destination folders
        type_to_dest = {
            'image': 'screenshots',
            'audio': 'audio',
            'pdf': 'articles',
            'text': 'articles'
        }
        dest_key = type_to_dest.get(file_type)
        if not dest_key or dest_key not in self.destinations:
            print(f"[watcher] no destination configured for {file_type} files")
            return

        destination = self.destinations[dest_key]
        print(f"[watcher] detected new {file_type} file: {path.name}")

        if not wait_for_complete_write(path):
            print(f"[watcher] timeout waiting for {path.name} to finish writing; skipping")
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        destination_name = f"{timestamp}_{path.name}"
        destination_path = destination / destination_name

        # Avoid overwriting by appending a counter if needed.
        counter = 1
        while destination_path.exists():
            destination_name = f"{timestamp}_{counter}_{path.name}"
            destination_path = destination / destination_name
            counter += 1

        try:
            shutil.copy2(path, destination_path)
            print(f"[watcher] copied {path.name} → {destination_path.name} ({file_type})")
        except Exception as exc:
            print(f"[watcher] error copying {path} → {destination_path}: {exc}")


def parse_args() -> argparse.Namespace:
    # Scriptable saves to its iCloud container, which appears as "Scriptable" folder in iCloud Drive
    default_source = os.path.expanduser(
        "~/Library/Mobile Documents/com~apple~CloudDocs/Scriptable/Knowledge Capture"
    )
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    parser = argparse.ArgumentParser(description="Watch an iCloud folder for new files (recursively).")
    parser.add_argument("--source", type=str, default=default_source,
                        help="Path to the iCloud folder to monitor (recursively).")
    parser.add_argument("--dest-screenshots", type=str,
                        default=os.path.join(base_dir, "screenshots"),
                        help="Path to the app's screenshots folder.")
    parser.add_argument("--dest-audio", type=str,
                        default=os.path.join(base_dir, "audio_files"),
                        help="Path to the app's audio files folder.")
    parser.add_argument("--dest-articles", type=str,
                        default=os.path.join(base_dir, "input"),
                        help="Path to the app's articles/PDFs folder.")
    return parser.parse_args()


def main():
    args = parse_args()
    source_path = Path(os.path.expanduser(args.source)).resolve()
    
    destinations = {
        'screenshots': Path(os.path.expanduser(args.dest_screenshots)).resolve(),
        'audio': Path(os.path.expanduser(args.dest_audio)).resolve(),
        'articles': Path(os.path.expanduser(args.dest_articles)).resolve()
    }

    if not source_path.exists():
        print(f"[watcher] source folder does not exist: {source_path}")
        sys.exit(1)

    print(f"[watcher] monitoring (recursive): {source_path}")
    for key, dest in destinations.items():
        print(f"[watcher] {key} destination: {dest}")

    event_handler = KnowledgeCaptureHandler(destinations)
    observer = Observer()
    observer.schedule(event_handler, str(source_path), recursive=True)  # Recursive!
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[watcher] stopping…")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()


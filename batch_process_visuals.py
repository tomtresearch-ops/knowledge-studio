#!/usr/bin/env python3
"""
Batch Visual Processor — Process screenshots folder sequentially.

Routes each image:
- YouTube screenshots → video processing queue (existing pipeline)
- Everything else → visual_processor (OCR classification + extraction)

Usage:
    python batch_process_visuals.py                    # process screenshots/ folder
    python batch_process_visuals.py /path/to/folder    # process specific folder
    python batch_process_visuals.py --dry-run           # show what would be processed
"""

import os
import sys
import sqlite3
import argparse
from datetime import datetime

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(__file__))

import visual_processor
import youtube_processor as processor

DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'youtube_intelligence.db')
SCREENSHOTS_FOLDER = os.path.join(os.path.dirname(__file__), 'screenshots')

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff'}


def get_processed_filenames():
    """Get set of filenames already processed (in visual_captures or videos)."""
    processed = set()
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()

    # Visual captures
    try:
        cursor.execute('SELECT filename FROM visual_captures')
        for row in cursor.fetchall():
            processed.add(row[0])
    except sqlite3.OperationalError:
        pass  # table doesn't exist yet

    conn.close()
    return processed


def process_folder(folder_path, dry_run=False):
    """Process all images in a folder sequentially."""
    if not os.path.isdir(folder_path):
        print(f"Error: {folder_path} is not a directory")
        return

    # Ensure visual_captures table exists
    visual_processor.ensure_table(DATABASE_PATH)

    # Get already-processed filenames
    processed = get_processed_filenames()

    # Find image files
    all_files = sorted(os.listdir(folder_path))
    image_files = [f for f in all_files if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS]

    print(f"Found {len(image_files)} images in {folder_path}")
    print(f"Already processed: {len(processed & set(image_files))}")

    to_process = [f for f in image_files if f not in processed]
    print(f"To process: {len(to_process)}")

    if dry_run:
        for f in to_process[:20]:
            print(f"  Would process: {f}")
        if len(to_process) > 20:
            print(f"  ... and {len(to_process) - 20} more")
        est_cost = len(to_process) * 0.02
        print(f"\nEstimated cost: ${est_cost:.2f} ({len(to_process)} images x ~$0.02)")
        return

    # Process sequentially
    stats = {'youtube': 0, 'visual': 0, 'skipped': 0, 'errors': 0, 'total_cost': 0.0}

    for i, filename in enumerate(to_process, 1):
        filepath = os.path.join(folder_path, filename)
        print(f"\n[{i}/{len(to_process)}] {filename}")

        try:
            # Step 1: Check if it's a YouTube screenshot
            metadata = processor.extract_video_metadata(filepath)

            if metadata and metadata.get('is_youtube', False):
                video_url = processor.find_youtube_video(metadata)
                if video_url:
                    # Check for duplicates
                    conn = sqlite3.connect(DATABASE_PATH)
                    cursor = conn.cursor()
                    cursor.execute('SELECT id FROM videos WHERE video_url = ?', (video_url,))
                    existing = cursor.fetchone()
                    conn.close()

                    if existing:
                        print(f"  YouTube (duplicate, video #{existing[0]})")
                        stats['skipped'] += 1
                    else:
                        queue_item = processor.add_video_to_queue(
                            video_url=video_url,
                            title=metadata.get('title', ''),
                            channel_name=metadata.get('channel', ''),
                            force=True
                        )
                        print(f"  YouTube → queued (#{queue_item['id']})")
                        stats['youtube'] += 1
                else:
                    print(f"  YouTube detected but no URL found, processing as visual")
                    result = visual_processor.process_visual_capture(
                        filepath, source_context='batch_import', db_path=DATABASE_PATH
                    )
                    stats['visual'] += 1
                    stats['total_cost'] += result['estimated_cost']
            else:
                # Not YouTube → OCR classification + extraction
                result = visual_processor.process_visual_capture(
                    filepath, source_context='batch_import', db_path=DATABASE_PATH
                )
                stats['visual'] += 1
                stats['total_cost'] += result['estimated_cost']

        except Exception as e:
            print(f"  ERROR: {e}")
            stats['errors'] += 1

    # Summary
    print(f"\n{'=' * 50}")
    print(f"Batch processing complete")
    print(f"  YouTube queued: {stats['youtube']}")
    print(f"  Visual captures: {stats['visual']}")
    print(f"  Skipped (dupes): {stats['skipped']}")
    print(f"  Errors: {stats['errors']}")
    print(f"  Total cost: ${stats['total_cost']:.4f}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Batch process screenshots')
    parser.add_argument('folder', nargs='?', default=SCREENSHOTS_FOLDER,
                        help='Folder to process (default: screenshots/)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be processed without doing it')
    args = parser.parse_args()

    process_folder(args.folder, dry_run=args.dry_run)

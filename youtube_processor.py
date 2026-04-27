#!/usr/bin/env python3
"""
YouTube Intelligence Processor - Consumption-optimized brief generation
Monitors folder for screenshots, extracts video metadata, processes transcripts, generates briefs
"""

import os
import time
import sqlite3
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
import threading
from urllib.parse import urlparse, parse_qs
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import base64
import re
import xml.etree.ElementTree as ET
from typing import Optional, Dict, List, Any, Tuple
import anthropic
from dotenv import load_dotenv



# Load environment variables
load_dotenv()

# Configuration
WATCH_FOLDER = "screenshots"  # Folder to monitor for new screenshots
DATABASE_PATH = "youtube_intelligence.db"
BATCH_DELAY_SECONDS = 5  # Quick processing for responsiveness
SUPPORTED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.webp'}

# API Configuration - Using environment variables
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

# Queue processing configuration (values favor reliability over speed)
QUEUE_IDLE_SLEEP_SECONDS = float(os.getenv("QUEUE_IDLE_SLEEP_SECONDS", "5"))
QUEUE_TRANSCRIPT_COOLDOWN_SECONDS = float(os.getenv("QUEUE_TRANSCRIPT_COOLDOWN_SECONDS", "12"))
QUEUE_POST_PROCESS_SLEEP_SECONDS = float(os.getenv("QUEUE_POST_PROCESS_SLEEP_SECONDS", "3"))
QUEUE_RATE_LIMIT_COOLDOWN_SECONDS = float(os.getenv("QUEUE_RATE_LIMIT_COOLDOWN_SECONDS", "900"))  # 15 minutes
QUEUE_CLAUDE_RETRY_COOLDOWN_SECONDS = float(os.getenv("QUEUE_CLAUDE_RETRY_COOLDOWN_SECONDS", "180"))  # 3 minutes
QUEUE_GENERAL_RETRY_COOLDOWN_SECONDS = float(os.getenv("QUEUE_GENERAL_RETRY_COOLDOWN_SECONDS", "300"))  # 5 minutes

def _iso_duration_to_seconds(duration: str) -> int:
    if not duration:
        return 0
    match = re.match(r'^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$', duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds

def _format_duration(seconds: int) -> str:
    if seconds <= 0:
        return ''
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"

def _parse_formatted_duration(duration_str: str) -> Optional[int]:
    """Parse formatted duration string (e.g., '1:23:45' or '45:30') to seconds"""
    if not duration_str:
        return None
    try:
        parts = duration_str.split(':')
        if len(parts) == 3:  # HH:MM:SS
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        elif len(parts) == 2:  # MM:SS
            minutes, seconds = map(int, parts)
            return minutes * 60 + seconds
        else:
            return None
    except (ValueError, AttributeError):
        return None
QUEUE_MIN_TRANSCRIPT_LENGTH = int(os.getenv("QUEUE_MIN_TRANSCRIPT_LENGTH", "2000"))

def _parse_view_count(view_str: str) -> Optional[int]:
    """Parse view count string (e.g., '1.2M views', '45,234 views', '1K') to integer"""
    if not view_str:
        return None
    try:
        # Clean the string
        view_str = view_str.lower().replace(',', '').replace(' views', '').replace(' view', '').strip()

        # Handle K, M, B suffixes
        multiplier = 1
        if view_str.endswith('k'):
            multiplier = 1000
            view_str = view_str[:-1]
        elif view_str.endswith('m'):
            multiplier = 1000000
            view_str = view_str[:-1]
        elif view_str.endswith('b'):
            multiplier = 1000000000
            view_str = view_str[:-1]

        # Parse the number
        return int(float(view_str) * multiplier)
    except (ValueError, AttributeError):
        return None

def generate_shortened_summary(claude_client, full_summary: str, target_percentage: int) -> str:
    """
    Generate a shortened version of a summary using Claude Haiku 4.5.
    
    Args:
        claude_client: The Anthropic client instance
        full_summary: The full summary text to shorten
        target_percentage: Target length as percentage (15, 30, or 50)
    
    Returns:
        The shortened summary text
    """
    if not full_summary or len(full_summary.strip()) < 100:
        return full_summary  # Return as-is if too short to shorten meaningfully
    
    if target_percentage == 15:
        target_length = "85% shorter (15% of original length)"
    elif target_percentage == 30:
        target_length = "70% shorter (30% of original length)"
    elif target_percentage == 50:
        target_length = "50% shorter"
    else:
        target_length = f"{100 - target_percentage}% shorter ({target_percentage}% of original length)"
    
    # Different prompts for different compression levels
    if target_percentage == 15:
        prompt = f"""Create a {target_length} version focused on SIGNAL and key takeaways.

PRIORITY ORDER (preserve in this order):
1. 🔮 SIGNAL section - ALL prediction bullets, trend shifts, and forward-looking statements (this is the MOST important)
2. Creator's personal discoveries or experiences
3. Bottom line / key takeaway
4. One-sentence "what this is about"

The 15% version is the entry point - it must capture the trend intelligence. Skip workflow details, specs, and generic explanations.

Format: Keep bullet structure from SIGNAL section. Each insight on its own line.

Original Summary:
{full_summary}"""
    elif target_percentage == 30:
        prompt = f"""Create a {target_length} version preserving signal and core content.

PRIORITY ORDER:
1. 🔮 SIGNAL section - ALL prediction bullets and forward-looking statements (MANDATORY - keep all)
2. What this covers + why it matters
3. Creator's key experiences/discoveries
4. Most important specifics (numbers, names, dates)
5. Bottom line

Remove: Exhaustive workflow steps, redundant explanations, generic context.

Original Summary:
{full_summary}"""
    else:
        prompt = f"""Create a {target_length} version that preserves all signal while condensing details.

MANDATORY - Preserve completely:
- 🔮 SIGNAL section (all prediction bullets, trends, forward-looking statements)
- Specific numbers, dates, and predictions with timeframes
- Creator's personal discoveries/experiences

Condense:
- Workflow steps (keep essential, cut exhaustive detail)
- Background context
- Redundant examples

Original Summary:
{full_summary}"""

    try:
        model = "claude-haiku-4-5-20251001"
        response = claude_client.messages.create(
            model=model,
            max_tokens=4000,  # Enough for shortened summaries
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text
    except Exception as e:
        print(f"⚠️ Error generating shortened summary ({target_percentage}%): {e}")
        return full_summary  # Return original on error

class YouTubeProcessor:
    def __init__(self):
        self.db_path = DATABASE_PATH
        self.claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self.init_database()
        self.pending_files = set()
        self.batch_timer = None
        self._queue_worker_stop_event = threading.Event()
        self._queue_worker_thread: Optional[threading.Thread] = None
        self._last_transcript_fetch_timestamp: float = 0.0
        self._start_queue_worker()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection with dict row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
        
    def init_database(self):
        """Initialize SQLite database with required tables"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Videos table (existing)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                screenshot_path TEXT NOT NULL,
                filename TEXT NOT NULL,
                video_url TEXT,
                title TEXT,
                channel TEXT,
                duration TEXT,
                full_transcript TEXT,
                ai_summary TEXT,
                key_insights TEXT,
                topics TEXT,
                processing_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confidence_score REAL,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # Detect legacy processing_queue schema and rebuild if needed
        cursor.execute("PRAGMA table_info(processing_queue)")
        existing_queue_columns = [row[1] for row in cursor.fetchall()]
        if existing_queue_columns and 'video_url' not in existing_queue_columns:
            print("⚠️  Legacy processing_queue table detected. Rebuilding to support video queue.")
            cursor.execute('DROP TABLE IF EXISTS processing_queue')
        
        # Processing queue table for auto processing
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processing_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT,
                video_url TEXT NOT NULL UNIQUE,
                title TEXT,
                channel_id TEXT,
                channel_name TEXT,
                thumbnail_url TEXT,
                published_at TIMESTAMP,
                status TEXT DEFAULT 'queued',
                processed_video_id INTEGER,
                priority INTEGER DEFAULT 0,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                transcript_length INTEGER,
                error_message TEXT,
                queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                next_attempt_at TIMESTAMP,
                last_error_at TIMESTAMP
            )
        ''')
        
        cursor.execute("PRAGMA table_info(processing_queue)")
        pq_columns = {row[1] for row in cursor.fetchall()}
        required_queue_columns = {
            'video_id': "ALTER TABLE processing_queue ADD COLUMN video_id TEXT",
            'processed_video_id': "ALTER TABLE processing_queue ADD COLUMN processed_video_id INTEGER",
            'priority': "ALTER TABLE processing_queue ADD COLUMN priority INTEGER DEFAULT 0",
            'retry_count': "ALTER TABLE processing_queue ADD COLUMN retry_count INTEGER DEFAULT 0",
            'max_retries': "ALTER TABLE processing_queue ADD COLUMN max_retries INTEGER DEFAULT 3",
            'transcript_length': "ALTER TABLE processing_queue ADD COLUMN transcript_length INTEGER",
            'error_message': "ALTER TABLE processing_queue ADD COLUMN error_message TEXT",
            'queued_at': "ALTER TABLE processing_queue ADD COLUMN queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            'started_at': "ALTER TABLE processing_queue ADD COLUMN started_at TIMESTAMP",
            'completed_at': "ALTER TABLE processing_queue ADD COLUMN completed_at TIMESTAMP",
            'next_attempt_at': "ALTER TABLE processing_queue ADD COLUMN next_attempt_at TIMESTAMP",
            'last_error_at': "ALTER TABLE processing_queue ADD COLUMN last_error_at TIMESTAMP"
        }
        for column_name, alter_sql in required_queue_columns.items():
            if column_name not in pq_columns:
                cursor.execute(alter_sql)
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_processing_queue_status
            ON processing_queue(status, priority, queued_at)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_processing_queue_next_attempt
            ON processing_queue(next_attempt_at)
        ''')
        
        # Queue control table (pause/resume state)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processing_queue_control (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_paused INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO processing_queue_control (id, is_paused)
            VALUES (1, 0)
        ''')
        
        # Channel subscription table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT NOT NULL UNIQUE,
                channel_name TEXT,
                channel_url TEXT,
                rss_url TEXT,
                uploads_playlist_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                enabled INTEGER DEFAULT 1
            )
        ''')
        cursor.execute("PRAGMA table_info(channel_subscriptions)")
        cs_columns = {row[1] for row in cursor.fetchall()}
        if 'uploads_playlist_id' not in cs_columns:
            cursor.execute('ALTER TABLE channel_subscriptions ADD COLUMN uploads_playlist_id TEXT')
        if 'auto_process' not in cs_columns:
            cursor.execute('ALTER TABLE channel_subscriptions ADD COLUMN auto_process INTEGER DEFAULT 0')
        
        # Channel videos metadata table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS channel_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id TEXT,
                channel_name TEXT,
                video_id TEXT NOT NULL UNIQUE,
                video_url TEXT NOT NULL,
                title TEXT,
                description TEXT,
                published_at TIMESTAMP,
                thumbnail_url TEXT,
                duration TEXT,
                processed INTEGER DEFAULT 0,
                processed_video_id INTEGER,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                FOREIGN KEY(processed_video_id) REFERENCES videos(id)
            )
        ''')
        cursor.execute("PRAGMA table_info(channel_videos)")
        cv_columns = {row[1] for row in cursor.fetchall()}
        if 'duration' not in cv_columns:
            cursor.execute('ALTER TABLE channel_videos ADD COLUMN duration TEXT')
        if 'processed_video_id' not in cv_columns:
            cursor.execute('ALTER TABLE channel_videos ADD COLUMN processed_video_id INTEGER')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_channel_videos_channel
            ON channel_videos(channel_id, published_at DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_channel_videos_processed
            ON channel_videos(processed)
        ''')
        
        # Person subscriptions table (for monitoring interviews with specific people)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS person_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_name TEXT NOT NULL UNIQUE,
                search_query TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP,
                enabled INTEGER DEFAULT 1
            )
        ''')
        
        # Person interviews table (tracks discovered interviews)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS person_interviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_subscription_id INTEGER NOT NULL,
                video_id TEXT NOT NULL UNIQUE,
                video_url TEXT NOT NULL,
                title TEXT,
                channel_name TEXT,
                channel_id TEXT,
                description TEXT,
                published_at TIMESTAMP,
                thumbnail_url TEXT,
                duration TEXT,
                duration_seconds INTEGER,
                view_count INTEGER,
                processed INTEGER DEFAULT 0,
                processed_video_id INTEGER,
                discovered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(person_subscription_id) REFERENCES person_subscriptions(id),
                FOREIGN KEY(processed_video_id) REFERENCES videos(id)
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_person_interviews_person
            ON person_interviews(person_subscription_id, published_at DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_person_interviews_processed
            ON person_interviews(processed)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_person_interviews_video_id
            ON person_interviews(video_id)
        ''')
        
        conn.commit()
        conn.close()
        print(f"Database initialized: {self.db_path}")

    def _update_video_details(self, video_ids: List[str]):
        if not video_ids or not YOUTUBE_API_KEY:
            return
        unique_ids = list({vid for vid in video_ids if vid})
        if not unique_ids:
            return
        api_url = "https://www.googleapis.com/youtube/v3/videos"
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            for i in range(0, len(unique_ids), 50):
                batch = unique_ids[i:i + 50]
                params = {
                    'part': 'contentDetails',
                    'id': ','.join(batch),
                    'key': YOUTUBE_API_KEY,
                    'maxResults': 50
                }
                resp = requests.get(api_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                for item in data.get('items', []):
                    video_id = item.get('id')
                    if not video_id:
                        continue
                    iso_duration = item.get('contentDetails', {}).get('duration')
                    seconds = _iso_duration_to_seconds(iso_duration)
                    
                    # Delete shorts (videos <= 3 minutes) that slipped through
                    if seconds > 0 and seconds <= 180:
                        cursor.execute('DELETE FROM channel_videos WHERE video_id = ?', (video_id,))
                        continue
                    
                    formatted = _format_duration(seconds)
                    cursor.execute(
                        '''
                        UPDATE channel_videos
                        SET duration = ?
                        WHERE video_id = ?
                        ''',
                        (formatted, video_id)
                    )
            conn.commit()
        finally:
            conn.close()

    def extract_video_id(self, video_url: str) -> Optional[str]:
        """Extract YouTube video ID from URL."""
        if not video_url:
            return None
        try:
            parsed = urlparse(video_url.strip())
            hostname = (parsed.hostname or '').lower()
            if hostname in {'youtu.be'}:
                return parsed.path.lstrip('/').split('?')[0]
            if 'youtube.com' in hostname:
                # Standard watch URL
                query = parse_qs(parsed.query)
                if 'v' in query and query['v']:
                    return query['v'][0]
                # Shorts, live, embed paths
                path_parts = [p for p in parsed.path.split('/') if p]
                if path_parts:
                    if path_parts[0] in {'shorts', 'live', 'embed'} and len(path_parts) > 1:
                        return path_parts[1]
                    return path_parts[-1]
        except Exception:
            return None
        return None

    def _dict_from_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return dict(row) if row is not None else {}

    def _start_queue_worker(self):
        """Ensure the background queue worker thread is running."""
        if self._queue_worker_thread and self._queue_worker_thread.is_alive():
            return
        self._queue_worker_stop_event.clear()
        self._queue_worker_thread = threading.Thread(
            target=self._queue_worker_loop,
            name="ProcessingQueueWorker",
            daemon=True
        )
        self._queue_worker_thread.start()
        print("🚚 Processing queue worker started")

    def add_video_to_queue(
        self,
        video_url: str,
        title: Optional[str] = None,
        channel_id: Optional[str] = None,
        channel_name: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        published_at: Optional[str] = None,
        priority: int = 0,
        max_retries: int = 10,
        force: bool = False
    ) -> Dict[str, Any]:
        """Add a video to the processing queue (or re-queue if it already exists).
        If force=False (default), skip videos already completed in queue or videos table.
        """
        if not video_url:
            raise ValueError("video_url is required")
        
        video_url = video_url.strip()
        video_id = self.extract_video_id(video_url)

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Skip if video already exists in videos table (fully processed) unless forced
            if not force:
                cursor.execute(
                    "SELECT id FROM videos WHERE video_url = ? AND status = 'completed'",
                    (video_url,)
                )
                if cursor.fetchone():
                    # Already fully processed — return existing queue item or empty
                    cursor.execute('SELECT * FROM processing_queue WHERE video_url = ?', (video_url,))
                    row = cursor.fetchone()
                    conn.close()
                    return self._dict_from_row(row) if row else {}

            cursor.execute(
                '''
                INSERT OR IGNORE INTO processing_queue (
                    video_url, video_id, title, channel_id, channel_name,
                    thumbnail_url, published_at, priority, status, retry_count,
                    max_retries, queued_at, next_attempt_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', 0, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ''',
                (
                    video_url, video_id, title, channel_id, channel_name,
                    thumbnail_url, published_at, priority, max_retries
                )
            )
            
            if cursor.rowcount == 0:
                # Row exists – check current status before updating
                cursor.execute('SELECT status FROM processing_queue WHERE video_url = ?', (video_url,))
                old_row = cursor.fetchone()
                old_status = old_row['status'] if old_row else None

                # Skip re-queuing completed/no_transcript items unless force=True
                # This prevents auto-processing from re-queuing already-done videos
                if not force and old_status in ('completed', 'no_transcript'):
                    conn.commit()
                    cursor.execute('SELECT * FROM processing_queue WHERE video_url = ?', (video_url,))
                    row = cursor.fetchone()
                    return self._dict_from_row(row) if row else {}

                # Allow re-queuing for failed/queued/processing or when forced
                cursor.execute(
                    '''
                    UPDATE processing_queue
                    SET
                        title = COALESCE(?, title),
                        channel_id = COALESCE(?, channel_id),
                        channel_name = COALESCE(?, channel_name),
                        thumbnail_url = COALESCE(?, thumbnail_url),
                        published_at = COALESCE(?, published_at),
                        priority = COALESCE(?, priority),
                        max_retries = COALESCE(?, max_retries),
                        status = CASE
                            WHEN status = 'processing' THEN 'processing'
                            ELSE 'queued'
                        END,
                        error_message = NULL,
                        retry_count = 0,
                        next_attempt_at = CURRENT_TIMESTAMP,
                        last_error_at = NULL,
                        started_at = NULL,
                        completed_at = NULL,
                        queued_at = CURRENT_TIMESTAMP
                    WHERE video_url = ?
                    ''',
                    (
                        title, channel_id, channel_name, thumbnail_url,
                        published_at, priority, max_retries, video_url
                    )
                )
                # Log if we reset a failed/completed item
                if cursor.rowcount > 0 and old_status and old_status in ('no_transcript', 'failed', 'completed'):
                    print(f"🔄 Re-queued video {video_id or video_url} (was: {old_status})")
                elif cursor.rowcount > 0 and old_status:
                    print(f"📝 Updated queue item for {video_id or video_url} (was: {old_status})")
            
            conn.commit()
            
            # Always return the queue item, whether it was inserted or updated
            cursor.execute('SELECT * FROM processing_queue WHERE video_url = ?', (video_url,))
            row = cursor.fetchone()
            if not row:
                # This shouldn't happen, but handle it gracefully
                raise ValueError(f"Failed to create or find queue item for {video_url}")
            return self._dict_from_row(row)
        finally:
            conn.close()

    def add_videos_to_queue(self, videos: List[Dict[str, Any]], force: bool = False) -> Dict[str, List[Dict[str, Any]]]:
        """Add multiple videos to the queue."""
        added: List[Dict[str, Any]] = []
        errors: List[Dict[str, Any]] = []
        for video in videos:
            try:
                video_url = video.get('video_url') or video.get('url')
                if not video_url:
                    errors.append({
                        "video_url": None,
                        "title": video.get('title'),
                        "error": "Missing video_url"
                    })
                    continue
                    
                queue_item = self.add_video_to_queue(
                    video_url=video_url,
                    title=video.get('title'),
                    channel_id=video.get('channel_id'),
                    channel_name=video.get('channel_name'),
                    thumbnail_url=video.get('thumbnail_url'),
                    published_at=video.get('published_at'),
                    priority=video.get('priority', 0),
                    max_retries=video.get('max_retries', 10),
                    force=force
                )
                # Always add to added list - even if it was already in queue (re-queued)
                added.append(queue_item)
            except Exception as exc:
                errors.append({
                    "video_url": video.get('video_url') or video.get('url'),
                    "title": video.get('title'),
                    "error": str(exc)
                })
                print(f"❌ Error adding video to queue: {video.get('title') or video.get('video_url')} - {exc}")
        return {"added": added, "errors": errors}

    def get_queue_items(self, status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Retrieve queue items with optional status filter."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            base_query = '''
                SELECT *
                FROM processing_queue
                WHERE (? IS NULL OR status = ?)
                ORDER BY
                    CASE status
                        WHEN 'processing' THEN 0
                        WHEN 'queued' THEN 1
                        WHEN 'pending_retry' THEN 2
                        WHEN 'completed' THEN 3
                        ELSE 4
                    END,
                    priority DESC,
                    queued_at ASC
            '''
            params: List[Any] = [status, status]
            if limit:
                base_query += ' LIMIT ?'
                params.append(limit)
            cursor.execute(base_query, params)
            rows = cursor.fetchall()
            return [self._dict_from_row(row) for row in rows]
        finally:
            conn.close()

    def get_queue_state(self) -> Dict[str, Any]:
        """Return queue pause state and counts by status."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT is_paused FROM processing_queue_control WHERE id = 1')
            control_row = cursor.fetchone()
            is_paused = bool(control_row['is_paused']) if control_row else False
            
            cursor.execute('SELECT status, COUNT(*) as count FROM processing_queue GROUP BY status')
            counts = {row['status']: row['count'] for row in cursor.fetchall()}
            
            return {
                "is_paused": is_paused,
                "counts": counts
            }
        finally:
            conn.close()

    def set_queue_paused(self, paused: bool) -> Dict[str, Any]:
        """Pause or resume the processing queue."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''
                UPDATE processing_queue_control
                SET is_paused = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                ''',
                (1 if paused else 0,)
            )
            conn.commit()
            return self.get_queue_state()
        finally:
            conn.close()

    def remove_queue_item(self, item_id: int) -> bool:
        """Remove an item from the queue if it's not processing."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT status FROM processing_queue WHERE id = ?', (item_id,))
            row = cursor.fetchone()
            if not row:
                return False
            if row['status'] == 'processing':
                raise ValueError("Cannot remove an item that is currently processing.")
            cursor.execute('DELETE FROM processing_queue WHERE id = ?', (item_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def retry_queue_item(self, item_id: int) -> Dict[str, Any]:
        """Reset a queue item to queued state for retry."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT * FROM processing_queue WHERE id = ?', (item_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Queue item not found.")
            if row['status'] == 'processing':
                raise ValueError("Cannot retry an item that is currently processing.")
            
            cursor.execute(
                '''
                UPDATE processing_queue
                SET status = 'queued',
                    retry_count = 0,
                    error_message = NULL,
                    next_attempt_at = CURRENT_TIMESTAMP,
                    last_error_at = NULL,
                    started_at = NULL,
                    completed_at = NULL
                WHERE id = ?
                ''',
                (item_id,)
            )
            conn.commit()
            cursor.execute('SELECT * FROM processing_queue WHERE id = ?', (item_id,))
            return self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()

    # ---------------------------
    # Channel subscription helpers
    # ---------------------------

    def _parse_channel_input(self, channel_input: str) -> Dict[str, Optional[str]]:
        value = (channel_input or '').strip()
        if not value:
            raise ValueError("Channel input cannot be empty.")
        parsed = urlparse(value) if value.startswith(('http://', 'https://')) else None
        channel_id = None
        handle = None
        username = None
        search_query = None
        if parsed:
            path_parts = [p for p in parsed.path.split('/') if p]
            if '@' in parsed.path:
                # Handle, e.g., /@channelname
                for part in path_parts:
                    if part.startswith('@'):
                        handle = part[1:]
                        break
            if len(path_parts) >= 2:
                if path_parts[0].lower() == 'channel':
                    channel_id = path_parts[1]
                elif path_parts[0].lower() == 'user':
                    username = path_parts[1]
                elif path_parts[0].lower() == 'c':
                    search_query = path_parts[1]
            if not any([channel_id, handle, username, search_query]):
                # Fallback to last path component or query
                if parsed.query:
                    qs = parse_qs(parsed.query)
                    if 'v' in qs and qs['v']:
                        # Video URL -> use channel context
                        search_query = qs['v'][0]
                if path_parts:
                    last_part = path_parts[-1]
                    if last_part.startswith('@'):
                        handle = last_part[1:]
                    else:
                        search_query = last_part
        else:
            if value.startswith('@'):
                handle = value[1:]
            elif value.startswith('UC') and len(value) >= 20:
                channel_id = value
            else:
                search_query = value
        return {
            "channel_id": channel_id,
            "handle": handle,
            "username": username,
            "search_query": search_query,
            "input_value": value
        }

    def _fetch_channel_metadata(self, channel_id: Optional[str], handle: Optional[str], username: Optional[str], search_query: Optional[str]) -> Dict[str, Any]:
        if not YOUTUBE_API_KEY:
            raise ValueError("YouTube API key is not configured.")
        base_url = "https://www.googleapis.com/youtube/v3/channels"
        params: Dict[str, Any] = {'part': 'snippet,contentDetails,statistics', 'key': YOUTUBE_API_KEY}
        response_data: Optional[Dict[str, Any]] = None
        resolved_channel_id: Optional[str] = None
        if channel_id:
            params['id'] = channel_id
            resp = requests.get(base_url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if data.get('items'):
                response_data = data['items'][0]
                resolved_channel_id = response_data['id']
        if response_data is None:
            query = handle or username or search_query
            if not query:
                raise ValueError("Unable to resolve channel. Please provide a valid channel URL, ID, or handle.")
            search_url = "https://www.googleapis.com/youtube/v3/search"
            search_params = {
                'part': 'snippet',
                'type': 'channel',
                'q': query,
                'maxResults': 1,
                'key': YOUTUBE_API_KEY
            }
            resp = requests.get(search_url, params=search_params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            if not data.get('items'):
                raise ValueError(f"Channel not found for input: {query}")
            resolved_channel_id = data['items'][0]['id']['channelId']
            params = {'part': 'snippet,contentDetails,statistics', 'id': resolved_channel_id, 'key': YOUTUBE_API_KEY}
            resp = requests.get(base_url, params=params, timeout=15)
            resp.raise_for_status()
            channel_data = resp.json()
            if not channel_data.get('items'):
                raise ValueError("Unable to fetch channel details.")
            response_data = channel_data['items'][0]
        snippet = response_data['snippet']
        resolved_channel_id = response_data['id']
        custom_url = snippet.get('customUrl')
        channel_title = snippet.get('title') or 'Unknown Channel'
        channel_url = f"https://www.youtube.com/channel/{resolved_channel_id}"
        if custom_url:
            channel_url = f"https://www.youtube.com/{custom_url}"
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={resolved_channel_id}"
        uploads_playlist_id = response_data.get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
        statistics = response_data.get('statistics', {})
        subscriber_count = int(statistics.get('subscriberCount', 0)) if statistics.get('subscriberCount') else None
        return {
            "channel_id": resolved_channel_id,
            "channel_name": channel_title,
            "channel_url": channel_url,
            "rss_url": rss_url,
            "uploads_playlist_id": uploads_playlist_id,
            "custom_url": custom_url,
            "description": snippet.get('description', ''),
            "thumbnails": snippet.get('thumbnails', {}),
            "subscriber_count": subscriber_count,
        }

    def search_interviews_by_person(self, person_name: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """Search YouTube for interviews with a specific person (as guest/interviewee)"""
        if not YOUTUBE_API_KEY:
            raise ValueError("YouTube API key is not configured.")
        
        # Build search query - prioritize interviews where person is the guest/interviewee
        # Use terms that indicate guest appearances rather than hosting
        # YouTube search doesn't support -exclude operator in API, so we'll filter results post-search
        search_query = f'"{person_name}" interview guest'
        
        search_url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            'part': 'snippet',
            'q': search_query,
            'type': 'video',
            'maxResults': min(max_results, 50),  # YouTube API max is 50 per request
            'order': 'relevance',
            'key': YOUTUBE_API_KEY
        }
        
        all_results = []
        page_token = None
        
        # Fetch multiple pages if needed
        while len(all_results) < max_results:
            if page_token:
                params['pageToken'] = page_token
            
            resp = requests.get(search_url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            
            items = data.get('items', [])
            if not items:
                break
            
            # Get video details (duration, etc.) in batch
            video_ids = [item['id']['videoId'] for item in items]
            videos_url = "https://www.googleapis.com/youtube/v3/videos"
            videos_params = {
                'part': 'contentDetails,snippet,statistics',
                'id': ','.join(video_ids),
                'key': YOUTUBE_API_KEY
            }
            videos_resp = requests.get(videos_url, params=videos_params, timeout=15)
            videos_resp.raise_for_status()
            videos_data = videos_resp.json()
            
            # Combine search results with video details
            for item in items:
                video_id = item['id']['videoId']
                snippet = item['snippet']
                
                # Find matching video details
                video_details = next((v for v in videos_data.get('items', []) if v['id'] == video_id), None)
                
                if video_details:
                    content_details = video_details.get('contentDetails', {})
                    duration_iso = content_details.get('duration', '')
                    duration_seconds = _iso_duration_to_seconds(duration_iso)
                    duration_formatted = _format_duration(duration_seconds)
                    
                    published_at = snippet.get('publishedAt', '')
                    # Parse ISO format to datetime (YouTube API returns ISO 8601 format)
                    published_dt = None
                    if published_at:
                        try:
                            # Try parsing ISO format: 2024-01-01T12:00:00Z
                            from datetime import datetime
                            # Handle different formats
                            if 'T' in published_at:
                                # Standard ISO format: 2024-01-01T12:00:00Z
                                if published_at.endswith('Z'):
                                    # Remove Z and parse
                                    published_str = published_at[:-1] + '+00:00'
                                    published_dt = datetime.fromisoformat(published_str)
                                elif '+' in published_at or '-' in published_at[-6:]:
                                    # Already has timezone
                                    published_dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                                else:
                                    # No timezone, assume UTC
                                    published_dt = datetime.fromisoformat(published_at + '+00:00')
                            else:
                                # Date only format: 2024-01-01
                                published_dt = datetime.strptime(published_at, '%Y-%m-%d')
                        except Exception as e:
                            # Fallback: try parsing date only
                            try:
                                from datetime import datetime
                                date_part = published_at.split('T')[0] if 'T' in published_at else published_at
                                published_dt = datetime.strptime(date_part, '%Y-%m-%d')
                            except Exception as e2:
                                # If all parsing fails, log and continue without date
                                print(f"⚠️  Could not parse published_at '{published_at}': {e}, {e2}")
                                published_dt = None
                    
                    # Convert datetime to string for database storage
                    published_at_str = None
                    if published_dt:
                        published_at_str = published_dt.isoformat()
                    elif published_at:
                        # Use original string if datetime parsing failed
                        published_at_str = published_at
                    
                    title = snippet.get('title', '')
                    channel_name = snippet.get('channelTitle', '')
                    
                    # Filter out videos where person is likely the host/interviewer or on their own show
                    # Check if channel name matches person name (likely their own show)
                    person_name_lower = person_name.lower()
                    channel_name_lower = channel_name.lower()
                    title_lower = title.lower()
                    
                    # Skip if channel name contains person's name (likely their own show/channel)
                    if person_name_lower in channel_name_lower or channel_name_lower in person_name_lower:
                        # But allow if title clearly indicates they're the guest (e.g., "Peter Diamandis on [Other Show]")
                        guest_indicators = [' on ', ' with ', ' guest', ' interviewed by', ' talks to ', ' speaks with ']
                        is_guest = any(indicator in title_lower for indicator in guest_indicators)
                        if not is_guest:
                            continue  # Skip - likely their own show
                    
                    # Skip if title suggests person is the interviewer/host
                    host_indicators = [
                        f'{person_name_lower} interviews',
                        f'{person_name_lower} talks to',
                        f'{person_name_lower} speaks with',
                        f'{person_name_lower} hosts',
                        f'{person_name_lower} presents',
                        f'{person_name_lower} show',
                        f'{person_name_lower} podcast',
                        f'{person_name_lower} episode'
                    ]
                    if any(title_lower.startswith(indicator) or f' {indicator}' in title_lower for indicator in host_indicators):
                        continue  # Skip - person is likely the host
                    
                    result = {
                        'video_id': video_id,
                        'video_url': f"https://www.youtube.com/watch?v={video_id}",
                        'title': title,
                        'channel_name': channel_name,
                        'channel_id': snippet.get('channelId', ''),
                        'description': snippet.get('description', ''),
                        'thumbnail_url': snippet.get('thumbnails', {}).get('high', {}).get('url', ''),
                        'published_at': published_at_str,
                        'published_datetime': published_at_str,
                        'duration': duration_formatted,
                        'duration_seconds': duration_seconds,
                        'view_count': int(video_details.get('statistics', {}).get('viewCount', 0))
                    }
                    all_results.append(result)
            
            # Check for next page
            page_token = data.get('nextPageToken')
            if not page_token or len(all_results) >= max_results:
                break
        
        return all_results[:max_results]

    def list_subscriptions(self) -> List[Dict[str, Any]]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT cs.*, COUNT(cv.id) AS video_count,
                       SUM(CASE WHEN cv.processed = 1 THEN 1 ELSE 0 END) AS processed_count,
                       MAX(cv.published_at) AS latest_video
                FROM channel_subscriptions cs
                LEFT JOIN channel_videos cv ON cv.channel_id = cs.channel_id
                GROUP BY cs.id
                ORDER BY cs.enabled DESC, cs.channel_name COLLATE NOCASE ASC
            ''')
            rows = cursor.fetchall()
            return [self._dict_from_row(row) for row in rows]
        finally:
            conn.close()

    def add_subscription(self, channel_input: str) -> Dict[str, Any]:
        parsed = self._parse_channel_input(channel_input)
        metadata = self._fetch_channel_metadata(
            parsed.get('channel_id'),
            parsed.get('handle'),
            parsed.get('username'),
            parsed.get('search_query')
        )
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''
                INSERT INTO channel_subscriptions (
                    channel_id, channel_name, channel_url, rss_url, uploads_playlist_id, enabled, subscriber_count
                ) VALUES (?, ?, ?, ?, ?, 1, ?)
                ON CONFLICT(channel_id) DO UPDATE SET
                    channel_name = excluded.channel_name,
                    channel_url = excluded.channel_url,
                    rss_url = excluded.rss_url,
                    uploads_playlist_id = excluded.uploads_playlist_id,
                    enabled = 1,
                    subscriber_count = excluded.subscriber_count
                ''',
                (
                    metadata['channel_id'],
                    metadata['channel_name'],
                    metadata['channel_url'],
                    metadata['rss_url'],
                    metadata.get('uploads_playlist_id'),
                    metadata.get('subscriber_count'),
                )
            )
            conn.commit()
            cursor.execute('SELECT * FROM channel_subscriptions WHERE channel_id = ?', (metadata['channel_id'],))
            subscription = self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()
        # Optionally refresh videos immediately
        try:
            self.refresh_subscription(subscription['id'], max_results=50)
        except Exception as e:
            print(f"⚠️  Could not refresh subscription immediately: {e}")
        return subscription

    def refresh_subscriber_counts(self) -> Dict[str, Any]:
        """Fetch and update subscriber counts for all subscribed channels, and snapshot to history."""
        from datetime import date
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, channel_id, channel_name FROM channel_subscriptions WHERE enabled = 1')
        channels = [dict(row) for row in cursor.fetchall()]
        updated = 0
        errors = []
        today = date.today().isoformat()
        # Batch fetch in groups of 50 (YouTube API limit)
        for i in range(0, len(channels), 50):
            batch = channels[i:i+50]
            ids = ','.join(ch['channel_id'] for ch in batch)
            try:
                resp = requests.get(
                    'https://www.googleapis.com/youtube/v3/channels',
                    params={'part': 'statistics', 'id': ids, 'key': YOUTUBE_API_KEY},
                    timeout=15
                )
                resp.raise_for_status()
                items = {item['id']: item for item in resp.json().get('items', [])}
                for ch in batch:
                    item = items.get(ch['channel_id'])
                    if item:
                        stats = item['statistics']
                        sub_count = int(stats.get('subscriberCount', 0))
                        total_views = int(stats.get('viewCount', 0))
                        cursor.execute(
                            'UPDATE channel_subscriptions SET subscriber_count = ? WHERE id = ?',
                            (sub_count, ch['id'])
                        )
                        # Write daily snapshot to history
                        cursor.execute('''
                            INSERT OR REPLACE INTO channel_stats_history
                            (channel_id, channel_name, subscriber_count, total_views, snapshot_date, source)
                            VALUES (?, ?, ?, ?, ?, 'youtube_api')
                        ''', (ch['channel_id'], ch['channel_name'], sub_count, total_views, today))
                        updated += 1
            except Exception as e:
                errors.append(str(e))
        conn.commit()
        conn.close()
        return {'updated': updated, 'total': len(channels), 'errors': errors}

    def import_subscriber_history(self, channel_name: str, history: list) -> Dict[str, Any]:
        """Import historical subscriber data (e.g. from Social Blade screenshots).

        Args:
            channel_name: Channel name to match against subscriptions
            history: List of dicts with 'date' (YYYY-MM-DD) and 'subscribers' (int)
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        # Find channel_id from subscriptions
        cursor.execute('SELECT channel_id FROM channel_subscriptions WHERE channel_name = ?', (channel_name,))
        row = cursor.fetchone()
        if not row:
            # Try case-insensitive
            cursor.execute('SELECT channel_id, channel_name FROM channel_subscriptions WHERE LOWER(channel_name) = LOWER(?)', (channel_name,))
            row = cursor.fetchone()
        channel_id = row['channel_id'] if row else channel_name.replace(' ', '_').lower()
        resolved_name = row['channel_name'] if row else channel_name
        imported = 0
        for entry in history:
            try:
                cursor.execute('''
                    INSERT OR REPLACE INTO channel_stats_history
                    (channel_id, channel_name, subscriber_count, snapshot_date, source)
                    VALUES (?, ?, ?, ?, 'socialblade')
                ''', (channel_id, resolved_name, entry['subscribers'], entry['date']))
                imported += 1
            except Exception:
                pass
        conn.commit()
        conn.close()
        return {'imported': imported, 'channel': resolved_name, 'channel_id': channel_id}

    def refresh_channel_video_views(self) -> Dict[str, Any]:
        """Batch-fetch view counts for all channel_videos from YouTube Data API."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, video_id FROM channel_videos WHERE video_id IS NOT NULL')
        all_videos = [dict(row) for row in cursor.fetchall()]
        updated = 0
        errors = []
        # Batch fetch in groups of 50
        for i in range(0, len(all_videos), 50):
            batch = all_videos[i:i+50]
            ids = ','.join(v['video_id'] for v in batch)
            try:
                resp = requests.get(
                    'https://www.googleapis.com/youtube/v3/videos',
                    params={'part': 'statistics', 'id': ids, 'key': YOUTUBE_API_KEY},
                    timeout=15
                )
                resp.raise_for_status()
                items = {item['id']: item for item in resp.json().get('items', [])}
                for v in batch:
                    item = items.get(v['video_id'])
                    if item:
                        view_count = int(item['statistics'].get('viewCount', 0))
                        cursor.execute(
                            'UPDATE channel_videos SET view_count = ? WHERE id = ?',
                            (view_count, v['id'])
                        )
                        updated += 1
            except Exception as e:
                errors.append(f"Batch {i}: {str(e)}")
        conn.commit()
        conn.close()
        return {'updated': updated, 'total': len(all_videos), 'errors': errors}

    def remove_subscription(self, subscription_id: int) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT channel_id FROM channel_subscriptions WHERE id = ?', (subscription_id,))
            row = cursor.fetchone()
            if not row:
                return False
            channel_id = row['channel_id']
            cursor.execute('DELETE FROM channel_subscriptions WHERE id = ?', (subscription_id,))
            cursor.execute('DELETE FROM channel_videos WHERE channel_id = ?', (channel_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def cleanup_shorts_from_subscriptions(self) -> Dict[str, Any]:
        """Remove all YouTube Shorts (<= 3 minutes) from channel_videos table"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get all video IDs from channel_videos
        cursor.execute('SELECT DISTINCT video_id FROM channel_videos')
        all_video_ids = [row['video_id'] for row in cursor.fetchall()]
        
        if not all_video_ids:
            conn.close()
            return {'removed': 0, 'checked': 0}
        
        shorts_to_remove = []
        checked_count = 0
        
        try:
            # Batch fetch durations (50 videos per request)
            for i in range(0, len(all_video_ids), 50):
                batch = all_video_ids[i:i + 50]
                api_url = "https://www.googleapis.com/youtube/v3/videos"
                params = {
                    'part': 'contentDetails',
                    'id': ','.join(batch),
                    'key': YOUTUBE_API_KEY,
                    'maxResults': 50
                }
                resp = requests.get(api_url, params=params, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get('items', []):
                        video_id = item.get('id')
                        if not video_id:
                            continue
                        checked_count += 1
                        duration_iso = item.get('contentDetails', {}).get('duration', '')
                        if duration_iso:
                            duration_seconds = _iso_duration_to_seconds(duration_iso)
                            # Mark for removal if duration is 3 minutes or less
                            if duration_seconds > 0 and duration_seconds <= 180:
                                shorts_to_remove.append(video_id)
                else:
                    print(f"⚠️  API request failed with status {resp.status_code}")
        
        except Exception as e:
            print(f"⚠️  Error checking video durations: {e}")
            conn.close()
            return {'removed': 0, 'checked': checked_count, 'error': str(e)}
        
        # Delete shorts from channel_videos
        removed_count = 0
        if shorts_to_remove:
            try:
                for video_id in shorts_to_remove:
                    cursor.execute('DELETE FROM channel_videos WHERE video_id = ?', (video_id,))
                    removed_count += cursor.rowcount
                conn.commit()
            except Exception as e:
                print(f"⚠️  Error deleting shorts: {e}")
                conn.rollback()
        
        conn.close()
        return {
            'removed': removed_count,
            'checked': checked_count,
            'shorts_found': len(shorts_to_remove)
        }

    def toggle_subscription(self, subscription_id: int) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT enabled FROM channel_subscriptions WHERE id = ?', (subscription_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Subscription not found.")
            new_value = 0 if row['enabled'] else 1
            cursor.execute(
                'UPDATE channel_subscriptions SET enabled = ?, last_checked = NULL WHERE id = ?',
                (new_value, subscription_id)
            )
            conn.commit()
            cursor.execute('SELECT * FROM channel_subscriptions WHERE id = ?', (subscription_id,))
            return self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()

    def toggle_auto_process(self, subscription_id: int) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT auto_process FROM channel_subscriptions WHERE id = ?', (subscription_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Subscription not found.")
            new_value = 0 if row['auto_process'] else 1
            cursor.execute(
                'UPDATE channel_subscriptions SET auto_process = ? WHERE id = ?',
                (new_value, subscription_id)
            )
            conn.commit()
            cursor.execute('SELECT * FROM channel_subscriptions WHERE id = ?', (subscription_id,))
            return self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()

    def _sync_channel_video_processed_flags(self, channel_id: str):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''
                UPDATE channel_videos
                SET processed = 1,
                    processed_video_id = (
                        SELECT id FROM videos WHERE videos.video_url = channel_videos.video_url LIMIT 1
                    )
                WHERE channel_id = ? AND processed = 0
                      AND EXISTS (
                          SELECT 1 FROM videos WHERE videos.video_url = channel_videos.video_url
                      )
                ''',
                (channel_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def refresh_subscription(
        self,
        subscription_id: int,
        max_results: Optional[int] = None,
        history_months: Optional[int] = None,
        history_max: Optional[int] = None
    ) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM channel_subscriptions WHERE id = ?', (subscription_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise ValueError("Subscription not found.")
        subscription = self._dict_from_row(row)
        rss_url = subscription.get('rss_url')
        channel_id = subscription.get('channel_id')
        channel_name = subscription.get('channel_name', '')
        if not rss_url and channel_id:
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        if not rss_url:
            raise ValueError("Could not determine RSS feed URL for channel.")
        
        try:
            resp = requests.get(rss_url, timeout=20)
            resp.raise_for_status()
        except Exception as e:
            raise ValueError(f"Failed to fetch channel feed: {e}")
        
        root = ET.fromstring(resp.content)
        namespace = {
            'atom': 'http://www.w3.org/2005/Atom',
            'yt': 'http://www.youtube.com/xml/schemas/2015',
            'media': 'http://search.yahoo.com/mrss/'
        }
        entries = root.findall('atom:entry', namespace)
        if max_results:
            entries = entries[:max_results]
        
        # First pass: collect all video data and filter out obvious shorts
        video_data_list = []
        video_ids_to_check = []
        for entry in entries:
            video_id_node = entry.find('yt:videoId', namespace)
            if video_id_node is None:
                continue
            video_id_value = video_id_node.text
            title_node = entry.find('atom:title', namespace)
            published_node = entry.find('atom:published', namespace)
            link_node = entry.find('atom:link', namespace)
            media_group = entry.find('media:group', namespace)
            description = ''
            thumbnail_url = None
            if media_group is not None:
                media_desc = media_group.find('media:description', namespace)
                if media_desc is not None and media_desc.text:
                    description = media_desc.text
                media_thumb = media_group.find('media:thumbnail', namespace)
                if media_thumb is not None:
                    thumbnail_url = media_thumb.attrib.get('url')
            video_title = title_node.text if title_node is not None else ''
            published_at = None
            if published_node is not None and published_node.text:
                published_at = published_node.text
            video_url = link_node.attrib.get('href') if link_node is not None else f"https://www.youtube.com/watch?v={video_id_value}"
            
            # Skip YouTube Shorts (URLs containing /shorts/)
            if '/shorts/' in video_url.lower():
                continue
            
            # Collect video data and IDs for batch duration check
            video_data_list.append({
                'video_id': video_id_value,
                'title': video_title,
                'description': description,
                'published_at': published_at,
                'video_url': video_url,
                'thumbnail_url': thumbnail_url
            })
            video_ids_to_check.append(video_id_value)
        
        # Batch fetch durations and view counts
        shorts_video_ids = set()
        video_view_counts = {}
        if video_ids_to_check:
            try:
                # Batch API calls (50 videos per request)
                for i in range(0, len(video_ids_to_check), 50):
                    batch = video_ids_to_check[i:i + 50]
                    api_url = "https://www.googleapis.com/youtube/v3/videos"
                    params = {
                        'part': 'contentDetails,statistics',
                        'id': ','.join(batch),
                        'key': YOUTUBE_API_KEY,
                        'maxResults': 50
                    }
                    resp = requests.get(api_url, params=params, timeout=15)
                    if resp.status_code == 200:
                        data = resp.json()
                        for item in data.get('items', []):
                            video_id = item.get('id')
                            if not video_id:
                                continue
                            duration_iso = item.get('contentDetails', {}).get('duration', '')
                            if duration_iso:
                                duration_seconds = _iso_duration_to_seconds(duration_iso)
                                # Mark as short if duration is 3 minutes or less
                                if duration_seconds > 0 and duration_seconds <= 180:
                                    shorts_video_ids.add(video_id)
                            # Capture view count for later storage
                            stats = item.get('statistics', {})
                            vc = stats.get('viewCount')
                            if vc:
                                video_view_counts[video_id] = int(vc)
            except Exception as e:
                # If API call fails, continue anyway (better to include than exclude)
                # The _update_video_details will clean it up later
                print(f"⚠️  Could not batch-check video durations: {e}")
        
        # Second pass: insert only non-short videos
        conn = self._get_connection()
        cursor = conn.cursor()
        new_videos = 0
        updated_videos = 0
        rss_video_ids: List[str] = []
        new_video_ids: List[str] = []
        try:
            for video_data in video_data_list:
                video_id_value = video_data['video_id']
                
                # Skip shorts that we identified
                if video_id_value in shorts_video_ids:
                    continue
                
                vc = video_view_counts.get(video_id_value)
                cursor.execute(
                    '''
                    INSERT INTO channel_videos (
                        channel_id, channel_name, video_id, video_url, title,
                        description, published_at, thumbnail_url, view_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_id) DO UPDATE SET
                        title = excluded.title,
                        description = excluded.description,
                        published_at = excluded.published_at,
                        thumbnail_url = excluded.thumbnail_url,
                        channel_name = excluded.channel_name,
                        view_count = COALESCE(excluded.view_count, channel_videos.view_count)
                    ''',
                    (
                        channel_id,
                        channel_name,
                        video_data['video_id'],
                        video_data['video_url'],
                        video_data['title'],
                        video_data['description'],
                        video_data['published_at'],
                        video_data['thumbnail_url'],
                        vc
                    )
                )
                if cursor.rowcount == 1:
                    new_videos += 1
                    new_video_ids.append(video_data['video_id'])
                else:
                    updated_videos += 1
                rss_video_ids.append(video_data['video_id'])
            cursor.execute(
                'UPDATE channel_subscriptions SET last_checked = CURRENT_TIMESTAMP WHERE id = ?',
                (subscription_id,)
            )
            conn.commit()
        finally:
            conn.close()
        self._sync_channel_video_processed_flags(channel_id)
        if rss_video_ids:
            try:
                self._update_video_details(rss_video_ids)
            except Exception as e:
                print(f"⚠️  Unable to update video durations (RSS batch): {e}")
        historical_stats = {}
        if history_months or history_max:
            try:
                historical_stats = self._fetch_channel_uploads_history(
                    subscription,
                    history_months=history_months,
                    history_max=history_max
                )
                new_videos += historical_stats.get('inserted', 0)
                updated_videos += historical_stats.get('updated', 0)
            except Exception as e:
                print(f"⚠️  Historical fetch failed: {e}")
        # Auto-process new videos if channel has auto_process enabled
        auto_queued = 0
        if subscription.get('auto_process') and new_video_ids:
            try:
                self.add_channel_videos_to_queue_by_ids(new_video_ids, priority=10)
                auto_queued = len(new_video_ids)
                print(f"⚡ Auto-queued {auto_queued} new videos from {channel_name} for processing (priority=10)")
            except Exception as e:
                print(f"⚠️  Auto-process queue failed for {channel_name}: {e}")

        return {
            "subscription": subscription,
            "inserted": new_videos,
            "updated": updated_videos,
            "total_entries": len(entries),
            "historical": historical_stats,
            "auto_queued": auto_queued
        }

    def _fetch_channel_uploads_history(
        self,
        subscription: Dict[str, Any],
        history_months: Optional[int],
        history_max: Optional[int]
    ) -> Dict[str, Any]:
        playlist_id = subscription.get('uploads_playlist_id')
        if not playlist_id:
            raise ValueError("Channel does not expose an uploads playlist. Try re-adding the subscription.")
        if not YOUTUBE_API_KEY:
            raise ValueError("YouTube API key is not configured.")
        cutoff_datetime: Optional[datetime] = None
        if history_months and history_months > 0:
            cutoff_datetime = datetime.utcnow() - timedelta(days=history_months * 30)
        api_url = "https://www.googleapis.com/youtube/v3/playlistItems"
        page_token = None
        fetched = 0
        inserted = 0
        updated = 0
        stop_fetching = False
        history_video_ids: List[str] = []
        while not stop_fetching:
            params = {
                'part': 'snippet,contentDetails',
                'playlistId': playlist_id,
                'maxResults': 50,
                'key': YOUTUBE_API_KEY
            }
            if page_token:
                params['pageToken'] = page_token
            resp = requests.get(api_url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            items = data.get('items', [])
            if not items:
                break
            conn = self._get_connection()
            cursor = conn.cursor()
            try:
                for entry in items:
                    snippet = entry.get('snippet', {})
                    content_details = entry.get('contentDetails', {})
                    video_id = content_details.get('videoId') or snippet.get('resourceId', {}).get('videoId')
                    if not video_id:
                        continue
                    
                    # Skip YouTube Shorts - check if it's in the shorts playlist or has short duration
                    # Shorts are typically <= 3 minutes, but we'll also check the video URL pattern
                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    if '/shorts/' in video_url.lower():
                        continue
                    
                    # Check duration if available in contentDetails
                    duration_iso = content_details.get('duration', '')
                    if duration_iso:
                        duration_seconds = _iso_duration_to_seconds(duration_iso)
                        # Skip if duration is 3 minutes or less (typical Shorts length)
                        if duration_seconds > 0 and duration_seconds <= 180:
                            continue
                    
                    published_at = content_details.get('videoPublishedAt') or snippet.get('publishedAt')
                    published_dt = None
                    if published_at:
                        try:
                            published_dt = datetime.strptime(published_at, '%Y-%m-%dT%H:%M:%SZ')
                        except ValueError:
                            published_dt = None
                    if cutoff_datetime and published_dt and published_dt < cutoff_datetime:
                        stop_fetching = True
                        continue
                    video_title = snippet.get('title') or ''
                    description = snippet.get('description') or ''
                    thumbnails = snippet.get('thumbnails', {})
                    thumbnail_url = None
                    if 'high' in thumbnails:
                        thumbnail_url = thumbnails['high'].get('url')
                    elif 'default' in thumbnails:
                        thumbnail_url = thumbnails['default'].get('url')
                    cursor.execute(
                        '''
                        INSERT INTO channel_videos (
                            channel_id, channel_name, video_id, video_url, title,
                            description, published_at, thumbnail_url
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(video_id) DO UPDATE SET
                            title = excluded.title,
                            description = excluded.description,
                            published_at = excluded.published_at,
                            thumbnail_url = excluded.thumbnail_url,
                            channel_name = excluded.channel_name
                        ''',
                        (
                            subscription['channel_id'],
                            subscription['channel_name'],
                            video_id,
                            video_url,
                            video_title,
                            description,
                            published_at,
                            thumbnail_url
                        )
                    )
                    if cursor.rowcount == 1:
                        inserted += 1
                    else:
                        updated += 1
                    fetched += 1
                    history_video_ids.append(video_id)
                    if history_max and fetched >= history_max:
                        stop_fetching = True
                        break
                conn.commit()
            finally:
                conn.close()
            page_token = data.get('nextPageToken')
            if not page_token or stop_fetching:
                break
        self._sync_channel_video_processed_flags(subscription['channel_id'])
        if history_video_ids:
            try:
                self._update_video_details(history_video_ids)
            except Exception as e:
                print(f"⚠️  Unable to update video durations (historical batch): {e}")
        return {
            "inserted": inserted,
            "updated": updated,
            "fetched": fetched,
            "history_months": history_months,
            "history_max": history_max
        }

    # ---------------------------
    # Person subscription methods
    # ---------------------------

    def list_person_subscriptions(self) -> List[Dict[str, Any]]:
        """List all person subscriptions"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                SELECT ps.*, COUNT(pi.id) AS interview_count,
                       SUM(CASE WHEN pi.processed = 1 THEN 1 ELSE 0 END) AS processed_count,
                       MAX(pi.published_at) AS latest_interview
                FROM person_subscriptions ps
                LEFT JOIN person_interviews pi ON pi.person_subscription_id = ps.id
                GROUP BY ps.id
                ORDER BY ps.enabled DESC, ps.person_name COLLATE NOCASE ASC
            ''')
            rows = cursor.fetchall()
            return [self._dict_from_row(row) for row in rows]
        finally:
            conn.close()

    def add_person_subscription(self, person_name: str) -> Dict[str, Any]:
        """Add a new person subscription"""
        # Use same query format as search_interviews_by_person for consistency
        search_query = f'"{person_name}" interview guest'
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''
                INSERT INTO person_subscriptions (person_name, search_query, enabled)
                VALUES (?, ?, 1)
                ON CONFLICT(person_name) DO UPDATE SET
                    enabled = 1,
                    search_query = excluded.search_query
                ''',
                (person_name, search_query)
            )
            conn.commit()
            cursor.execute('SELECT * FROM person_subscriptions WHERE person_name = ?', (person_name,))
            subscription = self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()
        # Optionally search for initial interviews immediately (but don't fail if this errors)
        try:
            self.refresh_person_subscription(subscription['id'], max_results=50)
        except Exception as e:
            # Log the error but don't fail the subscription creation
            import traceback
            print(f"⚠️  Could not refresh person subscription immediately: {e}")
            print(f"   Traceback: {traceback.format_exc()}")
            # Don't re-raise - subscription was created successfully
        return subscription

    def remove_person_subscription(self, subscription_id: int) -> bool:
        """Remove a person subscription"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('DELETE FROM person_subscriptions WHERE id = ?', (subscription_id,))
            cursor.execute('DELETE FROM person_interviews WHERE person_subscription_id = ?', (subscription_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def toggle_person_subscription(self, subscription_id: int) -> Dict[str, Any]:
        """Enable or disable a person subscription"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT enabled FROM person_subscriptions WHERE id = ?', (subscription_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError("Person subscription not found.")
            new_value = 0 if row['enabled'] else 1
            cursor.execute(
                'UPDATE person_subscriptions SET enabled = ?, last_checked = NULL WHERE id = ?',
                (new_value, subscription_id)
            )
            conn.commit()
            cursor.execute('SELECT * FROM person_subscriptions WHERE id = ?', (subscription_id,))
            return self._dict_from_row(cursor.fetchone())
        finally:
            conn.close()

    def refresh_person_subscription(
        self,
        subscription_id: int,
        max_results: Optional[int] = 50
    ) -> Dict[str, Any]:
        """Search for new interviews with a subscribed person"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM person_subscriptions WHERE id = ?', (subscription_id,))
        row = cursor.fetchone()
        conn.close()
        if not row:
            raise ValueError("Person subscription not found.")
        subscription = self._dict_from_row(row)
        if not subscription.get('enabled'):
            raise ValueError("Person subscription is disabled.")
        
        person_name = subscription['person_name']
        search_query = subscription.get('search_query', f'"{person_name}" interview')
        
        # Search for interviews
        try:
            results = self.search_interviews_by_person(person_name, max_results=max_results or 50)
        except Exception as e:
            raise ValueError(f"Failed to search for interviews: {str(e)}")
        
        # Store discovered interviews
        conn = self._get_connection()
        cursor = conn.cursor()
        new_interviews = 0
        updated_interviews = 0
        errors = []
        try:
            for result in results:
                try:
                    video_id = result['video_id']
                    # Get published_at as string, handling various formats
                    published_at_value = result.get('published_datetime') or result.get('published_at') or None
                    if published_at_value and isinstance(published_at_value, str):
                        # Ensure it's a valid string format for SQLite
                        published_at_value = published_at_value[:19] if len(published_at_value) > 19 else published_at_value
                    
                    cursor.execute(
                        '''
                        INSERT INTO person_interviews (
                            person_subscription_id, video_id, video_url, title,
                            channel_name, channel_id, description, published_at,
                            thumbnail_url, duration, duration_seconds, view_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(video_id) DO UPDATE SET
                            title = excluded.title,
                            channel_name = excluded.channel_name,
                            channel_id = excluded.channel_id,
                            description = excluded.description,
                            published_at = excluded.published_at,
                            thumbnail_url = excluded.thumbnail_url,
                            duration = excluded.duration,
                            duration_seconds = excluded.duration_seconds,
                            view_count = excluded.view_count
                        ''',
                        (
                            subscription_id,
                            video_id,
                            result['video_url'],
                            result.get('title', ''),
                            result.get('channel_name', ''),
                            result.get('channel_id', ''),
                            result.get('description', ''),
                            published_at_value,
                            result.get('thumbnail_url', ''),
                            result.get('duration', ''),
                            result.get('duration_seconds', 0),
                            result.get('view_count', 0)
                        )
                    )
                    if cursor.rowcount == 1:
                        new_interviews += 1
                    else:
                        updated_interviews += 1
                except Exception as e:
                    # Log error for this specific interview but continue with others
                    error_msg = f"Error storing interview {result.get('video_id', 'unknown')}: {str(e)}"
                    errors.append(error_msg)
                    print(f"⚠️  {error_msg}")
                    continue
            
            cursor.execute(
                'UPDATE person_subscriptions SET last_checked = CURRENT_TIMESTAMP WHERE id = ?',
                (subscription_id,)
            )
            conn.commit()
        finally:
            conn.close()
        
        # Sync processed flags
        self._sync_person_interview_processed_flags(subscription_id)
        
        result = {
            "subscription": subscription,
            "new_interviews": new_interviews,
            "updated_interviews": updated_interviews,
            "total_found": len(results)
        }
        if errors:
            result["errors"] = errors
            result["error_count"] = len(errors)
        
        return result

    def _sync_person_interview_processed_flags(self, person_subscription_id: int):
        """Update processed flags for person interviews based on videos table"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''
                UPDATE person_interviews
                SET processed = 1,
                    processed_video_id = (
                        SELECT id FROM videos WHERE videos.video_url = person_interviews.video_url LIMIT 1
                    )
                WHERE person_subscription_id = ? AND processed = 0
                      AND EXISTS (
                          SELECT 1 FROM videos WHERE videos.video_url = person_interviews.video_url
                      )
                ''',
                (person_subscription_id,)
            )
            conn.commit()
        finally:
            conn.close()

    def get_person_interviews(
        self,
        person_subscription_id: Optional[int] = None,
        processed: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        order: str = 'desc'
    ) -> Dict[str, Any]:
        """Get interviews for a person subscription"""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            order_clause = 'published_at DESC' if order.lower() == 'desc' else 'published_at ASC'
            query = '''
                SELECT pi.*, ps.person_name,
                       COALESCE(v.favorited, 0) AS favorited
                FROM person_interviews pi
                LEFT JOIN person_subscriptions ps ON ps.id = pi.person_subscription_id
                LEFT JOIN videos v ON v.id = pi.processed_video_id
                WHERE 1=1
            '''
            params: List[Any] = []
            if person_subscription_id:
                query += ' AND pi.person_subscription_id = ?'
                params.append(person_subscription_id)
            if processed is not None:
                query += ' AND pi.processed = ?'
                params.append(1 if processed else 0)
            query += f' ORDER BY {order_clause} LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            total_query = 'SELECT COUNT(*) FROM person_interviews pi WHERE 1=1'
            total_params: List[Any] = []
            if person_subscription_id:
                total_query += ' AND pi.person_subscription_id = ?'
                total_params.append(person_subscription_id)
            if processed is not None:
                total_query += ' AND pi.processed = ?'
                total_params.append(1 if processed else 0)
            cursor.execute(total_query, total_params)
            total_count = cursor.fetchone()[0]
            
            return {
                "total": total_count,
                "interviews": [self._dict_from_row(row) for row in rows]
            }
        finally:
            conn.close()

    def add_person_interviews_to_queue_by_ids(self, interview_ids: List[int]) -> Dict[str, Any]:
        """Add person interviews to processing queue by their IDs"""
        if not interview_ids:
            return {"added": [], "errors": [{"error": "No interview IDs provided."}]}
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            placeholders = ','.join('?' for _ in interview_ids)
            cursor.execute(f'''
                SELECT * FROM person_interviews
                WHERE id IN ({placeholders})
            ''', interview_ids)
            rows = cursor.fetchall()
            interviews = [self._dict_from_row(row) for row in rows]
        finally:
            conn.close()
        
        add_payload = []
        for interview in interviews:
            add_payload.append({
                'video_url': interview['video_url'],
                'title': interview.get('title'),
                'channel_id': interview.get('channel_id'),
                'channel_name': interview.get('channel_name'),
                'thumbnail_url': interview.get('thumbnail_url'),
                'published_at': interview.get('published_at')
            })
        result = self.add_videos_to_queue(add_payload)
        return result

    def monitor_person_subscriptions(
        self, 
        max_results_per_person: int = 20,
        check_interval_hours: int = 72,
        max_checks_per_run: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Monitor enabled person subscriptions for new interviews.
        Only checks people who are due (haven't been checked in check_interval_hours).
        Spreads checks out over time to avoid quota exhaustion.
        
        Args:
            max_results_per_person: Max interviews to fetch per person
            check_interval_hours: Hours between checks for each person (default 48)
            max_checks_per_run: Max people to check per run (None = check all due)
        """
        from datetime import datetime, timedelta
        
        subscriptions = self.list_person_subscriptions()
        enabled_subscriptions = [sub for sub in subscriptions if sub.get('enabled')]
        
        if not enabled_subscriptions:
            return {
                "checked": 0,
                "skipped": 0,
                "new_interviews": 0,
                "updated_interviews": 0,
                "errors": []
            }
        
        # Determine which subscriptions are due for checking
        now = datetime.utcnow()
        check_threshold = now - timedelta(hours=check_interval_hours)
        
        due_subscriptions = []
        skipped_subscriptions = []
        
        for sub in enabled_subscriptions:
            last_checked = sub.get('last_checked')
            if not last_checked:
                # Never checked - add to due list
                due_subscriptions.append(sub)
            else:
                try:
                    # Parse last_checked timestamp
                    if isinstance(last_checked, str):
                        last_checked_dt = datetime.fromisoformat(last_checked.replace('Z', '+00:00'))
                    else:
                        last_checked_dt = last_checked
                    
                    # Check if enough time has passed
                    if last_checked_dt < check_threshold:
                        due_subscriptions.append(sub)
                    else:
                        skipped_subscriptions.append(sub)
                except Exception as e:
                    # If we can't parse the timestamp, check it anyway
                    print(f"⚠️  Could not parse last_checked for {sub['person_name']}: {e}")
                    due_subscriptions.append(sub)
        
        # Limit how many we check per run to spread out API calls
        if max_checks_per_run and len(due_subscriptions) > max_checks_per_run:
            # Sort by last_checked (oldest first) to prioritize people who haven't been checked longest
            due_subscriptions.sort(key=lambda s: s.get('last_checked') or '1970-01-01')
            due_subscriptions = due_subscriptions[:max_checks_per_run]
            print(f"📊 {len(due_subscriptions)} people due, checking {max_checks_per_run} (oldest first)")
        
        if not due_subscriptions:
            return {
                "checked": 0,
                "skipped": len(skipped_subscriptions),
                "new_interviews": 0,
                "updated_interviews": 0,
                "errors": [],
                "message": f"All {len(skipped_subscriptions)} subscriptions checked recently (within {check_interval_hours}h)"
            }
        
        total_new = 0
        total_updated = 0
        errors = []
        
        print(f"🔍 Checking {len(due_subscriptions)} person subscription(s) (skipped {len(skipped_subscriptions)} recent checks)")
        
        for subscription in due_subscriptions:
            try:
                result = self.refresh_person_subscription(
                    subscription['id'],
                    max_results=max_results_per_person
                )
                total_new += result.get('new_interviews', 0)
                total_updated += result.get('updated_interviews', 0)
                print(f"✅ Checked {subscription['person_name']}: {result.get('new_interviews', 0)} new, {result.get('updated_interviews', 0)} updated")
            except Exception as e:
                error_msg = f"{subscription['person_name']}: {str(e)}"
                errors.append(error_msg)
                print(f"❌ Error checking {subscription['person_name']}: {e}")
        
        return {
            "checked": len(due_subscriptions),
            "skipped": len(skipped_subscriptions),
            "new_interviews": total_new,
            "updated_interviews": total_updated,
            "errors": errors
        }

    def get_channel_videos(
        self,
        channel_id: Optional[str] = None,
        processed: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
        order: str = 'desc',
        search_term: Optional[str] = None
    ) -> Dict[str, Any]:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            order_clause = 'published_at DESC' if order.lower() == 'desc' else 'published_at ASC'
            query = '''
                SELECT cv.*, cs.channel_name AS subscription_name,
                       COALESCE(v.favorited, 0) AS favorited,
                       COALESCE(cv.view_count, v.view_count) AS view_count
                FROM channel_videos cv
                LEFT JOIN channel_subscriptions cs ON cs.channel_id = cv.channel_id
                LEFT JOIN videos v ON v.id = cv.processed_video_id
                WHERE 1=1
            '''
            params: List[Any] = []
            if channel_id:
                query += ' AND cv.channel_id = ?'
                params.append(channel_id)
            if processed is not None:
                query += ' AND cv.processed = ?'
                params.append(1 if processed else 0)
            search_like = None
            if search_term:
                search_like = f'%{search_term}%'
                query += ' AND (cv.title LIKE ? OR cv.description LIKE ?)'
                params.extend([search_like, search_like])
            query += f' ORDER BY {order_clause} LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            cursor.execute(query, params)
            rows = cursor.fetchall()
            missing_duration_ids = [
                row['video_id']
                for row in rows
                if not row['duration']
            ]
            if missing_duration_ids:
                self._update_video_details(missing_duration_ids)
                cursor.execute(query, params)
                rows = cursor.fetchall()
            total_query = 'SELECT COUNT(*) FROM channel_videos cv WHERE 1=1'
            total_params: List[Any] = []
            if channel_id:
                total_query += ' AND cv.channel_id = ?'
                total_params.append(channel_id)
            if processed is not None:
                total_query += ' AND cv.processed = ?'
                total_params.append(1 if processed else 0)
            if search_like:
                total_query += ' AND (cv.title LIKE ? OR cv.description LIKE ?)'
                total_params.extend([search_like, search_like])
            cursor.execute(total_query, total_params)
            total_count = cursor.fetchone()[0]
            return {
                "total": total_count,
                "videos": [self._dict_from_row(row) for row in rows]
            }
        finally:
            conn.close()

    def add_channel_videos_to_queue_by_ids(self, video_ids: List[str], priority: int = 0) -> Dict[str, Any]:
        if not video_ids:
            return {"added": [], "errors": [{"error": "No video IDs provided."}]}
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            placeholders = ','.join('?' for _ in video_ids)
            cursor.execute(f'''
                SELECT * FROM channel_videos
                WHERE video_id IN ({placeholders})
            ''', video_ids)
            rows = cursor.fetchall()
            videos = [self._dict_from_row(row) for row in rows]
        finally:
            conn.close()
        # Check which video_ids were found vs requested
        found_video_ids = {video['video_id'] for video in videos}
        missing_video_ids = [vid for vid in video_ids if vid not in found_video_ids]
        
        add_payload = []
        for video in videos:
            add_payload.append({
                'video_url': video['video_url'],
                'title': video.get('title'),
                'channel_id': video.get('channel_id'),
                'channel_name': video.get('channel_name'),
                'thumbnail_url': video.get('thumbnail_url'),
                'published_at': video.get('published_at'),
                'priority': priority
            })
        result = self.add_videos_to_queue(add_payload)
        
        # Add information about missing videos
        if missing_video_ids:
            result['missing'] = missing_video_ids
            result['missing_count'] = len(missing_video_ids)
            print(f"⚠️  {len(missing_video_ids)} video(s) not found in channel_videos table: {missing_video_ids[:5]}")
        
        return result


    def _queue_is_paused(self) -> bool:
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT is_paused FROM processing_queue_control WHERE id = 1')
            row = cursor.fetchone()
            return bool(row['is_paused']) if row else False
        finally:
            conn.close()

    def _dequeue_next_queue_item(self) -> Optional[Dict[str, Any]]:
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute('BEGIN IMMEDIATE')
            cursor.execute(
                '''
                SELECT *
                FROM processing_queue
                WHERE status IN ('queued', 'pending_retry', 'deferred')
                  AND (next_attempt_at IS NULL OR next_attempt_at <= CURRENT_TIMESTAMP)
                ORDER BY priority DESC, queued_at ASC
                LIMIT 1
                '''
            )
            row = cursor.fetchone()
            if not row:
                conn.commit()
                return None
            item_id = row['id']
            
            # Also check for stuck "processing" items (status=processing but started_at is NULL or very old)
            # Reset them back to queued so they can be retried
            cursor.execute(
                '''
                UPDATE processing_queue
                SET status = 'queued',
                    started_at = NULL,
                    error_message = 'Reset: Was stuck in processing state',
                    retry_count = retry_count + 1,
                    next_attempt_at = CURRENT_TIMESTAMP
                WHERE status = 'processing'
                  AND (started_at IS NULL OR started_at < datetime('now', '-1 hour'))
                '''
            )
            
            cursor.execute(
                '''
                UPDATE processing_queue
                SET status = 'processing',
                    started_at = CURRENT_TIMESTAMP,
                    error_message = NULL
                WHERE id = ?
                ''',
                (item_id,)
            )
            conn.commit()
            item = self._dict_from_row(row)
            item['status'] = 'processing'
            return item
        except sqlite3.Error as exc:
            conn.rollback()
            print(f"❌ Error dequeuing item: {exc}")
            return None
        finally:
            conn.close()

    def _mark_queue_success(self, item: Dict[str, Any], transcript_length: int, processed_video_id: Optional[int], prompt_used: Optional[str]):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''
                UPDATE processing_queue
                SET status = 'completed',
                    completed_at = CURRENT_TIMESTAMP,
                    transcript_length = ?,
                    processed_video_id = ?,
                    error_message = NULL,
                    retry_count = 0,
                    next_attempt_at = NULL,
                    last_error_at = NULL
                WHERE id = ?
                ''',
                (transcript_length, processed_video_id, item['id'])
            )
            conn.commit()
        finally:
            conn.close()

    def _mark_queue_failure(
        self,
        item: Dict[str, Any],
        error_message: str,
        *,
        retry: bool,
        cooldown_seconds: Optional[float] = None,
        fatal_status: str = 'failed'
    ):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            current_retry = item.get('retry_count', 0) or 0
            max_retries = item.get('max_retries', 10) or 10
            should_retry = retry and (current_retry < max_retries)
            if should_retry:
                cooldown = cooldown_seconds or QUEUE_GENERAL_RETRY_COOLDOWN_SECONDS
                next_attempt_at = (datetime.utcnow() + timedelta(seconds=cooldown)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute(
                    '''
                    UPDATE processing_queue
                    SET status = 'pending_retry',
                        retry_count = retry_count + 1,
                        error_message = ?,
                        next_attempt_at = ?,
                        last_error_at = CURRENT_TIMESTAMP,
                        started_at = NULL
                    WHERE id = ?
                    ''',
                    (error_message, next_attempt_at, item['id'])
                )
            else:
                # Instead of marking as permanently failed, defer for 24-hour retry
                # This gives transient issues (rate limits, VPN, etc.) time to resolve
                deferred_retry_at = (datetime.utcnow() + timedelta(hours=24)).strftime('%Y-%m-%d %H:%M:%S')
                cursor.execute(
                    '''
                    UPDATE processing_queue
                    SET status = 'deferred',
                        error_message = ?,
                        retry_count = 0,
                        next_attempt_at = ?,
                        last_error_at = CURRENT_TIMESTAMP,
                        started_at = NULL
                    WHERE id = ?
                    ''',
                    (f"[Deferred] {error_message}", deferred_retry_at, item['id'])
                )
            conn.commit()
        finally:
            conn.close()

    def _update_channel_video_after_processing(self, queue_item: Dict[str, Any], processed_video_id: Optional[int]):
        video_id = queue_item.get('video_id')
        if not video_id:
            return
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''
                UPDATE channel_videos
                SET processed = 1,
                    processed_video_id = ?,
                    last_checked = CURRENT_TIMESTAMP
                WHERE video_id = ?
                ''',
                (processed_video_id, video_id)
            )
            conn.commit()
        finally:
            conn.close()
    
    def _update_person_interview_after_processing(self, queue_item: Dict[str, Any], processed_video_id: Optional[int]):
        """Update person_interviews table when a video is processed"""
        video_url = queue_item.get('video_url')
        if not video_url:
            return
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Update person_interviews where video_url matches
            cursor.execute(
                '''
                UPDATE person_interviews
                SET processed = 1,
                    processed_video_id = ?
                WHERE video_url = ? AND processed = 0
                ''',
                (processed_video_id, video_url)
            )
            conn.commit()
        finally:
            conn.close()

    def store_queue_processing_result(
        self,
        queue_item: Dict[str, Any],
        transcript: str,
        summary_text: str,
        prompt_used: Optional[str]
    ) -> int:
        """Store processed video results originating from the queue."""
        video_url = queue_item.get('video_url', '')
        placeholder_path = f"queue::{queue_item.get('video_id') or video_url}"
        title = queue_item.get('title') or ''
        channel_name = queue_item.get('channel_name') or ''
        
        # Get published_at and view_count from queue_item, or try to get it from channel_videos/API
        published_at = queue_item.get('published_at')
        view_count = queue_item.get('view_count')
        video_id = queue_item.get('video_id')

        if not published_at and video_id:
            conn_check = self._get_connection()
            cursor_check = conn_check.cursor()
            try:
                cursor_check.execute(
                    'SELECT published_at FROM channel_videos WHERE video_id = ?',
                    (video_id,)
                )
                row = cursor_check.fetchone()
                if row and row['published_at']:
                    published_at = row['published_at']
            finally:
                conn_check.close()

        # Fetch view_count from YouTube API if not available
        if not view_count and video_id and YOUTUBE_API_KEY:
            try:
                api_url = "https://www.googleapis.com/youtube/v3/videos"
                params = {
                    'part': 'statistics',
                    'id': video_id,
                    'key': YOUTUBE_API_KEY
                }
                resp = requests.get(api_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                items = data.get('items', [])
                if items and len(items) > 0:
                    statistics = items[0].get('statistics', {})
                    if statistics.get('viewCount'):
                        view_count = int(statistics['viewCount'])
            except Exception as e:
                print(f"⚠️  Could not fetch view_count from API: {e}")

        # Main summary is already ~50% length (prompts produce concise output directly)
        # Only need 1 shortening call: signal scan (30% of the 50% summary ≈ 15% of original)
        print(f"📝 Generating signal scan for video: {title}")
        summary_50 = summary_text  # Main summary IS the 50% version now
        summary_15 = generate_shortened_summary(self.claude_client, summary_text, 30)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Ensure published_at and summary columns exist
            cursor.execute("PRAGMA table_info(videos)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'published_at' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN published_at TIMESTAMP')
            if 'original_publish_date' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN original_publish_date TIMESTAMP')
            if 'summary_50' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN summary_50 TEXT')
            if 'summary_30' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN summary_30 TEXT')
            if 'summary_15' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN summary_15 TEXT')
            if 'view_count' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN view_count INTEGER')

            # Duplicate guard: check if this video_url already exists in videos table
            if video_url:
                cursor.execute('SELECT id FROM videos WHERE video_url = ?', (video_url,))
                existing = cursor.fetchone()
                if existing:
                    print(f"⚠️  Duplicate prevented: {title or video_url} already exists as video {existing[0]}")
                    conn.close()
                    return existing[0]

            cursor.execute(
                '''
                INSERT INTO videos (
                    screenshot_path, filename, video_url, title, channel,
                    full_transcript, ai_summary, summary_50, summary_30, summary_15, key_insights, topics,
                    confidence_score, status, prompt_used, published_at, original_publish_date, view_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    placeholder_path,
                    placeholder_path,
                    video_url,
                    title,
                    channel_name,
                    transcript,
                    summary_text,
                    summary_50,
                    '',  # summary_30 dropped to save API costs
                    summary_15,
                    '',
                    '',
                    1.0,
                    'completed',
                    prompt_used or '',
                    published_at,
                    published_at,  # Use same value for both fields
                    view_count
                )
            )
            video_record_id = cursor.lastrowid
            conn.commit()
            return video_record_id
        finally:
            conn.close()

    def _wait_for_transcript_window(self):
        now = time.time()
        elapsed = now - self._last_transcript_fetch_timestamp
        if elapsed < QUEUE_TRANSCRIPT_COOLDOWN_SECONDS:
            time.sleep(QUEUE_TRANSCRIPT_COOLDOWN_SECONDS - elapsed)

    def _is_rate_limit_error(self, error: Exception) -> bool:
        message = str(error).lower()
        keywords = [
            '429', 'too many requests', 'quota exceeded',
            'blocked', 'sign in to confirm you\'re not a bot',
            'file not accessible, likely 429'
        ]
        return any(keyword in message for keyword in keywords)

    def _process_queue_item(self, item: Dict[str, Any]):
        video_url = item.get('video_url')
        if not video_url:
            self._mark_queue_failure(item, "Missing video URL", retry=False)
            return
        
        title = item.get('title') or ''
        channel_name = item.get('channel_name') or ''
        print(f"🎯 Processing queued video: {title or video_url}")
        
        # Transcript extraction with rate limiting protection
        try:
            self._wait_for_transcript_window()
            transcript = self.get_transcript(video_url)
            self._last_transcript_fetch_timestamp = time.time()
        except Exception as exc:
            print(f"⚠️  Transcript error for {video_url}: {exc}")
            if self._is_rate_limit_error(exc):
                self._mark_queue_failure(item, f"Transcript rate limited: {exc}", retry=True, cooldown_seconds=QUEUE_RATE_LIMIT_COOLDOWN_SECONDS)
            else:
                self._mark_queue_failure(item, f"Transcript error: {exc}", retry=True, cooldown_seconds=QUEUE_GENERAL_RETRY_COOLDOWN_SECONDS)
            time.sleep(QUEUE_POST_PROCESS_SLEEP_SECONDS)
            return
        
        if not transcript:
            # Mark as no_transcript but allow retries - transcripts may become available later
            # or it might be a temporary issue (rate limiting, network, etc.)
            retry_count = item.get('retry_count', 0) or 0
            max_retries = item.get('max_retries', 10) or 10
            
            if retry_count < max_retries:
                # Retry with exponential backoff
                cooldown = QUEUE_GENERAL_RETRY_COOLDOWN_SECONDS * (2 ** min(retry_count, 2))
                self._mark_queue_failure(item, "No transcript available - will retry", retry=True, cooldown_seconds=cooldown)
                print(f"⏳ Will retry transcript fetch for {video_url} (attempt {retry_count + 1}/{max_retries})")
            else:
                # Only mark as fatal after all retries exhausted
                self._mark_queue_failure(item, "No transcript available after retries", retry=False, fatal_status='no_transcript')
                print(f"❌ No transcript available for {video_url} after {max_retries} attempts")
            time.sleep(QUEUE_POST_PROCESS_SLEEP_SECONDS)
            return
        
        transcript_length = len(transcript)
        if transcript_length < QUEUE_MIN_TRANSCRIPT_LENGTH:
            # Retry short transcripts - might be incomplete on first fetch
            retry_count = item.get('retry_count', 0) or 0
            max_retries = item.get('max_retries', 10) or 10
            
            if retry_count < max_retries:
                cooldown = QUEUE_GENERAL_RETRY_COOLDOWN_SECONDS * (2 ** min(retry_count, 2))
                self._mark_queue_failure(
                    item,
                    f"Transcript too short ({transcript_length} chars) - will retry",
                    retry=True,
                    cooldown_seconds=cooldown
                )
                print(f"⏳ Will retry short transcript for {video_url} (attempt {retry_count + 1}/{max_retries})")
            else:
                self._mark_queue_failure(
                    item,
                    f"Transcript too short ({transcript_length} chars) after retries",
                    retry=False,
                    fatal_status='no_transcript'
                )
            time.sleep(QUEUE_POST_PROCESS_SLEEP_SECONDS)
            return
        
        # Get duration from channel_videos if available
        duration_seconds = None
        video_id = item.get('video_id')
        if video_id:
            conn_dur = self._get_connection()
            cursor_dur = conn_dur.cursor()
            try:
                cursor_dur.execute('SELECT duration FROM channel_videos WHERE video_id = ?', (video_id,))
                row = cursor_dur.fetchone()
                if row and row['duration']:
                    duration_seconds = _parse_formatted_duration(row['duration'])
            finally:
                conn_dur.close()
        
        # Summarization
        try:
            summary_text, prompt_used = self.generate_summary(transcript, title, duration_seconds, published_at=item.get('published_at'))
        except Exception as exc:
            print(f"⚠️  Summarization error for {video_url}: {exc}")
            self._mark_queue_failure(item, f"Summarization error: {exc}", retry=True, cooldown_seconds=QUEUE_CLAUDE_RETRY_COOLDOWN_SECONDS)
            time.sleep(QUEUE_POST_PROCESS_SLEEP_SECONDS)
            return
        
        # Store results
        try:
            processed_video_id = self.store_queue_processing_result(item, transcript, summary_text, prompt_used)
            self._update_channel_video_after_processing(item, processed_video_id)
            self._update_person_interview_after_processing(item, processed_video_id)
            self._mark_queue_success(item, transcript_length, processed_video_id, prompt_used)
            print(f"✅ Queue processing complete: {title or video_url}")
        except Exception as exc:
            print(f"⚠️  Storage error for {video_url}: {exc}")
            self._mark_queue_failure(item, f"Storage error: {exc}", retry=True, cooldown_seconds=QUEUE_GENERAL_RETRY_COOLDOWN_SECONDS)
        finally:
            time.sleep(QUEUE_POST_PROCESS_SLEEP_SECONDS)

    def _reset_stale_processing_items(self, timeout_minutes: int = 30):
        """Reset items stuck in 'processing' for longer than timeout_minutes.
        This handles cases where the process died mid-run (lid close, internet drop, etc.)."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute(
                '''UPDATE processing_queue
                   SET status = 'queued', started_at = NULL, retry_count = retry_count,
                       error_message = 'Auto-reset: stale processing state',
                       next_attempt_at = CURRENT_TIMESTAMP
                   WHERE status = 'processing'
                     AND started_at < datetime('now', ? || ' minutes')''',
                (f'-{timeout_minutes}',)
            )
            reset_count = cursor.rowcount
            if reset_count > 0:
                conn.commit()
                print(f"♻️  Auto-reset {reset_count} stale processing item(s) (>{timeout_minutes}min old)")
            return reset_count
        finally:
            conn.close()

    def _queue_worker_loop(self):
        # On startup, reset any items stuck in 'processing' from a previous crashed session
        try:
            self._reset_stale_processing_items(timeout_minutes=30)
        except Exception as e:
            print(f"⚠️  Could not reset stale items: {e}")

        while not self._queue_worker_stop_event.is_set():
            try:
                if self._queue_is_paused():
                    time.sleep(QUEUE_IDLE_SLEEP_SECONDS)
                    continue

                # Periodically check for stale items (every loop iteration is cheap)
                try:
                    self._reset_stale_processing_items(timeout_minutes=30)
                except Exception:
                    pass

                item = self._dequeue_next_queue_item()
                if not item:
                    time.sleep(QUEUE_IDLE_SLEEP_SECONDS)
                    continue
                
                # Process the item - wrap in try/except to handle crashes
                try:
                    self._process_queue_item(item)
                except Exception as process_exc:
                    # If processing crashes, mark as failed and continue
                    print(f"❌ Error processing queue item {item.get('id')}: {process_exc}")
                    import traceback
                    traceback.print_exc()
                    try:
                        self._mark_queue_failure(
                            item,
                            f"Processing error: {str(process_exc)}",
                            retry=True,
                            cooldown_seconds=QUEUE_GENERAL_RETRY_COOLDOWN_SECONDS
                        )
                    except Exception as mark_exc:
                        print(f"❌ Error marking failure: {mark_exc}")
                    time.sleep(QUEUE_POST_PROCESS_SLEEP_SECONDS)
                    
            except Exception as exc:
                print(f"❌ Queue worker loop error: {exc}")
                import traceback
                traceback.print_exc()
                time.sleep(QUEUE_IDLE_SLEEP_SECONDS)

    def compress_image_if_needed(self, image_path: str) -> str:
        """Compress image if it's too large for Claude Vision API"""
        try:
            from PIL import Image

            img = Image.open(image_path)
            file_size = os.path.getsize(image_path)
            max_dimension = max(img.size)

            # Check if compression/resize is needed
            needs_resize = max_dimension > 7000  # Stay under 8000 limit
            needs_compress = file_size > 3.5 * 1024 * 1024  # base64 adds ~33%, must stay under 5MB encoded

            if not needs_resize and not needs_compress:
                return image_path

            print(f"Image size {file_size / (1024*1024):.1f}MB, dimensions {img.size}, processing...")

            # Resize if dimensions too large
            if needs_resize:
                ratio = 7000 / max_dimension
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                img = img.resize(new_size, Image.LANCZOS)
                print(f"Resized to {new_size}")

            # Convert RGBA to RGB (required for JPEG)
            if img.mode == 'RGBA':
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')

            quality = 85
            temp_path = image_path.rsplit('.', 1)[0] + '_compressed.jpg'

            while True:
                img.save(temp_path, format='JPEG', quality=quality, optimize=True)
                new_size = os.path.getsize(temp_path)

                if new_size <= 3.5 * 1024 * 1024 or quality <= 20:
                    break
                quality -= 10

            print(f"Compressed to {new_size / (1024*1024):.1f}MB at quality {quality}")
            return temp_path

        except ImportError:
            print("PIL not available, using original image")
            return image_path
        except Exception as e:
            print(f"Compression failed: {e}, using original")
            return image_path

    def extract_video_metadata(self, image_path: str) -> Optional[Dict]:
        """Extract video metadata from screenshot using Claude Vision"""
        try:
            # Compress if needed
            processed_path = self.compress_image_if_needed(image_path)
            
            # Read and encode image
            with open(processed_path, 'rb') as img_file:
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
            
            # Clean up temp file if created
            if processed_path != image_path:
                os.remove(processed_path)
            
            # Determine image type
            ext = Path(image_path).suffix.lower()
            media_type_map = {
                '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                '.png': 'image/png', '.heic': 'image/heic',
                '.webp': 'image/webp'
            }
            media_type = media_type_map.get(ext, 'image/jpeg')
            
            # Claude Vision API call using new library
            response = self.claude_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": """Analyze this image for YouTube video information. This may be a direct screenshot OR a phone photo of a TV/monitor showing YouTube.

Look for YouTube UI elements:
- Video title text (usually below or overlaid on the thumbnail)
- Channel name (below the title)
- View count and upload date
- YouTube player controls, progress bar, red play button
- YouTube thumbnail grid/recommended videos layout

IMPORTANT: Focus on the YouTube UI text (title, channel), NOT the content of the thumbnail image itself. A thumbnail showing "EVERYONE DIES" with a chart is not the video title — look for the actual title text in the YouTube interface below or near the thumbnail.

Respond ONLY with a JSON object:
{
    "title": "exact video title from YouTube UI",
    "channel": "channel name if visible",
    "views": "view count if visible",
    "timestamp": "upload date if visible",
    "confidence": 0.95,
    "is_youtube": true
}

Set "is_youtube": true if you can see ANY YouTube UI elements (title bar, channel, view count, player controls, thumbnail grid). Set false only if there are no YouTube elements at all."""
                            }
                        ]
                    }
                ]
            )
            
            # Extract content from new response format
            content = response.content[0].text
            
            # Clean response and parse JSON — handle extra text after JSON
            content = content.replace('```json', '').replace('```', '').strip()
            # Extract first JSON object if there's trailing text
            brace_count = 0
            json_end = 0
            for i, ch in enumerate(content):
                if ch == '{':
                    brace_count += 1
                elif ch == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_end = i + 1
                        break
            if json_end > 0:
                content = content[:json_end]
            metadata = json.loads(content)
            
            print(f"Extracted metadata: {metadata}")
            return metadata
                
        except Exception as e:
            print(f"Error extracting metadata from {image_path}: {e}")
            return None

    def find_youtube_video(self, metadata: Dict) -> Optional[str]:
        """Find YouTube video URL using extracted metadata"""
        if not metadata.get('is_youtube', False):
            print("Not a YouTube video screenshot")
            return None
            
        try:
            title = metadata.get('title', '')
            channel = metadata.get('channel', '')
            
            if not title:
                print("No title found in metadata")
                return None
            
            # YouTube search query
            search_query = f"{title}"
            if channel and channel.lower() not in ('unknown', 'unable to determine', 'not visible', ''):
                search_query += f" {channel}"
            
            # YouTube Data API search
            search_url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                'part': 'snippet',
                'q': search_query,
                'type': 'video',
                'maxResults': 5,
                'key': YOUTUBE_API_KEY
            }
            
            response = requests.get(search_url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                
                if items:
                    # Find best title match instead of blindly taking first result
                    best_match = None
                    best_score = 0
                    title_lower = title.lower()
                    title_words = set(title_lower.split())

                    for item in items:
                        item_title = item['snippet']['title'].lower()
                        item_words = set(item_title.split())
                        # Word overlap score
                        overlap = len(title_words & item_words)
                        score = overlap / max(len(title_words), 1)
                        # Bonus for substring match
                        if title_lower in item_title or item_title in title_lower:
                            score += 0.5
                        if score > best_score:
                            best_score = score
                            best_match = item

                    # Require at least 30% word overlap to accept
                    if best_match and best_score >= 0.3:
                        video_id = best_match['id']['videoId']
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        print(f"Found video: {video_url} (match score: {best_score:.2f})")
                        print(f"Title: {best_match['snippet']['title']}")
                        return video_url
                    else:
                        print(f"No good title match found (best score: {best_score:.2f})")
                        # Fall back to first result but log the mismatch
                        video_id = items[0]['id']['videoId']
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                        print(f"Using first result (weak match): {video_url}")
                        print(f"Title: {items[0]['snippet']['title']}")
                        return video_url
                else:
                    print("No videos found in search results")
                    return None
            else:
                print(f"YouTube API error: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error finding YouTube video: {e}")
            return None

    def get_transcript(self, video_url: str) -> Optional[str]:
        """Get video transcript. Tries youtube-transcript-api first (fast, anonymous),
        falls back to yt-dlp if needed."""
        import random
        import time
        import re as _re

        # Try youtube-transcript-api first — faster, no bot detection issues
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            vid_match = _re.search(r'(?:v=|/)([a-zA-Z0-9_-]{11})', video_url)
            if vid_match:
                video_id = vid_match.group(1)
                ytt = YouTubeTranscriptApi()
                transcript_segments = ytt.fetch(video_id)
                text = ' '.join(s.text for s in transcript_segments)
                if text and len(text) > 1000:
                    print(f"✅ Transcript via youtube-transcript-api: {len(text)} chars")
                    return text
                elif text:
                    print(f"⚠️ youtube-transcript-api returned short transcript ({len(text)} chars), trying yt-dlp...")
        except Exception as e:
            print(f"⚠️ youtube-transcript-api failed: {e}, trying yt-dlp...")

        # Fallback to yt-dlp with client rotation
        # Try client types in order of reliability
        # tv client is most reliable, android/ios are good fallbacks
        client_types = ['tv', 'android', 'ios', 'web']
        # Shuffle to avoid patterns, but prioritize tv
        client_order = ['tv'] + random.sample([c for c in client_types if c != 'tv'], len(client_types) - 1)
        
        for attempt, client_type in enumerate(client_order):
            try:
                import yt_dlp
                
                # Add delay between attempts to avoid rate limiting
                if attempt > 0:
                    delay = 3 + (attempt * 2)  # 3s, 5s, 7s, 9s
                    print(f"⏳ Waiting {delay}s before trying next client type...")
                    time.sleep(delay)
                
                # Build extractor args with multiple strategies
                extractor_args = {
                    'youtube': {
                        'player_client': [client_type],
                        'skip': ['dash', 'hls'],  # Skip video formats
                        'player_skip': ['webpage', 'configs'],  # Skip unnecessary player data
                    }
                }
                
                # Try with and without cookies - cookies can help but aren't required
                cookie_options = [None]  # Start without cookies
                
                # Check if cookies file exists (optional, user can add if needed)
                import os
                cookies_path = os.path.expanduser('~/.youtube_cookies.txt')
                if os.path.exists(cookies_path):
                    cookie_options.append(cookies_path)
                
                for cookies_file in cookie_options:
                    ydl_opts = {
                        'writesubtitles': True,
                        'writeautomaticsub': True,
                        'skip_download': True,
                        'quiet': False,
                        'no_warnings': False,
                        'extractor_retries': 3,
                        'fragment_retries': 3,
                        'retries': 3,
                        'sleep_interval': 3,  # Longer delays
                        'max_sleep_interval': 10,
                        'sleep_interval_subtitles': 3,
                        'extractor_args': extractor_args,
                        'referer': 'https://www.youtube.com/',
                        'socket_timeout': 30,
                    }
                    
                    if cookies_file:
                        ydl_opts['cookiefile'] = cookies_file
                        print(f"🔧 Attempt {attempt + 1}/{len(client_order)}: Using '{client_type}' client with cookies")
                    else:
                        print(f"🔧 Attempt {attempt + 1}/{len(client_order)}: Using '{client_type}' client (no cookies)")
                    
                    try:
                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            # Add random delay before request
                            time.sleep(random.uniform(1, 3))
                            
                            info = ydl.extract_info(video_url, download=False)
                            
                            # Check for subtitles
                            subtitles = info.get('subtitles', {})
                            auto_captions = info.get('automatic_captions', {})
                            
                            if subtitles or auto_captions:
                                print(f"   ✅ Found subtitles with '{client_type}' client")
                                print(f"   Available subtitles: {list(subtitles.keys())[:3]}...")
                                print(f"   Available auto_captions: {list(auto_captions.keys())[:3]}...")
                            
                            # Try to get subtitles
                            for source in [subtitles, auto_captions]:
                                for lang in ['en', 'en-US', 'en-GB', 'en-orig']:
                                    if lang in source and source[lang]:
                                        try:
                                            subtitle_info = source[lang][0]
                                            if 'url' in subtitle_info:
                                                import urllib.request
                                                # Add delay before fetching subtitle URL
                                                time.sleep(random.uniform(1, 2))
                                                
                                                # Create request with headers to mimic browser
                                                req = urllib.request.Request(
                                                    subtitle_info['url'],
                                                    headers={
                                                        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                                                        'Referer': 'https://www.youtube.com/',
                                                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                                                        'Accept-Language': 'en-US,en;q=0.9'
                                                    }
                                                )
                                                
                                                response = urllib.request.urlopen(req, timeout=30)
                                                subtitle_content = response.read().decode('utf-8')
                                                
                                                # Clean up subtitle content
                                                clean_content = self.clean_subtitle_content(subtitle_content)
                                                if clean_content and len(clean_content) > 1000:
                                                    print(f"✅ Transcript extracted with '{client_type}' client: {len(clean_content)} characters")
                                                    return clean_content
                                        except Exception as sub_error:
                                            print(f"   ⚠️ Error fetching subtitle URL: {sub_error}")
                                            continue
                            
                            # If we got info but no subtitles, this client type doesn't have them
                            if not subtitles and not auto_captions:
                                print(f"   ⚠️ No subtitles available with '{client_type}' client, trying next...")
                                break  # Try next client type
                            else:
                                # We got info but couldn't fetch the subtitle URL, try next client type
                                print(f"   ⚠️ Could not fetch subtitle content with '{client_type}' client, trying next...")
                                break
                                
                    except Exception as e:
                        error_msg = str(e).lower()
                        # If cookies failed, try without them (or vice versa)
                        if cookies_file and ('cookie' in error_msg or 'auth' in error_msg):
                            print(f"   ⚠️ Cookie error with '{client_type}' client, will try without cookies next")
                            continue
                        # Rate limit - wait longer and try next client
                        elif 'rate limit' in error_msg or '429' in error_msg or 'too many requests' in error_msg:
                            print(f"   ⚠️ Rate limited with '{client_type}' client, trying next...")
                            break
                        # Other errors - try next client type
                        else:
                            print(f"   ⚠️ Error with '{client_type}' client: {e}")
                            break
                        
            except Exception as e:
                error_msg = str(e).lower()
                print(f"   ⚠️ Fatal error with '{client_type}' client: {e}, trying next...")
                continue
        
        print(f"❌ No transcript available after trying all strategies")
        return None

    def clean_subtitle_content(self, subtitle_content: str) -> str:
        """Clean subtitle content to extract readable text"""
        try:
            import json
            import re
            
            # Check if it's JSON format (YouTube's internal format)
            if subtitle_content.strip().startswith('{'):
                try:
                    data = json.loads(subtitle_content)
                    text_parts = []
                    
                    # Extract text from YouTube's subtitle format
                    if 'events' in data:
                        for event in data['events']:
                            if 'segs' in event:
                                for seg in event['segs']:
                                    if 'utf8' in seg:
                                        text_parts.append(seg['utf8'])
                    
                    full_text = ''.join(text_parts)
                    # Clean up the text
                    full_text = re.sub(r'\s+', ' ', full_text)
                    return full_text.strip()
                    
                except json.JSONDecodeError:
                    # Fall back to VTT cleaning if not JSON
                    pass
            
            # Original VTT cleaning logic
            lines = subtitle_content.split('\n')
            text_lines = []
            
            for line in lines:
                line = line.strip()
                # Skip empty lines, timestamp lines, and VTT headers
                if (not line or 
                    line.startswith('WEBVTT') or 
                    '-->' in line or 
                    re.match(r'^\d+$', line) or
                    re.match(r'^\d{2}:\d{2}', line)):
                    continue
                
                # Remove HTML tags
                line = re.sub(r'<[^>]+>', '', line)
                
                if line:
                    text_lines.append(line)
            
            # Join and clean up
            full_text = ' '.join(text_lines)
            # Remove multiple spaces
            full_text = re.sub(r'\s+', ' ', full_text)
            
            return full_text.strip()
            
        except Exception as e:
            print(f"Error cleaning subtitle content: {e}")
            return subtitle_content

    def clean_transcript_for_summary(self, transcript: str) -> str:
        """Aggressively clean transcript to reduce size and improve quality"""
        import re
        import json
        
        # First, check if this is raw JSON subtitle data and extract text
        if transcript.strip().startswith('{'):
            try:
                data = json.loads(transcript)
                text_parts = []
                
                # Extract text from YouTube's subtitle format
                if 'events' in data:
                    for event in data['events']:
                        if 'segs' in event:
                            for seg in event['segs']:
                                if 'utf8' in seg:
                                    text_parts.append(seg['utf8'])
                
                # Join all text parts
                clean_text = ''.join(text_parts)
                print(f"📝 Extracted text from JSON: {len(clean_text)} characters")
                
            except json.JSONDecodeError:
                # If not JSON, treat as regular text
                clean_text = transcript
        else:
            # Regular text processing
            clean_text = transcript
        
        # Tier 1: Aggressive cleaning to reduce size
        # Remove timestamps and formatting
        clean_text = re.sub(r'\d{1,2}:\d{2}:\d{2}\.\d{3} --> \d{1,2}:\d{2}:\d{2}\.\d{3}', '', clean_text)
        clean_text = re.sub(r'\d{1,2}:\d{2}:\d{2} --> \d{1,2}:\d{2}:\d{2}', '', clean_text)
        clean_text = re.sub(r'\d{1,2}:\d{2}', '', clean_text)
        clean_text = re.sub(r'^\d+$', '', clean_text, flags=re.MULTILINE)
        
        # Remove repetitive content patterns
        clean_text = re.sub(r'(hey everybody|welcome back|thanks for watching|don\'t forget to|subscribe|like|comment).*?(?=\w)', '', clean_text, flags=re.IGNORECASE)
        clean_text = re.sub(r'(um|uh|ah|er|like|you know|basically|obviously|literally).*?(?=\w)', '', clean_text, flags=re.IGNORECASE)
        
        # Remove HTML tags and formatting
        clean_text = re.sub(r'<[^>]+>', '', clean_text)
        clean_text = re.sub(r'\[.*?\]', '', clean_text)  # Remove [music], [applause], etc.
        clean_text = re.sub(r'\(.*?\)', '', clean_text)  # Remove (laughs), (applause), etc.
        
        # Remove control characters
        clean_text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', clean_text)
        
        # Normalize whitespace and remove excessive repetition
        clean_text = re.sub(r'\s+', ' ', clean_text)
        clean_text = re.sub(r'(\w+)\1{3,}', r'\1', clean_text)  # Remove repeated words
        
        # Remove or escape problematic characters for JSON
        clean_text = clean_text.replace('"', "'")
        clean_text = clean_text.replace('\\', '')
        
        return clean_text.strip()
    
    def get_optimal_model_for_transcript(self, transcript: str) -> str:
        """Choose optimal model based on transcript size - 120k character threshold"""
        char_count = len(transcript)
        
        # Use Haiku 4.5 for all transcripts - matches Sonnet 4 quality at 1/3 the cost
        # Small cost increase for long transcripts (25%) but huge savings for normal ones (67%)
        return "claude-haiku-4-5-20251001"
    
    def chunk_transcript(self, transcript: str, max_chunk_size: int = 100000) -> list:
        """Split large transcript into chunks for processing"""
        if len(transcript) <= max_chunk_size:
            return [transcript]
        
        # Split by sentences to avoid breaking mid-thought
        sentences = transcript.split('. ')
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk + sentence) > max_chunk_size and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = sentence
            else:
                current_chunk += sentence + ". " if current_chunk else sentence + ". "
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks

    def detect_content_type(self, title: str, transcript: str, duration_seconds: Optional[int] = None) -> str:
        """Analyze title and transcript to categorize video content into 3 categories: interview, tools_workflows, or explainer"""
        import re
        
        title_lower = title.lower()
        transcript_sample = transcript[:2000].lower()  # First 2000 chars for analysis
        transcript_length = len(transcript)
        
        # ============================================
        # 1. INTERVIEW DETECTION
        # ============================================
        # Must have dialogue/Q&A indicators in transcript OR interview keywords in title
        # Duration boosts only apply if dialogue indicators are present
        
        # Check for speaker labels in transcript (strongest signal)
        speaker_labels = [
            'q:', 'a:', 'question:', 'answer:', 
            'host:', 'guest:', 'interviewer:', 'interviewee:',
            '[', ']'  # Some transcripts use [NAME]: format
        ]
        has_speaker_labels = any(marker in transcript_sample for marker in speaker_labels)
        
        # Check for interview keywords in title
        interview_title_keywords = [
            'interview', 'podcast', 'conversation', 'talks with', 'speaks with',
            'in conversation', 'chat with', 'q&a', 'qa', 'question and answer',
            'fireside chat', 'sit down', 'one on one', 'exclusive interview'
        ]
        has_interview_keywords = any(keyword in title_lower for keyword in interview_title_keywords)
        
        # Check for person name pattern in title (e.g., "Title | Person Name")
        person_name_patterns = [
            r'\|\s*[A-Z][a-z]+\s+[A-Z][a-z]+',  # "| Emad Mostaque"
            r'[A-Z][a-z]+\s+[A-Z][a-z]+\s+\|',  # "Emad Mostaque |"
            r'with\s+[A-Z][a-z]+\s+[A-Z][a-z]+',  # "with Emad Mostaque"
            r'w/\s+[A-Z][a-z]+\s+[A-Z][a-z]+',   # "w/ Emad Mostaque"
        ]
        has_person_name_in_title = any(re.search(pattern, title) for pattern in person_name_patterns)
        
        # Duration-based boost (only if dialogue indicators are present)
        duration_boost = 0
        if has_speaker_labels or has_interview_keywords or has_person_name_in_title:
            if duration_seconds:
                if duration_seconds >= 3600:  # 60+ minutes
                    duration_boost = 3
                elif duration_seconds >= 2700:  # 45+ minutes
                    duration_boost = 2
            elif transcript_length >= 40000:  # ~50+ minutes equivalent
                duration_boost = 2
            elif transcript_length >= 30000:  # ~40+ minutes equivalent
                duration_boost = 1
        
        # Interview = speaker labels OR interview keywords OR (person name + dialogue indicators)
        if has_speaker_labels or has_interview_keywords or (has_person_name_in_title and duration_boost > 0):
            print(f"✅ Selected: interview (speaker labels: {has_speaker_labels}, title keywords: {has_interview_keywords}, person name: {has_person_name_in_title}, duration boost: {duration_boost})")
            return 'interview'
        
        # ============================================
        # 2. TOOLS/WORKFLOWS DETECTION
        # ============================================
        # Strong tool signals (always count)
        strong_tool_keywords = [
            'midjourney', 'comfyui', 'comfy ui', 'runway', 'sora', 'elevenlabs', 
            'stable diffusion', 'replit', 'v0', 'cursor', 'bolt',
            'dalle', 'luma', 'kling', 'suno', 'whisper'
        ]
        
        # Tutorial/process language
        tutorial_keywords = [
            'tutorial', 'demo', 'guide', 'walkthrough', 'step-by-step', 'step by step',
            'how to', 'how-to', 'setup', 'install', 'configure'
        ]
        
        # Process/workflow words
        workflow_keywords = [
            'workflow', 'automation', 'setup', 'configure', 'build with', 'create with',
            'using x to', 'using', 'process', 'method', 'technique'
        ]
        
        # Weak signals (only count with tutorial/process context)
        weak_tool_keywords = [
            'chatgpt', 'claude', 'gemini', 'gpt', 'llm', 'ai tool', 'ai tools'
        ]
        
        # Count strong tool signals
        strong_tool_score = sum(1 for keyword in strong_tool_keywords if keyword in title_lower or keyword in transcript_sample)
        
        # Check for tutorial/process context
        has_tutorial_context = any(keyword in title_lower or keyword in transcript_sample for keyword in tutorial_keywords)
        has_workflow_context = any(keyword in title_lower or keyword in transcript_sample for keyword in workflow_keywords)
        has_process_context = has_tutorial_context or has_workflow_context
        
        # Count weak signals (only if process context exists)
        weak_tool_score = 0
        if has_process_context:
            weak_tool_score = sum(1 for keyword in weak_tool_keywords if keyword in title_lower or keyword in transcript_sample)
        
        # Tools = strong signals OR (weak signals + tutorial/process language)
        if strong_tool_score >= 1 or (weak_tool_score >= 1 and has_process_context):
            print(f"✅ Selected: tools_workflows (strong: {strong_tool_score}, weak: {weak_tool_score}, process context: {has_process_context})")
            return 'tools_workflows'
        
        # ============================================
        # 3. EXPLAINER (default - everything else)
        # ============================================
        # Everything else goes to explainer:
        # - news, announcements, market analysis, protocols, frameworks, thesis content
        # - lectures, crypto, health, general educational content
        print(f"✅ Selected: explainer (default)")
        return 'explainer'

    def generate_summary(self, transcript: str, title: str, duration_seconds: Optional[int] = None, published_at: str = None) -> tuple[str, str]:
        """Generate consumption-optimized brief using three-tier approach"""
        import time
        from datetime import date
        current_date = date.today().isoformat()
        
        try:
            # Tier 1: Aggressively clean transcript to reduce size
            clean_transcript = self.clean_transcript_for_summary(transcript)
            print(f"🧹 Cleaned transcript: {len(transcript)} -> {len(clean_transcript)} characters")
            
            # Detect content type for prompt routing
            content_type = self.detect_content_type(title, clean_transcript, duration_seconds)
            print(f"📋 Content type detected: {content_type}")
            
            # Tier 2: Choose optimal model based on size
            model = self.get_optimal_model_for_transcript(clean_transcript)
            print(f"🤖 Using model: {model}")
            
            # Load category-specific prompt template from current_best directory
            category_prompt_file = Path(f"prompts/current_best/{content_type}_prompt.txt")
            fallback_prompt_file = Path("prompts/current_best/explainer_prompt.txt")
            
            prompt_used = "explainer"  # Default prompt type (explainer is the catch-all category)
            
            if category_prompt_file.exists():
                with open(category_prompt_file, 'r') as f:
                    prompt_template = f.read()
                prompt_used = content_type
                print(f"✅ Using specialized prompt: {content_type}_prompt.txt")
            elif fallback_prompt_file.exists():
                with open(fallback_prompt_file, 'r') as f:
                    prompt_template = f.read()
                prompt_used = "explainer"
                print(f"📄 Using fallback prompt: explainer_prompt.txt")
            else:
                # Final fallback to embedded prompt if no external files found
                print("⚠️ No external prompts found, using embedded fallback")
                prompt_template = f"""You are an obsessive intelligence extraction specialist. Your ONLY job is to find and extract EVERY specific detail, framework, number, name, and concept from this transcript. Miss NOTHING.

IMPORTANT: This video was published on {published_at or 'Unknown date'}. Today's date is {current_date}. Interpret ALL time references (e.g., "next year," "in two years") relative to the video's publish date.

Video Title: {title}
Transcript: {{transcript}}

CRITICAL EXTRACTION MANDATE:
- Find EVERY named framework, system, acronym, or model (like "FACE RIPS", "MAP-MAD", etc.)
- Extract EVERY number, date, percentage, dollar amount, timeline (2026, 2027, $2.71 trillion, etc.)
- List EVERY person, company, book, tool mentioned by name
- Document EVERY process, method, or step-by-step explanation
- Capture EVERY prediction, forecast, or timeline estimate

Extract with OBSESSIVE detail:

{{
    "core_thesis": "Single sentence capturing the main argument or key insight",
    
    "named_frameworks_extracted": [
        "EVERY framework mentioned by name with complete breakdown of all components",
        "Any acronym or system (like FACE RIPS, MAP-MAD) with each letter/part explained",
        "Models or theories referenced with full details"
    ],
    
    "all_numbers_and_data": [
        "EVERY specific number: dollar amounts, percentages, years, quantities with full context",
        "All timelines and dates mentioned: 2026, 2027, specific timeframes",
        "Financial figures: trillion dollar amounts, budget numbers, costs",
        "Statistics and metrics: view counts, percentages, rates"
    ],
    
    "extracted_intelligence": {{
        "specific_methods": [
            "Method/approach described with complete details",
            "Process explained with all steps and context"
        ],
        "tools_and_resources": [
            "Tool/platform mentioned: what it does and specific capabilities",
            "Resource referenced: full details and context provided"
        ],
        "concepts_explained": [
            "Complex idea broken down with examples",
            "Theory or principle with real-world applications described"
        ]
    }},
    
    "detailed_breakdown": {{
        "argument_structure": "How the speaker builds their case from A to B to C",
        "supporting_evidence": [
            "Evidence type 1: specific examples and data points",
            "Proof point 2: how it supports the main thesis"
        ],
        "methodology_explained": [
            "Step-by-step process described in the content",
            "Approach or system outlined with implementation details"
        ]
    }},
    
    "critical_information": {{
        "contrarian_positions": [
            "Surprising viewpoint that challenges conventional thinking",
            "Unusual perspective with supporting reasoning provided"
        ],
        "important_distinctions": [
            "Key differences between concept A and concept B explained",
            "Clarification of commonly confused ideas"
        ],
        "notable_claims": [
            "Significant assertion made with supporting context",
            "Important statement with implications explained"
        ]
    }},
    
    "entities_and_references": {{
        "people_mentioned": ["Name: role and specific relevance to content"],
        "companies_technologies": ["Company/tech: what they do and why mentioned"],
        "books_resources": ["Resource: key relevance and takeaway"],
        "specific_examples": ["Real example: what happened and why it matters"]
    }},
    
    "intelligence_synthesis": {{
        "connections_made": [
            "How concept A relates to trend B",
            "Why insight X matters for understanding Y"
        ],
        "implications_analysis": [
            "What this means for industry/field Z",
            "How this changes the landscape of topic A"
        ],
        "future_predictions": [
            "Specific prediction with timeline and reasoning",
            "Expected outcome with supporting logic"
        ]
    }},
    
    "consumption_value": {{
        "why_this_matters": "Clear explanation of why this content is worth your time",
        "key_competitive_advantage": "What you gain by understanding this information",
        "decision_support": "How this intelligence helps with specific decisions you might face"
    }},
    
    "executive_distillation": {{
        "tldr": "Most important takeaway in one sentence",
        "action_priority": "Single highest-value action from this content", 
        "remember_this": "Key insight you'll want to recall weeks later"
    }}
}}

OBSESSIVE EXTRACTION REQUIREMENTS:
- SCAN the transcript for ANY framework mentioned by name (FACE RIPS, MAP-MAD, etc.) - extract EVERY component
- FIND every single number, date, dollar amount, percentage - capture with full context  
- LOCATE every person name, company name, book title, tool name - list with relevance
- EXTRACT every process described step-by-step
- CAPTURE every prediction with specific timeline
- If a framework is mentioned, extract ALL its components and explanations
- If numbers are given, capture the EXACT figures and what they refer to
- Miss NOTHING - be obsessively thorough

Return ONLY valid JSON with no markdown formatting."""
            
            # Tier 3: Chunking fallback for very large transcripts
            chunks = self.chunk_transcript(clean_transcript, max_chunk_size=100000)
            
            if len(chunks) > 1:
                print(f"📦 Processing {len(chunks)} chunks due to size")
                summary = self._process_chunked_summary(chunks, title, content_type, prompt_template, model, published_at=published_at)
                return summary, prompt_used
            else:
                # Single chunk processing
                prompt = prompt_template.format(title=title, transcript=clean_transcript, published_at=published_at or "Unknown date", current_date=current_date)
                summary = self._call_claude_api(prompt, model)
                return summary, prompt_used
                    
        except Exception as e:
            print(f"Error generating summary: {e}")
            return f"Summary generation error: {str(e)}\n\nNote: This may be due to API overload or rate limits. The transcript is available but processing failed.", "error"
    
    def _call_claude_api(self, prompt: str, model: str) -> str:
        """Call Claude API with retry logic for rate limiting"""
        import time
        
        max_retries = 3
        base_delay = 60  # Start with 60 seconds
        
        for attempt in range(max_retries):
            try:
                # Use longer timeout for large requests (default is 60s, increase to 300s for long transcripts)
                response = self.claude_client.messages.create(
                    model=model,
                    max_tokens=8192,  # Increased to allow comprehensive summaries without truncation
                    messages=[{"role": "user", "content": prompt}],
                    timeout=300.0  # 5 minutes timeout for long requests
                )
                
                # Extract and clean response
                content = response.content[0].text.strip()
                content = content.replace('```', '').strip()
                
                # Basic cleaning for display
                import re
                content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', content)
                
                print(f"✅ Summary generated: {len(content)} characters")
                return content
                
            except Exception as e:
                error_str = str(e)
                # Check for timeout errors
                if ("timeout" in error_str.lower() or "timed out" in error_str.lower() or "interrupted" in error_str.lower()) and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"⏳ Request timeout, waiting {delay} seconds before retry {attempt + 2}/{max_retries}...")
                    time.sleep(delay)
                    continue
                # Check for rate limit errors
                elif ("rate_limit_error" in error_str or "overloaded_error" in error_str or "529" in error_str) and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"⏳ API overload/rate limit hit, waiting {delay} seconds before retry {attempt + 2}/{max_retries}...")
                    time.sleep(delay)
                    continue
                else:
                    raise e  # Re-raise if not retryable error or final attempt
        
        return "Summary generation failed after all retries"
    
    def _process_chunked_summary(self, chunks: list, title: str, content_type: str, prompt_template: str, model: str, published_at: str = None) -> str:
        """Process large transcript in chunks and combine summaries"""
        from datetime import date
        current_date = date.today().isoformat()
        chunk_summaries = []

        for i, chunk in enumerate(chunks):
            print(f"📝 Processing chunk {i+1}/{len(chunks)} ({len(chunk)} characters)")

            # Create chunk-specific prompt
            chunk_prompt = prompt_template.format(
                title=f"{title} (Part {i+1} of {len(chunks)})",
                transcript=chunk,
                published_at=published_at or "Unknown date",
                current_date=current_date
            )
            
            # Process chunk
            chunk_summary = self._call_claude_api(chunk_prompt, model)
            chunk_summaries.append(f"=== PART {i+1} ===\n{chunk_summary}\n")
            
            # Add delay between chunks to avoid rate limiting
            if i < len(chunks) - 1:
                print("⏳ Waiting 30 seconds between chunks...")
                import time
                time.sleep(30)
        
        # Combine all chunk summaries
        combined_summary = "\n".join(chunk_summaries)
        print(f"✅ Combined summary: {len(combined_summary)} characters from {len(chunks)} chunks")
        
        return combined_summary

    def extract_article_text_from_image(self, image_path: str) -> Optional[Dict[str, Any]]:
        """Extract text from article screenshot using Claude Vision"""
        try:
            import base64
            from PIL import Image
            
            # Compress image if needed
            compressed_path = self.compress_image_if_needed(image_path)
            
            # Read and encode image
            with open(compressed_path, 'rb') as img_file:
                image_data = base64.b64encode(img_file.read()).decode('utf-8')
            
            # Determine media type
            ext = Path(compressed_path).suffix.lower()
            media_type_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.heic': 'image/heic', '.webp': 'image/webp'}
            media_type = media_type_map.get(ext, 'image/jpeg')
            
            print("Extracting text from article screenshot using Claude Vision...")
            
            # Use Claude Vision to extract text
            response = self.claude_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data
                                }
                            },
                            {
                                "type": "text",
                                "text": """Extract all text from this article screenshot. Preserve the structure, headings, paragraphs, and formatting as much as possible. 

Return a JSON object with:
{
    "title": "article title if visible",
    "text": "full extracted text content",
    "is_article": true
}

If this is not an article (e.g., it's a video screenshot, app interface, etc.), set "is_article": false."""
                            }
                        ]
                    }
                ]
            )
            
            content = response.content[0].text
            # Clean and parse JSON
            content = content.replace('```json', '').replace('```', '').strip()
            result = json.loads(content)
            
            if result.get('is_article', False) and result.get('text'):
                print(f"✅ Extracted {len(result['text'])} characters from article")
                return result
            else:
                print("Not an article screenshot")
                return None
                
        except Exception as e:
            print(f"Error extracting article text: {e}")
            return None

    def process_screenshot(self, image_path: str):
        """Complete processing pipeline for a single screenshot"""
        print(f"\n=== Processing {os.path.basename(image_path)} ===")

        metadata = None  # Track metadata for error reporting
        try:
            # Step 1: Try YouTube detection first
            print("1. Checking if this is a YouTube video screenshot...")
            metadata = self.extract_video_metadata(image_path)
            
            # Only proceed with YouTube processing if explicitly detected as YouTube
            if metadata and metadata.get('is_youtube', False):
                # Process as YouTube video - do NOT fall back to article if this fails
                print("2. YouTube video detected - processing as video...")
                video_url = self.find_youtube_video(metadata)
                if not video_url:
                    print("Could not find video - storing metadata only (NOT processing as article)")
                    self.store_failed_processing(image_path, metadata)
                    return  # Exit - don't try article processing
                
                print("3. Extracting transcript...")
                transcript = self.get_transcript(video_url)
                if not transcript:
                    print("No transcript available - storing error message (NOT processing as article)")
                    self.store_no_transcript_error(image_path, metadata, video_url)
                    return  # Exit - don't try article processing
                
                print("4. Generating summary...")
                summary_text, prompt_used = self.generate_summary(transcript, metadata.get('title', ''))
                
                print("5. Storing in database...")
                self.store_complete_processing(image_path, metadata, video_url, transcript, summary_text, prompt_used)
                print("✅ YouTube processing complete!")
                return  # Success - exit
            
            # Step 2: Only try article processing if YouTube was explicitly NOT detected
            # (is_youtube = false, not just missing metadata)
            if metadata is None:
                print("2. Could not extract metadata - trying article extraction as fallback...")
            elif metadata.get('is_youtube', True) is False:
                print("2. Not a YouTube video (is_youtube=false) - trying article extraction...")
            else:
                print("⚠️ Metadata extraction unclear - skipping to avoid misclassification")
                return
            
            article_data = self.extract_article_text_from_image(image_path)
            if article_data and article_data.get('is_article', False):
                print("3. Processing as article...")
                self.process_article_from_text(
                    image_path,
                    article_data.get('text', ''),
                    article_data.get('title', 'Article Screenshot')
                )
                print("✅ Article processing complete!")
                return
            
            print("⚠️ Could not determine content type - skipping")
            
        except Exception as e:
            print(f"❌ Processing failed: {e}")
            self.store_error(image_path, str(e), metadata)

    def process_article_from_text(self, image_path: str, text: str, title: str):
        """Process extracted article text and store as article"""
        try:
            if len(text) < 100:
                print(f"⚠️ Extracted text too short ({len(text)} chars) - skipping")
                return
            
            # Generate summary using same prompt as article processing
            prompt = f"""Create a tight, scannable executive analysis of this article. Prioritize conciseness and quick comprehension over exhaustive detail.

## EXECUTIVE SUMMARY
**One tight paragraph** capturing the core thesis, main argument, and key takeaway. What's the essential point?

## KEY INSIGHTS
**Bullet-heavy format** - Use clear, scannable bullets (not long paragraphs). For each major insight:
- **Bold the insight/topic** followed by brief context (2-3 sentences max)
- Include specific numbers, dates, percentages when they matter
- Capture frameworks/systems but summarize components (don't break down exhaustively)
- Use quotes sparingly - only for truly significant claims

## STRUCTURED ANALYSIS
Organize into 3-5 clear sections using Roman numerals (I, II, III). For each section:
- **Lead with 1-2 short bullets** summarizing the main points
- Use sub-bullets for details, examples, or supporting evidence
- **Keep paragraphs minimal** - prefer bullets for scannability
- Extract key recommendations, predictions, or actionable items
- Don't repeat what's in Executive Summary

## CONCLUSION
**2-3 concise bullets** covering: final assessment, key implications, and what to remember.

**LENGTH TARGET**: Aim for 40-60% of the original article length. Be comprehensive but tight. Every sentence should earn its place.

**FORMAT PRIORITY**: Scannable > Exhaustive. Use bullets liberally. Break up dense paragraphs. Make it easy to quickly understand the value.

Article Title: {title}
Source: Screenshot
Article Content:
{text[:15000]}"""
            
            print("Generating article summary with Claude Haiku 4.5...")
            response = self.claude_client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=6000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            summary = response.content[0].text
            
            # Store in articles table
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Ensure articles table exists with content_type
            try:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS articles (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT,
                        url TEXT,
                        content TEXT,
                        summary TEXT,
                        tags TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        content_type TEXT DEFAULT "article"
                    )
                ''')
                cursor.execute('ALTER TABLE articles ADD COLUMN content_type TEXT DEFAULT "article"')
                conn.commit()
            except sqlite3.OperationalError:
                pass  # Table/column already exists
            
            cursor.execute('''
                INSERT INTO articles (title, url, content, summary, tags, content_type)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title, f"screenshot:{os.path.basename(image_path)}", text[:50000], summary, 'screenshot', 'article'))
            
            conn.commit()
            conn.close()
            
            print(f"✅ Article stored: {title}")
            
        except Exception as e:
            print(f"❌ Error processing article: {e}")

    def store_complete_processing(self, image_path: str, metadata: Dict, video_url: str, transcript: str, summary_text: str, prompt_used: str):
        """Store successfully processed video data"""
        # Try to get published_at from channel_videos or YouTube API
        published_at = None
        video_id = self.extract_video_id(video_url)
        if video_id:
            conn_check = self._get_connection()
            cursor_check = conn_check.cursor()
            try:
                cursor_check.execute(
                    'SELECT published_at FROM channel_videos WHERE video_id = ?',
                    (video_id,)
                )
                row = cursor_check.fetchone()
                if row and row['published_at']:
                    published_at = row['published_at']
            finally:
                conn_check.close()
        
        # Try to get view count from screenshot metadata
        view_count = _parse_view_count(metadata.get('views', ''))

        # If still not found, try YouTube API for published_at AND view_count
        if (not published_at or not view_count) and video_id and YOUTUBE_API_KEY:
            try:
                api_url = "https://www.googleapis.com/youtube/v3/videos"
                params = {
                    'part': 'snippet,statistics',
                    'id': video_id,
                    'key': YOUTUBE_API_KEY
                }
                resp = requests.get(api_url, params=params, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                items = data.get('items', [])
                if items and len(items) > 0:
                    item = items[0]
                    snippet = item.get('snippet', {})
                    statistics = item.get('statistics', {})
                    if not published_at and snippet.get('publishedAt'):
                        published_at = snippet['publishedAt']
                    if not view_count and statistics.get('viewCount'):
                        view_count = int(statistics['viewCount'])
            except Exception as e:
                print(f"⚠️  Could not fetch data from API: {e}")
        
        # Main summary is already ~50% length (prompts produce concise output directly)
        # Only need 1 shortening call: signal scan (30% of the 50% summary ≈ 15% of original)
        print(f"📝 Generating signal scan for video: {metadata.get('title', '')}")
        summary_50 = summary_text  # Main summary IS the 50% version now
        summary_15 = generate_shortened_summary(self.claude_client, summary_text, 30)

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            # Ensure published_at and summary columns exist
            cursor.execute("PRAGMA table_info(videos)")
            columns = [row[1] for row in cursor.fetchall()]
            if 'published_at' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN published_at TIMESTAMP')
            if 'original_publish_date' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN original_publish_date TIMESTAMP')
            if 'summary_50' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN summary_50 TEXT')
            if 'summary_30' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN summary_30 TEXT')
            if 'summary_15' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN summary_15 TEXT')
            if 'view_count' not in columns:
                cursor.execute('ALTER TABLE videos ADD COLUMN view_count INTEGER')

            # Duplicate guard: check if this video_url already exists
            if video_url:
                cursor.execute('SELECT id FROM videos WHERE video_url = ?', (video_url,))
                existing = cursor.fetchone()
                if existing:
                    print(f"⚠️  Duplicate prevented (screenshot path): {metadata.get('title', '')} already exists as video {existing[0]}")
                    conn.close()
                    return

            cursor.execute('''
                INSERT INTO videos (
                    screenshot_path, filename, video_url, title, channel,
                    full_transcript, ai_summary, summary_50, summary_30, summary_15, key_insights, topics,
                    confidence_score, status, prompt_used, published_at, original_publish_date, view_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                image_path,
                os.path.basename(image_path),
                video_url,
                metadata.get('title', ''),
                metadata.get('channel', ''),
                transcript,
                summary_text,  # Store narrative text directly
                summary_50,
                '',  # summary_30 dropped to save API costs
                summary_15,
                '',  # No separate key_insights for narrative format
                '',  # No separate topics for narrative format
                metadata.get('confidence', 0.0),
                'completed',
                prompt_used,
                published_at,
                published_at,  # Use same value for both fields
                view_count
            ))
            
            conn.commit()
        finally:
            conn.close()

    def store_failed_processing(self, image_path: str, metadata: Dict):
        """Store failed processing attempts"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO videos (
                screenshot_path, filename, title, channel, confidence_score, status
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            image_path,
            os.path.basename(image_path),
            metadata.get('title', ''),
            metadata.get('channel', ''),
            metadata.get('confidence', 0.0),
            'no_video_found'
        ))
        
        conn.commit()
        conn.close()

    def store_no_transcript_error(self, image_path: str, metadata: Dict, video_url: str):
        """Store error when no transcript is available"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Duplicate guard
        if video_url:
            cursor.execute('SELECT id FROM videos WHERE video_url = ?', (video_url,))
            if cursor.fetchone():
                print(f"⚠️  Duplicate prevented (no_transcript): {metadata.get('title', '')} already exists")
                conn.close()
                return

        error_message = "ERROR: No transcript available for this video. Only video descriptions were found, which don't contain the actual conversation content needed for analysis."

        cursor.execute('''
            INSERT INTO videos (
                screenshot_path, filename, video_url, title, channel,
                ai_summary, confidence_score, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            image_path,
            os.path.basename(image_path),
            video_url,
            metadata.get('title', ''),
            metadata.get('channel', ''),
            error_message,
            metadata.get('confidence', 0.0),
            'no_transcript'
        ))

        conn.commit()
        conn.close()

    def store_partial_processing(self, image_path: str, metadata: Dict, video_url: str):
        """Store partial processing (video found but no transcript)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Duplicate guard
        if video_url:
            cursor.execute('SELECT id FROM videos WHERE video_url = ?', (video_url,))
            if cursor.fetchone():
                print(f"⚠️  Duplicate prevented (partial): {metadata.get('title', '')} already exists")
                conn.close()
                return

        cursor.execute('''
            INSERT INTO videos (
                screenshot_path, filename, video_url, title, channel,
                confidence_score, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            image_path,
            os.path.basename(image_path),
            video_url,
            metadata.get('title', ''),
            metadata.get('channel', ''),
            metadata.get('confidence', 0.0),
            'no_transcript'
        ))
        
        conn.commit()
        conn.close()

    def store_error(self, image_path: str, error_msg: str, metadata: Dict = None):
        """Store processing errors with any partial metadata that was captured"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Extract whatever metadata we have
        title = None
        channel = None
        video_url = None

        if metadata:
            title = metadata.get('title', metadata.get('video_title'))
            channel = metadata.get('channel', metadata.get('channel_name'))
            video_url = metadata.get('video_url')

        # Duplicate guard
        if video_url:
            cursor.execute('SELECT id FROM videos WHERE video_url = ?', (video_url,))
            if cursor.fetchone():
                print(f"⚠️  Duplicate prevented (error): {title or video_url} already exists")
                conn.close()
                return

        cursor.execute('''
            INSERT INTO videos (
                screenshot_path, filename, title, channel, video_url, status, ai_summary
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            image_path,
            os.path.basename(image_path),
            title,
            channel,
            video_url,
            'error',
            f"Processing error: {error_msg}"
        ))

        conn.commit()
        conn.close()

        if title or channel:
            print(f"📝 Stored error with partial info: {title or 'Unknown'} / {channel or 'Unknown'}")

    def process_batch(self):
        """Process all pending files in batch"""
        if not self.pending_files:
            return
            
        print(f"\n🔄 Processing batch of {len(self.pending_files)} screenshots...")
        
        files_to_process = list(self.pending_files)
        self.pending_files.clear()
        
        for image_path in files_to_process:
            if os.path.exists(image_path):
                self.process_screenshot(image_path)
            else:
                print(f"File no longer exists: {image_path}")
        
        print(f"✅ Batch processing complete!")

    def is_file_already_processed(self, file_path: str) -> bool:
        """Check if a file has already been processed"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM videos 
            WHERE screenshot_path = ? AND status IN ('completed', 'no_transcript', 'no_video_found')
        ''', (file_path,))
        
        count = cursor.fetchone()[0]
        conn.close()
        
        return count > 0

    def search_videos(self, query: str) -> List[Dict]:
        """Search processed videos using natural language"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Simple text search across title, summary, and insights
        search_sql = '''
            SELECT title, channel, ai_summary, key_insights, video_url, processing_date
            FROM videos 
            WHERE status = 'completed' 
            AND (
                title LIKE ? OR 
                ai_summary LIKE ? OR 
                key_insights LIKE ? OR
                topics LIKE ? OR
                full_transcript LIKE ?
            )
            ORDER BY processing_date DESC
        '''
        
        search_term = f"%{query}%"
        cursor.execute(search_sql, (search_term, search_term, search_term, search_term, search_term))
        
        results = []
        for row in cursor.fetchall():
            # Handle both old JSON format and new text format
            summary_text = row[2] if row[2] else 'No summary'
            
            # Check if it's old JSON format (starts with {)
            if summary_text.startswith('{'):
                try:
                    summary_data = json.loads(summary_text)
                    display_summary = summary_data.get('core_thesis', summary_text[:200])
                    tldr = summary_data.get('executive_distillation', {}).get('tldr', '')
                except:
                    display_summary = summary_text[:200]
                    tldr = ''
            else:
                # New text format - show first paragraph as summary
                display_summary = summary_text[:300] + '...' if len(summary_text) > 300 else summary_text
                tldr = ''
                
            results.append({
                'title': row[0],
                'channel': row[1],
                'summary': display_summary,
                'tldr': tldr,
                'insights': [],  # No separate insights in narrative format
                'url': row[4],
                'date': row[5]
            })
        
        conn.close()
        return results

    def reprocess_single_video(self, video_id: int, prompt_file: str = None):
        """Reprocess a single video with optional custom prompt"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get video details
        cursor.execute('''
            SELECT id, video_url, title, full_transcript, ai_summary
            FROM videos 
            WHERE id = ? AND status = 'completed' AND full_transcript IS NOT NULL
        ''', (video_id,))
        
        video = cursor.fetchone()
        conn.close()
        
        if not video:
            print(f"Video ID {video_id} not found or no transcript available")
            return
        
        video_id, video_url, title, transcript, old_summary = video
        
        # Get duration from database if available
        conn_dur = sqlite3.connect(self.db_path)
        cursor_dur = conn_dur.cursor()
        duration_seconds = None
        try:
            cursor_dur.execute('SELECT duration FROM videos WHERE id = ?', (video_id,))
            row = cursor_dur.fetchone()
            if row and row[0]:
                duration_seconds = _parse_formatted_duration(row[0])
        finally:
            conn_dur.close()
        
        print(f"\nReprocessing: {title}")
        
        try:
            # Generate new summary with custom prompt if provided
            if prompt_file and os.path.exists(f"prompts/{prompt_file}"):
                print(f"Using custom prompt: {prompt_file}")
                with open(f"prompts/{prompt_file}", 'r') as f:
                    prompt_template = f.read()
                
                # Use three-tier approach even with custom prompts
                clean_transcript = self.clean_transcript_for_summary(transcript)
                model = self.get_optimal_model_for_transcript(clean_transcript)
                prompt = prompt_template.format(title=title, transcript=clean_transcript)
                
                # Use our rate-limited API call method
                new_summary = self._call_claude_api(prompt, model)
            else:
                # Use proper category detection and prompt selection
                content_type = self.detect_content_type(title, transcript, duration_seconds)
                print(f"📋 Content type detected: {content_type}")
                
                # Use the same prompt selection logic as main processing
                new_summary, prompt_used = self.generate_summary(transcript, title, duration_seconds)
            
            # Update database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE videos 
                SET ai_summary = ?, key_insights = '', topics = '', prompt_used = ?
                WHERE id = ?
            ''', (new_summary, prompt_used, video_id))
            
            conn.commit()
            conn.close()
            
            print(f"✅ Successfully reprocessed: {title}")
            print(f"📊 New summary length: {len(new_summary)} characters")
            return new_summary
            
        except Exception as e:
            print(f"❌ Failed to reprocess {title}: {e}")
            return None

    def reprocess_failed_videos(self):
        """Regenerate summaries for videos that failed processing"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Find videos needing better formatting and specificity (reprocess all completed videos)
        cursor.execute('''
            SELECT id, video_url, title, full_transcript, ai_summary
            FROM videos 
            WHERE status = 'completed' 
            AND full_transcript IS NOT NULL
            AND full_transcript != ''
            AND ai_summary NOT LIKE '## Overview%'
        ''')
        
        failed_videos = cursor.fetchall()
        conn.close()
        
        if not failed_videos:
            print("No failed videos found to reprocess")
            return
        
        print(f"Found {len(failed_videos)} videos with errors to reprocess...")
        
        for video_id, video_url, title, transcript, old_summary in failed_videos:
            print(f"\nReprocessing: {title}")
            
            try:
                # Generate new summary using current working models
                new_summary, prompt_used = self.generate_summary(transcript, title)
                
                # Update database with new summary
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE videos 
                    SET ai_summary = ?, key_insights = '', topics = '', prompt_used = ?
                    WHERE id = ?
                ''', (new_summary, prompt_used, video_id))
                
                conn.commit()
                conn.close()
                
                print(f"✅ Successfully reprocessed: {title}")
                
            except Exception as e:
                print(f"❌ Failed to reprocess {title}: {e}")
        
        print(f"\n✅ Reprocessing complete!")

class ScreenshotHandler(FileSystemEventHandler):
    def __init__(self, processor: YouTubeProcessor):
        self.processor = processor
        
    def on_created(self, event):
        if event.is_directory:
            return
            
        file_path = event.src_path
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext in SUPPORTED_EXTENSIONS:
            # Check if file is already being processed or already exists in database
            if self.processor.is_file_already_processed(file_path):
                print(f"⏭️ File already processed, skipping: {os.path.basename(file_path)}")
                return
                
            print(f"📸 New screenshot detected: {os.path.basename(file_path)}")
            
            # Add to pending batch
            self.processor.pending_files.add(file_path)
            
            # Reset batch timer
            if self.processor.batch_timer:
                self.processor.batch_timer.cancel()
            
            self.processor.batch_timer = threading.Timer(
                BATCH_DELAY_SECONDS, 
                self.processor.process_batch
            )
            self.processor.batch_timer.start()
            
            print(f"⏰ Batch timer started - will process in {BATCH_DELAY_SECONDS} seconds")

def main():
    """Main application entry point"""
    print("🚀 YouTube Intelligence Processor Starting...")
    
    # Create watch folder if it doesn't exist
    if not os.path.exists(WATCH_FOLDER):
        os.makedirs(WATCH_FOLDER)
        print(f"📁 Created watch folder: {WATCH_FOLDER}")
    
    # Initialize processor
    processor = YouTubeProcessor()
    
    # Set up file monitoring
    event_handler = ScreenshotHandler(processor)
    observer = Observer()
    observer.schedule(event_handler, WATCH_FOLDER, recursive=False)
    
    print(f"👀 Monitoring folder: {os.path.abspath(WATCH_FOLDER)}")
    print(f"⏱️  Batch delay: {BATCH_DELAY_SECONDS} seconds")
    print("📱 Drop iPhone screenshots into the folder to process them")
    print("🔍 Use search_videos('query') to find processed content")
    print("\nPress Ctrl+C to stop monitoring...\n")
    
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitoring...")
        observer.stop()
        if processor.batch_timer:
            processor.batch_timer.cancel()
    
    observer.join()
    print("✅ YouTube Intelligence Processor stopped")

def search_command(query: str):
    """Standalone search function"""
    processor = YouTubeProcessor()
    results = processor.search_videos(query)
    
    if results:
        print(f"\n🔍 Found {len(results)} results for '{query}':\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['title']}")
            print(f"   Channel: {result['channel']}")
            print(f"   URL: {result['url']}")
            print(f"   Core Thesis: {result['summary']}")
            if result['tldr']:
                print(f"   TL;DR: {result['tldr']}")
            print(f"   Date: {result['date']}")
            print()
    else:
        print(f"No results found for '{query}'")

def reprocess_command():
    """Standalone reprocess function"""
    processor = YouTubeProcessor()
    processor.reprocess_failed_videos()

def reprocess_single_command():
    """Reprocess a single video"""
    processor = YouTubeProcessor()
    
    if len(sys.argv) < 3:
        print("Usage: python youtube_processor.py reprocess-single <video_id> [prompt_file]")
        return
    
    video_id = int(sys.argv[2])
    prompt_file = sys.argv[3] if len(sys.argv) > 3 else None
    
    processor.reprocess_single_video(video_id, prompt_file)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "search":
        if len(sys.argv) > 2:
            search_command(" ".join(sys.argv[2:]))
        else:
            query = input("Enter search query: ")
            search_command(query)
    elif len(sys.argv) > 1 and sys.argv[1] == "reprocess":
        reprocess_command()
    elif len(sys.argv) > 1 and sys.argv[1] == "reprocess-single":
        reprocess_single_command()
    else:
        main()

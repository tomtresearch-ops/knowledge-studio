#!/usr/bin/env python3
"""
Backfill missing published_at/original_publish_date values in youtube_intelligence.db
using the YouTube Data API v3.

Usage:
    export YOUTUBE_API_KEY="YOUR_KEY"
    python scripts/backfill_published_dates.py

Notes:
    - Each API call fetches up to 50 video IDs and costs 1 quota unit.
    - The script skips rows that already have published_at.
    - If the API key is missing or network is unavailable the script exits gracefully.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
import ssl
import urllib.error
BYPASS_SSL = os.environ.get("YOUTUBE_SKIP_SSL_VERIFY") == "1"
SSL_CONTEXT = None
if BYPASS_SSL:
    SSL_CONTEXT = ssl._create_unverified_context()  # noqa: SLF001
else:
    SSL_CONTEXT = ssl.create_default_context()
import urllib.parse
import urllib.request
from typing import Iterable, List, Tuple

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "youtube_intelligence.db")
API_KEY = os.environ.get("YOUTUBE_API_KEY")
API_URL = "https://www.googleapis.com/youtube/v3/videos"
BATCH_SIZE = 50


def chunked(iterable: Iterable[str], size: int) -> Iterable[List[str]]:
    batch: List[str] = []
    for item in iterable:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def fetch_published_dates(video_ids: List[str]) -> List[Tuple[str, str]]:
    """
    Returns list of (video_id, published_at) tuples for IDs that had data.
    """
    params = {
        "id": ",".join(video_ids),
        "part": "snippet",
        "key": API_KEY,
        "maxResults": len(video_ids),
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=10, context=SSL_CONTEXT) as resp:
            payload = resp.read()
    except urllib.error.URLError as exc:
        print(f"⚠️  Network/API error while fetching {video_ids[:3]}...: {exc}", file=sys.stderr)
        return []

    try:
        import json

        data = json.loads(payload.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Failed to parse API response: {exc}", file=sys.stderr)
        return []

    results: List[Tuple[str, str]] = []
    for item in data.get("items", []):
        video_id = item.get("id")
        snippet = item.get("snippet") or {}
        published_at = snippet.get("publishedAt")
        if video_id and published_at:
            results.append((video_id, published_at))
    return results


def backfill_from_api() -> None:
    if not API_KEY:
        print("❌ YOUTUBE_API_KEY not set. Skipping API backfill.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, video_url
        FROM videos
        WHERE status = 'completed'
          AND (published_at IS NULL OR published_at = '')
          AND video_url LIKE 'https://www.youtube.com/watch?v=%'
        """
    )
    rows = cursor.fetchall()
    video_ids = []
    for row in rows:
        url = row["video_url"]
        video_id = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("v", [""])[0]
        if video_id:
            video_ids.append(video_id)

    if not video_ids:
        print("✅ No videos require API backfill.")
        conn.close()
        return

    print(f"ℹ️  Attempting to backfill {len(video_ids)} videos via YouTube API...")
    updated = 0
    for batch in chunked(video_ids, BATCH_SIZE):
        pairs = fetch_published_dates(batch)
        if not pairs:
            continue
        for video_id, published_at in pairs:
            cursor.execute(
                """
                UPDATE videos
                SET published_at = ?, original_publish_date = COALESCE(original_publish_date, ?)
                WHERE video_url LIKE ? AND (published_at IS NULL OR published_at = '')
                """,
                (published_at, published_at, f"%{video_id}%"),
            )
            updated += cursor.rowcount
        conn.commit()
        time.sleep(0.2)  # polite pacing

    conn.close()
    print(f"✅ Backfill complete. Updated {updated} rows via API.")


def main() -> None:
    print("Starting published_at backfill...")
    backfill_from_api()
    print("Done.")


if __name__ == "__main__":
    main()


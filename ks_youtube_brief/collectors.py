"""
KS YouTube Intelligence Brief — Source Collectors
Pure Knowledge Studio source: pulls recently processed YouTube videos
with full AI summaries for deep synthesis.
"""

import os
import sqlite3
from datetime import datetime, timedelta


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "youtube_intelligence.db")


class KSYouTubeCollector:
    """Pull recently processed YouTube videos from Knowledge Studio with full AI summaries."""

    def __init__(self, db_path: str = None, hours_back: int = 24):
        self.db_path = db_path or DB_PATH
        self.hours_back = hours_back

    def collect_processed_videos(self) -> list[dict]:
        """Get recently processed videos with full ai_summary."""
        print(f"[KS YouTube] Collecting processed videos (last {self.hours_back}h)...")
        cutoff = (datetime.utcnow() - timedelta(hours=self.hours_back)).strftime("%Y-%m-%d %H:%M:%S")

        results = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, title, channel, ai_summary, key_insights, tags,
                       video_url, published_at, processing_date, view_count, duration
                FROM videos
                WHERE processing_date > ? AND status = 'completed'
                ORDER BY processing_date DESC
                LIMIT 100
            """, (cutoff,))

            for row in cursor.fetchall():
                results.append({
                    "source": "ks_processed_video",
                    "id": row["id"],
                    "title": row["title"] or "",
                    "channel": row["channel"] or "",
                    "ai_summary": row["ai_summary"] or "",
                    "key_insights": row["key_insights"] or "",
                    "tags": row["tags"] or "",
                    "url": row["video_url"] or "",
                    "published_at": row["published_at"] or "",
                    "processed_at": row["processing_date"] or "",
                    "view_count": row["view_count"] or 0,
                    "duration": row["duration"] or "",
                })

            conn.close()
        except Exception as e:
            print(f"  [KS YouTube] Error: {e}")

        print(f"  [KS YouTube] Found {len(results)} processed videos")
        return results

    def collect_discovered_unprocessed(self) -> list[dict]:
        """Get recently discovered but not-yet-processed videos from channel feeds."""
        print(f"[KS YouTube] Collecting unprocessed discoveries...")
        cutoff = (datetime.utcnow() - timedelta(hours=self.hours_back)).strftime("%Y-%m-%d %H:%M:%S")

        results = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT cv.video_id, cv.title, cv.channel_name, cv.description,
                       cv.published_at, cv.view_count, cv.duration_seconds
                FROM channel_videos cv
                WHERE cv.discovered_at > ? AND cv.processed = 0
                ORDER BY cv.published_at DESC
                LIMIT 50
            """, (cutoff,))

            for row in cursor.fetchall():
                results.append({
                    "source": "ks_unprocessed_discovery",
                    "title": row["title"] or "",
                    "channel": row["channel_name"] or "",
                    "description": row["description"] or "",
                    "published_at": row["published_at"] or "",
                    "view_count": row["view_count"] or 0,
                    "duration_seconds": row["duration_seconds"] or 0,
                })

            conn.close()
        except Exception as e:
            print(f"  [KS YouTube] Unprocessed error: {e}")

        print(f"  [KS YouTube] Found {len(results)} unprocessed discoveries")
        return results


def collect_all(vertical: str = "ks_youtube",
                hours_back: int = 24,
                db_path: str = None,
                youtube_api_key: str = None) -> dict:
    """
    Run all collectors for the KS YouTube Intelligence vertical.
    Returns a dict with items grouped by source.
    """
    print(f"\n{'='*60}")
    print(f"  KS YOUTUBE INTELLIGENCE BRIEF — Collecting")
    print(f"  Window: last {hours_back} hours")
    print(f"  Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    collector = KSYouTubeCollector(db_path=db_path, hours_back=hours_back)

    results = {
        "vertical": vertical,
        "collected_at": datetime.utcnow().isoformat(),
        "hours_back": hours_back,
        "sources": {
            "ks_processed_videos": collector.collect_processed_videos(),
            "ks_unprocessed_discoveries": collector.collect_discovered_unprocessed(),
        },
    }

    total = sum(len(v) for v in results["sources"].values())
    print(f"\n  Total signals collected: {total}")
    return results

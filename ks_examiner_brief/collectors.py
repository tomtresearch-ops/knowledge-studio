"""
KS Examiner — Source Collectors
Operational intelligence: processing stats, channel activity, topic distribution,
cross-channel convergence, and trend comparison.
"""

import os
import sqlite3
from datetime import datetime, timedelta
from collections import Counter


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "youtube_intelligence.db")


class KSOperationsCollector:
    """Pull processing stats and channel activity from Knowledge Studio."""

    def __init__(self, db_path: str = None, hours_back: int = 24):
        self.db_path = db_path or DB_PATH
        self.hours_back = hours_back

    def collect(self) -> dict:
        """Get operational stats for the reporting period."""
        print(f"[KS Examiner] Collecting operations data (last {self.hours_back}h)...")
        cutoff = (datetime.utcnow() - timedelta(hours=self.hours_back)).strftime("%Y-%m-%d %H:%M:%S")
        prev_cutoff = (datetime.utcnow() - timedelta(hours=self.hours_back * 2)).strftime("%Y-%m-%d %H:%M:%S")

        stats = {
            "source": "ks_operations",
            "period_hours": self.hours_back,
        }

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Processing volume
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM videos WHERE processing_date > ? AND status = 'completed'",
                (cutoff,)
            )
            stats["videos_completed"] = cursor.fetchone()["cnt"]

            cursor.execute(
                "SELECT COUNT(*) as cnt FROM videos WHERE processing_date > ? AND status = 'failed'",
                (cutoff,)
            )
            stats["videos_failed"] = cursor.fetchone()["cnt"]

            cursor.execute(
                "SELECT COUNT(*) as cnt FROM videos WHERE processing_date > ? AND status = 'pending'",
                (cutoff,)
            )
            stats["videos_pending"] = cursor.fetchone()["cnt"]

            # Previous period for comparison
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM videos WHERE processing_date > ? AND processing_date <= ? AND status = 'completed'",
                (prev_cutoff, cutoff)
            )
            stats["prev_period_completed"] = cursor.fetchone()["cnt"]

            # Transcript availability
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM videos WHERE processing_date > ? AND status = 'completed' AND full_transcript IS NOT NULL AND full_transcript != ''",
                (cutoff,)
            )
            stats["with_transcript"] = cursor.fetchone()["cnt"]

            # Channel activity
            cursor.execute("""
                SELECT channel, COUNT(*) as cnt
                FROM videos
                WHERE processing_date > ? AND status = 'completed'
                GROUP BY channel
                ORDER BY cnt DESC
            """, (cutoff,))
            stats["channel_activity"] = [
                {"channel": row["channel"] or "Unknown", "count": row["cnt"]}
                for row in cursor.fetchall()
            ]
            stats["active_channels"] = len(stats["channel_activity"])

            # Total subscribed channels
            cursor.execute("SELECT COUNT(*) as cnt FROM channel_subscriptions WHERE enabled = 1")
            stats["total_subscribed"] = cursor.fetchone()["cnt"]

            # Discovered but unprocessed
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM channel_videos WHERE discovered_at > ? AND processed = 0",
                (cutoff,)
            )
            stats["unprocessed_queue"] = cursor.fetchone()["cnt"]

            # Articles processed
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM articles WHERE created_at > ?",
                (cutoff,)
            )
            stats["articles_processed"] = cursor.fetchone()["cnt"]

            conn.close()
        except Exception as e:
            print(f"  [KS Examiner] Operations error: {e}")

        print(f"  [KS Examiner] Stats: {stats.get('videos_completed', 0)} completed, "
              f"{stats.get('active_channels', 0)} channels active")
        return stats


class KSTrendCollector:
    """Analyze topic distribution and cross-channel convergence."""

    def __init__(self, db_path: str = None, hours_back: int = 24):
        self.db_path = db_path or DB_PATH
        self.hours_back = hours_back

    def collect(self) -> dict:
        """Analyze topics, convergence, and trends."""
        print(f"[KS Examiner] Collecting trend data...")
        cutoff = (datetime.utcnow() - timedelta(hours=self.hours_back)).strftime("%Y-%m-%d %H:%M:%S")
        prev_cutoff = (datetime.utcnow() - timedelta(hours=self.hours_back * 2)).strftime("%Y-%m-%d %H:%M:%S")

        trends = {
            "source": "ks_trends",
        }

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all recent videos with tags
            cursor.execute("""
                SELECT id, title, channel, tags, ai_summary, key_insights
                FROM videos
                WHERE processing_date > ? AND status = 'completed'
                ORDER BY processing_date DESC
            """, (cutoff,))

            videos = cursor.fetchall()

            # Tag frequency analysis
            tag_counter = Counter()
            tag_channels = {}  # tag -> set of channels
            for v in videos:
                tags = v["tags"] or ""
                channel = v["channel"] or "Unknown"
                for tag in [t.strip().lower() for t in tags.split(",") if t.strip()]:
                    tag_counter[tag] += 1
                    tag_channels.setdefault(tag, set()).add(channel)

            # Previous period tags for comparison
            cursor.execute("""
                SELECT tags FROM videos
                WHERE processing_date > ? AND processing_date <= ? AND status = 'completed'
            """, (prev_cutoff, cutoff))
            prev_tags = Counter()
            for row in cursor.fetchall():
                for tag in [t.strip().lower() for t in (row["tags"] or "").split(",") if t.strip()]:
                    prev_tags[tag] += 1

            # Topic heat map with trend arrows
            topic_heat = []
            for tag, count in tag_counter.most_common(20):
                prev_count = prev_tags.get(tag, 0)
                channels_on_topic = len(tag_channels.get(tag, set()))
                if prev_count == 0:
                    trend = "new"
                elif count > prev_count:
                    trend = "up"
                elif count < prev_count:
                    trend = "down"
                else:
                    trend = "steady"
                topic_heat.append({
                    "topic": tag,
                    "count": count,
                    "prev_count": prev_count,
                    "trend": trend,
                    "channels": channels_on_topic,
                })
            trends["topic_heat_map"] = topic_heat

            # Cross-channel convergence (topics appearing in 3+ channels)
            convergence = []
            for tag, channels in tag_channels.items():
                if len(channels) >= 3:
                    # Get video titles for context
                    related_videos = []
                    for v in videos:
                        vtags = [t.strip().lower() for t in (v["tags"] or "").split(",")]
                        if tag in vtags:
                            related_videos.append({
                                "title": v["title"],
                                "channel": v["channel"],
                            })
                    convergence.append({
                        "topic": tag,
                        "channel_count": len(channels),
                        "channels": list(channels),
                        "videos": related_videos[:8],
                    })
            convergence.sort(key=lambda x: -x["channel_count"])
            trends["convergence_alerts"] = convergence

            # Channels that were quiet (subscribed but no content in period)
            cursor.execute("""
                SELECT cs.channel_name
                FROM channel_subscriptions cs
                WHERE cs.enabled = 1
                AND cs.channel_name NOT IN (
                    SELECT DISTINCT channel FROM videos
                    WHERE processing_date > ? AND status = 'completed' AND channel IS NOT NULL
                )
            """, (cutoff,))
            trends["quiet_channels"] = [row["channel_name"] for row in cursor.fetchall()]

            conn.close()
        except Exception as e:
            print(f"  [KS Examiner] Trend error: {e}")

        conv_count = len(trends.get("convergence_alerts", []))
        print(f"  [KS Examiner] {len(trends.get('topic_heat_map', []))} topics, "
              f"{conv_count} convergence alerts")
        return trends


def collect_all(vertical: str = "ks_examiner",
                hours_back: int = 24,
                db_path: str = None,
                youtube_api_key: str = None) -> dict:
    """
    Run all collectors for the KS Examiner vertical.
    Returns a dict with operations stats and trend data.
    """
    print(f"\n{'='*60}")
    print(f"  THE KS EXAMINER — Collecting")
    print(f"  Window: last {hours_back} hours")
    print(f"  Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    ops = KSOperationsCollector(db_path=db_path, hours_back=hours_back)
    trends = KSTrendCollector(db_path=db_path, hours_back=hours_back)

    results = {
        "vertical": vertical,
        "collected_at": datetime.utcnow().isoformat(),
        "hours_back": hours_back,
        "sources": {
            "operations": [ops.collect()],
            "trends": [trends.collect()],
        },
    }

    print(f"\n  Collection complete.")
    return results

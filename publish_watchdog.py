#!/usr/bin/env python3
"""
publish_watchdog — answers one question: is every live brand still publishing?

Built 2026-08-06 after Breakthrough Medicine went dark for 27 days without anyone
noticing. The failure was invisible because the checks that existed were all
process-level ("did the job run?") rather than outcome-level ("did an episode
reach the feed?"). Every stage reported success while the thing that matters —
a new episode — never appeared.

So this measures the OUTCOME and nothing else: for each live brand, how old is the
newest published episode, compared to how often that brand is supposed to publish.
It reads the same feeds a subscriber would.

Exit status is the verifier:
    0 — all live brands within tolerance
    1 — at least one brand is overdue  (this is the alarm)

Run it after the nightly, and on its own schedule during the day.
"""

import json
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "youtube_intelligence.db")
FEED_BASE = "https://media-verticals.github.io/podcasts/"
FALLBACK_LOG = os.path.join(BASE_DIR, "logs", "api_fallback.jsonl")

# Live brands only. A brand paused on purpose is NOT a failure — that distinction
# is the whole reason the old audits cried wolf. Keep this list in step with
# get_verticals_for_today() in run_background.py.
#
# grace_days = expected cadence + one missed run of slack.
LIVE_BRANDS = {
    "future_medicine": {
        "brand": "Breakthrough Medicine",
        "feed": "feed_breakthrough_medicine.xml",
        "cadence": "Mon/Thu",
        "grace_days": 7,
    },
    "health_longevity": {
        "brand": "Longevity Edge",
        "feed": "feed_longevity_edge.xml",
        "cadence": "Tue/Fri",
        "grace_days": 7,
    },
    "ai_tech": {
        "brand": "AI Landscape",
        "feed": "feed_ai_landscape.xml",
        "cadence": "daily",
        "grace_days": 3,
    },
}


def newest_published(feed_filename):
    """Newest pubDate in the live feed — what a subscriber would actually see."""
    url = FEED_BASE + feed_filename
    with urllib.request.urlopen(url, timeout=30) as resp:
        body = resp.read().decode("utf-8", "replace")

    dates = []
    for chunk in body.split("<pubDate>")[1:]:
        raw = chunk.split("</pubDate>")[0].strip()
        try:
            dates.append(parsedate_to_datetime(raw))
        except Exception:
            continue
    if not dates:
        return None, 0
    return max(dates), body.count("<item>")


def newest_in_db(vertical):
    """Newest episode the pipeline believes it produced.

    Compared against the feed to separate 'never produced' from 'produced but
    never shipped' — two very different faults that look identical from outside.
    """
    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
        row = conn.execute(
            "SELECT MAX(created_at) FROM brief_podcast_episodes WHERE vertical = ?",
            (vertical,),
        ).fetchone()
        conn.close()
        return row[0] if row and row[0] else None
    except Exception:
        return None


def recent_fallbacks(hours=36):
    """Fallbacks to the metered API mean we are publishing, but degraded."""
    if not os.path.exists(FALLBACK_LOG):
        return []
    cutoff = datetime.now() - timedelta(hours=hours)
    hits = []
    try:
        with open(FALLBACK_LOG, encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    if datetime.fromisoformat(rec["ts"]) >= cutoff:
                        hits.append(rec)
                except Exception:
                    continue
    except Exception:
        return []
    return hits


def main():
    now = datetime.now()
    overdue, healthy, unreachable = [], [], []

    for vertical, cfg in LIVE_BRANDS.items():
        try:
            newest, count = newest_published(cfg["feed"])
        except Exception as exc:
            unreachable.append((cfg["brand"], str(exc)[:120]))
            continue

        if newest is None:
            overdue.append((cfg["brand"], None, cfg, None))
            continue

        age_days = (now - newest.replace(tzinfo=None)).days
        db_newest = newest_in_db(vertical)
        record = (cfg["brand"], age_days, cfg, db_newest)
        (overdue if age_days > cfg["grace_days"] else healthy).append(record)

    lines = [f"Publish watchdog — {now:%Y-%m-%d %H:%M}"]

    for brand, age, cfg, db_newest in overdue:
        age_txt = "no episodes in feed" if age is None else f"{age} days stale"
        line = f"OVERDUE — {brand}: {age_txt} (publishes {cfg['cadence']})"
        # The critical distinction: did production stop, or did shipping stop?
        if db_newest and age is not None:
            try:
                db_age = (now - datetime.fromisoformat(db_newest)).days
                if db_age < age - 1:
                    line += f" — episode exists in the database ({db_age}d old) but never shipped"
                else:
                    line += " — nothing produced upstream; the writing stage is failing"
            except Exception:
                pass
        lines.append(line)

    for brand, err in unreachable:
        lines.append(f"UNREACHABLE — {brand}: {err}")

    for brand, age, cfg, _ in healthy:
        lines.append(f"ok — {brand}: {age}d old (publishes {cfg['cadence']})")

    fb = recent_fallbacks()
    if fb:
        lines.append(
            f"DEGRADED — {len(fb)} call(s) fell back to the metered API in the last 36h; "
            f"latest: {fb[-1].get('reason', '')[:120]}"
        )

    report = "\n".join(lines)
    print(report)

    if overdue or unreachable:
        try:
            sys.path.insert(0, BASE_DIR)
            from run_background import notify_mattermost
            notify_mattermost("alerts", "**PUBLISH WATCHDOG**\n```\n" + report + "\n```")
        except Exception as exc:
            print(f"(could not send alert: {exc})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

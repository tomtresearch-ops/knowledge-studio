"""
Late Career / Second Act (50-65) Brief — Collectors
Imports shared collectors and configures stage-specific sources.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import collect_all_for_stage

# ============================================================
# STAGE-SPECIFIC CONFIGURATION
# ============================================================

STAGE_NAME = "Late Career / Second Act (50-65)"
VERTICAL_ID = "lifestage_late_career"

PUBMED_QUERIES = [
    "career transition older workers",
    "age discrimination employment",
    "encore career research",
    "phased retirement",
    "mentoring effectiveness",
    "lifelong learning older adults",
    "workforce participation seniors",
    "skill updating mature workers",
    "entrepreneurship older adults",
    "bridge employment",
]

RSS_FEEDS = {
    "AARP Research": "https://www.aarp.org/content/dam/aarp/rss/aarp_health.xml",
    "Next Avenue": "https://www.nextavenue.org/feed/",
    "Harvard Business Review": "https://feeds.hbr.org/harvardbusiness",
    "Forbes Retirement": "https://www.forbes.com/retirement/feed/",
}

SUBREDDITS = [
    "retirement",
    "financialindependence",
    "Boomer",
    "over50",
    "careerguidance",
]

HN_QUERIES = [
    "career after 50",
    "age discrimination tech",
    "retirement planning",
    "encore career",
    "AI older workers",
    "lifelong learning",
]


# ============================================================
# COLLECT FUNCTION
# ============================================================

def collect_all(
    vertical: str = VERTICAL_ID,
    hours_back: int = 24,
    db_path: str = None,
    youtube_api_key: str = None,
) -> dict:
    """
    Collect all signals for Late Career / Second Act (50-65).
    youtube_api_key accepted for interface compatibility but not used.
    """
    if db_path is None:
        db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "youtube_intelligence.db"
        )

    return collect_all_for_stage(
        stage_name=STAGE_NAME,
        pubmed_queries=PUBMED_QUERIES,
        rss_feeds=RSS_FEEDS,
        hn_queries=HN_QUERIES,
        subreddits=SUBREDDITS,
        hours_back=hours_back,
        db_path=db_path,
    )


if __name__ == "__main__":
    import json
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "youtube_intelligence.db"
    )
    results = collect_all(hours_back=24, db_path=DB_PATH)
    print(json.dumps(results, indent=2, default=str))

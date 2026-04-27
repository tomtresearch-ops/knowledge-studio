"""
Retirement / Seniors (65+) Brief — Collectors
Imports shared collectors and configures stage-specific sources.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import collect_all_for_stage

# ============================================================
# STAGE-SPECIFIC CONFIGURATION
# ============================================================

STAGE_NAME = "Retirement / Seniors (65+)"
VERTICAL_ID = "lifestage_seniors"

PUBMED_QUERIES = [
    "aging technology adoption",
    "digital literacy seniors",
    "social isolation older adults technology",
    "telehealth elderly",
    "AI assistive technology",
    "cognitive engagement retirement",
    "senior entrepreneurship",
    "intergenerational technology",
    "elder care technology",
    "health technology wearables seniors",
]

RSS_FEEDS = {
    "AARP Technology": "https://www.aarp.org/content/dam/aarp/rss/aarp_tech.xml",
    "New Atlas Health": "https://newatlas.com/health-wellbeing/rss/",
    "Medical Xpress Aging": "https://medicalxpress.com/rss-feed/search/?search=aging",
    "Next Avenue Technology": "https://www.nextavenue.org/feed/",
}

SUBREDDITS = [
    "retirement",
    "AskOldPeople",
    "eldercare",
    "aging",
]

HN_QUERIES = [
    "technology seniors",
    "AI elderly",
    "retirement technology",
    "digital literacy older adults",
    "health tech wearables",
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
    Collect all signals for Retirement / Seniors (65+).
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

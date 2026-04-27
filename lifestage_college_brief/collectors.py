"""
College (18-22) Brief — Collectors
Imports shared collectors and configures stage-specific sources.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import collect_all_for_stage

# ============================================================
# STAGE-SPECIFIC CONFIGURATION
# ============================================================

STAGE_NAME = "College (18-22)"
VERTICAL_ID = "lifestage_college"

PUBMED_QUERIES = [
    "higher education outcomes",
    "career readiness college",
    "student mental health university",
    "internship effectiveness",
    "major selection career outcomes",
    "graduate employment",
    "student loan research",
    "AI higher education",
    "online education outcomes",
    "skill development college",
]

RSS_FEEDS = {
    "Inside Higher Ed": "https://www.insidehighered.com/rss/feed",
    "Chronicle of Higher Education": "https://www.chronicle.com/feed",
    "Education Week Higher Ed": "https://www.edweek.org/rss/teaching-learning.xml",
}

SUBREDDITS = [
    "college",
    "cscareerquestions",
    "GetEmployed",
    "gradadmissions",
    "LifeAfterSchool",
]

HN_QUERIES = [
    "college degree value",
    "career AI era",
    "internship",
    "new grad job market",
    "learn AI",
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
    Collect all signals for College (18-22).
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

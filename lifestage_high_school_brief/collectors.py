"""
High School (14-18) Brief — Collectors
Imports shared collectors and configures stage-specific sources.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import collect_all_for_stage

# ============================================================
# STAGE-SPECIFIC CONFIGURATION
# ============================================================

STAGE_NAME = "High School (14-18)"
VERTICAL_ID = "lifestage_high_school"

PUBMED_QUERIES = [
    "adolescent career development",
    "college readiness research",
    "vocational education",
    "adolescent mental health",
    "teen independence",
    "academic motivation high school",
    "gap year outcomes",
    "apprenticeship youth",
    "financial literacy teens",
    "AI education secondary",
]

RSS_FEEDS = {
    "Education Week": "https://www.edweek.org/rss/teaching-learning.xml",
    "Inside Higher Ed": "https://www.insidehighered.com/rss/feed",
    "Hechinger Report": "https://hechingerreport.org/feed/",
    "College Board News": "https://newsroom.collegeboard.org/rss.xml",
}

SUBREDDITS = [
    "ParentingTeens",
    "ApplyingToCollege",
    "college",
    "highschool",
]

HN_QUERIES = [
    "college value AI era",
    "teen career planning",
    "high school education",
    "vocational training",
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
    Collect all signals for High School (14-18).
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

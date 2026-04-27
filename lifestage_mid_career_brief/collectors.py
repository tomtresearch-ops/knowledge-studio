"""
Mid Career (30-50) Brief — Collectors
Imports shared collectors and configures stage-specific sources.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import collect_all_for_stage

# ============================================================
# STAGE-SPECIFIC CONFIGURATION
# ============================================================

STAGE_NAME = "Mid Career (30-50)"
VERTICAL_ID = "lifestage_mid_career"

PUBMED_QUERIES = [
    "career transitions midlife",
    "leadership development",
    "mid-career skill obsolescence",
    "work identity midlife",
    "career plateau research",
    "executive development",
    "workplace automation impact",
    "career reinvention",
    "professional burnout mid-career",
    "intergenerational workplace",
]

RSS_FEEDS = {
    "Harvard Business Review": "https://feeds.hbr.org/harvardbusiness",
    "McKinsey Insights": "https://www.mckinsey.com/rss/insights",
    "MIT Sloan Management Review": "https://sloanreview.mit.edu/feed/",
    "Fast Company Leadership": "https://www.fastcompany.com/section/leadership/rss",
}

SUBREDDITS = [
    "ExperiencedDevs",
    "careerguidance",
    "Entrepreneur",
    "smallbusiness",
    "managers",
]

HN_QUERIES = [
    "career change",
    "mid career pivot",
    "management AI",
    "leadership",
    "automation jobs",
    "career strategy",
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
    Collect all signals for Mid Career (30-50).
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

"""
Elementary (6-10) Brief — Collectors
Imports shared collectors and configures stage-specific sources.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import collect_all_for_stage

# ============================================================
# STAGE-SPECIFIC CONFIGURATION
# ============================================================

STAGE_NAME = "Elementary (6-10)"
VERTICAL_ID = "lifestage_elementary"

PUBMED_QUERIES = [
    "elementary education research",
    "reading development children",
    "STEM education primary school",
    "child cognitive development 6-10",
    "homework effectiveness elementary",
    "gifted education",
    "social emotional learning elementary",
    "physical activity child cognition",
    "mathematics learning children",
    "creativity education",
]

RSS_FEEDS = {
    "Education Week": "https://www.edweek.org/rss/teaching-learning.xml",
    "Hechinger Report": "https://hechingerreport.org/feed/",
    "ScienceDaily Child Development": "https://www.sciencedaily.com/rss/mind_brain/child_development.xml",
}

SUBREDDITS = [
    "Parenting",
    "ScienceBasedParenting",
    "Teachers",
    "education",
]

HN_QUERIES = [
    "elementary education AI",
    "children technology",
    "education research",
    "homeschool",
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
    Collect all signals for Elementary (6-10).
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

"""
Middle School (11-13) Brief — Collectors
Imports shared collectors and configures stage-specific sources.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import collect_all_for_stage

# ============================================================
# STAGE-SPECIFIC CONFIGURATION
# ============================================================

STAGE_NAME = "Middle School (11-13)"
VERTICAL_ID = "lifestage_middle_school"

PUBMED_QUERIES = [
    "adolescent development early",
    "puberty psychology",
    "social media effects adolescents",
    "cyberbullying prevention",
    "middle school transition",
    "identity formation adolescence",
    "peer influence tween",
    "executive function adolescent",
    "sleep adolescent development",
    "digital literacy youth",
]

RSS_FEEDS = {
    "Education Week": "https://www.edweek.org/rss/teaching-learning.xml",
    "Common Sense Media": "https://www.commonsensemedia.org/rss.xml",
    "ScienceDaily Adolescence": "https://www.sciencedaily.com/rss/mind_brain/child_development.xml",
}

SUBREDDITS = [
    "Parenting",
    "MiddleSchool",
    "internetparents",
    "AskParents",
]

HN_QUERIES = [
    "social media teens",
    "adolescent development",
    "middle school education",
    "kids online safety",
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
    Collect all signals for Middle School (11-13).
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

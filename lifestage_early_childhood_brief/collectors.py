"""
Early Childhood (0-5) Brief — Collectors
Imports shared collectors and configures stage-specific sources.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import collect_all_for_stage

# ============================================================
# STAGE-SPECIFIC CONFIGURATION
# ============================================================

STAGE_NAME = "Early Childhood (0-5)"
VERTICAL_ID = "lifestage_early_childhood"

PUBMED_QUERIES = [
    "infant development",
    "toddler cognition",
    "screen time children under 5",
    "play-based learning",
    "early childhood education",
    "developmental milestones",
    "language acquisition toddler",
    "attachment parenting",
    "sensory development infant",
    "preschool readiness",
]

RSS_FEEDS = {
    "Education Week Early Childhood": "https://www.edweek.org/rss/early-childhood.xml",
    "ScienceDaily Child Development": "https://www.sciencedaily.com/rss/mind_brain/child_development.xml",
    "Medical Xpress Pediatrics": "https://medicalxpress.com/rss-feed/search/?search=pediatrics",
}

SUBREDDITS = [
    "NewParents",
    "toddlers",
    "Parenting",
    "ScienceBasedParenting",
    "preschool",
]

HN_QUERIES = [
    "early childhood education",
    "screen time children",
    "child development",
    "AI education kids",
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
    Collect all signals for Early Childhood (0-5).
    youtube_api_key accepted for interface compatibility but not used (no YT search).
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

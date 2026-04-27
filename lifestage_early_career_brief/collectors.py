"""
Early Career (22-30) Brief — Collectors
Redesigned with purpose-built signal sources for career-stage intelligence.
PubMed minimized. Industry analysis, workforce data, and community signal prioritized.
YouTube headline scanner for career/AI-focused creators.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import collect_all_for_stage

# ============================================================
# STAGE-SPECIFIC CONFIGURATION
# ============================================================

STAGE_NAME = "Early Career (22-30)"
VERTICAL_ID = "lifestage_early_career"

# YouTube channel list for headline scanning (career/AI-focused creators)
YOUTUBE_CHANNELS_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_channels.json")

# ---- PubMed: MINIMAL — only workplace psychology, not the anchor ----
PUBMED_QUERIES = [
    "workplace burnout young professionals",
    "AI adoption workforce productivity",
    "career adaptability artificial intelligence",
]

# ---- RSS Feeds: PRIMARY SIGNAL — industry analysis + workforce data ----
RSS_FEEDS = {
    # Tier 1: Industry analysis (highest weight)
    "MIT Sloan Management Review": "https://sloanreview.mit.edu/feed/",
    "Harvard Business Review": "https://hbr.org/resources/xml/rss.xml",
    "Fast Company": "https://www.fastcompany.com/latest/rss",
    "TechCrunch": "https://techcrunch.com/feed/",
    # Tier 1: Workforce data
    "Indeed Hiring Lab": "https://www.hiringlab.org/feed/",
    "BLS Monthly Labor Review": "https://www.bls.gov/feed/mlr.rss",
    "BLS Employment": "https://www.bls.gov/feed/emp.rss",
    "Pew Research": "https://www.pewresearch.org/feed/",
    # Tier 2: AI + work voices
    "Ethan Mollick — One Useful Thing": "https://www.oneusefulthing.org/feed",
    "Pragmatic Engineer": "https://newsletter.pragmaticengineer.com/feed",
    "Exponential View": "https://www.exponentialview.co/feed",
    # Tier 3: Narrative/editorial
    "Kyla Scanlon": "https://kylascanlon.substack.com/feed",
    "Scott Galloway": "https://www.profgalloway.com/feed/",
    "Stratechery": "https://stratechery.com/feed/",
    "Stack Overflow Blog": "https://stackoverflow.blog/feed/",
}

# ---- Reddit: HIGH-VALUE — real people, real-time career anxiety ----
SUBREDDITS = [
    "careerguidance",
    "cscareerquestions",
    "jobs",
    "personalfinance",
    "LifeAfterSchool",
    "ExperiencedDevs",
]

# ---- HN: Sharpened queries for career + AI workforce signal ----
HN_QUERIES = [
    "AI replacing jobs",
    "entry level hiring",
    "career advice AI",
    "layoffs automation",
    "skills AI era",
    "remote work AI tools",
    "junior developer AI",
    "workforce automation",
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
    Collect all signals for Early Career (22-30).
    Redesigned source hierarchy: Industry analysis > Community > YouTube > PubMed.
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
        youtube_channels_json=YOUTUBE_CHANNELS_JSON,
        youtube_api_key=youtube_api_key or os.environ.get("YOUTUBE_API_KEY", ""),
    )


if __name__ == "__main__":
    import json
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "youtube_intelligence.db"
    )
    results = collect_all(hours_back=72, db_path=DB_PATH)
    print(json.dumps(results, indent=2, default=str))

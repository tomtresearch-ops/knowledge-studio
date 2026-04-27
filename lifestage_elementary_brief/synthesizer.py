"""
Elementary (6-10) Brief — Synthesizer
Takes collected signals and produces a structured brief using Claude Haiku.
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional
from anthropic import Anthropic

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import (
    prepare_signal_digest,
    get_previous_brief,
    build_dedup_section,
)

VERTICAL_ID = "lifestage_elementary"


def synthesize_brief(collected_data: dict,
                     vertical: str = VERTICAL_ID,
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured Elementary brief.
    If previous_brief is None, automatically fetches the most recent one from DB.
    """
    client = Anthropic(api_key=api_key) if api_key else Anthropic()

    digest = prepare_signal_digest(collected_data)
    today = datetime.now().strftime("%B %d, %Y")

    source_counts = {k: len(v) for k, v in collected_data.get("sources", {}).items()}
    total = sum(source_counts.values())

    # Auto-fetch previous brief for dedup if not provided
    if previous_brief is None:
        previous_brief = get_previous_brief(vertical)

    dedup_section = build_dedup_section(previous_brief)

    prompt = f"""You are an education intelligence analyst producing a daily brief for parents of children ages 6-10. Your readers are navigating school systems, homework battles, and their child's first real exposure to technology. They want practical, grounded guidance backed by research — not ideological takes on education. They're the parents whose kid's school just gave them a Chromebook. They need to know what the research says about how to make that work.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}

Your job: synthesize these raw signals into a practical, grounded brief. Your kid's school just gave them a Chromebook. Here's what the research says about how to make that work.

## SOURCE HIERARCHY
1. Research (PubMed papers) — primary evidence, highest weight
2. News aggregators (RSS feeds) — context and coverage
3. Community (Reddit, HN) — parent and teacher sentiment, real-world experience
4. Cross-vertical context — if recent AI or Health brief findings are relevant to parents at this stage, reference them naturally

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# ELEMENTARY BRIEF — {today}

## TARGET SIGNAL
The single most important finding or development today for parents of 6-10 year olds. 2-3 sentences. Why this matters for your child's learning and development right now.

## RESEARCH
3-5 items from PubMed/aggregators. For each:
- **Bold finding headline** — 1-2 sentence analysis. What does this mean for your child's education? Is it confirmatory, novel, or does it challenge what their school is doing?
- Include the source URL on a new line.
- Note the evidence level — peer-reviewed study vs preliminary finding matters.

## THIS WEEK
2-3 actionable items parents can actually use. Specific, practical, grounded in evidence. Not generic "help with homework" advice — real intelligence about what's changing in education, what works, what doesn't, and what you should be asking your child's teacher about.

## BIGGER PICTURE
2-3 observations connecting dots across signals. How do this week's findings fit into the larger story of elementary education? What converging trends should parents be watching? Always connect to how rapid technological change (AI in classrooms, adaptive learning tools, screen exposure) intersects with how 6-10 year olds actually learn.

## WORTH YOUR TIME
2-3 items worth deeper reading. Brief note on why each matters. Include URLs.

## RULES
- Research first. PubMed findings anchor the brief. Community discussion is context, not the story.
- Be practical and grounded — these parents are dealing with real school systems, real homework battles, real decisions about tech exposure.
- Be precise about evidence levels: distinguish between observational study, RCT, meta-analysis, and expert consensus.
- Note if something is a preprint (not yet peer-reviewed).
- Translate education jargon: "social-emotional learning" becomes "teaching kids to manage emotions, work with others, and make good decisions."
- Be opinionated but evidence-grounded. "This matters because..." not "Some researchers think..."
- If recent AI or Health brief findings are relevant to parents at this stage, reference them naturally — don't force it.
- Keep the entire brief under 800 words. Density over length.
- If signals are thin or redundant, say so honestly rather than padding.
- For YouTube links, ALWAYS format as a markdown link with title and channel: [Video Title — Channel Name](url). Never output bare YouTube URLs.
- For non-YouTube URLs (papers, articles), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating elementary brief ({total} signals -> Claude Haiku)...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    brief = response.content[0].text

    # Add metadata footer
    brief += f"\n\n---\n*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Sources: {total} signals across {len(source_counts)} sources*"

    print(f"[Synthesizer] Brief generated ({len(brief)} chars)")
    return brief


def generate_daily_brief(vertical: str = VERTICAL_ID,
                         hours_back: int = 24,
                         db_path: str = None,
                         youtube_api_key: str = None,
                         anthropic_api_key: str = None,
                         output_dir: str = None) -> str:
    """
    Full pipeline: collect -> synthesize -> save.
    Returns the brief text.
    """
    from collectors import collect_all

    # Step 1: Collect
    collected = collect_all(
        vertical=vertical,
        hours_back=hours_back,
        db_path=db_path,
        youtube_api_key=youtube_api_key,
    )

    # Step 2: Synthesize
    brief = synthesize_brief(collected, vertical=vertical, api_key=anthropic_api_key)

    # Step 3: Save
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y-%m-%d")
        filename = f"{date_str}_{vertical}_brief.md"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w") as f:
            f.write(brief)
        print(f"\n[Brief] Saved to: {filepath}")

    return brief


if __name__ == "__main__":
    DB_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "youtube_intelligence.db"
    )
    OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

    brief = generate_daily_brief(
        vertical=VERTICAL_ID,
        hours_back=24,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)

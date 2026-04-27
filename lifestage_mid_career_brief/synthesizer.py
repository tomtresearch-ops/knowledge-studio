"""
Mid Career (30-50) Brief — Synthesizer
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

VERTICAL_ID = "lifestage_mid_career"


def synthesize_brief(collected_data: dict,
                     vertical: str = VERTICAL_ID,
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured Mid Career brief.
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

    prompt = f"""You are a career strategy analyst producing a daily brief for established professionals ages 30-50 navigating career evolution. Your readers have built something — expertise, teams, reputations — and now the ground is shifting under them. They're managing people, making real decisions, possibly raising kids simultaneously. They don't need career basics; they need strategic intelligence.

Your editorial voice: Strategic peer — "You spent 15 years becoming an expert. Here's what the research says about how AI is changing what 'expert' means — and three ways to stay ahead of it."

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}

Your job: synthesize these raw signals into a sharp, evidence-grounded brief that helps mid-career professionals make strategic decisions about leadership, skill evolution, career pivots, and navigating organizational change during an AI transformation.

## SOURCE HIERARCHY
1. Research (PubMed papers, workforce studies) — primary evidence, highest weight
2. News aggregators (HBR, McKinsey, MIT Sloan) — expert analysis and strategic context
3. Community (Reddit, HN) — real-world experience from people managing teams, making career transitions, running businesses
4. Cross-vertical context — if recent AI or Health brief findings are relevant to people at this career stage, reference them naturally

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# MID CAREER BRIEF — {today}

## TARGET SIGNAL
The single most important finding or development today for mid-career professionals. 2-3 sentences. Why this matters for someone who's invested years building expertise and now needs to evolve.

## RESEARCH
3-5 items from PubMed/aggregators/workforce data. For each:
- **Bold finding headline** — 1-2 sentence analysis. What does this mean for someone managing a team, leading a department, or considering a pivot? Is this a strategic opportunity, a threat to prepare for, or a shift to ride?
- Include the source URL on a new line.
- Note the evidence level — peer-reviewed study vs industry report vs consulting firm analysis.

## ACTIONABLE
2-3 things you can do this week or this month based on today's signals. Specific and strategic — not "upskill" but "here's what the data says about which leadership capabilities are becoming more valuable as AI handles more analytical work." Grounded in research, not thought-leadership buzzwords.

## BIGGER PICTURE
2-3 observations connecting dots across signals. How do today's findings fit into the larger story of mid-career professionals navigating AI transformation? What converging trends should you be watching as someone with both organizational leverage and career runway? "Three signals this week converge on [insight about leadership/expertise/career strategy]..."

## WORTH YOUR TIME
2-3 items worth deeper reading. Brief note on why each matters for someone at this career stage. Include URLs.

## RULES
- Research first. Workforce studies and PubMed findings anchor the brief. Community discussion is context, not the story.
- Be strategic and direct — these readers are decision-makers. They can handle complexity and nuance.
- Be precise about evidence levels: distinguish between large-scale workforce studies, organizational research, industry surveys, and consulting firm reports.
- Note if something is a preprint (not yet peer-reviewed).
- Write for someone who knows what organizational dynamics, change management, and strategic positioning mean. High context assumed.
- Be opinionated but evidence-grounded. "This matters because..." not "Some thought leaders suggest..."
- Respect the time pressure — these people are juggling leadership, family, and self-development. Every sentence must earn its place.
- If recent AI or Health brief findings are relevant to people at this career stage, reference them naturally — don't force it.
- Keep the entire brief under 800 words. Density over length.
- If signals are thin or redundant, say so honestly rather than padding.
- For YouTube links, ALWAYS format as a markdown link with title and channel: [Video Title — Channel Name](url). Never output bare YouTube URLs.
- For non-YouTube URLs (papers, articles), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating mid career brief ({total} signals -> Claude Haiku)...")

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

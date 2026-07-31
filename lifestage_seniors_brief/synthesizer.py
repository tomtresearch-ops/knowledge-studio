"""
Retirement / Seniors (65+) Brief — Synthesizer
Takes collected signals and produces a structured brief using Claude Haiku.
"""

import json
import os
import sys
from datetime import datetime
from typing import Optional
from claude_cli_client import make_client as Anthropic  # subscription, not metered API

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lifestage_shared_collectors import (
    prepare_signal_digest,
    get_previous_brief,
    build_dedup_section,
)

VERTICAL_ID = "lifestage_seniors"


def synthesize_brief(collected_data: dict,
                     vertical: str = VERTICAL_ID,
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured Seniors brief.
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

    prompt = f"""You are a technology and wellness intelligence analyst producing a daily brief for retirees and active seniors (65+). Your readers are not a monolith — many are sharp, curious, and determined to stay connected, independent, and mentally engaged. They want to understand how technology, especially AI, can serve them — not replace them or leave them behind.

Your editorial voice: Warm, inclusive, empowering. "AI isn't just for your grandkids. Here's what the latest research says about how seniors are using AI tools to stay independent, connected, and mentally sharp."

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}

Your job: synthesize these raw signals into a warm, clear, evidence-grounded brief that helps seniors understand how technology and health research intersect with their daily lives — staying independent, staying sharp, staying connected, and making the most of this chapter.

## SOURCE HIERARCHY
1. Research (PubMed papers, health studies, technology adoption research) — primary evidence, highest weight
2. News aggregators (AARP, New Atlas, Medical Xpress, Next Avenue) — trusted sources that cover aging and technology
3. Community (Reddit, HN) — real-world experience from seniors and caregivers
4. Cross-vertical context — if recent AI or Health brief findings are relevant to seniors, reference them naturally

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# SENIORS BRIEF — {today}

## TARGET SIGNAL
The single most important finding or development today for seniors. 2-3 sentences. Why this matters for staying independent, healthy, connected, or mentally engaged.

## RESEARCH
3-5 items from PubMed/aggregators/health data. For each:
- **Bold finding headline** — 1-2 sentence analysis. What does this mean for seniors? Is this a new tool to try, a health finding to act on, or a trend that changes how we think about aging and technology?
- Include the source URL on a new line.
- Note the evidence level — peer-reviewed study vs industry report vs preliminary finding.

## ACTIONABLE
2-3 things you can do this week based on today's signals. Specific and accessible — not "adopt AI" but "here's a specific AI tool that can help you [manage medications / stay in touch with family / exercise safely], and here's how the research says it actually helps." Grounded in evidence, described clearly without jargon.

## BIGGER PICTURE
2-3 observations connecting dots across signals. How do today's findings fit into the larger story of technology serving seniors rather than excluding them? What converging trends should you be aware of? "Three signals this week point to [insight about aging, technology, independence, health]..."

## WORTH YOUR TIME
2-3 items worth deeper reading. Brief note on why each matters. Include URLs.

## RULES
- Research first. PubMed findings and health technology studies anchor the brief. Community discussion is context, not the story.
- Be warm and inclusive — but NEVER condescending. Write for intelligent adults who happen to be older, not for people who need hand-holding.
- Explain technical concepts clearly without being patronizing. Assume curiosity and capability.
- Be precise about evidence levels: distinguish between clinical trials, observational studies, technology adoption surveys, and anecdotal reports.
- Note if something is a preprint (not yet peer-reviewed).
- Health findings are especially relevant for this audience — always connect technology to health outcomes, independence, and quality of life when the data supports it.
- Be opinionated but evidence-grounded. "This matters because..." not "Some experts believe..."
- If recent AI or Health brief findings are relevant to seniors, reference them naturally — these cross-vertical connections are especially valuable here.
- Keep the entire brief under 800 words. Density over length.
- If signals are thin or redundant, say so honestly rather than padding.
- For YouTube links, ALWAYS format as a markdown link with title and channel: [Video Title — Channel Name](url). Never output bare YouTube URLs.
- For non-YouTube URLs (papers, articles), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating seniors brief ({total} signals -> Claude Haiku)...")

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

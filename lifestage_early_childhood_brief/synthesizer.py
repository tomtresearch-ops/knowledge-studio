"""
Early Childhood (0-5) Brief — Synthesizer
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

VERTICAL_ID = "lifestage_early_childhood"


def synthesize_brief(collected_data: dict,
                     vertical: str = VERTICAL_ID,
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured Early Childhood brief.
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

    prompt = f"""You are a child development intelligence analyst producing a daily brief for parents of children ages 0-5. Your readers are thoughtful, anxious, time-starved parents of infants, toddlers, and preschoolers. They trust research over mommy blogs, but they need it translated into plain language they can act on.

Your unique lens — and the reason this brief exists — is that the world your child will grow up into is fundamentally different from the one you grew up in. AI, automation, and rapid technological change are reshaping what skills matter, what jobs exist, and how humans live. Your job is to work backwards from that future: what will the world look like when today's 3-year-old is 25? What does that mean for how you raise them RIGHT NOW, at the most neuroplastic stage of their life?

This is not an "AI parenting" newsletter. It's a child development brief with an AI-era interpretation layer. Core developmental science (attachment, language acquisition, play, motor skills) is the foundation — but always interpreted through the lens of: what's different now? Where can AI and technology FACILITATE your child's growth (e.g., AI reading companions, personalized learning tools, ensuring adequate word exposure)? Where can it DEBILITATE it (e.g., passive screen time replacing exploration, algorithmic content replacing human interaction)?

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}

## SOURCE HIERARCHY
1. Research (PubMed papers) — primary evidence, highest weight
2. News aggregators (RSS feeds) — context and coverage
3. Community (Reddit, HN) — parent sentiment and real-world experience
4. Cross-vertical context — if recent AI or Health brief findings are relevant to parents at this stage, weave them in

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# EARLY CHILDHOOD BRIEF — {today}

## TARGET SIGNAL
The single most important finding or development today for parents of 0-5 year olds. 2-3 sentences. Why this matters for your child's development — and how the changing world makes it more or less urgent.

## RESEARCH
3-5 items from PubMed/aggregators. For each:
- **Bold finding headline** — 1-2 sentence analysis. What does this mean for your child? Is it confirmatory, novel, or does it challenge conventional wisdom? Where relevant, connect to the AI-era context.
- Include the source URL on a new line.
- Note the evidence level — peer-reviewed study vs preliminary finding matters.

## THIS WEEK
2-3 actionable items parents can actually use. Specific, practical, grounded in what the research says. Not generic "read to your child" advice — real intelligence. Include at least one item about how AI/tech tools can help or hurt at this stage, when the signals support it.

## BIGGER PICTURE
2-3 observations connecting dots across signals. The core question: what kind of world is your child growing into, and what does this week's evidence tell you about how to prepare them? What capabilities will matter most? What's changing about childhood itself?

## WORTH YOUR TIME
2-3 items worth deeper reading. Brief note on why each matters. Include URLs.

## RULES
- Research first. PubMed findings anchor the brief. Community discussion is context, not the story.
- Be warm and reassuring — parents of tiny humans are anxious. Don't add to it. Frame findings as empowering, not scary.
- The AI-era lens should feel natural, not forced. If a finding is pure developmental science with no tech angle, that's fine — present it as foundational. But always ask: does knowing the future is AI-shaped change how we interpret this?
- Be precise about evidence levels: distinguish between observational study, RCT, and meta-analysis.
- Note if something is a preprint (not yet peer-reviewed).
- Translate jargon: "executive function" becomes "your child's ability to focus, remember instructions, and control impulses."
- Be opinionated but evidence-grounded. "This matters because..." not "Some researchers think..."
- Target 1500-2000 words. This brief feeds podcast and video production — give the editorial agent substance to work with. Density over padding, but don't artificially compress.
- If signals are thin or redundant, say so honestly rather than padding.
- For YouTube links, ALWAYS format as a markdown link with title and channel: [Video Title — Channel Name](url). Never output bare YouTube URLs.
- For non-YouTube URLs (papers, articles), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating early childhood brief ({total} signals -> Claude Haiku)...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4000,
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

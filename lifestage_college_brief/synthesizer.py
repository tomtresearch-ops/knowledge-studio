"""
College (18-22) Brief — Synthesizer
Takes collected signals and produces a structured brief using Claude Haiku.
DUAL AUDIENCE: college students themselves AND their parents.
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

VERTICAL_ID = "lifestage_college"


def synthesize_brief(collected_data: dict,
                     vertical: str = VERTICAL_ID,
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured College brief.
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

    prompt = f"""You are a higher education and career intelligence analyst producing a daily brief for a DUAL audience: college students (18-22) themselves AND their parents. College students don't want to be talked down to. Parents want actionable intelligence. This is the most acute crisis point in the education pipeline: expensive decisions being made on rapidly shifting ground. You're paying $50K/year for a degree. Here's what the latest employment data says about your major's ROI, and how AI just changed the calculation.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}

Your job: synthesize these raw signals into a direct, no-BS brief. You're paying $50K/year for a degree. Here's what the latest employment data says about your major's ROI, and how AI just changed the calculation.

## SOURCE HIERARCHY
1. Research (PubMed papers, education research) — primary evidence, highest weight
2. News aggregators (RSS feeds) — context on higher ed policy, employment trends, industry shifts
3. Community (Reddit, HN) — real-world experience from current students, recent grads, hiring managers
4. Cross-vertical context — if recent AI or Health brief findings are relevant to college students or their parents, reference them naturally

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# COLLEGE BRIEF — {today}

## TARGET SIGNAL
The single most important finding or development today for college students and their parents. 2-3 sentences. Why this matters for the $50K+ decision being made right now.

## RESEARCH
3-5 items from PubMed/aggregators. For each:
- **Bold finding headline** — 1-2 sentence analysis. What does this mean for major selection, career planning, or the value of the degree itself? Is it confirmatory, novel, or does it upend conventional wisdom?
- Include the source URL on a new line.
- Note the evidence level — peer-reviewed study vs preliminary finding matters.

## THIS WEEK
2-3 actionable items students or parents can actually use. Specific, strategic, grounded in evidence. Not generic "network more" advice — real intelligence about which internships actually convert to jobs, what employers are actually hiring for, which skills to stack alongside a major, or what the latest data says about student loan strategies.

## BIGGER PICTURE
2-3 observations connecting dots across signals. How do this week's findings fit into the larger story of higher education's transformation? What converging trends should students and parents be watching? Always connect to how rapid technological change (AI automating entry-level knowledge work, new credentialing models, remote work reshaping career geography) intersects with the decisions being made on campus right now.

## WORTH YOUR TIME
2-3 items worth deeper reading. Brief note on why each matters. Include URLs.

## RULES
- Research first. Education research and employment data anchor the brief. Community discussion is context, not the story.
- Be direct and no-BS — college students see through fluff instantly. Parents are spending real money and want real answers.
- Address both audiences naturally: some findings matter more to the student (mental health, skill-building), some to the parent (ROI, employment outcomes, loan strategy). Don't awkwardly split them — just write clearly and both audiences will find what they need.
- Be precise about evidence levels: distinguish between observational study, RCT, longitudinal study, meta-analysis, and labor market data.
- Note if something is a preprint (not yet peer-reviewed).
- Career and major advice MUST be contextualized against the AI/automation landscape. Recommending a major without considering AI disruption risk is malpractice in 2025+.
- Be opinionated but evidence-grounded. "This matters because..." not "Some researchers think..."
- Student mental health research is critical signal — don't bury it. This age group is in crisis and the data matters.
- If recent AI or Health brief findings are relevant, reference them naturally — don't force it.
- Keep the entire brief under 800 words. Density over length.
- If signals are thin or redundant, say so honestly rather than padding.
- For YouTube links, ALWAYS format as a markdown link with title and channel: [Video Title — Channel Name](url). Never output bare YouTube URLs.
- For non-YouTube URLs (papers, articles), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating college brief ({total} signals -> Claude Haiku)...")

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

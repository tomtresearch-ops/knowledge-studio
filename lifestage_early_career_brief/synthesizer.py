"""
Early Career (22-30) Brief — Synthesizer
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

VERTICAL_ID = "lifestage_early_career"


def synthesize_brief(collected_data: dict,
                     vertical: str = VERTICAL_ID,
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured Early Career brief.
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

    prompt = f"""You are a career intelligence analyst producing a weekly brief for people in their first career decade (ages 22-30). Your audience is BROAD — not just tech workers. Teachers, nurses, accountants, marketing grads, business majors, tradespeople, people who just graduated and can't find a job, people two years into something wondering if it has a future. Some are parents reading this to help guide their adult child. Most of your readers don't know what an LLM is and don't care — they care about finding good work, building skills that matter, and not getting blindsided.

Your job is to help them navigate a career landscape that's changing fast. The old playbook (degree → entry-level → climb the ladder) is breaking down. Entry-level hiring is shrinking. Entire job categories are shifting. AI is part of why, but it's not the whole story — economic pressures, degree inflation, remote work shifts, and industry restructuring all play a role.

Your editorial voice: A sharp, warm friend who reads everything so they don't have to. You explain what's happening in the job market in plain language, tell people what it means for them specifically, and always give them something they can DO about it. You never assume technical knowledge. When AI is relevant, you explain it simply and focus on the practical impact — "companies are using AI to screen resumes now, which means your application strategy needs to change" not "multi-agent orchestration is shipping to production."

CRITICAL TONE RULES:
- Lead with what matters to someone looking for a job or building a career, not with AI infrastructure news
- AI is context that shapes the landscape, NOT the headline every week. Many weeks the lead story will be about hiring trends, skill demand, industry shifts, or career strategy — not AI
- When you discuss AI, ground it in everyday impact: "more companies are automating entry-level analyst tasks, which means the bar for what gets you hired is shifting toward judgment and communication" — NOT technical details about how the AI works
- This is NOT the AI brief. Do not lead with AI company announcements or technical capabilities. If Stripe ships an agent, the story for this audience is "what does this mean for entry-level hiring at companies like Stripe?" not "here's how multi-agent orchestration works"
- Cover ALL career paths, not just tech. Healthcare, education, trades, finance, marketing, government, nonprofit — the audience is everyone starting out
- Reddit community signal is GOLD — these are real people sharing real struggles. Elevate their voices.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}

## SOURCE HIERARCHY
1. Workforce data and industry analysis (Indeed, BLS, HBR, MIT Sloan, Fast Company) — what's actually happening in hiring, wages, and job markets
2. Community signal (Reddit, HN) — real people sharing real experiences. What are early-career people actually going through? This is high-value signal.
3. YouTube creator analysis — what are the sharpest career/AI voices saying this week?
4. Cross-vertical context — when AI brief findings have practical career implications, translate them into plain language
5. Research (PubMed) — workplace psychology, burnout, skill acquisition studies. Supporting evidence.

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# EARLY CAREER BRIEF — {today}

## THE HEADLINE
The single most important career signal this week. 2-3 sentences. Something that affects people looking for jobs or building careers RIGHT NOW. Lead with the human impact, not the technology.

## WHAT'S HAPPENING
3-5 items covering what's changing in the job market and career landscape. Mix of workforce data, industry shifts, community experience, and (where relevant) how technology is changing the game. For each:
- **Bold headline in plain language** — 2-3 sentence analysis. What does this mean if you're job hunting, choosing a career path, or wondering if your current path has a future?
- Include the source URL on a new line.
- Note the source type.

## WHAT YOU CAN DO
2-3 specific, concrete actions. Not "upskill" — actual steps someone can take this week. "Here's a free tool that..." or "When you're applying, try..." or "The data says this approach works better than..." Make it practical for someone who isn't technical.

## THE BIGGER PICTURE
2-3 observations connecting this week's signals to the larger shifts in how careers work. What patterns are emerging? What's the world going to look like for someone who's 25 right now by the time they're 35? Be honest about uncertainty — present scenarios, not predictions. When something is genuinely scary, pair it with what people can do about it. Never just scare people.

## WORTH YOUR TIME
2-3 items for deeper reading or watching. Include YouTube videos from creators when relevant (format as markdown links). Brief note on why each matters.

## RULES
- CAREER FIRST, ALWAYS. The reader's question is "what does this mean for my career?" not "what's new in AI?"
- Write for a broad audience. A teacher, a nurse, an accountant, and a software developer should all find value in this brief. Don't assume technical knowledge.
- When AI comes up, translate it: "Companies are using AI tools that can now do work that used to require a junior analyst. What this means for you: the skills that get you hired are shifting from 'can you run this report' to 'can you interpret what this report means and decide what to do about it.'"
- Elevate Reddit voices — real quotes from real people struggling with real career decisions are more powerful than any industry report
- Be warm but honest. These people are anxious about their futures. Don't add to the anxiety — give them clarity and agency. Every scary signal should come with "here's what you can do about it"
- Cover multiple industries and career paths, not just tech. The brief should feel relevant to anyone in their 20s.
- Be opinionated but evidence-grounded. Take positions. "Based on what we're seeing, here's what we'd recommend..." not "there are many perspectives on this issue."
- YouTube creator headlines: when a creator (Nate B Jones, DOAC, Diamandis, etc.) covered something relevant this week, reference it naturally as a recommendation, not as a primary source
- Target 1500-2000 words. This brief feeds podcast and video production — give substance but stay accessible.
- If signals are thin or redundant, say so honestly rather than padding.
- For YouTube links, ALWAYS format as a markdown link with title and channel: [Video Title — Channel Name](url). Never output bare YouTube URLs.
- For non-YouTube URLs (papers, articles), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating early career brief ({total} signals -> Claude Haiku)...")

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

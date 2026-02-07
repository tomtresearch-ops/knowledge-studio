"""
Daily Brief — Synthesizer
Takes collected signals and produces a structured daily brief using Claude.
"""

import json
import os
from datetime import datetime
from typing import Optional
from anthropic import Anthropic


def prepare_signal_digest(collected_data: dict) -> str:
    """
    Compress collected signals into a text digest for Claude to synthesize.
    Prioritizes high-signal items to stay within context limits.
    """
    sections = []

    # Hacker News — top items by signal score
    hn_items = collected_data.get("sources", {}).get("hacker_news", [])
    if hn_items:
        hn_lines = []
        for item in hn_items[:25]:  # Top 25 by score
            score = item.get("signal_score", 0)
            title = item.get("title", "")
            url = item.get("url", "")
            comments = item.get("comments", 0)
            points = item.get("points", 0)
            hn_lines.append(f"- [{points}pts, {comments}c] {title}\n  URL: {url}")
        sections.append(f"## HACKER NEWS (top {len(hn_lines)} stories)\n" + "\n".join(hn_lines))

    # Reddit — top items
    reddit_items = collected_data.get("sources", {}).get("reddit", [])
    if reddit_items:
        reddit_lines = []
        for item in reddit_items[:25]:
            title = item.get("title", "")
            sub = item.get("subreddit", "")
            url = item.get("reddit_url", item.get("url", ""))
            selftext = item.get("selftext", "")
            line = f"- [r/{sub}] {title}\n  URL: {url}"
            if selftext:
                line += f"\n  Context: {selftext[:150]}"
            reddit_lines.append(line)
        sections.append(f"## REDDIT (top {len(reddit_lines)} posts)\n" + "\n".join(reddit_lines))

    # YouTube Search
    yt_items = collected_data.get("sources", {}).get("youtube_search", [])
    if yt_items:
        yt_lines = []
        for item in yt_items[:15]:
            title = item.get("title", "")
            channel = item.get("channel", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            line = f"- [{channel}] {title}\n  URL: {url}"
            if desc:
                line += f"\n  Desc: {desc[:150]}"
            yt_lines.append(line)
        sections.append(f"## YOUTUBE ({len(yt_lines)} videos)\n" + "\n".join(yt_lines))

    # Knowledge Studio — recently processed
    ks_items = collected_data.get("sources", {}).get("knowledge_studio", [])
    if ks_items:
        ks_lines = []
        for item in ks_items[:20]:
            title = item.get("title", "")
            channel = item.get("channel", "")
            ct = item.get("content_type", "")
            summary_short = item.get("summary_short", "")
            url = item.get("url", "")
            line = f"- [{ct}] {title}"
            if channel:
                line += f" ({channel})"
            line += f"\n  URL: {url}"
            if summary_short:
                line += f"\n  Summary: {summary_short[:300]}"
            ks_lines.append(line)
        sections.append(f"## KNOWLEDGE STUDIO (recently processed)\n" + "\n".join(ks_lines))

    return "\n\n".join(sections)


def synthesize_brief(collected_data: dict,
                     vertical: str = "ai_tech",
                     api_key: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured daily brief.
    """
    client = Anthropic(api_key=api_key) if api_key else Anthropic()

    digest = prepare_signal_digest(collected_data)
    today = datetime.now().strftime("%B %d, %Y")

    source_counts = {k: len(v) for k, v in collected_data.get("sources", {}).items()}
    total = sum(source_counts.values())

    prompt = f"""You are an elite intelligence analyst producing a daily brief for a tech entrepreneur and AI strategist.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.

Your job: synthesize these raw signals into a sharp, high-value daily brief. This is NOT a news roundup — it's intelligence analysis. Connect dots, identify patterns, surface what actually matters.

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# AI & TECH DAILY BRIEF — {today}

## 🔴 TOP SIGNAL
The single most important thing today. 2-3 sentences max. Why it matters, not just what happened.

## ⚡ KEY DEVELOPMENTS
3-5 items. For each:
- **Bold headline** — 1-2 sentence analysis. Not a summary of the article — your take on why it matters, what it means, what to watch for.
- Include the source URL on a new line.

## 🔗 EMERGING PATTERNS
2-3 observations connecting dots ACROSS the signals. Things like: "Three separate signals point to X trend accelerating..." or "The gap between X and Y is widening because..."

This is where you show strategic thinking, not just reporting.

## 📚 WORTH YOUR TIME
2-3 items worth deeper reading/watching. Brief note on why. Include URLs.

## RULES
- Be opinionated. Take positions. "This matters because..." not "Some people think..."
- Prioritize actionable insight over comprehensive coverage. Miss things — that's fine. Don't be boring.
- Write for someone who's already deeply in this space. High context assumed. No explaining what an LLM is.
- Keep the entire brief under 800 words. Density over length.
- If signals are thin or redundant, say so honestly rather than padding.
- Group related developments rather than listing them separately.
- For YouTube links, ALWAYS format as a markdown link with title and channel: [Video Title — Channel Name](https://youtube.com/watch?v=...). Never output bare YouTube URLs.
- For non-YouTube URLs (HN, Reddit, blogs, etc.), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating brief ({total} signals → Claude)...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",  # Fast + cheap for daily runs
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    brief = response.content[0].text

    # Add metadata footer
    brief += f"\n\n---\n*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Sources: {total} signals across {len(source_counts)} sources*"

    print(f"[Synthesizer] Brief generated ({len(brief)} chars)")
    return brief


def generate_daily_brief(vertical: str = "ai_tech",
                         hours_back: int = 24,
                         db_path: str = None,
                         youtube_api_key: str = None,
                         anthropic_api_key: str = None,
                         output_dir: str = None) -> str:
    """
    Full pipeline: collect → synthesize → save.
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
    DB_PATH = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/youtube_intelligence.db"
    OUTPUT_DIR = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/daily_brief/output"

    # YouTube API key (same one used by youtube_processor.py)
    YT_API_KEY = "AIzaSyA5VGDmqxRfYzgab5kqcRwxtLckH35BHNQ"

    brief = generate_daily_brief(
        vertical="ai_tech",
        hours_back=24,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)

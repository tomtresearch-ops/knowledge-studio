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
        sections.append(f"## YOUTUBE SEARCH ({len(yt_lines)} videos)\n" + "\n".join(yt_lines))

    # YouTube Headlines — curated channel scan (topic signal)
    yth_items = collected_data.get("sources", {}).get("youtube_headlines", [])
    if yth_items:
        yth_lines = []
        for item in yth_items[:30]:
            title = item.get("title", "")
            channel = item.get("channel", "")
            desc = item.get("description", "")
            line = f"- [{channel}] {title}"
            if desc:
                line += f"\n  Desc: {desc[:150]}"
            yth_lines.append(line)
        sections.append(f"## YOUTUBE HEADLINES — TOPIC SIGNAL ({len(yth_lines)} recent uploads from curated channels)\n" + "\n".join(yth_lines))

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


def get_previous_brief(vertical: str = "ai_tech", db_path: str = None) -> Optional[str]:
    """Fetch the most recent brief for this vertical from the database."""
    import sqlite3
    if db_path is None:
        db_path = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/youtube_intelligence.db"
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT content FROM daily_briefs WHERE vertical = ? ORDER BY created_at DESC LIMIT 1",
            (vertical,)
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def synthesize_brief(collected_data: dict,
                     vertical: str = "ai_tech",
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured daily brief.
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

    dedup_section = ""
    if previous_brief:
        dedup_section = f"""
## PREVIOUS BRIEF (DO NOT REPEAT)

The following is the most recent brief that was already published. DO NOT repeat the same stories, findings, or framings. If a topic appeared in the previous brief:
- SKIP it entirely unless there is genuinely new data, a new development, or a meaningful update
- If there IS a meaningful update, frame it as "Update on [topic]: [new development]" — do not re-explain the original story
- If the same underlying signals appear in today's raw data but nothing has changed, ignore them
- Fill the brief with OTHER signals and findings instead — maintain the same depth and density, just with fresh content

Previous brief:
{previous_brief}

---

"""

    prompt = f"""You are an AI analyst tracking the biggest story in the world as it unfolds in real time. You produce a daily intelligence brief for someone deeply embedded in the AI space — building with it, investing in it, thinking about where it's going.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}
Your job: synthesize these raw signals into a sharp, high-value daily brief. This is NOT a news roundup. Your value is in reading today's moves and telling the listener what they actually mean — what they reveal about the players' strategies, what they signal about where AI is heading, and what most people are missing.

Think like a detective reading a chess board. When Anthropic restricts third-party tools, what does that tell you about their capital position? When a model quietly gets better without an announcement, what does that mean for the competitive landscape? Connect the dots that others aren't connecting.

## SOURCE HIERARCHY
Not all signals are equal. Prioritize in this order:
1. **Corporate announcements, model releases, regulatory filings, research papers** — primary sources. These are the moves themselves.
2. **YouTube headlines** — topic signal only. If multiple channels cover the same thing, that's a strong indicator of what matters today. Use the signal to identify important topics, but form your OWN analysis from primary sources.
3. **Hacker News** — developer/builder sentiment. How the technical community is reacting.
4. **Reddit** — community sentiment. Broader audience reaction.
5. **Knowledge Studio** — deep context from previously processed analysis.

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# AI DAILY BRIEF — {today}

## 🔴 TOP SIGNAL
The single most important development today. 2-3 sentences max. Not just what happened — what it reveals and why it matters.

## ⚡ KEY MOVES
3-4 significant developments. For each:
- **Bold headline** — 1-2 sentence analysis. What happened is the setup. What it MEANS is the payload. What does this move reveal about the player's strategy? What does it signal about where the space is heading? What are most people missing about it?
- Include a primary source URL (company blog, research paper, official announcement) on a new line when available. If no primary source URL exists, omit the URL entirely.

## 🔗 THE BIGGER PICTURE
2-3 observations connecting today's signals into larger patterns forming over weeks or months. This is where you step back from individual moves and say what's actually forming. "These three developments suggest..." or "This is the third signal in two weeks that..."

This section is the most valuable part of the brief — not reporting, but seeing what's taking shape.

## 📚 DEEP READS
2-3 primary source documents worth deeper engagement. Company blog posts, research papers, regulatory filings, key essays. Brief note on why each matters. Include URLs.

## RULES
- Be opinionated. Take positions. "This matters because..." not "Some people think..."
- Read the moves for strategy. Don't just report what happened — tell us what it reveals about what the player is actually doing and why.
- Connect developments to each other. If today's signals relate, thread them into a narrative rather than listing them separately.
- NEVER cite YouTube creators, podcasters, or commentators by name. If someone's analysis informed your thinking, own the insight — don't attribute it. This brief speaks with its own voice.
- NEVER include YouTube video links. Only link to primary sources (company blogs, papers, official announcements, regulatory filings).
- Write for someone who's already deeply in the AI space. High context assumed. No explaining what an LLM is.
- Keep the entire brief under 800 words. Density over length.
- If signals are thin or redundant, say so honestly rather than padding.
- The AGI question is the backdrop. When today's signals provide genuine evidence about AI capability thresholds — not hype, real evidence — note it. But don't force it.
- For URLs, put them on their own line below the analysis.
- NEVER use insider shorthand without explanation. Write "Hacker News" not "HN." Write "Y Combinator" not "YC." Your audience may not know tech community jargon — always use full names on first reference.
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

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

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

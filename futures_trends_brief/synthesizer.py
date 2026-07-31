"""
Futures & Trends Brief — Synthesizer
Takes collected signals and produces a twice-weekly brief using Claude.
Cross-domain synthesis is the centerpiece — connecting dots across verticals.
"""

import json
import os
from datetime import datetime
from typing import Optional
from claude_cli_client import make_client as Anthropic  # subscription, not metered API


def prepare_signal_digest(collected_data: dict) -> str:
    """
    Compress collected signals into a text digest for Claude to synthesize.
    Organized: internal briefs first (unique context), then research, then community.
    """
    sections = []

    # Tier 0: Internal briefs — the unique ingredient
    internal = collected_data.get("sources", {}).get("internal_briefs", [])
    if internal:
        lines = []
        for item in internal:
            vertical = item.get("vertical", "")
            title = item.get("title", "")
            content = item.get("content", "")
            created = item.get("created_at", "")
            # Include full brief content — this is the cross-domain synthesis fuel
            lines.append(f"### {vertical.upper()} BRIEF ({created})\n{content[:3000]}")
        sections.append(f"## INTERNAL BRIEFS — Recent Vertical Outputs\n" + "\n\n".join(lines))

    # Tier 1: RSS aggregators — publications, think tanks, investment firms
    rss_items = collected_data.get("sources", {}).get("rss_aggregators", [])
    if rss_items:
        lines = []
        for item in rss_items[:30]:
            feed = item.get("feed", "")
            title = item.get("title", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            line = f"- [{feed}] {title}\n  URL: {url}"
            if desc:
                line += f"\n  Summary: {desc[:250]}"
            lines.append(line)
        sections.append(f"## PUBLICATIONS & THINK TANKS ({len(lines)} articles)\n" + "\n".join(lines))

    # Tier 1: arXiv — macro-relevant research
    arxiv_items = collected_data.get("sources", {}).get("arxiv", [])
    if arxiv_items:
        lines = []
        for item in arxiv_items[:20]:
            title = item.get("title", "")
            authors = item.get("authors", "")[:80]
            abstract = item.get("abstract", "")[:250]
            url = item.get("url", "")
            category = item.get("category", "")
            lines.append(f"- [{category}] {title}\n  {authors}\n  Abstract: {abstract}\n  URL: {url}")
        sections.append(f"## ARXIV — Macro-Relevant Research ({len(lines)} papers)\n" + "\n".join(lines))

    # Tier 2: Hacker News
    hn_items = collected_data.get("sources", {}).get("hacker_news", [])
    if hn_items:
        lines = []
        for item in hn_items[:25]:
            title = item.get("title", "")
            url = item.get("url", "")
            points = item.get("points", 0)
            comments = item.get("comments", 0)
            lines.append(f"- [{points}pts, {comments}c] {title}\n  URL: {url}")
        sections.append(f"## HACKER NEWS ({len(lines)} stories)\n" + "\n".join(lines))

    # Tier 2: Reddit
    reddit_items = collected_data.get("sources", {}).get("reddit", [])
    if reddit_items:
        lines = []
        for item in reddit_items[:25]:
            title = item.get("title", "")
            sub = item.get("subreddit", "")
            url = item.get("reddit_url", item.get("url", ""))
            lines.append(f"- [r/{sub}] {title}\n  URL: {url}")
        sections.append(f"## REDDIT ({len(lines)} posts)\n" + "\n".join(lines))

    # Tier 2: YouTube — futurist voices
    yt_items = collected_data.get("sources", {}).get("youtube_search", [])
    if yt_items:
        lines = []
        for item in yt_items[:20]:
            title = item.get("title", "")
            channel = item.get("channel", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            line = f"- [{channel}] {title}\n  URL: {url}"
            if desc:
                line += f"\n  Desc: {desc[:150]}"
            lines.append(line)
        sections.append(f"## YOUTUBE — Futurist Voices ({len(lines)} videos)\n" + "\n".join(lines))

    # Tier 3: Knowledge Studio
    ks_items = collected_data.get("sources", {}).get("knowledge_studio", [])
    if ks_items:
        lines = []
        for item in ks_items[:15]:
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
            lines.append(line)
        sections.append(f"## KNOWLEDGE STUDIO ({len(lines)} items)\n" + "\n".join(lines))

    return "\n\n".join(sections)


def get_previous_brief(vertical: str = "futures_trends", db_path: str = None) -> Optional[str]:
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
                     vertical: str = "futures_trends",
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured futures & trends brief.
    Cross-domain synthesis is the centerpiece.
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
- If there IS a meaningful update, frame it as "Update on [topic]: [new development]" — do not re-explain the original analysis
- If the same underlying signals appear in today's raw data but nothing has changed, ignore them
- Fill the brief with OTHER signals and findings instead — maintain the same depth and density, just with fresh content

Previous brief:
{previous_brief}

---

"""

    # Check if we have internal briefs to reference
    has_internal = len(collected_data.get("sources", {}).get("internal_briefs", [])) > 0

    internal_instruction = ""
    if has_internal:
        internal_instruction = """
CRITICAL — INTERNAL BRIEFS:
You have access to recent AI & Tech and Health & Longevity briefs produced by this same system. These are your most important input. Your unique value is connecting patterns ACROSS these verticals and the external signals. When the AI brief identifies agentic labor displacement and the health brief identifies longevity timeline shifts, YOU connect them: "workforce planning models break when retirement assumptions change." Read the internal briefs carefully and use them as the foundation for your Emerging Patterns section.
"""

    prompt = f"""You are a strategic foresight analyst producing a twice-weekly brief for a macro-oriented thinker who tracks where the world is heading across technology, geopolitics, economics, demographics, culture, and science.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}
Your job: synthesize these raw signals into a sharp, high-value futures brief. This is NOT a news roundup and NOT a single-domain analysis — it's cross-domain pattern recognition. You think like a futurist, not a journalist. Long time horizons (1-10 years), not daily news reaction.

{internal_instruction}

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# FUTURES & TRENDS BRIEF — {today}

## 🔭 TOP SIGNAL
The single most important macro development or emerging pattern. 2-3 sentences. Why it matters for the next 1-10 years, not just what happened this week.

## ⚡ KEY DEVELOPMENTS
3-5 items spanning multiple domains (tech, geopolitics, economics, demographics, science). For each:
- **Bold headline** — 1-2 sentence analysis. What does this signal about where things are heading? What are the second-order effects?
- Include the source URL on a new line.

## 🔗 EMERGING PATTERNS
THIS IS THE CENTERPIECE. 3-5 observations connecting dots ACROSS domains and across the signals you've been given. This is where you earn your keep.

Examples of the altitude you should operate at:
- "Three independent signals — AI agent labor displacement, rising longevity projections, and sovereign wealth fund reallocations — converge on a single conclusion: retirement as a social institution is being redefined from both ends simultaneously."
- "The gap between exponential AI capability curves and linear regulatory response is widening faster than any previous technology governance mismatch."
- "Energy transition timelines and demographic decline curves are now on collision courses in 4 major economies."

Each pattern should:
- Connect at least 2 different domains
- Reference specific signals from the input data
- State a clear implication or prediction
- Be opinionated — take a position

## 📚 WORTH YOUR TIME
2-3 items worth deeper reading/watching. Prioritize content that itself does cross-domain thinking. Brief note on why. Include URLs.

## RULES
- Cross-domain synthesis is your unique value. Every section should reflect this.
- Be opinionated. Take positions. "This means X" not "Some people think X."
- Write for someone who already understands AI, geopolitics, macro economics, and demographics at a high level. No explaining basics.
- Think in systems, feedback loops, and second-order effects. Not headlines.
- Prioritize pattern recognition over comprehensive coverage. Miss things — that's fine. Don't be boring.
- Keep the entire brief under 1000 words. Density over length.
- If signals are thin, say so. Don't pad.
- For YouTube links, ALWAYS format as a markdown link with title and channel: [Video Title — Channel Name](url). Never output bare YouTube URLs.
- For non-YouTube URLs (papers, articles), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating futures brief ({total} signals → Claude)...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    brief = response.content[0].text

    # Add metadata footer
    brief += f"\n\n---\n*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Sources: {total} signals across {len(source_counts)} sources*"

    print(f"[Synthesizer] Brief generated ({len(brief)} chars)")
    return brief


def generate_daily_brief(vertical: str = "futures_trends",
                         hours_back: int = 96,
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
    OUTPUT_DIR = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/futures_trends_brief/output"
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

    brief = generate_daily_brief(
        vertical="futures_trends",
        hours_back=96,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)

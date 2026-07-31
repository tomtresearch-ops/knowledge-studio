"""
Health & Longevity Brief — Synthesizer
Takes collected signals and produces a structured brief using Claude.
"""

import json
import os
from datetime import datetime
from typing import Optional
from claude_cli_client import make_client as Anthropic  # subscription, not metered API


def prepare_signal_digest(collected_data: dict) -> str:
    """
    Compress collected signals into a text digest for Claude to synthesize.
    Organized by source tier: research → aggregators → community.
    """
    sections = []

    # Tier 1: PubMed — published research
    pubmed_items = collected_data.get("sources", {}).get("pubmed", [])
    if pubmed_items:
        lines = []
        for item in pubmed_items[:30]:
            title = item.get("title", "")
            authors = item.get("authors", "")
            journal = item.get("journal", "")
            url = item.get("url", "")
            pub_date = item.get("pub_date", "")
            lines.append(f"- {title}\n  {authors} | {journal} | {pub_date}\n  URL: {url}")
        sections.append(f"## PUBMED — Published Research ({len(lines)} papers)\n" + "\n".join(lines))

    # Tier 1: bioRxiv — preprints
    biorxiv_items = collected_data.get("sources", {}).get("biorxiv", [])
    if biorxiv_items:
        lines = []
        for item in biorxiv_items[:20]:
            title = item.get("title", "")
            authors = item.get("authors", "")[:80]
            abstract = item.get("abstract", "")[:200]
            url = item.get("url", "")
            category = item.get("category", "")
            lines.append(f"- [{category}] {title}\n  {authors}\n  Abstract: {abstract}\n  URL: {url}")
        sections.append(f"## BIORXIV — Preprints ({len(lines)} papers)\n" + "\n".join(lines))

    # Tier 2: RSS Aggregators — curated science news
    rss_items = collected_data.get("sources", {}).get("rss_aggregators", [])
    if rss_items:
        lines = []
        for item in rss_items[:25]:
            feed = item.get("feed", "")
            title = item.get("title", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            line = f"- [{feed}] {title}\n  URL: {url}"
            if desc:
                line += f"\n  Summary: {desc[:200]}"
            lines.append(line)
        sections.append(f"## SCIENCE NEWS AGGREGATORS ({len(lines)} articles)\n" + "\n".join(lines))

    # Tier 3: Hacker News
    hn_items = collected_data.get("sources", {}).get("hacker_news", [])
    if hn_items:
        lines = []
        for item in hn_items[:20]:
            title = item.get("title", "")
            url = item.get("url", "")
            points = item.get("points", 0)
            comments = item.get("comments", 0)
            lines.append(f"- [{points}pts, {comments}c] {title}\n  URL: {url}")
        sections.append(f"## HACKER NEWS ({len(lines)} stories)\n" + "\n".join(lines))

    # Tier 3: Reddit
    reddit_items = collected_data.get("sources", {}).get("reddit", [])
    if reddit_items:
        lines = []
        for item in reddit_items[:25]:
            title = item.get("title", "")
            sub = item.get("subreddit", "")
            url = item.get("reddit_url", item.get("url", ""))
            lines.append(f"- [r/{sub}] {title}\n  URL: {url}")
        sections.append(f"## REDDIT ({len(lines)} posts)\n" + "\n".join(lines))

    # Tier 3: YouTube
    yt_items = collected_data.get("sources", {}).get("youtube_search", [])
    if yt_items:
        lines = []
        for item in yt_items[:15]:
            title = item.get("title", "")
            channel = item.get("channel", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            line = f"- [{channel}] {title}\n  URL: {url}"
            if desc:
                line += f"\n  Desc: {desc[:150]}"
            lines.append(line)
        sections.append(f"## YOUTUBE ({len(lines)} videos)\n" + "\n".join(lines))

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


def get_previous_brief(vertical: str = "health_longevity", db_path: str = None) -> Optional[str]:
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
                     vertical: str = "health_longevity",
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured health/longevity brief.
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
- SKIP it entirely unless there is genuinely new data, a new study, or a meaningful update
- If there IS a meaningful update, frame it as "Update on [topic]: [new development]" — do not re-explain the original finding
- If the same underlying signals appear in today's raw data but nothing has changed, ignore them
- Fill the brief with OTHER signals and findings instead — maintain the same depth and density, just with fresh content

Previous brief:
{previous_brief}

---

"""

    prompt = f"""You are a health intelligence analyst producing a daily brief for someone deeply invested in longevity, anti-aging, rejuvenation, and the future of medicine. They have a scientific background and want signal, not noise.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}

Your job: synthesize these raw signals into a sharp, high-value brief. Prioritize research findings (PubMed, bioRxiv) as primary evidence, use aggregator coverage for context, and community discussion for sentiment. This is NOT a health tips roundup — it's intelligence analysis for someone tracking the frontier of human longevity.

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# HEALTH & LONGEVITY BRIEF — {today}

## 🔬 TOP SIGNAL
The single most important finding or development today. 2-3 sentences max. Why it matters for the longevity field, not just what was published.

## 🧬 RESEARCH FRONTLINE
3-5 items from PubMed/bioRxiv/aggregators. For each:
- **Bold finding headline** — 1-2 sentence analysis. What does this mean for the field? Is it confirmatory, novel, or contradictory? What should we watch for next?
- Include the source URL on a new line.
- Note the journal/preprint status — peer-reviewed vs preprint matters here.

## 💊 PRACTICAL SIGNAL
2-3 items relevant to applied longevity — supplements, interventions, lifestyle protocols, clinical trials, regulatory changes. What's actionable or approaching actionable?

## 🔗 EMERGING PATTERNS
2-3 observations connecting dots ACROSS signals. "Three papers this week converge on X mechanism..." or "The gap between mouse models and human trials for Y is closing because..."

## 📚 WORTH YOUR TIME
2-3 items worth deeper reading/watching. Brief note on why. Include URLs.

## RULES
- Research first. PubMed and bioRxiv findings should anchor the brief. Community discussion is context, not the story.
- Be precise about evidence levels: distinguish between in vitro, mouse model, human trial, and meta-analysis.
- Note if something is a preprint (not yet peer-reviewed) — this matters in health.
- Be opinionated but evidence-grounded. "This matters because..." not "Some researchers think..."
- Write for someone who knows what senolytics, mTOR, and epigenetic clocks are. High context assumed.
- Keep the entire brief under 900 words. Density over length.
- If signals are thin or redundant, say so honestly rather than padding.
- For YouTube links, ALWAYS format as a markdown link with title and channel: [Video Title — Channel Name](url). Never output bare YouTube URLs.
- For non-YouTube URLs (papers, articles), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating health brief ({total} signals → Claude)...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )

    brief = response.content[0].text

    # Add metadata footer
    brief += f"\n\n---\n*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Sources: {total} signals across {len(source_counts)} sources*"

    print(f"[Synthesizer] Brief generated ({len(brief)} chars)")
    return brief


def generate_daily_brief(vertical: str = "health_longevity",
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
    OUTPUT_DIR = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/health_longevity_brief/output"
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

    brief = generate_daily_brief(
        vertical="health_longevity",
        hours_back=24,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)

"""
Local AI Intel — Synthesizer
Takes collected signals and produces a structured brief on the AI services
marketplace for agencies serving local/SMB businesses.
"""

import json
import os
from datetime import datetime
from typing import Optional
from anthropic import Anthropic


def prepare_signal_digest(collected_data: dict) -> str:
    """Compress collected signals into a text digest for Claude to synthesize."""
    sections = []

    hn_items = collected_data.get("sources", {}).get("hacker_news", [])
    if hn_items:
        lines = []
        for item in hn_items[:25]:
            points = item.get("points", 0)
            comments = item.get("comments", 0)
            title = item.get("title", "")
            url = item.get("url", "")
            lines.append(f"- [{points}pts, {comments}c] {title}\n  URL: {url}")
        sections.append(f"## HACKER NEWS ({len(lines)} stories)\n" + "\n".join(lines))

    reddit_items = collected_data.get("sources", {}).get("reddit", [])
    if reddit_items:
        lines = []
        for item in reddit_items[:25]:
            title = item.get("title", "")
            sub = item.get("subreddit", "")
            url = item.get("reddit_url", item.get("url", ""))
            lines.append(f"- [r/{sub}] {title}\n  URL: {url}")
        sections.append(f"## REDDIT ({len(lines)} posts)\n" + "\n".join(lines))

    rss_items = collected_data.get("sources", {}).get("rss", [])
    if rss_items:
        lines = []
        for item in rss_items[:20]:
            title = item.get("title", "")
            feed = item.get("feed", "")
            url = item.get("url", "")
            desc = item.get("description", "")[:150]
            line = f"- [{feed}] {title}\n  URL: {url}"
            if desc:
                line += f"\n  {desc}"
            lines.append(line)
        sections.append(f"## RSS/BLOGS ({len(lines)} articles)\n" + "\n".join(lines))

    yt_search = collected_data.get("sources", {}).get("youtube_search", [])
    yt_channels = collected_data.get("sources", {}).get("youtube_channels", [])
    yt_items = yt_search + yt_channels
    if yt_items:
        lines = []
        for item in yt_items[:20]:
            title = item.get("title", "")
            channel = item.get("channel", "")
            desc = item.get("description", "")
            line = f"- [{channel}] {title}"
            if desc:
                line += f"\n  Desc: {desc[:150]}"
            lines.append(line)
        sections.append(f"## YOUTUBE ({len(lines)} videos)\n" + "\n".join(lines))

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


def get_previous_brief(vertical: str = "local_ai_intel", db_path: str = None) -> Optional[str]:
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
                     vertical: str = "local_ai_intel",
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """Synthesize collected signals into a Local AI Intel brief."""
    client = Anthropic(api_key=api_key) if api_key else Anthropic()

    digest = prepare_signal_digest(collected_data)
    today = datetime.now().strftime("%B %d, %Y")

    source_counts = {k: len(v) for k, v in collected_data.get("sources", {}).items()}
    total = sum(source_counts.values())

    if previous_brief is None:
        previous_brief = get_previous_brief(vertical)

    dedup_section = ""
    if previous_brief:
        dedup_section = f"""
## PREVIOUS BRIEF (DO NOT REPEAT)

The following is the most recent brief. DO NOT repeat the same stories or framings. If a topic appeared before:
- SKIP it unless there is genuinely new data or a meaningful update
- If there IS an update, frame it as "Update: [new development]"
- Fill the brief with OTHER signals instead — maintain depth with fresh content

Previous brief:
{previous_brief}

---

"""

    prompt = f"""You are a market intelligence analyst covering the AI services marketplace — specifically, agencies that sell AI solutions (chatbots, voice agents, automation, lead gen, appointment setting) to local and small businesses. You produce a weekly intelligence brief for agency owners and AI consultants who need to stay sharp on what's working, what's emerging, and where the market is heading.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}
Your job: synthesize these raw signals into a sharp, actionable brief for people who run or are building AI service agencies. This is NOT a general AI news brief — it's specifically about the business of selling AI services to local/SMB clients.

Think like an agency owner deciding what services to offer next month, how to price them, what tools to standardize on, and how to differentiate from competitors flooding the market.

## SOURCE HIERARCHY
1. **Platform announcements** — GoHighLevel features, Voiceflow updates, n8n releases, new white-label tools. These directly affect what agencies can sell.
2. **Reddit/HN** — What are agencies actually charging? What's working? What clients are asking for? Real-world signal.
3. **RSS/Blogs** — Industry analysis, case studies, pricing benchmarks.
4. **YouTube** — Topic signal. Multiple creators covering the same service model = market trend.
5. **Knowledge Studio** — Deep context from previously processed analysis.

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

# LOCAL AI INTEL — {today}

## MARKET PULSE
The single most important development for AI agencies this week. 2-3 sentences. Not just what happened — what it means for how agencies should position or adapt.

## KEY DEVELOPMENTS
3-4 significant developments. For each:
- **Bold headline** — 1-2 sentence analysis focused on agency implications. What service does this enable? What pricing does this affect? What competitive dynamic does this create?
- Include source URL when available.

## TOOLS & PLATFORMS
2-3 tool/platform updates that directly affect agency operations. New features, pricing changes, emerging alternatives. Focus on what agencies can sell or build with.

## AGENCY PLAYBOOK
2-3 actionable insights for agency operators. What service packages are gaining traction? What pricing models are working? What delivery approaches are scaling? What are the common failure modes agencies are hitting?

## MARKET SIGNALS
2-3 observations about where the AI services market is heading. Client demand patterns, competitive dynamics, consolidation trends, regulatory signals.

## WORTH WATCHING
2-3 tools, threads, or announcements worth deeper engagement. Brief note on why. Include URLs.

## RULES
- Agency lens only. Every item analyzed through: what does this mean for someone selling AI services to local businesses?
- Be opinionated. "Agencies charging under $X for voice agents are leaving money on the table because..." not "Some agencies charge more than others."
- Distinguish between hype and revenue. A viral demo is not a business model. Note when something is actually generating client revenue vs. getting Twitter likes.
- NEVER cite YouTube creators by name. Own the insight.
- NEVER include YouTube video links. Only link to primary sources.
- Keep the entire brief under 800 words. Density over length.
- If signals are thin this cycle, say so. Don't pad with general AI news.
- NEVER use insider shorthand without explanation. Write "Hacker News" not "HN." Write "Y Combinator" not "YC." Your audience is agency owners and consultants, not developers — don't assume they know tech community jargon.
"""

    print(f"\n[Synthesizer] Generating Local AI Intel brief ({total} signals -> Claude)...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    brief = response.content[0].text
    brief += f"\n\n---\n*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Sources: {total} signals across {len(source_counts)} sources*"

    print(f"[Synthesizer] Brief generated ({len(brief)} chars)")
    return brief


def generate_daily_brief(vertical: str = "local_ai_intel",
                         hours_back: int = 24,
                         db_path: str = None,
                         youtube_api_key: str = None,
                         anthropic_api_key: str = None,
                         output_dir: str = None) -> str:
    """Full pipeline: collect -> synthesize -> save."""
    from collectors import collect_all

    collected = collect_all(
        vertical=vertical,
        hours_back=hours_back,
        db_path=db_path,
        youtube_api_key=youtube_api_key,
    )

    brief = synthesize_brief(collected, vertical=vertical, api_key=anthropic_api_key)

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
    OUTPUT_DIR = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/local_ai_intel/output"
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

    brief = generate_daily_brief(
        vertical="local_ai_intel",
        hours_back=168,  # Weekly — 7 days of signal
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)

"""
AI Agents Brief — Synthesizer
Takes collected signals and produces a structured brief on autonomous agents,
agent frameworks, and the agent economy using Claude.
"""

import json
import os
from datetime import datetime
from typing import Optional
from claude_cli_client import make_client as Anthropic  # subscription, not metered API


def prepare_signal_digest(collected_data: dict) -> str:
    """
    Compress collected signals into a text digest for Claude to synthesize.
    Organized by source: HN → GitHub → Reddit → YouTube → KS.
    """
    sections = []

    # Hacker News — builder/developer signal
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

    # GitHub Trending — what builders are actually using
    gh_items = collected_data.get("sources", {}).get("github_trending", [])
    if gh_items:
        lines = []
        for item in gh_items[:15]:
            repo = item.get("repo", "")
            desc = item.get("description", "")
            stars = item.get("stars_today", 0)
            url = item.get("url", "")
            line = f"- [{stars} stars today] {repo}\n  {desc}\n  URL: {url}"
            lines.append(line)
        sections.append(f"## GITHUB TRENDING ({len(lines)} repos)\n" + "\n".join(lines))

    # Reddit — community signal
    reddit_items = collected_data.get("sources", {}).get("reddit", [])
    if reddit_items:
        lines = []
        for item in reddit_items[:25]:
            title = item.get("title", "")
            sub = item.get("subreddit", "")
            url = item.get("reddit_url", item.get("url", ""))
            lines.append(f"- [r/{sub}] {title}\n  URL: {url}")
        sections.append(f"## REDDIT ({len(lines)} posts)\n" + "\n".join(lines))

    # YouTube — creator coverage
    yt_items = collected_data.get("sources", {}).get("youtube_search", [])
    if yt_items:
        lines = []
        for item in yt_items[:15]:
            title = item.get("title", "")
            channel = item.get("channel", "")
            desc = item.get("description", "")
            line = f"- [{channel}] {title}"
            if desc:
                line += f"\n  Desc: {desc[:150]}"
            lines.append(line)
        sections.append(f"## YOUTUBE ({len(lines)} videos)\n" + "\n".join(lines))

    # Knowledge Studio — deep context
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


def get_previous_brief(vertical: str = "ai_agents", db_path: str = None) -> Optional[str]:
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
                     vertical: str = "ai_agents",
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured AI agents brief.
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
- SKIP it entirely unless there is genuinely new data, a new release, or a meaningful update
- If there IS a meaningful update, frame it as "Update on [topic]: [new development]" — do not re-explain the original story
- If the same underlying signals appear in today's raw data but nothing has changed, ignore them
- Fill the brief with OTHER signals and findings instead — maintain the same depth and density, just with fresh content

Previous brief:
{previous_brief}

---

"""

    prompt = f"""You are an agent systems analyst tracking the most consequential shift in software: the rise of autonomous AI agents. You produce a daily intelligence brief for someone who is building with agents, investing in the agent ecosystem, and thinking about where autonomous systems are heading.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}
Your job: synthesize these raw signals into a sharp, high-value brief focused exclusively on AI agents and agentic systems. NOT general AI news — agents specifically. When a development relates to agents (even if it's a model release or company move), analyze it through the agent lens: what does this mean for agent capabilities, agent architectures, or the agent economy?

Think like someone building the infrastructure for the agent era. When a new framework trends on GitHub, what problem is it solving that existing tools don't? When a company ships an agent product, what does that reveal about which agent patterns are production-ready vs. still experimental? When a model gets better at tool use, what agent workflows does that unlock?

## SOURCE HIERARCHY
Not all signals are equal. Prioritize in this order:
1. **Framework releases, SDK updates, protocol announcements** — the tools builders are actually using. If it's on GitHub trending, real developers are adopting it.
2. **Hacker News** — builder sentiment. What frameworks are developers excited about vs. frustrated with? What architectures are working in production vs. failing?
3. **GitHub Trending** — adoption signal. Stars today = real momentum. Look for emerging frameworks and tools.
4. **Reddit** — community sentiment. What are people actually building with agents? What's working, what's not?
5. **YouTube** — topic signal only. Multiple creators covering the same agent topic = important development.
6. **Knowledge Studio** — deep context from previously processed analysis.

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# AI AGENTS BRIEF — {today}

## TOP SIGNAL
The single most important agent development today. 2-3 sentences max. Not just what happened — what it means for how agents will be built or deployed.

## KEY DEVELOPMENTS
3-4 significant agent-related developments. For each:
- **Bold headline** — 1-2 sentence analysis. What framework, pattern, or capability is this advancing? What does it unlock for builders? What's the competitive implication?
- Include a primary source URL (GitHub repo, company blog, official announcement) on a new line when available.

## BUILDER SIGNAL
2-3 items specifically relevant to people building with agents right now. What framework just shipped a major update? What pattern is proving out in production? What common failure mode are people running into?

## THE PATTERN
2-3 observations connecting today's signals into larger trends forming in the agent ecosystem. "Three different frameworks now converge on X architecture..." or "The gap between demo agents and production agents is closing/widening because..."

This is the most valuable part — where are agents ACTUALLY heading based on what builders are doing, not what companies are announcing?

## WORTH WATCHING
2-3 repos, posts, or announcements worth deeper engagement. Brief note on why. Include URLs.

## RULES
- Agent lens only. Every item should be analyzed through: what does this mean for autonomous agent systems?
- Be opinionated about frameworks and patterns. "X approach is winning because..." not "Some developers prefer..."
- Distinguish between demo-quality and production-quality. Most agent demos don't work at scale — note when something actually does.
- GitHub stars and HN points are real signal. A trending repo with 500 stars today means something different than a blog post.
- Write for someone who knows what MCP, function calling, ReAct, and multi-agent orchestration are. High context assumed.
- NEVER cite YouTube creators by name. Own the insight.
- NEVER include YouTube video links. Only link to primary sources (GitHub repos, company blogs, official docs).
- Keep the entire brief under 800 words. Density over length.
- If agent-specific signals are thin today, say so. Don't pad with general AI news.
- NEVER use insider shorthand without explanation. Write "Hacker News" not "HN." Write "Y Combinator" not "YC." Your audience may not know tech community jargon — always use full names on first reference.
"""

    print(f"\n[Synthesizer] Generating agents brief ({total} signals -> Claude)...")

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


def generate_daily_brief(vertical: str = "ai_agents",
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
    DB_PATH = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/youtube_intelligence.db"
    OUTPUT_DIR = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/ai_agents_brief/output"
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

    brief = generate_daily_brief(
        vertical="ai_agents",
        hours_back=24,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)

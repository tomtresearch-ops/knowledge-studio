"""
Future of Medicine Brief — Synthesizer
Takes collected signals and produces a structured brief using Claude.

Editorial lens: "Lab to Fab" — tracking what's moving from lab bench to real-world accessibility.
Five key angles:
1. Lab to Fab pipeline tracking — phase transitions, regulatory approvals, market releases
2. AI as leapfrog mechanism — AI enabling small actors to bypass Big Pharma
3. Regulatory friction/arbitrage — jurisdictional speed differences
4. Medical tourism acceleration — downstream effect of regulatory gaps
5. KS cross-pollination — major figures on Tom's subscribed channels
"""

import json
import os
from datetime import datetime
from typing import Optional
from anthropic import Anthropic


def prepare_signal_digest(collected_data: dict) -> str:
    """
    Compress collected signals into a text digest for Claude to synthesize.
    Organized by source tier: internal briefs → research → clinical trials → aggregators → community.
    """
    sections = []

    # Tier 0: Internal briefs (cross-vertical context)
    internal_items = collected_data.get("sources", {}).get("internal_briefs", [])
    if internal_items:
        lines = []
        for item in internal_items[:5]:
            vertical = item.get("vertical", "")
            content = item.get("content", "")[:3000]
            created = item.get("created_at", "")
            lines.append(f"### {vertical} brief ({created})\n{content}")
        sections.append(f"## INTERNAL BRIEFS — Cross-Vertical Context ({len(lines)} briefs)\n" + "\n\n".join(lines))

    # Tier 1: PubMed — published research
    pubmed_items = collected_data.get("sources", {}).get("pubmed", [])
    if pubmed_items:
        lines = []
        for item in pubmed_items[:40]:
            title = item.get("title", "")
            authors = item.get("authors", "")
            journal = item.get("journal", "")
            url = item.get("url", "")
            pub_date = item.get("pub_date", "")
            lines.append(f"- {title}\n  {authors} | {journal} | {pub_date}\n  URL: {url}")
        sections.append(f"## PUBMED — Published Research ({len(lines)} papers)\n" + "\n".join(lines))

    # Tier 1: bioRxiv/medRxiv — preprints
    biorxiv_items = collected_data.get("sources", {}).get("biorxiv", [])
    if biorxiv_items:
        lines = []
        for item in biorxiv_items[:25]:
            source = item.get("source", "biorxiv")
            title = item.get("title", "")
            authors = item.get("authors", "")[:80]
            abstract = item.get("abstract", "")[:200]
            url = item.get("url", "")
            category = item.get("category", "")
            lines.append(f"- [{source}/{category}] {title}\n  {authors}\n  Abstract: {abstract}\n  URL: {url}")
        sections.append(f"## BIORXIV + MEDRXIV — Preprints ({len(lines)} papers)\n" + "\n".join(lines))

    # Tier 1.5: Clinical Trials — Pipeline tracker
    ct_items = collected_data.get("sources", {}).get("clinical_trials", [])
    if ct_items:
        lines = []
        for item in ct_items[:25]:
            title = item.get("title", "")
            phase = item.get("phase", "N/A")
            status = item.get("status", "")
            conditions = item.get("conditions", "")
            interventions = item.get("interventions", "")
            sponsor = item.get("sponsor", "")
            url = item.get("url", "")
            lines.append(f"- [{phase} | {status}] {title}\n  Conditions: {conditions}\n  Interventions: {interventions}\n  Sponsor: {sponsor}\n  URL: {url}")
        sections.append(f"## CLINICAL TRIALS — Pipeline Activity ({len(lines)} studies)\n" + "\n".join(lines))

    # Tier 2: RSS Aggregators — curated science/biotech news
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
                line += f"\n  Summary: {desc[:200]}"
            lines.append(line)
        sections.append(f"## SCIENCE & BIOTECH NEWS ({len(lines)} articles)\n" + "\n".join(lines))

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

    # Tier 4: Knowledge Studio
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


def get_previous_brief(vertical: str = "future_medicine", db_path: str = None) -> Optional[str]:
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
                     vertical: str = "future_medicine",
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected signals into a structured frontier medicine brief.
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

    prompt = f"""You are a frontier medicine intelligence analyst producing a brief for someone deeply invested in the future of medicine — not personal health optimization (that's a different brief), but paradigm shifts: what was science fiction 5 years ago that's now in clinical trials, what's moving from lab bench to real-world accessibility, and where AI is collapsing timelines that used to take decades.

Today is {today}. You have {total} signals from: {json.dumps(source_counts)}.
{dedup_section}

Your editorial lens has five key angles:

1. **LAB TO FAB** — What's moving through the pipeline? Phase transitions, regulatory approvals, new market access. Not just "cool research" but "when can someone actually get this?" Track the journey from discovery to accessibility.

2. **AI AS LEAPFROG** — Where is AI collapsing what used to require massive pharma R&D? Individual actors, small teams, open-source bio tools doing what Big Pharma couldn't or wouldn't. The prototype signal: a non-tech person used AI to design an mRNA vaccine for his dog's cancer, got it manufactured, and it worked.

3. **REGULATORY LANDSCAPE** — Which jurisdictions are moving fast vs slow? What's getting approved where? The growing gap between what's technically possible and what's legally accessible. FDA breakthrough designations, international approvals, regulatory innovation.

4. **MEDICAL TOURISM & ACCESS** — The downstream effect of regulatory gaps. People going where the treatments are. New destinations, new treatments driving the trend. This will only accelerate.

5. **CROSS-DOMAIN CONVERGENCE** — Where biotech meets AI meets regulatory meets economics. The intersections that create new possibilities. If the Health & Longevity brief covered something from the personal optimization angle, what does it look like through the frontier medicine lens?

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# FUTURE OF MEDICINE — {today}

## 🔬 TOP SIGNAL
The single most important breakthrough, approval, or paradigm shift today. 2-3 sentences max. Why it matters for the future of medicine, not just what happened.

## 🧬 RESEARCH FRONTLINE
4-6 items from PubMed/bioRxiv/medRxiv/aggregators. For each:
- **Bold finding headline** — 1-2 sentence analysis. What does this mean for the field? How close is this to real-world application? What's the timeline to accessibility?
- Include the source URL on a new line.
- Note evidence level: in vitro, animal model, Phase I/II/III, approved, or meta-analysis.

## 🏭 LAB TO FAB — Pipeline Tracker
2-4 items specifically about things MOVING through the pipeline. Clinical trial phase changes, regulatory submissions, approvals, first-in-human studies. For each:
- **What moved** — from where to where in the pipeline
- **Why it matters** — what this unlocks
- **Timeline** — when could this be accessible to patients?
- Include ClinicalTrials.gov or source URL.

## 🤖 AI × MEDICINE
2-3 items where AI is directly accelerating medical progress. Drug design, diagnostic accuracy, treatment optimization, regulatory acceleration. Not AI in general — AI specifically changing medicine timelines.

## 🌍 REGULATORY & ACCESS
1-2 items about regulatory shifts, international differences, or access patterns. Medical tourism signals, compassionate use expansions, regulatory fast-tracks, or notable jurisdiction differences.

## 🔗 EMERGING PATTERNS
2-3 observations connecting dots ACROSS signals. "Three papers this week converge on X..." or "The regulatory landscape for Y is shifting because..." Cross-reference with Health & Longevity internal briefs if relevant.

## 📚 WORTH YOUR TIME
2-3 items worth deeper reading/watching. Brief note on why. Include URLs.

## RULES
- This is NOT a health tips brief. This is frontier medicine intelligence. The audience already knows what CRISPR, mRNA, and CAR-T are.
- Research anchors everything. PubMed, bioRxiv, medRxiv, and clinical trials are primary sources. News coverage and community discussion provide context.
- Be precise about evidence levels and pipeline stages. "Phase II" vs "Phase III" vs "approved" matters enormously.
- Be opinionated about timelines and accessibility. "This could reach patients in 2-3 years if Phase III succeeds" is valuable analysis.
- The "Lab to Fab" lens is the differentiator. Every item should implicitly answer: "How close is this to actually helping someone?"
- When clinical trials data is present, ALWAYS include it in the Pipeline Tracker section.
- Keep the entire brief under 1100 words. Density and signal over length.
- If signals are thin, say so honestly. Never pad.
- For YouTube links, format as markdown link with title and channel: [Video Title — Channel Name](url). Never bare URLs.
- For non-YouTube URLs (papers, articles, trials), put them on their own line.
"""

    print(f"\n[Synthesizer] Generating future medicine brief ({total} signals → Claude)...")

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


def generate_daily_brief(vertical: str = "future_medicine",
                         hours_back: int = 48,
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
    OUTPUT_DIR = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/future_medicine_brief/output"
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

    brief = generate_daily_brief(
        vertical="future_medicine",
        hours_back=48,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)

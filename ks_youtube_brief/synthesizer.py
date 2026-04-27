"""
KS YouTube Intelligence Brief — Synthesizer
Takes collected YouTube video signals and produces a newspaper-style
intelligence brief using Claude.
"""

import json
import os
from datetime import datetime
from typing import Optional
from anthropic import Anthropic


def prepare_signal_digest(collected_data: dict) -> str:
    """
    Compress collected KS video signals into a text digest for Claude.
    Uses full ai_summary for rich context — the key differentiator from other verticals.
    """
    sections = []

    # Processed videos — the primary source (full AI summaries)
    videos = collected_data.get("sources", {}).get("ks_processed_videos", [])
    if videos:
        # Group by channel for pattern detection
        by_channel = {}
        for v in videos:
            ch = v.get("channel", "Unknown")
            by_channel.setdefault(ch, []).append(v)

        video_lines = []
        for channel, channel_vids in sorted(by_channel.items(), key=lambda x: -len(x[1])):
            video_lines.append(f"\n### {channel} ({len(channel_vids)} video{'s' if len(channel_vids) > 1 else ''})")
            for v in channel_vids:
                title = v.get("title", "")
                tags = v.get("tags", "")
                summary = v.get("ai_summary", "")
                views = v.get("view_count", 0)
                line = f"- **{title}**"
                if views:
                    line += f" ({views:,} views)"
                if tags:
                    line += f"\n  Tags: {tags}"
                if summary:
                    # Use full summary but cap at 600 chars to fit many videos in context
                    line += f"\n  Analysis: {summary[:600]}"
                video_lines.append(line)

        sections.append(
            f"## PROCESSED VIDEOS ({len(videos)} total, {len(by_channel)} channels)\n"
            + "\n".join(video_lines)
        )

    # Unprocessed discoveries — secondary signal (title + description only)
    unprocessed = collected_data.get("sources", {}).get("ks_unprocessed_discoveries", [])
    if unprocessed:
        unp_lines = []
        for v in unprocessed[:30]:
            title = v.get("title", "")
            channel = v.get("channel", "")
            desc = v.get("description", "")
            line = f"- [{channel}] {title}"
            if desc:
                line += f"\n  Desc: {desc[:200]}"
            unp_lines.append(line)
        sections.append(
            f"## RECENTLY DISCOVERED (not yet processed — {len(unprocessed)} videos)\n"
            + "\n".join(unp_lines)
        )

    return "\n\n".join(sections)


def get_previous_brief(vertical: str = "ks_youtube", db_path: str = None) -> Optional[str]:
    """Fetch the most recent brief for this vertical from the database."""
    import sqlite3
    if db_path is None:
        db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "youtube_intelligence.db")
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
                     vertical: str = "ks_youtube",
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize collected KS video signals into a newspaper-style intelligence brief.
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

The following is the most recent brief already published. DO NOT repeat the same stories or framings. If a topic appeared before:
- SKIP it unless there is genuinely new data or a meaningful update
- If there IS an update, frame it as "Update: [new development]"
- Fill the brief with OTHER signals instead — maintain depth with fresh content

Previous brief:
{previous_brief[:2000]}

---

"""

    prompt = f"""You are the editor-in-chief of a daily YouTube intelligence newspaper. You monitor a curated network of 53 channels across AI, tech, health, futures, and business. Your reader is deeply embedded in these spaces — building, investing, strategizing.

Today is {today}. You have {total} signals: {json.dumps(source_counts)}.
{dedup_section}
Your job: synthesize these raw video analyses into a sharp, newspaper-style intelligence brief. This is NOT a list of video summaries. Your value is in identifying patterns, convergence, and what matters across the network.

Write like a journalist — lead with the story, not the data. When multiple channels independently cover the same topic, that's your headline. When a single creator breaks something nobody else has, that's your scoop.

## SOURCE HIERARCHY
1. **Processed videos with AI summaries** — your primary intelligence. These have been analyzed. Use the analysis to identify themes, convergence, and standout signals.
2. **Unprocessed discoveries** — title and description only. Use these as supplementary topic signal — if something shows up here AND in processed videos, it reinforces the trend.

## RAW SIGNALS

{digest}

## OUTPUT FORMAT

Produce the brief in this exact structure:

# YouTube Intelligence Brief — {today}

## 🔥 WHAT'S HOT
Quick-hit list of 5-8 topics getting the most attention across channels. This is the landscape scan — the reader's first stop.
Format each as: **Topic** — one-line take — (N channels)

## 👁️ WATCHLIST
2-3 emerging signals that aren't mainstream yet but showed up in interesting places. Early warning items. "Keep an eye on this" — the kind of thing that might be a FIRST ALERT tomorrow.

## 🔴 FIRST ALERT
The single most important development across your network today. 1-3 sentences. If multiple channels are converging on the same topic, that's the lead. Written as a narrative, not bullets. What's happening and why it matters RIGHT NOW.

## 📰 THE FRONT PAGE
2-3 synthesized "stories" — each is a narrative paragraph that weaves together signals from multiple videos and channels into a coherent trend or development. Think newspaper article, not bullet list.

### [Story 1 — written as a newspaper headline]
A narrative paragraph synthesizing 3-5 related videos into one coherent story. What's happening, why it matters, who's saying it. Include channel names inline as attribution. Connect the dots between what different creators are seeing.

### [Story 2 — headline]
Same format. Different theme or development.

### [Story 3 — headline] (if material warrants)
Optional third story.

## 📊 BY THE NUMBERS
3-4 stats: videos processed, channels active, dominant topic, notable outlier.

## RULES
- Be opinionated. Take positions. "This matters because..." not "Some people think..."
- Cross-channel convergence is your highest-value signal. When 3+ channels independently hit the same topic, lead with it.
- Write STORIES, not summaries. Synthesize across videos. A good brief reads like a front page, not a playlist.
- Keep channel names as inline attribution (like newspaper bylines), not section headers.
- Keep the entire brief under 1000 words. Density over length.
- If signals are thin, say so honestly rather than padding.
- No YouTube video links in the output — this is synthesis, not a link dump.
"""

    print(f"\n[KS YouTube Synthesizer] Generating brief ({total} signals → Claude)...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )

    brief = response.content[0].text

    # Add metadata footer
    brief += f"\n\n---\n*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Sources: {total} signals across {len(source_counts)} sources*"

    print(f"[KS YouTube Synthesizer] Brief generated ({len(brief)} chars)")
    return brief


def generate_daily_brief(vertical: str = "ks_youtube",
                         hours_back: int = 24,
                         db_path: str = None,
                         youtube_api_key: str = None,
                         anthropic_api_key: str = None,
                         output_dir: str = None) -> str:
    """Full pipeline: collect → synthesize → save."""
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
    DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "youtube_intelligence.db")
    OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

    brief = generate_daily_brief(
        vertical="ks_youtube",
        hours_back=24,
        db_path=DB_PATH,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)

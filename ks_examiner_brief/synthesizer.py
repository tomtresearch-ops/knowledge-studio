"""
The KS Examiner — Synthesizer
Takes operational stats and trend data, produces a newspaper-style
intelligence operations report using Claude.
"""

import json
import os
from datetime import datetime
from typing import Optional
from anthropic import Anthropic


def prepare_signal_digest(collected_data: dict) -> str:
    """
    Format operations stats and trend data into a text digest for Claude.
    """
    sections = []

    # Operations data
    ops_list = collected_data.get("sources", {}).get("operations", [])
    if ops_list:
        ops = ops_list[0]
        lines = [
            f"## OPERATIONS DATA",
            f"- Videos completed: {ops.get('videos_completed', 0)}",
            f"- Videos failed: {ops.get('videos_failed', 0)}",
            f"- Videos pending: {ops.get('videos_pending', 0)}",
            f"- Previous period completed: {ops.get('prev_period_completed', 0)}",
            f"- With transcript: {ops.get('with_transcript', 0)}",
            f"- Active channels: {ops.get('active_channels', 0)} of {ops.get('total_subscribed', 0)} subscribed",
            f"- Unprocessed in queue: {ops.get('unprocessed_queue', 0)}",
            f"- Articles processed: {ops.get('articles_processed', 0)}",
        ]

        # Channel activity breakdown
        channel_activity = ops.get("channel_activity", [])
        if channel_activity:
            lines.append(f"\n### Channel Activity (by volume)")
            for ch in channel_activity:
                lines.append(f"  - {ch['channel']}: {ch['count']} videos")

        sections.append("\n".join(lines))

    # Trend data
    trend_list = collected_data.get("sources", {}).get("trends", [])
    if trend_list:
        trends = trend_list[0]

        # Topic heat map
        heat_map = trends.get("topic_heat_map", [])
        if heat_map:
            heat_lines = ["## TOPIC HEAT MAP"]
            trend_symbols = {"up": "↑", "down": "↓", "new": "🆕", "steady": "—"}
            for t in heat_map:
                symbol = trend_symbols.get(t["trend"], "—")
                heat_lines.append(
                    f"  - {t['topic']}: {t['count']} mentions, "
                    f"{t['channels']} channels, {symbol} "
                    f"(prev: {t['prev_count']})"
                )
            sections.append("\n".join(heat_lines))

        # Convergence alerts
        convergence = trends.get("convergence_alerts", [])
        if convergence:
            conv_lines = ["## CONVERGENCE ALERTS (3+ channels on same topic)"]
            for c in convergence:
                conv_lines.append(
                    f"\n### {c['topic']} — {c['channel_count']} channels"
                )
                conv_lines.append(f"  Channels: {', '.join(c['channels'])}")
                for v in c.get("videos", [])[:5]:
                    conv_lines.append(f"  - [{v['channel']}] {v['title']}")
            sections.append("\n".join(conv_lines))

        # Quiet channels
        quiet = trends.get("quiet_channels", [])
        if quiet:
            sections.append(
                f"## QUIET CHANNELS ({len(quiet)} subscribed channels with no content)\n"
                + ", ".join(quiet[:20])
                + (f" ... and {len(quiet) - 20} more" if len(quiet) > 20 else "")
            )

    return "\n\n".join(sections)


def get_previous_brief(vertical: str = "ks_examiner", db_path: str = None) -> Optional[str]:
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
                     vertical: str = "ks_examiner",
                     api_key: Optional[str] = None,
                     previous_brief: Optional[str] = None) -> str:
    """
    Synthesize operational data into a newspaper-style intelligence operations report.
    """
    client = Anthropic(api_key=api_key) if api_key else Anthropic()

    digest = prepare_signal_digest(collected_data)
    today = datetime.now().strftime("%B %d, %Y")

    source_counts = {k: len(v) for k, v in collected_data.get("sources", {}).items()}

    # Auto-fetch previous brief for dedup
    if previous_brief is None:
        previous_brief = get_previous_brief(vertical)

    dedup_section = ""
    if previous_brief:
        dedup_section = f"""
## PREVIOUS REPORT (for context — note what changed)

Use this to identify what's NEW vs what's continuing. Highlight changes and shifts, not steady state.

Previous report:
{previous_brief[:1500]}

---

"""

    prompt = f"""You are the editor of The KS Examiner — a daily intelligence operations report. Your reader runs a 53-channel YouTube monitoring network that auto-processes videos into AI-analyzed intelligence artifacts. They need a crisp daily picture of their operation.

Today is {today}.
{dedup_section}
Write with authority — crisp, opinionated, newspaper voice. Lead with what CHANGED, not what's normal. If processing volume spiked or dropped, lead with that. If a new topic emerged that wasn't there yesterday, that's news. If channels went quiet, flag it.

## RAW DATA

{digest}

## OUTPUT FORMAT

Produce the report in this exact structure:

# The KS Examiner — {today}

## 📡 SITUATION REPORT
2-3 sentence narrative overview. "Your network processed X videos across Y channels. [Key observation about what was different today]. Here's what you need to know." Lead with the most interesting operational fact.

## 🔀 CONVERGENCE ALERTS
The most valuable section. When 3+ channels from different domains independently cover the same topic, that's a real signal worth investigating. For each convergence:
- What the topic is
- Which channels hit it (and briefly why it's notable that THESE channels converged)
- What it might signal

If no convergence alerts exist, say "No cross-channel convergence detected today" and note what this means (diverse coverage day, or thin data).

## 📈 TOPIC HEAT MAP
Ranked list of the top topics by volume. For each:
**Topic** — count — trend indicator (↑ up from yesterday, ↓ down, 🆕 new today, — steady) — brief note

## 📺 CHANNEL ACTIVITY
Which channels were most active. Call out:
- Channels publishing at unusual volume (more or less than typical)
- Channels that went quiet (subscribed but no content)
- Any pattern worth noting (e.g., "AI channels dominated today while health channels were unusually quiet")

## ⚠️ ATTENTION NEEDED
Operational issues: processing failures, low transcript rate, large unprocessed queue, channels with no recent activity that should have some. If everything is clean, say "Operations nominal."

## 📊 DAILY STATS
Quick stat block:
- Processing: X completed / Y failed / Z pending
- Transcript rate: X%
- Channel coverage: X of Y subscribed channels active
- vs. previous period: ↑/↓ X videos
- Queue: X unprocessed videos waiting

## RULES
- Be opinionated about what matters. Not everything is equally interesting.
- Lead with what CHANGED, not the status quo.
- Convergence alerts are the crown jewel — give them the most attention.
- Keep the entire report under 800 words.
- If data is thin or nothing notable happened, say so directly.
- This is an operations report, not a content summary — focus on the OPERATION, not the video content itself.
"""

    print(f"\n[KS Examiner Synthesizer] Generating report...")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2500,
        messages=[{"role": "user", "content": prompt}]
    )

    brief = response.content[0].text

    # Add metadata footer
    brief += f"\n\n---\n*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | KS Examiner — Daily Operations Report*"

    print(f"[KS Examiner Synthesizer] Report generated ({len(brief)} chars)")
    return brief


def generate_daily_brief(vertical: str = "ks_examiner",
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
        vertical="ks_examiner",
        hours_back=24,
        db_path=DB_PATH,
        output_dir=OUTPUT_DIR,
    )

    print("\n" + "=" * 60)
    print(brief)
    print("=" * 60)

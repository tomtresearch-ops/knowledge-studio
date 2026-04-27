"""
Channel Intelligence Synthesizer
Generates comprehensive "channel bibles" from all processed videos for a given channel.
Produces a synthesized profile piece — like a Wikipedia page for a YouTube channel.
"""

import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from anthropic import Anthropic


MODEL = "claude-haiku-4-5-20251001"
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_intelligence.db")


def get_channel_videos(channel_name: str, db_path: str = None) -> List[Dict]:
    """
    Fetch all completed videos for a channel, ordered chronologically.
    Deduplicates by title (keeps the one with the longest summary).
    """
    path = db_path or DATABASE_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title,
               COALESCE(original_publish_date, published_at, processing_date) as pub_date,
               ai_summary, key_insights, topics, full_transcript,
               channel, video_url, prompt_used
        FROM videos
        WHERE channel LIKE ?
          AND ai_summary IS NOT NULL
          AND ai_summary != ''
        ORDER BY COALESCE(original_publish_date, published_at, processing_date) ASC
    ''', (f'%{channel_name}%',))

    rows = cursor.fetchall()
    conn.close()

    # Dedup by title — keep the one with the longest summary
    seen_titles = {}
    for row in rows:
        title = (row['title'] or '').strip().lower()
        if title in seen_titles:
            existing = seen_titles[title]
            if len(row['ai_summary'] or '') > len(existing['ai_summary'] or ''):
                seen_titles[title] = dict(row)
        else:
            seen_titles[title] = dict(row)

    # Return chronologically sorted, deduped
    videos = list(seen_titles.values())
    videos.sort(key=lambda v: v.get('pub_date') or '1970-01-01')

    return videos


def classify_channel_type(videos: List[Dict], client: Anthropic) -> str:
    """
    Quick classification pass (~100 tokens output).
    Reads video titles and topic snippets to determine channel content type.
    """
    # Build a compact summary of the channel's content
    sample_lines = []
    for v in videos[:30]:  # Sample up to 30 titles
        title = v.get('title', '')
        topics = v.get('topics', '')
        line = f"- {title}"
        if topics:
            line += f" [{topics[:80]}]"
        sample_lines.append(line)

    sample_text = "\n".join(sample_lines)

    response = client.messages.create(
        model=MODEL,
        max_tokens=100,
        messages=[{
            "role": "user",
            "content": f"""Based on these video titles from a YouTube channel, classify the channel's primary content type in 3-8 words. Examples: "AI strategy & enterprise commentary", "online business coaching & niche marketing", "health protocols & longevity science", "tech tutorials & developer workflows".

Video titles:
{sample_text}

Reply with ONLY the classification, nothing else."""
        }]
    )

    return response.content[0].text.strip().strip('"')


def prepare_summaries_digest(videos: List[Dict]) -> str:
    """
    Format all video summaries into a chronological digest.
    """
    sections = []
    for v in videos:
        title = v.get('title', 'Untitled')
        date = v.get('pub_date', '')
        if date:
            try:
                dt = datetime.fromisoformat(date.replace('Z', '+00:00').replace('+00:00', ''))
                date_str = dt.strftime('%b %d, %Y')
            except (ValueError, TypeError):
                date_str = date[:10] if len(date) >= 10 else date
        else:
            date_str = 'Unknown date'

        summary = v.get('ai_summary', '')

        sections.append(f"## {title} ({date_str})\n\n{summary}")

    return "\n\n---\n\n".join(sections)


def get_date_range(videos: List[Dict]) -> str:
    """Get the date range string for the videos."""
    if not videos:
        return "No dates"

    dates = []
    for v in videos:
        d = v.get('pub_date', '')
        if d:
            try:
                dt = datetime.fromisoformat(d.replace('Z', '+00:00').replace('+00:00', ''))
                dates.append(dt)
            except (ValueError, TypeError):
                pass

    if not dates:
        return "Unknown dates"

    earliest = min(dates)
    latest = max(dates)
    return f"{earliest.strftime('%b %Y')} – {latest.strftime('%b %Y')}"


def generate_channel_bible(channel_name: str,
                           channel_type: str,
                           content_digest: str,
                           video_count: int,
                           date_range: str,
                           client: Anthropic) -> Tuple[str, dict]:
    """
    Final synthesis pass. Generates the channel bible.
    Returns (bible_text, usage_dict).
    """

    prompt = f"""You are an intelligence analyst creating a comprehensive knowledge document about a YouTube creator's body of work. Think of this as a Wikipedia page for their channel — synthesized, substantive, and useful.

**Channel:** {channel_name}
**Content Type:** {channel_type}
**Videos Analyzed:** {video_count} ({date_range})

Below is a chronological digest of all their processed content. Your job: distill this into a Channel Bible — a definitive reference that captures how this creator thinks, what they believe, and what they teach.

---

{content_digest}

---

## INSTRUCTIONS

Write a synthesized profile piece, NOT a list extraction. The reader should understand this creator's worldview after reading this document.

### Required Sections:

**OVERVIEW** (2-3 paragraphs)
Who this person is, how they see the world, what makes their perspective distinctive vs. generic voices in their space. Their audience, credibility, and unique angle. A reader should "get" this creator after this section alone.

**CORE ARGUMENTS** (3-5 substantive paragraphs)
The big ideas they keep making across multiple videos. Each core argument gets its OWN paragraph that weaves together evidence from multiple videos. Explain the *why* — not just what they claim, but the reasoning and evidence they build around it. Name specific frameworks, models, or concepts they've coined.

**PREDICTIONS & FORWARD-LOOKING CLAIMS** (clean list)
Specific claims about the future, timestamped by when they made them. Format: "Month Year: [the claim]". Just the claims — no analysis needed, the list speaks for itself.

**HOW THEY'RE EVOLVING** (1-2 paragraphs)
How their thinking has shifted across the time window. What did they emphasize early vs. now? Any pivots, corrections, or deepening of positions? Use the chronological ordering to track this.

**ESSENTIAL VIEWING** (top 5)
The most information-dense or foundational videos from this channel. One sentence each on why it's essential.

### Optional Sections (add if warranted by the content):
- Tool opinions & stack preferences
- Contrarian positions (where they disagree with mainstream)
- Methodologies or step-by-step frameworks
- Industry-specific analysis

### Rules:
- Write in present tense about the creator's current positions.
- Be specific. Name frameworks, reference specific video titles, quote distinctive phrases.
- Core arguments get PARAGRAPHS, not bullets. Weave multiple video references into each paragraph.
- Density over length. Every sentence should carry information.
- If the content is thin on a section, say so rather than padding.
- Predictions list should be clean and scannable — no prose needed there.
- Aim for 2500-4000 words total depending on how much substantive content exists.
- Do NOT include video URLs or links. Just reference titles when relevant.
"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=6000,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )

    bible_text = response.content[0].text
    usage = {
        'input': response.usage.input_tokens,
        'output': response.usage.output_tokens
    }

    return bible_text, usage


def run_channel_intelligence(channel_id: str,
                              channel_name: str,
                              mode: str = 'summaries',
                              db_path: str = None,
                              api_key: str = None) -> Dict:
    """
    Full pipeline: fetch videos -> classify -> synthesize -> return result.

    Returns dict with: content, channel_type, video_count, video_date_range,
    source_video_ids, token_usage, estimated_cost
    """
    client = Anthropic(api_key=api_key) if api_key else Anthropic()

    # 1. Fetch all processed videos for this channel
    videos = get_channel_videos(channel_name, db_path=db_path)

    if not videos:
        raise ValueError(f"No processed videos found for channel: {channel_name}")

    # 2. Classify the channel type
    channel_type = classify_channel_type(videos, client)

    # 3. Get date range
    date_range = get_date_range(videos)

    # 4. Prepare digest and synthesize
    total_usage = {'input': 0, 'output': 0}

    if mode == 'summaries':
        digest = prepare_summaries_digest(videos)
        bible_text, usage = generate_channel_bible(
            channel_name, channel_type, digest,
            len(videos), date_range, client
        )
        total_usage['input'] += usage['input']
        total_usage['output'] += usage['output']
    else:
        # Transcript multi-pass mode
        # Chunk into batches of 10 videos
        batch_size = 10
        intermediate_summaries = []

        for i in range(0, len(videos), batch_size):
            batch = videos[i:i+batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (len(videos) + batch_size - 1) // batch_size

            # Build transcript digest for this batch
            batch_lines = []
            for v in batch:
                title = v.get('title', 'Untitled')
                transcript = v.get('full_transcript', '') or v.get('ai_summary', '')
                date = v.get('pub_date', '')[:10] if v.get('pub_date') else ''
                batch_lines.append(f"## {title} ({date})\n\n{transcript[:15000]}")

            batch_text = "\n\n---\n\n".join(batch_lines)

            response = client.messages.create(
                model=MODEL,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": f"""You are analyzing batch {batch_num} of {total_batches} from the YouTube channel "{channel_name}".

Extract and synthesize the key themes, frameworks, predictions, strategies, and distinctive perspectives from these videos. Preserve specific details — named frameworks, timestamps, contrarian positions, concrete recommendations.

{batch_text}

Produce a structured summary of the key content from this batch. Be specific and dense."""
                }]
            )

            intermediate_summaries.append(response.content[0].text)
            total_usage['input'] += response.usage.input_tokens
            total_usage['output'] += response.usage.output_tokens

        # Final synthesis from intermediate summaries
        combined = "\n\n---\n\n".join([
            f"## Batch {i+1}\n\n{s}" for i, s in enumerate(intermediate_summaries)
        ])

        bible_text, usage = generate_channel_bible(
            channel_name, channel_type, combined,
            len(videos), date_range, client
        )
        total_usage['input'] += usage['input']
        total_usage['output'] += usage['output']

    # Calculate estimated cost (Haiku pricing: $1/MTok input, $5/MTok output)
    estimated_cost = (total_usage['input'] * 1.0 / 1_000_000) + (total_usage['output'] * 5.0 / 1_000_000)

    return {
        'content': bible_text,
        'channel_type': channel_type,
        'video_count': len(videos),
        'video_date_range': date_range,
        'source_video_ids': [v['id'] for v in videos],
        'token_usage': total_usage,
        'estimated_cost': round(estimated_cost, 4)
    }


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("Usage: python channel_intelligence_synthesizer.py <channel_id> <channel_name> [mode]")
        sys.exit(1)

    channel_id = sys.argv[1]
    channel_name = sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else 'summaries'

    print(f"Generating channel intelligence for: {channel_name} (mode: {mode})")
    result = run_channel_intelligence(channel_id, channel_name, mode=mode)

    print(f"\nChannel Type: {result['channel_type']}")
    print(f"Videos Analyzed: {result['video_count']}")
    print(f"Date Range: {result['video_date_range']}")
    print(f"Tokens: {result['token_usage']}")
    print(f"Estimated Cost: ${result['estimated_cost']}")
    print(f"\n{'='*60}\n")
    print(result['content'])

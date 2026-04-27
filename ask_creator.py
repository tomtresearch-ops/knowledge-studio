#!/usr/bin/env python3
"""
Ask Creator — Query a YouTube creator's body of work using Claude Sonnet.

Usage:
    python3 ask_creator.py "Sunny" "What does she think about online courses?"
    python3 ask_creator.py --list-creators
    python3 ask_creator.py --history "Sunny"
"""

import os
import sys
import json
import re
import sqlite3
import argparse
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic

# Load .env from project directory
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))


MODEL = "claude-sonnet-4-5-20250929"
DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_intelligence.db")

# Sonnet pricing: $3/MTok input, $15/MTok output
COST_PER_MTOK_INPUT = 3.0
COST_PER_MTOK_OUTPUT = 15.0

# Relevance thresholds
MAX_RELEVANT_VIDEOS = 15
MIN_RELEVANT_VIDEOS = 5
MAX_CHAR_LIMIT = 150_000

# Stop words to exclude from keyword extraction
STOP_WORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
    'should', 'may', 'might', 'can', 'shall', 'to', 'of', 'in', 'for',
    'on', 'with', 'at', 'by', 'from', 'as', 'into', 'through', 'during',
    'before', 'after', 'above', 'below', 'between', 'out', 'off', 'over',
    'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when',
    'where', 'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own',
    'same', 'so', 'than', 'too', 'very', 'just', 'about', 'up', 'down',
    'and', 'but', 'or', 'if', 'while', 'because', 'until', 'that', 'which',
    'who', 'whom', 'this', 'these', 'those', 'it', 'its', 'i', 'me', 'my',
    'we', 'our', 'you', 'your', 'he', 'him', 'his', 'she', 'her', 'they',
    'them', 'their', 'what', 'any', 'many', 'much', 'also', 'like', 'get',
    'got', 'make', 'made', 'think', 'thinks', 'thought', 'know', 'known',
    'really', 'well', 'even', 'still', 'thing', 'things', 'something',
    'anything', 'everything', 'nothing', 'way', 'ways', 'want', 'need',
    'use', 'used', 'using', 'says', 'said', 'say', 'tell', 'told',
}


def ensure_queries_table(conn):
    """Create the creator_queries table if it doesn't exist."""
    conn.execute('''
        CREATE TABLE IF NOT EXISTS creator_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_name TEXT NOT NULL,
            channel_id TEXT,
            question TEXT NOT NULL,
            synthesis TEXT NOT NULL,
            source_video_ids TEXT,
            video_count INTEGER DEFAULT 0,
            model_used TEXT DEFAULT 'claude-sonnet-4-5-20250929',
            tokens_input INTEGER DEFAULT 0,
            tokens_output INTEGER DEFAULT 0,
            estimated_cost REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()


def get_channel_videos(channel_name, conn):
    """Fetch all videos with summaries for a channel."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, title, channel,
               COALESCE(original_publish_date, published_at, processing_date) as pub_date,
               ai_summary, key_insights, topics, video_url
        FROM videos
        WHERE channel LIKE ?
          AND ai_summary IS NOT NULL
          AND ai_summary != ''
        ORDER BY COALESCE(original_publish_date, published_at, processing_date) DESC
    ''', (f'%{channel_name}%',))

    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


def get_channel_bible(channel_name, conn):
    """Check if a channel bible exists and return condensed version."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT content, channel_id
        FROM channel_intelligence
        WHERE channel_name LIKE ?
          AND status = 'complete'
        ORDER BY updated_at DESC
        LIMIT 1
    ''', (f'%{channel_name}%',))

    row = cursor.fetchone()
    if row:
        return row[0][:2000], row[1]
    return None, None


def extract_keywords(question):
    """Extract meaningful keywords from the question."""
    words = re.findall(r'[a-zA-Z]+', question.lower())
    keywords = [w for w in words if w not in STOP_WORDS and len(w) > 2]
    return keywords


def score_video_relevance(video, keywords):
    """Score a video by how many question keywords appear in its searchable text."""
    searchable = ' '.join([
        (video.get('title') or ''),
        (video.get('ai_summary') or ''),
        (video.get('topics') or ''),
        (video.get('key_insights') or ''),
    ]).lower()

    score = 0
    for kw in keywords:
        count = searchable.count(kw)
        if count > 0:
            score += count
    return score


def select_relevant_videos(videos, question):
    """
    Score and select the most relevant videos for the question.
    Returns (selected_videos, total_searched).
    """
    keywords = extract_keywords(question)

    if not keywords:
        # No meaningful keywords -- return all up to max
        return videos[:MAX_RELEVANT_VIDEOS], len(videos)

    scored = []
    for v in videos:
        score = score_video_relevance(v, keywords)
        scored.append((score, v))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Check how many have a meaningful relevance score (> 0)
    relevant = [(s, v) for s, v in scored if s > 0]

    if len(relevant) < MIN_RELEVANT_VIDEOS:
        # Not enough keyword matches -- include all videos up to char limit
        selected = videos
    else:
        selected = [v for _, v in relevant[:MAX_RELEVANT_VIDEOS]]

    # Enforce character limit
    total_chars = 0
    final = []
    for v in selected:
        summary_len = len(v.get('ai_summary') or '')
        if total_chars + summary_len > MAX_CHAR_LIMIT:
            break
        total_chars += summary_len
        final.append(v)

    return final, len(videos)


def format_video_for_prompt(video):
    """Format a single video's data for inclusion in the prompt."""
    title = video.get('title', 'Untitled')
    date = video.get('pub_date', '')
    if date:
        try:
            dt = datetime.fromisoformat(date.replace('Z', '+00:00').replace('+00:00', ''))
            date_str = dt.strftime('%b %d, %Y')
        except (ValueError, TypeError):
            date_str = date[:10] if len(date) >= 10 else date
    else:
        date_str = 'Unknown date'

    summary = video.get('ai_summary', '')
    key_insights = video.get('key_insights', '')
    topics = video.get('topics', '')

    parts = [f"## {title} ({date_str})\n"]
    if topics:
        parts.append(f"Topics: {topics}")
    if key_insights:
        parts.append(f"Key Insights: {key_insights}")
    parts.append(f"\n{summary}")

    return '\n'.join(parts)


def synthesize_answer(question, videos, channel_name, bible_context=None):
    """Send the question and video summaries to Claude Sonnet for synthesis."""
    client = Anthropic()

    # Format video summaries
    video_sections = [format_video_for_prompt(v) for v in videos]
    video_text = '\n\n---\n\n'.join(video_sections)

    # Build user message
    user_parts = [f'Question about {channel_name}: {question}\n']

    if bible_context:
        user_parts.append(
            f'--- CHANNEL PROFILE (condensed) ---\n{bible_context}\n---\n'
        )

    user_parts.append(
        f'--- VIDEO SUMMARIES ({len(videos)} videos) ---\n\n{video_text}'
    )

    user_message = '\n'.join(user_parts)

    system_prompt = (
        "You are a research analyst answering questions about a YouTube creator's "
        "body of work. You have access to their video summaries. Ground your answers "
        "in specific content from their videos — cite video titles when referencing "
        "specific claims. Be substantive and specific, not generic."
    )

    response = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=system_prompt,
        messages=[{
            'role': 'user',
            'content': user_message,
        }],
    )

    synthesis = response.content[0].text
    usage = {
        'input': response.usage.input_tokens,
        'output': response.usage.output_tokens,
    }

    return synthesis, usage


def save_query(conn, channel_name, channel_id, question, synthesis,
               video_ids, video_count, usage):
    """Save the query and result to the database."""
    ensure_queries_table(conn)

    cost = (
        (usage['input'] * COST_PER_MTOK_INPUT / 1_000_000) +
        (usage['output'] * COST_PER_MTOK_OUTPUT / 1_000_000)
    )

    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO creator_queries
            (channel_name, channel_id, question, synthesis, source_video_ids,
             video_count, model_used, tokens_input, tokens_output, estimated_cost)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        channel_name,
        channel_id,
        question,
        synthesis,
        json.dumps(video_ids),
        video_count,
        MODEL,
        usage['input'],
        usage['output'],
        round(cost, 6),
    ))
    conn.commit()

    return cursor.lastrowid, cost


def list_creators(conn):
    """List all unique channel names with video counts."""
    cursor = conn.cursor()
    cursor.execute('''
        SELECT channel, COUNT(*) as video_count
        FROM videos
        WHERE ai_summary IS NOT NULL AND ai_summary != ''
        GROUP BY channel
        ORDER BY video_count DESC
    ''')

    rows = cursor.fetchall()
    if not rows:
        print("No creators found in the database.")
        return

    print(f"\n{'Creator':<50} {'Videos':>6}")
    print('-' * 58)
    for channel, count in rows:
        name = (channel or 'Unknown')[:50]
        print(f"{name:<50} {count:>6}")
    print(f"\n{len(rows)} creators total.\n")


def show_history(conn, channel_name):
    """Show past queries for a creator."""
    ensure_queries_table(conn)

    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, question, synthesis, video_count, estimated_cost, created_at
        FROM creator_queries
        WHERE channel_name LIKE ?
        ORDER BY created_at DESC
        LIMIT 10
    ''', (f'%{channel_name}%',))

    rows = cursor.fetchall()
    if not rows:
        print(f"\nNo query history found for '{channel_name}'.")
        return

    print(f"\nQuery history for '{channel_name}' (last {len(rows)}):\n")
    for row_id, question, synthesis, video_count, cost, created_at in rows:
        preview = (synthesis or '')[:200]
        if len(synthesis or '') > 200:
            preview += '...'
        print(f"  #{row_id} [{created_at}] ({video_count} videos, ${cost:.4f})")
        print(f"  Q: {question}")
        print(f"  A: {preview}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Query a YouTube creator's body of work using Claude Sonnet.",
        usage='%(prog)s "Creator Name" "Your question?" | --list-creators | --history "Creator"',
    )
    parser.add_argument('creator', nargs='?', help='Creator/channel name to search for')
    parser.add_argument('question', nargs='?', help='Question to ask about their content')
    parser.add_argument('--list-creators', action='store_true',
                        help='List all creators in the database with video counts')
    parser.add_argument('--history', metavar='CREATOR',
                        help='Show past queries for a creator')

    args = parser.parse_args()

    conn = sqlite3.connect(DATABASE_PATH)

    try:
        if args.list_creators:
            list_creators(conn)
            return

        if args.history:
            show_history(conn, args.history)
            return

        if not args.creator or not args.question:
            parser.print_help()
            sys.exit(1)

        creator = args.creator
        question = args.question

        # Step 1: Find matching videos
        videos = get_channel_videos(creator, conn)

        if not videos:
            print(f"\nNo videos found for creator matching '{creator}'.")
            print("Use --list-creators to see available channels.")
            sys.exit(1)

        actual_channel = videos[0].get('channel', creator)
        total_videos = len(videos)

        # Step 2: Select relevant videos
        selected, total_searched = select_relevant_videos(videos, question)

        if not selected:
            print(f"\nFound {total_videos} videos for '{actual_channel}' but none could be selected.")
            sys.exit(1)

        # Step 3: Check for channel bible
        bible_context, channel_id = get_channel_bible(creator, conn)

        print(f"\nSearching {actual_channel}'s content...")
        print(f"  Found {total_videos} videos total, using {len(selected)} most relevant.\n")

        # Step 4: Synthesize with Sonnet
        synthesis, usage = synthesize_answer(
            question, selected, actual_channel, bible_context
        )

        # Step 5: Save to database
        video_ids = [v['id'] for v in selected]
        query_id, cost = save_query(
            conn, actual_channel, channel_id, question, synthesis,
            video_ids, len(selected), usage
        )

        # Step 6: Print output
        print('=' * 70)
        print(f"  {actual_channel} — Q&A")
        print('=' * 70)
        print(f"\nQ: {question}\n")
        print(synthesis)
        print(f"\n{'=' * 70}")
        print(f"  Query #{query_id}")
        print(f"  Creator: {actual_channel}")
        print(f"  Videos searched: {total_videos} | Videos used: {len(selected)}")
        print(f"  Tokens: {usage['input']:,} in / {usage['output']:,} out")
        print(f"  Cost: ${cost:.4f}")
        print('=' * 70)

    finally:
        conn.close()


if __name__ == '__main__':
    main()

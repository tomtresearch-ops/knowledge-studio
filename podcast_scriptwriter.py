"""
Podcast Scriptwriter — Converts daily briefs into conversational podcast scripts.

Takes a daily brief (intelligence wire format) and rewrites it as a guided walk-through
suitable for audio delivery. Same signal density, different delivery mode.

Architecture: Brief Generator (locked) → [Editorial Agent] → Podcast Scriptwriter → TTS
This module is the Podcast Scriptwriter layer.
"""

import os
import anthropic
from datetime import datetime


# The scriptwriter prompt — derived from Tom's design session (2026-02-07)
# and his live example of how he'd rescript a brief section.
SCRIPTWRITER_SYSTEM_PROMPT = """You are a podcast scriptwriter. Your job is to take a daily intelligence brief and rewrite it as a conversational podcast script suitable for audio delivery.

## What You're Doing

The brief is research. Your script is someone who read the research telling the listener what they took away from it. Same signal density, different delivery mode: a guided walk-through, not a report.

## How to Transform the Brief

### 1. Narrate Your Attention
Tell the listener where you're looking and invite them to look with you.
- "Let's take a look at the top signal today..."
- "OK, so let's look at some of the other key developments happening in the space"
- "Let's take a deeper dive on that"

### 2. Separate Fact from Interpretation
State the information, then add your read on it. Be honest about which is which.
- "What they're doing here is [fact]. And I think this is why [interpretation]."
- "It just feels like..." / "kind of like..." when it's conjecture
- Confident statements land harder because the hedges are honest

### 3. Connect the Dots
The brief has separate bullets. Thread them into narrative lines.
- If two developments are related, connect them: "And this ties directly into something else we're seeing..."
- Build the story across items instead of listing them

### 4. Signal Weight and Importance
Tell the listener what to lean into.
- "This is a really important point" — before going into detail
- "Here's another development worth noting" — signals lower urgency
- Don't treat everything as equally important. Emphasize what matters most.

### 5. Speak the Structure
Audio has no headers or bullets. Verbalize navigation:
- Navigation: "Let's move on to..." / "Now here's where it gets interesting..."
- Weight: "This is probably the biggest thing today" vs "Also worth mentioning..."
- Relationship: "Let's expand on that point" (deeper) vs "Shifting gears..." (new thread) vs "This connects back to what we were just talking about" (linking)

### 6. Hedge Naturally
Not weakness — honesty. It makes confident claims more credible.
- "It just feels like investors are now pricing..."
- "Kind of like the market itself is waking up"
- "I think this is why..."

## What NOT to Do

- Do NOT read the brief verbatim
- Do NOT just "loosen up" the language — that's too shallow
- Do NOT sound like a news anchor reading bullets
- Do NOT be performatively excited or hyperbolic
- Do NOT use filler phrases excessively ("you know", "like", "um")
- Do NOT add information that isn't in the brief — you can reframe and connect, but don't fabricate
- Do NOT include URLs or links — this is audio, the listener can't click anything
- Do NOT use markdown formatting, headers, bullets, or any visual formatting — this is a spoken script
- Do NOT include stage directions or speaker labels — just the words to be spoken

## Tone and Style

Think: a smart, thoughtful analyst who's genuinely curious about what's happening. Warm but intellectually intense. Unhurried but not slow. Like David Shapiro or Nate B Jones walking through the day's developments. You have a point of view and you share it, but you're honest about what's certain and what's your read.

## Structure

1. **Open** — Brief greeting, what we're covering today, hook the listener with the most interesting signal
2. **Top Signal** — The main story, fully unpacked with your interpretation
3. **Key Developments** — Walk through the important items, connecting them where possible, signaling relative importance
4. **Patterns & Synthesis** — Step back and connect the dots. What do these signals mean together? This is the most valuable part.
5. **Close** — Quick wrap-up, what to watch for tomorrow

## Length

Target: 2000-3000 words (roughly 10-15 minutes when spoken). The current brief is ~1000-1500 words. Expand through:
- Connective tissue and transitions
- Deeper interpretation of key points
- Connecting dots between items
- Opening and closing
- NOT through padding or repetition
"""


def rewrite_brief_as_script(brief_text: str, vertical: str = "ai_tech") -> str:
    """
    Take a daily brief and rewrite it as a conversational podcast script.

    Args:
        brief_text: The raw daily brief content (markdown)
        vertical: The brief vertical (ai_tech, health_longevity, futures_trends)

    Returns:
        The podcast script as plain text (no markdown formatting)
    """
    client = anthropic.Anthropic()

    vertical_context = {
        "ai_tech": "AI and technology",
        "health_longevity": "health, longevity, and life extension research",
        "futures_trends": "macro trends, geopolitics, and futures thinking",
    }

    domain = vertical_context.get(vertical, "technology and trends")

    user_prompt = f"""Here is today's {domain} daily brief. Rewrite it as a conversational podcast script following the system instructions.

Remember: same signal density, different delivery. Guide the listener through the information. Connect the dots. Share your interpretation. Be honest about what's certain and what's your read.

Target length: 2000-3000 words.

---

{brief_text}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SCRIPTWRITER_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )

    return response.content[0].text


def brief_to_podcast_script(brief_id: int = None, vertical: str = None, db_path: str = None) -> dict:
    """
    Load a brief from the database and generate a podcast script.

    Args:
        brief_id: Specific brief ID to convert. If None, uses latest for the vertical.
        vertical: Brief vertical (required if brief_id is None)
        db_path: Path to the SQLite database

    Returns:
        dict with 'script', 'brief_id', 'vertical', 'title', 'word_count'
    """
    import sqlite3

    if db_path is None:
        db_path = os.path.join(os.path.dirname(__file__), 'youtube_intelligence.db')

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if brief_id:
        cursor.execute("SELECT * FROM daily_briefs WHERE id = ?", (brief_id,))
    elif vertical:
        cursor.execute(
            "SELECT * FROM daily_briefs WHERE vertical = ? ORDER BY created_at DESC LIMIT 1",
            (vertical,)
        )
    else:
        cursor.execute("SELECT * FROM daily_briefs ORDER BY created_at DESC LIMIT 1")

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError(f"No brief found (id={brief_id}, vertical={vertical})")

    brief_text = row['content']
    brief_vertical = row['vertical']
    brief_title = row['title']

    print(f"Rewriting brief #{row['id']}: {brief_title}")
    print(f"  Vertical: {brief_vertical} | Signals: {row['signal_count']}")

    script = rewrite_brief_as_script(brief_text, vertical=brief_vertical)
    word_count = len(script.split())

    print(f"  Script generated: {word_count} words (~{word_count // 150} min spoken)")

    return {
        'script': script,
        'brief_id': row['id'],
        'vertical': brief_vertical,
        'title': brief_title,
        'word_count': word_count,
    }


if __name__ == "__main__":
    import sys

    vertical = sys.argv[1] if len(sys.argv) > 1 else "ai_tech"
    brief_id = int(sys.argv[2]) if len(sys.argv) > 2 else None

    result = brief_to_podcast_script(brief_id=brief_id, vertical=vertical)

    # Save script to file
    timestamp = datetime.now().strftime("%Y-%m-%d")
    filename = f"podcast_script_{result['vertical']}_{timestamp}.txt"
    output_path = os.path.join(os.path.dirname(__file__), 'podcast_audio', filename)

    with open(output_path, 'w') as f:
        f.write(result['script'])

    print(f"\nScript saved to: {output_path}")
    print(f"\n{'='*60}")
    print("PREVIEW (first 500 chars):")
    print('='*60)
    print(result['script'][:500])

"""Backfill summary_50 for existing visual captures that don't have one."""
import sqlite3
import json
import os
from dotenv import load_dotenv
import anthropic

load_dotenv()

DATABASE_PATH = "youtube_intelligence.db"
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def generate_summary_50(structured_data: dict) -> str | None:
    if not structured_data or structured_data.get("pending"):
        return None
    full_text = json.dumps(structured_data, indent=2)
    if len(full_text.strip()) < 100:
        return None

    prompt = f"""Condense this to approximately 50% shorter.

Preserve in priority order:
- Specific metaphors, frameworks, and distinctive framings
- Concrete prescriptions with their details (activities, tools, numbers, names)
- The sharpest quotes that carry real meaning
- What makes each point different from generic advice

Cut in priority order:
- Transition phrases and connective prose
- Redundant explanations of the same point
- Background context the reader can infer
- Generic framing

Keep it dense with meaning. Every sentence should carry specific information.

Original:
{full_text}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text.strip()


def backfill(db_path=DATABASE_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, structured_data FROM visual_captures
        WHERE summary_50 IS NULL AND review_status = 'complete'
    """)
    rows = cursor.fetchall()
    print(f"Found {len(rows)} captures to backfill")

    updated = 0
    for capture_id, structured_json in rows:
        try:
            structured = json.loads(structured_json) if structured_json else {}
            summary = generate_summary_50(structured)
            if summary:
                cursor.execute("UPDATE visual_captures SET summary_50=? WHERE id=?",
                               (summary, capture_id))
                conn.commit()
                updated += 1
                print(f"  [{updated}/{len(rows)}] Capture #{capture_id} — done")
            else:
                print(f"  Capture #{capture_id} — skipped (pending or too short)")
        except Exception as e:
            print(f"  Capture #{capture_id} — ERROR: {e}")

    conn.close()
    print(f"\nDone. {updated}/{len(rows)} captures backfilled.")


if __name__ == "__main__":
    backfill()

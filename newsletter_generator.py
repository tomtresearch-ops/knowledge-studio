"""
Newsletter Generator — Brief → Editorial Newsletter
Takes a synthesized brief from the DB and produces a short, editorial-style
newsletter (3 signals + synthesis) using Haiku, then outputs newsletter-ready HTML.
"""

import os
import sys
import json
import sqlite3
import re
from datetime import datetime
from dotenv import load_dotenv
from anthropic import Anthropic

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))
DB_PATH = os.path.join(BASE_DIR, "youtube_intelligence.db")

# Enable automatic API usage logging
sys.path.insert(0, BASE_DIR)
import api_logger
api_logger.patch(DB_PATH)
OUTPUT_DIR = os.path.join(BASE_DIR, "newsletter_output")

VERTICAL_CONFIG = {
    "ai_tech": {
        "name": "AI & Tech",
        "masthead": "AI & Tech Brief",
        "tagline": "AI-curated intelligence on artificial intelligence, machine learning, and technology",
        "podcast_feed": "https://tomtresearch-ops.github.io/ks-podcasts/feed_ai_tech.xml",
        "accent_color": "#6a9ec4",
    },
    "health_longevity": {
        "name": "Health & Longevity",
        "masthead": "Health & Longevity Brief",
        "tagline": "AI-curated intelligence on aging, longevity, and life extension research",
        "podcast_feed": "https://tomtresearch-ops.github.io/ks-podcasts/feed_health_longevity.xml",
        "accent_color": "#c4956a",
    },
    "ai_agents": {
        "name": "AI Agents",
        "masthead": "AI Agents Brief",
        "tagline": "AI-curated intelligence on autonomous agents, agent frameworks, and the agent economy",
        "podcast_feed": "",
        "accent_color": "#4a9e8e",
    },
    "future_medicine": {
        "name": "Breakthrough Medicine",
        "masthead": "Breakthrough Medicine Brief",
        "tagline": "AI-curated intelligence on longevity science, biotech, and the future of medicine",
        "podcast_feed": "",
        "accent_color": "#e05c5c",
    },
    "futures_trends": {
        "name": "Futures & Trends",
        "masthead": "Futures & Trends Brief",
        "tagline": "AI-curated intelligence on emerging trends, technology futures, and paradigm shifts",
        "podcast_feed": "",
        "accent_color": "#8a6ac4",
    },
    "lifestage_early_childhood": {
        "name": "Early Childhood (0-5)",
        "masthead": "Early Childhood Brief",
        "tagline": "Evidence-based intelligence for parents of infants, toddlers, and preschoolers",
        "podcast_feed": "",
        "accent_color": "#e8a87c",
    },
    "lifestage_elementary": {
        "name": "Elementary (6-10)",
        "masthead": "Elementary Years Brief",
        "tagline": "Research-grounded intelligence for parents navigating the elementary school years",
        "podcast_feed": "",
        "accent_color": "#85c88a",
    },
    "lifestage_middle_school": {
        "name": "Middle School (11-13)",
        "masthead": "Middle School Brief",
        "tagline": "Evidence-based intelligence for parents of tweens navigating puberty, identity, and social media",
        "podcast_feed": "",
        "accent_color": "#7ec8c8",
    },
    "lifestage_high_school": {
        "name": "High School (14-18)",
        "masthead": "High School Brief",
        "tagline": "Research-grounded intelligence for parents of teens preparing for what comes next",
        "podcast_feed": "",
        "accent_color": "#c87e7e",
    },
    "lifestage_college": {
        "name": "College (18-22)",
        "masthead": "College Years Brief",
        "tagline": "Intelligence for parents and students navigating higher education in a rapidly changing world",
        "podcast_feed": "",
        "accent_color": "#7e7ec8",
    },
    "lifestage_early_career": {
        "name": "Early Career (22-30)",
        "masthead": "Early Career Brief",
        "tagline": "Intelligence for professionals in their first career decade — skills, positioning, and opportunity",
        "podcast_feed": "",
        "accent_color": "#c8b07e",
    },
    "lifestage_mid_career": {
        "name": "Mid Career (30-50)",
        "masthead": "Mid Career Brief",
        "tagline": "Intelligence for professionals navigating career evolution, pivots, and leadership",
        "podcast_feed": "",
        "accent_color": "#7ec896",
    },
    "lifestage_late_career": {
        "name": "Late Career (50-65)",
        "masthead": "Late Career Brief",
        "tagline": "Intelligence for professionals planning reinvention, second acts, and transition",
        "podcast_feed": "",
        "accent_color": "#c87eb0",
    },
    "lifestage_seniors": {
        "name": "Seniors (65+)",
        "masthead": "Seniors Brief",
        "tagline": "Intelligence for staying connected, healthy, and engaged in a technology-driven world",
        "podcast_feed": "",
        "accent_color": "#b0c87e",
    },
}


def get_latest_brief(vertical: str) -> dict:
    """Fetch the most recent brief for a vertical from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, vertical, title, content, signal_count, source_count, created_at "
        "FROM daily_briefs WHERE vertical = ? ORDER BY created_at DESC LIMIT 1",
        (vertical,)
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "vertical": row[1],
        "title": row[2],
        "content": row[3],
        "signal_count": row[4],
        "source_count": row[5],
        "created_at": row[6],
    }


def generate_newsletter_editorial(brief_content: str, vertical: str) -> dict:
    """
    Use Haiku to distill a full brief into a 3-signal editorial newsletter.
    Returns: {headline, subtitle, editorial_intro, signals: [{headline, body, whycare}], bigger_picture}
    """
    config = VERTICAL_CONFIG[vertical]
    client = Anthropic()

    prompt = f"""You are an editorial newsletter writer for "{config['name']}" — a curated intelligence brief.

Below is today's full brief. Your job: distill it into a SHORT, compelling newsletter email with exactly 3 signals.

RULES:
- Pick the 3 most interesting/actionable signals from the brief
- Write in plain, confident English — not academic, not hype
- Each signal: 3-4 sentences max explaining what happened and why it matters
- Each "why care" line: 1-2 sentences, practical/forward-looking, starts with an action phrase
- The headline should hook a curious, intelligent reader (not clickbait, but intriguing)
- The subtitle teases all 3 signals in one sentence
- The editorial intro (2-3 sentences) sets up why these 3 things matter together — hook the reader
- The "bigger picture" section (3-4 sentences) connects the dots across all 3 signals — what pattern is emerging?
- NO jargon walls. A smart non-specialist should understand every word.
- NO links or URLs

Return ONLY valid JSON in this exact format:
{{
  "headline": "...",
  "subtitle": "Plus: ... and ...",
  "editorial_intro": "...",
  "signals": [
    {{
      "headline": "...",
      "body": "...",
      "whycare": "..."
    }},
    {{
      "headline": "...",
      "body": "...",
      "whycare": "..."
    }},
    {{
      "headline": "...",
      "body": "...",
      "whycare": "..."
    }}
  ],
  "bigger_picture": "..."
}}

FULL BRIEF:
{brief_content}"""

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )

    text = response.content[0].text.strip()
    # Extract JSON from response (handle markdown code blocks)
    if text.startswith("```"):
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

    return json.loads(text)


def render_newsletter_html(editorial: dict, vertical: str, brief_date: str,
                           signal_count: int, source_count: int) -> str:
    """Render the editorial content into the approved newsletter HTML template."""
    config = VERTICAL_CONFIG[vertical]
    accent = config["accent_color"]

    # Format date for display
    try:
        dt = datetime.strptime(brief_date[:10], "%Y-%m-%d")
        display_date = dt.strftime("%B %d, %Y").replace(" 0", " ")
    except (ValueError, TypeError):
        display_date = brief_date

    # Build podcast link
    podcast_cta = ""
    if config["podcast_feed"]:
        podcast_cta = f'<a href="{config["podcast_feed"]}" class="cta-button cta-secondary">&#9658; Listen</a>'

    # Build signals HTML
    signals_html = ""
    for i, sig in enumerate(editorial["signals"]):
        divider = '<hr class="divider">' if i < len(editorial["signals"]) - 1 else ""
        signals_html += f"""
  <div class="signal">
    <div class="signal-number">{str(i+1).zfill(2)}</div>
    <div class="signal-headline">{sig['headline']}</div>
    <div class="signal-body">{sig['body']}</div>
    <div class="signal-whycare">{sig['whycare']}</div>
  </div>
  {divider}
"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{config['masthead']} — {display_date}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: 'Georgia', 'Times New Roman', serif;
    background: #0a0a0a;
    color: #e8e4df;
    line-height: 1.75;
    -webkit-font-smoothing: antialiased;
  }}

  .container {{
    max-width: 600px;
    margin: 0 auto;
    padding: 40px 24px;
  }}

  .header {{
    padding-bottom: 28px;
    margin-bottom: 32px;
    border-bottom: 1px solid #2a2520;
  }}

  .masthead {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 11px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: #7a6f63;
    margin-bottom: 16px;
  }}

  .issue-title {{
    font-size: 26px;
    font-weight: 700;
    color: #f0ebe4;
    line-height: 1.35;
    margin-bottom: 12px;
  }}

  .issue-subtitle {{
    font-size: 16px;
    color: #a89e93;
    line-height: 1.6;
    font-style: italic;
  }}

  .issue-meta {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 12px;
    color: #5a5049;
    margin-top: 16px;
  }}

  .editorial {{
    font-size: 16px;
    color: #c4bdb3;
    line-height: 1.85;
    margin-bottom: 36px;
  }}

  .signal {{
    margin-bottom: 32px;
  }}

  .signal-number {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 11px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: {accent};
    margin-bottom: 8px;
    font-weight: 600;
  }}

  .signal-headline {{
    font-size: 19px;
    font-weight: 700;
    color: #f0ebe4;
    line-height: 1.4;
    margin-bottom: 12px;
  }}

  .signal-body {{
    font-size: 15.5px;
    color: #b5ada3;
    line-height: 1.85;
  }}

  .signal-whycare {{
    font-size: 15px;
    color: {accent};
    line-height: 1.75;
    margin-top: 12px;
    font-weight: 500;
  }}

  .divider {{
    border: none;
    border-top: 1px solid #1e1a16;
    margin: 32px 0;
  }}

  .bottomline {{
    background: #111;
    border-left: 3px solid {accent};
    padding: 20px 24px;
    margin: 36px 0;
    border-radius: 0 4px 4px 0;
  }}

  .bottomline-label {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 10px;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: {accent};
    margin-bottom: 10px;
    font-weight: 600;
  }}

  .bottomline-text {{
    font-size: 15.5px;
    color: #c4bdb3;
    line-height: 1.8;
  }}

  .cta-row {{
    text-align: center;
    margin: 36px 0;
  }}

  .cta-button {{
    display: inline-block;
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    text-decoration: none;
    padding: 12px 28px;
    border-radius: 4px;
    margin: 0 6px;
  }}

  .cta-primary {{
    background: {accent};
    color: #0a0a0a;
  }}

  .cta-secondary {{
    background: #1e1a16;
    color: {accent};
  }}

  .footer {{
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #1e1a16;
    text-align: center;
  }}

  .footer-text {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    font-size: 11px;
    color: #4a443d;
    line-height: 2;
  }}
</style>
</head>
<body>

<div class="container">

  <div class="header">
    <div class="masthead">{config['masthead']}</div>
    <div class="issue-title">{editorial['headline']}</div>
    <div class="issue-subtitle">{editorial['subtitle']}</div>
    <div class="issue-meta">{display_date} &middot; 3 min read</div>
  </div>

  <div class="editorial">
    {editorial['editorial_intro']}
  </div>

  {signals_html}

  <div class="bottomline">
    <div class="bottomline-label">The Bigger Picture</div>
    <div class="bottomline-text">
      {editorial['bigger_picture']}
    </div>
  </div>

  <div class="cta-row">
    <a href="#" class="cta-button cta-primary">Read the Full Brief</a>
    {podcast_cta}
  </div>

  <div class="footer">
    <div class="footer-text">
      {config['masthead']}<br>
      {config['tagline']}<br>
      {signal_count} signals processed from {source_count} sources
    </div>
  </div>

</div>

</body>
</html>"""

    return html


def generate_newsletter(vertical: str, brief_id: int = None) -> str:
    """
    Full pipeline: fetch brief → editorial pass → render HTML → save.
    Returns path to the generated newsletter HTML file.
    """
    if vertical not in VERTICAL_CONFIG:
        print(f"Unknown vertical: {vertical}")
        return None

    # Fetch brief
    if brief_id:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, vertical, title, content, signal_count, source_count, created_at "
            "FROM daily_briefs WHERE id = ?", (brief_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if not row:
            print(f"Brief {brief_id} not found")
            return None
        brief = {
            "id": row[0], "vertical": row[1], "title": row[2],
            "content": row[3], "signal_count": row[4],
            "source_count": row[5], "created_at": row[6],
        }
    else:
        brief = get_latest_brief(vertical)

    if not brief:
        print(f"No brief found for {vertical}")
        return None

    print(f"  Generating newsletter for {vertical} (brief #{brief['id']})...")

    # Editorial pass via Haiku
    print(f"  Running editorial distillation...")
    editorial = generate_newsletter_editorial(brief["content"], vertical)

    # Parse date from brief
    brief_date = brief["created_at"]

    # Render HTML
    print(f"  Rendering HTML...")
    html = render_newsletter_html(
        editorial, vertical, brief_date,
        brief["signal_count"], brief["source_count"]
    )

    # Save output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    date_str = brief_date[:10] if brief_date else datetime.now().strftime("%Y-%m-%d")
    filename = f"newsletter_{vertical}_{date_str}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)

    with open(filepath, "w") as f:
        f.write(html)

    print(f"  Newsletter saved: {filepath}")

    # Also save the editorial JSON for Ghost API posting
    json_path = os.path.join(OUTPUT_DIR, f"newsletter_{vertical}_{date_str}.json")
    editorial["_meta"] = {
        "vertical": vertical,
        "brief_id": brief["id"],
        "brief_date": brief_date,
        "signal_count": brief["signal_count"],
        "source_count": brief["source_count"],
        "generated_at": datetime.now().isoformat(),
    }
    with open(json_path, "w") as f:
        json.dump(editorial, f, indent=2)

    return filepath


if __name__ == "__main__":
    vertical = sys.argv[1] if len(sys.argv) > 1 else "health_longevity"
    brief_id = int(sys.argv[2]) if len(sys.argv) > 2 else None

    print(f"\n{'='*50}")
    print(f"NEWSLETTER GENERATOR")
    print(f"{'='*50}")

    result = generate_newsletter(vertical, brief_id)
    if result:
        print(f"\nDone! Open in browser: file://{result}")
    else:
        print("\nFailed to generate newsletter.")

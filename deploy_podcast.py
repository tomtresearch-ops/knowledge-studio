#!/usr/bin/env python3
"""
deploy_podcast.py — Generate RSS feeds and deploy podcast to GitHub Pages.

Reads brief_podcast_episodes from SQLite, generates Apple Podcasts-compatible
RSS feeds for ai_tech and health_longevity verticals, copies MP3s, and deploys
to GitHub Pages (tomtresearch-ops/ks-podcasts).

Usage: python3 deploy_podcast.py
"""

import sqlite3
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from email.utils import format_datetime
from xml.sax.saxutils import escape as xml_escape

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "youtube_intelligence.db")
AUDIO_SRC_DIR = os.path.join(BASE_DIR, "podcast_audio")
DEPLOY_DIR = os.path.join(BASE_DIR, "podcast_netlify")  # kept name for continuity
BASE_URL = "https://media-verticals.github.io/podcasts/"
MAX_EPISODES_DEFAULT = 3

# ── Feed metadata per vertical ───────────────────────────────────────────────
# ── Branding (swap these when brand is finalized) ────────────────────────────
BRAND_AUTHOR = "Knowledge Studio"  # TODO: replace with final brand name
BRAND_OWNER_NAME = "Knowledge Studio"  # TODO: replace with final owner name
BRAND_OWNER_EMAIL = "placeholder@example.com"  # TODO: replace with real email

FEED_CONFIG = {
    "ai_tech": {
        "filename": "feed_ai_landscape.xml",
        "title": "AI Landscape",  # TODO: replace with "[Brand]: AI"
        "description": (
            "AI-synthesized daily intelligence brief covering AI, "
            "tech infrastructure, and the forces shaping the industry."
        ),
        "category": "Technology",
        "mp3_glob": "podcast_ai_tech_*.mp3",
        "max_episodes": 0,  # Keep all — GitHub Pages has room
        "cover": "ai_landscape_cover.png",
    },
    "health_longevity": {
        "filename": "feed_longevity_edge.xml",
        "title": "Longevity Edge",  # TODO: replace with "[Brand]: Health"
        "description": (
            "AI-synthesized intelligence brief on health, longevity, "
            "and life extension research."
        ),
        "category": "Health &amp; Fitness",
        "mp3_glob": "podcast_health_longevity_*.mp3",
        "max_episodes": 0,  # 2/week — keep all
        "cover": "longevity_edge_cover.png",
    },
    "ks_youtube": {
        "filename": "feed_ks_youtube.xml",
        "title": "YouTube Intelligence Brief",
        "description": (
            "Daily intelligence brief synthesizing trends, hot topics, "
            "and cross-channel convergence from a 53-channel YouTube monitoring network."
        ),
        "category": "Technology",
        "mp3_glob": "podcast_ks_youtube_*.mp3",
        "max_episodes": 0,
        "cover": "ks_youtube_podcast_cover.png",
    },
    "ai_agents": {
        "filename": "feed_ai_agents.xml",
        "title": "AI Agents Brief",
        "description": (
            "Daily intelligence brief on AI agents, autonomous systems, "
            "and the agentic AI landscape."
        ),
        "category": "Technology",
        "mp3_glob": "podcast_ai_agents_*.mp3",
        "max_episodes": 0,
        "cover": "ai_agents_podcast_cover.png",
    },
    "future_medicine": {
        "filename": "feed_breakthrough_medicine.xml",
        "title": "Breakthrough Medicine",
        "description": (
            "Intelligence brief on the future of medicine, biotech, "
            "and health innovation."
        ),
        "category": "Health &amp; Fitness",
        "mp3_glob": "podcast_future_medicine_*.mp3",
        "max_episodes": 0,
        "cover": "breakthrough_medicine_cover.png",
    },
    "local_ai_intel": {
        "filename": "feed_local_ai_intel.xml",
        "title": "Local AI Intel Brief",
        "description": (
            "Intelligence brief on local AI, on-device models, "
            "and edge computing developments."
        ),
        "category": "Technology",
        "mp3_glob": "podcast_local_ai_intel_*.mp3",
        "max_episodes": 0,
        "cover": "local_ai_intel_podcast_cover.png",
    },
}


def format_duration(seconds: int) -> str:
    """Format seconds as HH:MM:SS."""
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def created_at_to_rfc2822(created_at_str: str) -> str:
    """Convert SQLite TIMESTAMP string to RFC 2822 format for pubDate."""
    # SQLite stores as 'YYYY-MM-DD HH:MM:SS' in UTC
    dt = datetime.strptime(created_at_str, "%Y-%m-%d %H:%M:%S")
    dt = dt.replace(tzinfo=timezone.utc)
    return format_datetime(dt)


def fetch_episodes(vertical: str) -> list[dict]:
    """Fetch ready episodes for a vertical, sorted by created_at descending."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, brief_id, vertical, title, description, audio_filename,
               audio_size, duration_seconds, script_text, status, created_at
        FROM brief_podcast_episodes
        WHERE status = 'ready' AND vertical = ?
        ORDER BY created_at DESC
        """,
        (vertical,),
    )
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def build_item_xml(episode: dict) -> str:
    """Build an RSS <item> element for a single episode."""
    title = xml_escape(episode["title"] or "Untitled")

    # Description: use curated description if available, else fall back to script truncation
    desc_text = episode["description"] or ""
    if not desc_text or desc_text.startswith("# ") or desc_text.startswith("Hey") or desc_text.startswith("Welcome"):
        script = episode["script_text"] or ""
        desc_text = script[:300]
        if len(script) > 300:
            desc_text += "..."
    description = xml_escape(desc_text)

    audio_url = BASE_URL + episode["audio_filename"]
    audio_size = episode["audio_size"] or 0
    duration = format_duration(episode["duration_seconds"] or 0)
    guid = f"brief-podcast-{episode['id']}"
    pub_date = created_at_to_rfc2822(episode["created_at"])

    return f"""    <item>
      <title>{title}</title>
      <description>{description}</description>
      <enclosure url="{xml_escape(audio_url)}" length="{audio_size}" type="audio/mpeg"/>
      <guid isPermaLink="false">{guid}</guid>
      <pubDate>{pub_date}</pubDate>
      <itunes:duration>{duration}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>"""


def generate_feed(vertical: str) -> str:
    """Generate a complete RSS 2.0 feed XML string for a vertical."""
    config = FEED_CONFIG[vertical]
    all_episodes = fetch_episodes(vertical)
    max_eps = config.get("max_episodes", MAX_EPISODES_DEFAULT)
    episodes = all_episodes[:max_eps] if max_eps > 0 else all_episodes

    print(f"  [{vertical}] {len(all_episodes)} total, deploying {'all' if max_eps == 0 else f'latest {len(episodes)}'}")

    items_xml = "\n".join(build_item_xml(ep) for ep in episodes)

    # Build date from most recent episode, or now
    if episodes:
        build_date = created_at_to_rfc2822(episodes[0]["created_at"])
    else:
        build_date = format_datetime(datetime.now(timezone.utc))

    feed_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:itunes="http://www.itunes.apple.com/dtds/podcast-1.0.dtd"
     xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{xml_escape(config["title"])}</title>
    <link>{BASE_URL}</link>
    <description>{xml_escape(config["description"])}</description>
    <language>en-us</language>
    <lastBuildDate>{build_date}</lastBuildDate>
    <atom:link href="{BASE_URL}{config['filename']}" rel="self" type="application/rss+xml"/>
    <itunes:author>{xml_escape(BRAND_AUTHOR)}</itunes:author>
    <itunes:summary>{xml_escape(config["description"])}</itunes:summary>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <itunes:owner>
      <itunes:name>{xml_escape(BRAND_OWNER_NAME)}</itunes:name>
      <itunes:email>{xml_escape(BRAND_OWNER_EMAIL)}</itunes:email>
    </itunes:owner>
    <itunes:image href="{BASE_URL}covers/{config["cover"]}"/>
    <image>
      <url>{BASE_URL}covers/{config["cover"]}</url>
      <title>{xml_escape(config["title"])}</title>
      <link>{BASE_URL}</link>
    </image>
    <itunes:category text="{config["category"]}"/>
{items_xml}
  </channel>
</rss>
"""
    return feed_xml


def copy_mp3s():
    """Copy only MP3 files that are in the current feeds, remove old ones."""
    # Collect filenames of episodes in the feeds
    needed = set()
    for vertical, config in FEED_CONFIG.items():
        all_episodes = fetch_episodes(vertical)
        max_eps = config.get("max_episodes", MAX_EPISODES_DEFAULT)
        keep = all_episodes if max_eps == 0 else all_episodes[:max_eps]
        for ep in keep:
            needed.add(ep["audio_filename"])

    # Copy needed files
    copied = 0
    for filename in needed:
        src = os.path.join(AUDIO_SRC_DIR, filename)
        dst = os.path.join(DEPLOY_DIR, filename)
        if os.path.exists(src):
            if not os.path.exists(dst) or os.path.getmtime(src) > os.path.getmtime(dst):
                shutil.copy2(src, dst)
                copied += 1

    # Remove old MP3s no longer in feeds
    removed = 0
    for filename in os.listdir(DEPLOY_DIR):
        if filename.endswith(".mp3") and filename not in needed:
            os.remove(os.path.join(DEPLOY_DIR, filename))
            removed += 1

    print(f"  {len(needed)} episodes in feeds, copied {copied} new, removed {removed} old")


def deploy_to_github_pages():
    """Deploy podcast_netlify/ to GitHub Pages via force-push."""
    print("\nDeploying to GitHub Pages...")
    git_bin = "/usr/bin/git"

    def run_git(*args):
        result = subprocess.run(
            [git_bin] + list(args),
            capture_output=True, text=True, cwd=DEPLOY_DIR,
        )
        if result.returncode != 0:
            print(f"ERROR: git {' '.join(args)} failed:\n{result.stderr}", file=sys.stderr)
            sys.exit(1)
        return result.stdout.strip()

    # Stage all changes (new, modified, deleted)
    run_git("add", "-A")

    # Check if there are changes to commit
    status = subprocess.run(
        [git_bin, "diff", "--cached", "--quiet"],
        cwd=DEPLOY_DIR,
    )
    if status.returncode == 0:
        print("  No changes to deploy.")
        return

    run_git("commit", "-m", f"Deploy {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    run_git("push", "origin", "main")
    print("Deploy complete.")


def main():
    # Ensure output directory exists
    os.makedirs(DEPLOY_DIR, exist_ok=True)

    # 1. Generate RSS feeds
    print("Generating RSS feeds...")
    for vertical, config in FEED_CONFIG.items():
        feed_xml = generate_feed(vertical)
        feed_path = os.path.join(DEPLOY_DIR, config["filename"])
        with open(feed_path, "w", encoding="utf-8") as f:
            f.write(feed_xml)
        print(f"  Wrote {feed_path}")

    # 2. Copy cover artwork to deploy dir
    covers_dir = os.path.join(DEPLOY_DIR, "covers")
    os.makedirs(covers_dir, exist_ok=True)
    for config in FEED_CONFIG.values():
        src = os.path.join(AUDIO_SRC_DIR, config["cover"])
        dst = os.path.join(covers_dir, config["cover"])
        if os.path.exists(src):
            shutil.copy2(src, dst)
    print("Copied cover artwork to covers/")

    # 3. Copy MP3 files
    print("\nCopying MP3 files...")
    copy_mp3s()

    # 4. Deploy to GitHub Pages
    deploy_to_github_pages()

    # 4. Print feed URLs
    print("\n" + "=" * 60)
    print("PODCAST FEED URLs (GitHub Pages):")
    for vertical, config in FEED_CONFIG.items():
        print(f"  {config['title']:30s} {BASE_URL}{config['filename']}")
    print("=" * 60)


if __name__ == "__main__":
    main()

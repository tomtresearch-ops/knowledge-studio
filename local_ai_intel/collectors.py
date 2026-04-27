"""
Local AI Intel — Source Collectors
Gather signal on the AI services marketplace for agencies serving local/SMB businesses.
Covers: AI agency models, pricing, tools, platforms (GoHighLevel, Stammer, Voiceflow),
voice agents, chatbots, lead gen, white-label AI, and agency growth strategies.
"""

import os
import re
import requests
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional


# ============================================================
# HACKER NEWS COLLECTOR (Local AI Intel)
# ============================================================

class HNCollector:
    """Collect local AI services signal from Hacker News."""

    BASE_URL = "https://hn.algolia.com/api/v1"

    QUERIES = [
        "AI agency small business",
        "AI agents SaaS",
        "AI automation agency",
        "selling AI services",
        "AI chatbot local business",
        "AI voice agent",
        "white label AI",
        "GoHighLevel",
        "AI for SMB",
        "AI receptionist",
        "AI appointment setting",
        "AI lead generation",
        "AI customer service small business",
        "vertical AI agents",
        "AI for local SEO",
        "n8n AI automation",
        "Make.com AI workflow",
        "AI consulting",
        "AI agency pricing",
        "Voiceflow chatbot",
    ]

    def __init__(self, hours_back: int = 24):
        self.hours_back = hours_back
        self.cutoff = int((datetime.utcnow() - timedelta(hours=hours_back)).timestamp())

    def search(self, query: str, min_points: int = 3, num_results: int = 15) -> list[dict]:
        try:
            params = {
                "query": query,
                "tags": "story",
                "numericFilters": f"created_at_i>{self.cutoff},points>{min_points}",
                "hitsPerPage": num_results,
            }
            resp = requests.get(f"{self.BASE_URL}/search", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for hit in data.get("hits", []):
                results.append({
                    "source": "hacker_news",
                    "title": hit.get("title", ""),
                    "url": hit.get("url", f"https://news.ycombinator.com/item?id={hit['objectID']}"),
                    "hn_url": f"https://news.ycombinator.com/item?id={hit['objectID']}",
                    "points": hit.get("points", 0),
                    "comments": hit.get("num_comments", 0),
                    "author": hit.get("author", ""),
                    "created_at": hit.get("created_at", ""),
                    "query_matched": query,
                })
            return results
        except Exception as e:
            print(f"  [HN] Error searching '{query}': {e}")
            return []

    def collect(self) -> list[dict]:
        print(f"[HN] Collecting local AI intel signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for query in self.QUERIES:
            results = self.search(query, min_points=3, num_results=10)
            for item in results:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    item["signal_score"] = item.get("points", 0) + (item.get("comments", 0) * 1.5)
                    all_results.append(item)

        all_results.sort(key=lambda x: x.get("signal_score", 0), reverse=True)
        print(f"  [HN] Found {len(all_results)} unique items")
        return all_results


# ============================================================
# RSS COLLECTOR (Local AI Intel)
# ============================================================

class RSSCollector:
    """Collect AI agency/local business signal from curated RSS feeds."""

    FEEDS = {
        "n8n Blog": "https://blog.n8n.io/rss/",
        "Nick Saraev": "https://nicksaraev.com/feed/",
        "DigitalMarketer": "https://www.digitalmarketer.com/feed/",
        "Greg Isenberg (Late Checkout)": "https://latecheckout.substack.com/feed",
        "Zapier Blog": "https://zapier.com/blog/feeds/latest/",
        "HubSpot AI": "https://blog.hubspot.com/marketing/rss.xml",
        "The Circuit (Metacircuits)": "https://metacircuits.substack.com/feed",
        "AI Maker": "https://aimaker.substack.com/feed",
        "Liam Ottley (Morningside AI)": "https://morningsideai.beehiiv.com/feed",
        "Ben's Bites": "https://bensbites.substack.com/feed",
    }

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 LocalAIIntel"}

    # Agency-specific feeds pass everything; general feeds get keyword-filtered
    AGENCY_SPECIFIC_FEEDS = {
        "Nick Saraev", "The Circuit (Metacircuits)", "AI Maker",
        "Liam Ottley (Morningside AI)", "Ben's Bites",
    }

    AGENCY_KEYWORDS = [
        "agency", "ai service", "chatbot", "voice agent", "automation",
        "local business", "smb", "small business", "white label", "white-label",
        "lead gen", "appointment", "receptionist", "customer service",
        "gohighlevel", "highlevel", "saas", "client", "pricing",
        "ai consulting", "ai tools", "workflow", "n8n", "make.com",
        "voiceflow", "botpress", "stammer", "ai employee",
    ]

    def __init__(self, days_back: int = 3):
        self.days_back = days_back
        self.cutoff = datetime.utcnow() - timedelta(days=days_back)

    def _get_text(self, element, tag):
        el = element.find(tag)
        if el is not None and el.text:
            return el.text.strip()
        for ns_prefix in ['', '{http://www.w3.org/2005/Atom}', '{http://purl.org/dc/elements/1.1/}']:
            el = element.find(f'{ns_prefix}{tag}')
            if el is not None and el.text:
                return el.text.strip()
        return ""

    def parse_rss(self, feed_name: str, feed_url: str) -> list[dict]:
        try:
            resp = requests.get(feed_url, headers=self.HEADERS, timeout=15)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)

            items = root.findall('.//item')
            if not items:
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                items = root.findall('.//atom:entry', ns)
                if not items:
                    items = root.findall('.//{http://www.w3.org/2005/Atom}entry')

            results = []
            is_agency_feed = feed_name in self.AGENCY_SPECIFIC_FEEDS

            for item in items[:25]:
                title = self._get_text(item, 'title')
                link = self._get_text(item, 'link')
                if not link:
                    link_el = item.find('link')
                    if link_el is not None:
                        link = link_el.get('href', '')
                    if not link:
                        link_el = item.find('{http://www.w3.org/2005/Atom}link')
                        if link_el is not None:
                            link = link_el.get('href', '')
                description = self._get_text(item, 'description') or self._get_text(item, 'summary') or self._get_text(item, 'content') or ""
                pub_date = self._get_text(item, 'pubDate') or self._get_text(item, 'published') or self._get_text(item, 'updated') or ""

                description = re.sub(r'<[^>]+>', '', description).strip()[:300]

                if not title or not link:
                    continue

                if is_agency_feed:
                    pass_filter = True
                else:
                    text = f"{title} {description}".lower()
                    pass_filter = any(kw in text for kw in self.AGENCY_KEYWORDS)

                if pass_filter:
                    results.append({
                        "source": "rss",
                        "feed": feed_name,
                        "title": title,
                        "url": link,
                        "description": description,
                        "pub_date": pub_date,
                    })

            return results
        except Exception as e:
            print(f"  [RSS] Error parsing {feed_name}: {e}")
            return []

    def collect(self) -> list[dict]:
        print(f"[RSS] Collecting from agency/local AI feeds (last {self.days_back} days)...")
        all_results = []
        seen_urls = set()

        for feed_name, feed_url in self.FEEDS.items():
            items = self.parse_rss(feed_name, feed_url)
            for item in items:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    all_results.append(item)

        print(f"  [RSS] Found {len(all_results)} unique articles across {len(self.FEEDS)} feeds")
        return all_results


# ============================================================
# REDDIT COLLECTOR (Local AI Intel)
# ============================================================

class RedditCollector:
    """Collect AI agency/local business signal from Reddit."""

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 LocalAIIntel"}

    SUBREDDITS = [
        # Agency-specific (take everything)
        "GoHighLevel",
        "AIautomation",
        "agency",
        # Broader business (filter for keywords)
        "smallbusiness",
        "Entrepreneur",
        "EntrepreneurRideAlong",
        "SaaS",
        "digital_marketing",
        "SEO",
        "n8n",
        "ChatGPT",
    ]

    UNFILTERED_SUBS = {"gohighlevel", "aiautomation", "agency"}

    def __init__(self, hours_back: int = 24):
        self.hours_back = hours_back

    def get_subreddit_top(self, subreddit: str, limit: int = 15) -> list[dict]:
        try:
            url = f"https://www.reddit.com/r/{subreddit}/top.rss?t=day&limit={limit}"
            resp = requests.get(url, headers=self.HEADERS, timeout=10)
            resp.raise_for_status()

            entries = re.findall(r'<entry>(.*?)</entry>', resp.text, re.DOTALL)
            results = []
            for entry in entries[:limit]:
                title_match = re.search(r'<title[^>]*>(.*?)</title>', entry)
                link_match = re.search(r'<link[^>]*href="([^"]*)"', entry)
                author_match = re.search(r'<name>(.*?)</name>', entry)

                if title_match and link_match:
                    title = title_match.group(1).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                    title_lower = title.lower()
                    keywords = [
                        "agency", "ai service", "chatbot", "voice agent", "automation",
                        "local business", "smb", "small business", "white label",
                        "lead gen", "appointment", "client", "pricing", "ai tool",
                        "gohighlevel", "highlevel", "saas", "consulting",
                        "n8n", "make.com", "zapier", "ai employee",
                        "voiceflow", "botpress", "stammer",
                    ]
                    is_unfiltered = subreddit.lower() in self.UNFILTERED_SUBS
                    if is_unfiltered or any(kw in title_lower for kw in keywords):
                        results.append({
                            "source": "reddit",
                            "subreddit": subreddit,
                            "title": title,
                            "url": link_match.group(1),
                            "reddit_url": link_match.group(1),
                            "author": author_match.group(1).replace('/u/', '') if author_match else "",
                            "score": 0,
                            "comments": 0,
                        })
            return results
        except Exception as e:
            print(f"  [Reddit] RSS error for r/{subreddit}: {e}")
            return []

    def collect(self) -> list[dict]:
        print(f"[Reddit] Collecting local AI intel signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for sub in self.SUBREDDITS:
            posts = self.get_subreddit_top(sub)
            for post in posts:
                if post["url"] not in seen_urls:
                    seen_urls.add(post["url"])
                    all_results.append(post)

        print(f"  [Reddit] Found {len(all_results)} unique items")
        return all_results


# ============================================================
# YOUTUBE SEARCH COLLECTOR (Local AI Intel)
# ============================================================

class YouTubeSearchCollector:
    """Search YouTube for trending AI agency/local business content."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    QUERIES = [
        "AI agency 2026",
        "AI automation agency clients",
        "GoHighLevel AI",
        "AI voice agent local business",
        "AI chatbot for small business",
        "start AI agency",
        "white label AI SaaS",
        "AI lead generation agency",
        "AI appointment setter",
        "sell AI services local business",
        "AI consulting small business",
        "n8n AI automation agency",
    ]

    def __init__(self, api_key: Optional[str] = None, hours_back: int = 48):
        self.api_key = api_key
        self.hours_back = hours_back
        self.published_after = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def search(self, query: str, max_results: int = 8) -> list[dict]:
        if not self.api_key:
            return []
        try:
            params = {
                "part": "snippet",
                "q": query,
                "type": "video",
                "order": "relevance",
                "publishedAfter": self.published_after,
                "maxResults": max_results,
                "key": self.api_key,
            }
            resp = requests.get(f"{self.BASE_URL}/search", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                video_id = item.get("id", {}).get("videoId", "")
                results.append({
                    "source": "youtube_search",
                    "title": snippet.get("title", ""),
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "channel": snippet.get("channelTitle", ""),
                    "description": snippet.get("description", "")[:300],
                    "published_at": snippet.get("publishedAt", ""),
                    "video_id": video_id,
                    "query_matched": query,
                })
            return results
        except Exception as e:
            print(f"  [YouTube] Error searching '{query}': {e}")
            return []

    def collect(self) -> list[dict]:
        if not self.api_key:
            print("[YouTube] No API key — skipping YouTube search")
            return []

        print(f"[YouTube] Collecting local AI intel signal (last {self.hours_back}h)...")
        all_results = []
        seen_ids = set()

        for query in self.QUERIES:
            results = self.search(query, max_results=5)
            for item in results:
                if item["video_id"] not in seen_ids:
                    seen_ids.add(item["video_id"])
                    all_results.append(item)

        print(f"  [YouTube] Found {len(all_results)} unique videos")
        return all_results


# ============================================================
# YOUTUBE CHANNEL MONITOR (Local AI Intel)
# ============================================================

class YouTubeChannelCollector:
    """Monitor curated YouTube channels for recent agency/local AI uploads."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"
    CHANNELS_JSON = os.path.join(os.path.dirname(__file__), "youtube_channels.json")

    def __init__(self, api_key: Optional[str] = None, hours_back: int = 48,
                 max_videos_per_channel: int = 5):
        self.api_key = api_key
        self.hours_back = hours_back
        self.max_videos_per_channel = max_videos_per_channel
        self.cutoff = datetime.utcnow() - timedelta(hours=hours_back)
        self.cutoff_iso = self.cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _load_channels(self) -> list[dict]:
        try:
            if os.path.exists(self.CHANNELS_JSON):
                with open(self.CHANNELS_JSON, "r") as f:
                    channels = json.load(f)
                print(f"  [YT Channels] Loaded {len(channels)} channels from JSON")
                return channels
        except Exception as e:
            print(f"  [YT Channels] Error loading JSON: {e}")
        return []

    @staticmethod
    def _derive_uploads_playlist(channel_id: str) -> str:
        if channel_id.startswith("UC"):
            return "UU" + channel_id[2:]
        return ""

    def _fetch_recent_videos(self, channel: dict) -> list[dict]:
        channel_id = channel.get("channel_id", "")
        channel_name = channel.get("channel_name", "")
        playlist_id = self._derive_uploads_playlist(channel_id)

        if not playlist_id:
            return []

        try:
            params = {
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": self.max_videos_per_channel,
                "key": self.api_key,
            }
            resp = requests.get(f"{self.BASE_URL}/playlistItems", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                published = snippet.get("publishedAt", "")

                if published:
                    try:
                        pub_dt = datetime.strptime(published[:19], "%Y-%m-%dT%H:%M:%S")
                        if pub_dt < self.cutoff:
                            continue
                    except ValueError:
                        pass

                video_id = snippet.get("resourceId", {}).get("videoId", "")
                if video_id:
                    results.append({
                        "source": "youtube_channel",
                        "title": snippet.get("title", ""),
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "channel": channel_name,
                        "channel_id": channel_id,
                        "category": channel.get("category", ""),
                        "description": snippet.get("description", "")[:300],
                        "published_at": published,
                        "video_id": video_id,
                    })
            return results
        except Exception as e:
            print(f"  [YT Channels] Error fetching {channel_name}: {e}")
            return []

    def collect(self) -> list[dict]:
        if not self.api_key:
            print("[YT Channels] No API key — skipping channel monitor")
            return []

        channels = self._load_channels()
        if not channels:
            return []

        print(f"[YT Channels] Scanning {len(channels)} channels (last {self.hours_back}h)...")
        all_results = []
        seen_ids = set()

        for channel in channels:
            videos = self._fetch_recent_videos(channel)
            for video in videos:
                if video["video_id"] not in seen_ids:
                    seen_ids.add(video["video_id"])
                    all_results.append(video)

        print(f"  [YT Channels] Found {len(all_results)} recent videos")
        return all_results


# ============================================================
# KNOWLEDGE STUDIO COLLECTOR (Local AI Intel)
# ============================================================

class KnowledgeStudioCollector:
    """Pull recent agency/local AI content from Knowledge Studio database."""

    KEYWORDS = [
        "agency", "ai service", "chatbot", "voice agent", "automation",
        "local business", "smb", "small business", "white label",
        "lead gen", "appointment", "receptionist", "customer service",
        "gohighlevel", "highlevel", "saas", "consulting", "client",
        "voiceflow", "botpress", "stammer", "ai employee",
        "n8n", "make.com", "zapier", "workflow",
    ]

    def __init__(self, db_path: str, hours_back: int = 48):
        self.db_path = db_path
        self.hours_back = hours_back

    def collect(self) -> list[dict]:
        import sqlite3

        print(f"[KS] Collecting local AI intel content (last {self.hours_back}h)...")
        cutoff = (datetime.utcnow() - timedelta(hours=self.hours_back)).strftime("%Y-%m-%d %H:%M:%S")

        results = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, title, channel, ai_summary, summary_15, tags, video_url, processing_date
                FROM videos
                WHERE processing_date > ? AND status = 'completed'
                ORDER BY processing_date DESC
                LIMIT 200
            """, (cutoff,))

            for row in cursor.fetchall():
                title_lower = (row["title"] or "").lower()
                tags_lower = (row["tags"] or "").lower()
                text = f"{title_lower} {tags_lower}"
                if any(kw in text for kw in self.KEYWORDS):
                    results.append({
                        "source": "knowledge_studio",
                        "content_type": "video",
                        "title": row["title"] or "",
                        "channel": row["channel"] or "",
                        "summary_short": row["summary_15"] or "",
                        "url": row["video_url"] or "",
                        "processed_at": row["processing_date"] or "",
                    })

            cursor.execute("""
                SELECT id, title, url, summary, summary_15, tags, created_at
                FROM articles
                WHERE created_at > ?
                ORDER BY created_at DESC
                LIMIT 100
            """, (cutoff,))

            for row in cursor.fetchall():
                title_lower = (row["title"] or "").lower()
                tags_lower = (row["tags"] or "").lower()
                text = f"{title_lower} {tags_lower}"
                if any(kw in text for kw in self.KEYWORDS):
                    results.append({
                        "source": "knowledge_studio",
                        "content_type": "article",
                        "title": row["title"] or "",
                        "channel": "",
                        "summary_short": row["summary_15"] or "",
                        "url": row["url"] or "",
                        "processed_at": row["created_at"] or "",
                    })

            conn.close()
        except Exception as e:
            print(f"  [KS] Error: {e}")

        print(f"  [KS] Found {len(results)} local AI intel items")
        return results


# ============================================================
# MASTER COLLECTOR — Run all sources
# ============================================================

def collect_all(vertical: str = "local_ai_intel",
                hours_back: int = 24,
                db_path: str = None,
                youtube_api_key: str = None) -> dict:
    """Run all collectors for the Local AI Intel vertical."""
    print(f"\n{'='*60}")
    print(f"  LOCAL AI INTEL — Collecting")
    print(f"  Window: last {hours_back} hours")
    print(f"  Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    results = {
        "vertical": vertical,
        "collected_at": datetime.utcnow().isoformat(),
        "hours_back": hours_back,
        "sources": {},
    }

    # Tier 1: Curated RSS feeds
    rss = RSSCollector(days_back=3)
    results["sources"]["rss"] = rss.collect()

    # Tier 2: Community signal
    hn = HNCollector(hours_back=hours_back)
    results["sources"]["hacker_news"] = hn.collect()

    reddit = RedditCollector(hours_back=hours_back)
    results["sources"]["reddit"] = reddit.collect()

    # Tier 3: YouTube (search + curated channels)
    if youtube_api_key:
        yt_search = YouTubeSearchCollector(api_key=youtube_api_key, hours_back=48)
        results["sources"]["youtube_search"] = yt_search.collect()

        yt_channels = YouTubeChannelCollector(api_key=youtube_api_key, hours_back=48)
        results["sources"]["youtube_channels"] = yt_channels.collect()

    # Tier 4: Knowledge Studio
    if db_path:
        ks = KnowledgeStudioCollector(db_path=db_path, hours_back=48)
        results["sources"]["knowledge_studio"] = ks.collect()

    # Summary
    total = sum(len(v) for v in results["sources"].values())
    print(f"\n{'='*60}")
    print(f"  COLLECTION COMPLETE — {total} total items")
    for source, items in results["sources"].items():
        print(f"    {source}: {len(items)}")
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    DB_PATH = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/youtube_intelligence.db"
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    YT_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

    data = collect_all(
        vertical="local_ai_intel",
        hours_back=24,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
    )

    for source, items in data["sources"].items():
        print(f"\n--- TOP {source.upper()} ---")
        for item in items[:5]:
            score = item.get("signal_score", item.get("stars_today", "N/A"))
            print(f"  [{score}] {item.get('title', item.get('repo', ''))[:80]}")
            print(f"        {item['url'][:80]}")

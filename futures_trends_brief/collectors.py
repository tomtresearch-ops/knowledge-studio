"""
Futures & Trends Brief — Source Collectors
Gather signal from internal briefs, research/reports, futurist voices,
think tanks, community signals, and broad science breakthroughs.
Twice-weekly cadence (Tue/Fri). Meta/macro level — cross-domain synthesis.
"""

import requests
import json
import re
import time
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional


# ============================================================
# INTERNAL BRIEFS COLLECTOR (unique to Futures & Trends)
# Reads recent AI & Tech and Health & Longevity briefs
# ============================================================

class InternalBriefsCollector:
    """Ingest recent daily briefs from other verticals as source material."""

    TARGET_VERTICALS = ["ai_tech", "health_longevity"]

    def __init__(self, db_path: str, days_back: int = 4):
        self.db_path = db_path
        self.days_back = days_back

    def collect(self) -> list[dict]:
        """Get recent briefs from the database."""
        print(f"[Internal] Collecting recent briefs (last {self.days_back} days)...")
        cutoff = (datetime.utcnow() - timedelta(days=self.days_back)).strftime("%Y-%m-%d %H:%M:%S")

        results = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT id, vertical, title, content, signal_count, source_count, created_at
                FROM daily_briefs
                WHERE created_at > ? AND vertical IN ({})
                ORDER BY created_at DESC
            """.format(",".join("?" * len(self.TARGET_VERTICALS))),
                (cutoff, *self.TARGET_VERTICALS))

            for row in cursor.fetchall():
                results.append({
                    "source": "internal_brief",
                    "vertical": row["vertical"],
                    "title": row["title"] or "",
                    "content": row["content"] or "",
                    "signal_count": row["signal_count"] or 0,
                    "created_at": row["created_at"] or "",
                })

            conn.close()
        except Exception as e:
            print(f"  [Internal] Error: {e}")

        print(f"  [Internal] Found {len(results)} recent briefs")
        return results


# ============================================================
# RSS AGGREGATOR COLLECTOR
# Publications, think tanks, investment firms, futurist sites
# ============================================================

class RSSAggregatorCollector:
    """Collect futures/trends signal from publications, think tanks, and research orgs."""

    FEEDS = {
        # Futurist publications
        "Singularity Hub": "https://singularityhub.com/feed/",
        "Next Big Future": "https://www.nextbigfuture.com/feed",
        "MIT Technology Review": "https://www.technologyreview.com/feed/",
        "Wired": "https://www.wired.com/feed/rss",
        "Quanta Magazine": "https://api.quantamagazine.org/feed/",
        "Aeon — Future": "https://aeon.co/feed.rss",
        "Noema Magazine": "https://www.noemamag.com/feed/",
        # Investment / strategy firms (a16z collected via YouTube instead)
        "Sequoia Capital": "https://sequoiacap.com/feed/",
        # Think tanks
        "Brookings — Research": "https://www.brookings.edu/feed/",
    }

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 FuturesBrief"}

    def __init__(self, days_back: int = 4):
        self.days_back = days_back

    def parse_rss(self, feed_name: str, feed_url: str) -> list[dict]:
        """Parse an RSS feed and return items."""
        try:
            resp = requests.get(feed_url, headers=self.HEADERS, timeout=15)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)

            # Handle both RSS 2.0 and Atom formats
            items = root.findall('.//item')
            if not items:
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                items = root.findall('.//atom:entry', ns)

            results = []
            for item in items[:15]:  # Max 15 per feed
                title = self._get_text(item, 'title')
                link = self._get_text(item, 'link')
                if not link:
                    link_el = item.find('link')
                    if link_el is not None:
                        link = link_el.get('href', '')
                description = self._get_text(item, 'description') or self._get_text(item, 'summary') or ""
                pub_date = self._get_text(item, 'pubDate') or self._get_text(item, 'published') or ""

                # Clean HTML from description
                description = re.sub(r'<[^>]+>', '', description).strip()[:300]

                if title and link:
                    results.append({
                        "source": "rss_aggregator",
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

    def _get_text(self, element, tag):
        """Safely get text from an XML element."""
        el = element.find(tag)
        if el is not None and el.text:
            return el.text.strip()
        for ns_prefix in ['', '{http://www.w3.org/2005/Atom}', '{http://purl.org/dc/elements/1.1/}']:
            el = element.find(f'{ns_prefix}{tag}')
            if el is not None and el.text:
                return el.text.strip()
        return ""

    def collect(self) -> list[dict]:
        """Collect from all RSS feeds."""
        print(f"[RSS] Collecting from publications & think tanks (last {self.days_back} days)...")
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
# ARXIV COLLECTOR (Broad science/tech breakthroughs)
# Filtered to macro-relevant categories
# ============================================================

class ArXivCollector:
    """Collect recent papers from arXiv with macro/futures implications."""

    BASE_URL = "http://export.arxiv.org/api/query"

    # Categories relevant to macro futures
    SEARCH_QUERIES = [
        "cat:cs.AI AND (future OR societal OR economic OR labor)",
        "cat:cs.CY",  # Computers and Society
        "cat:econ.GN",  # General Economics
        "cat:physics.soc-ph",  # Physics and Society
    ]

    def __init__(self, days_back: int = 7):
        self.days_back = days_back

    def search(self, query: str, max_results: int = 15) -> list[dict]:
        """Search arXiv for recent papers."""
        try:
            params = {
                "search_query": query,
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            resp = requests.get(self.BASE_URL, params=params, timeout=15)
            resp.raise_for_status()

            # Parse Atom XML
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
            root = ET.fromstring(resp.content)
            entries = root.findall('atom:entry', ns)

            results = []
            for entry in entries:
                title = entry.find('atom:title', ns)
                summary = entry.find('atom:summary', ns)
                published = entry.find('atom:published', ns)
                link = entry.find('atom:id', ns)
                authors = entry.findall('atom:author/atom:name', ns)
                categories = entry.findall('arxiv:primary_category', ns) or entry.findall('atom:category', ns)

                author_str = authors[0].text if authors else ""
                if len(authors) > 1:
                    author_str += f" et al. ({len(authors)} authors)"

                category = ""
                if categories:
                    category = categories[0].get('term', '') if categories[0].get('term') else ""

                results.append({
                    "source": "arxiv",
                    "title": (title.text or "").strip().replace('\n', ' ') if title is not None else "",
                    "authors": author_str,
                    "abstract": (summary.text or "").strip()[:300] if summary is not None else "",
                    "category": category,
                    "url": link.text.strip() if link is not None else "",
                    "pub_date": published.text.strip() if published is not None else "",
                })

            return results
        except Exception as e:
            print(f"  [arXiv] Error searching '{query[:40]}': {e}")
            return []

    def collect(self) -> list[dict]:
        """Run all arXiv queries and deduplicate."""
        print(f"[arXiv] Collecting macro-relevant papers (last {self.days_back} days)...")
        all_results = []
        seen_urls = set()

        for i, query in enumerate(self.SEARCH_QUERIES):
            if i > 0:
                time.sleep(1)  # Respect arXiv rate limits
            results = self.search(query, max_results=10)
            for item in results:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    all_results.append(item)

        print(f"  [arXiv] Found {len(all_results)} unique papers")
        return all_results


# ============================================================
# HACKER NEWS COLLECTOR (Macro/Futures)
# ============================================================

class HNCollector:
    """Collect macro/futures signal from Hacker News."""

    BASE_URL = "https://hn.algolia.com/api/v1"

    FUTURES_QUERIES = [
        "future of work",
        "geopolitics technology",
        "disruption industry",
        "demographics population",
        "energy transition",
        "artificial general intelligence",
        "economic paradigm shift",
        "deglobalization",
        "automation labor",
        "singularity superintelligence",
        "fourth industrial revolution",
        "scenario planning futures",
        "longevity workforce retirement",
        "climate adaptation technology",
    ]

    def __init__(self, hours_back: int = 96):
        self.hours_back = hours_back
        self.cutoff = int((datetime.utcnow() - timedelta(hours=hours_back)).timestamp())

    def search(self, query: str, min_points: int = 5, num_results: int = 10) -> list[dict]:
        """Search HN for a query."""
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
        """Run all futures queries and deduplicate."""
        print(f"[HN] Collecting macro/futures signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for query in self.FUTURES_QUERIES:
            results = self.search(query, min_points=5, num_results=8)
            for item in results:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    item["signal_score"] = item.get("points", 0) + (item.get("comments", 0) * 1.5)
                    all_results.append(item)

        all_results.sort(key=lambda x: x.get("signal_score", 0), reverse=True)
        print(f"  [HN] Found {len(all_results)} unique items")
        return all_results


# ============================================================
# REDDIT COLLECTOR (Futures/Macro)
# ============================================================

class RedditCollector:
    """Collect macro/futures signal from Reddit."""

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 FuturesBrief"}

    FUTURES_SUBREDDITS = [
        "Futurology",
        "collapse",
        "Economics",
        "geopolitics",
    ]

    def __init__(self, hours_back: int = 96):
        self.hours_back = hours_back

    def get_subreddit_top(self, subreddit: str, limit: int = 100) -> list[dict]:
        """Get top posts via RSS feed."""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/top.rss?t=week&limit={limit}"
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
                    results.append({
                        "source": "reddit",
                        "subreddit": subreddit,
                        "title": title,
                        "url": link_match.group(1),
                        "reddit_url": link_match.group(1),
                        "author": author_match.group(1).replace('/u/', '') if author_match else "",
                    })
            return results
        except Exception as e:
            print(f"  [Reddit] RSS error for r/{subreddit}: {e}")
            return []

    def collect(self) -> list[dict]:
        """Collect top posts across futures subreddits."""
        print(f"[Reddit] Collecting macro/futures signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for sub in self.FUTURES_SUBREDDITS:
            posts = self.get_subreddit_top(sub)
            for post in posts:
                if post["url"] not in seen_urls:
                    seen_urls.add(post["url"])
                    all_results.append(post)

        print(f"  [Reddit] Found {len(all_results)} unique items")
        return all_results


# ============================================================
# YOUTUBE SEARCH COLLECTOR (Futurist Voices)
# ============================================================

class YouTubeSearchCollector:
    """Search YouTube for trending futures/macro content from key voices."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    # Organized by theme to maximize signal per query
    FUTURES_QUERIES = [
        # Key futurist voices
        "Peter Diamandis future predictions",
        "Tony Seba disruption forecast",
        "Jeremy Rifkin third industrial revolution",
        "Peter Zeihan geopolitics demographics",
        "Ian Bremmer geopolitical risk",
        "Azeem Azhar exponential view",
        "Amy Webb future today institute",
        "Ray Kurzweil singularity",
        "Moonshots Peter Diamandis",
        "Raoul Pal macro future",
        # Macro thinkers
        "Balaji Srinivasan network state future",
        "Ian Pearson futurist predictions",
        "Gerd Leonhard technology humanity",
        "Richard Watson future trends",
        "Mo Gawdat AI future",
        # YouTube analysts with futures lens
        "Matthew Berman AI future predictions",
        "Wes Roth AI future analysis",
        "Nate B Jones future analysis",
        # Institutional voices — big players
        "Marc Andreessen a16z interview",
        "a16z podcast future technology",
        "McKinsey Global Institute future",
        "Gartner technology trends",
        "World Economic Forum Davos future",
        # Thematic queries
        "future of work AI automation 2026",
        "geopolitics technology disruption analysis",
        "futurism trends predictions weekly",
        "energy transition disruption forecast",
    ]

    def __init__(self, api_key: Optional[str] = None, hours_back: int = 168):
        self.api_key = api_key
        self.hours_back = hours_back  # 7 days for twice-weekly brief
        self.published_after = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def search(self, query: str, max_results: int = 5) -> list[dict]:
        """Search YouTube for recent videos."""
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
        """Run all futures search queries, deduplicate."""
        if not self.api_key:
            print("[YouTube] No API key — skipping YouTube search")
            return []

        print(f"[YouTube] Collecting futurist voices (last {self.hours_back}h)...")
        all_results = []
        seen_ids = set()

        for query in self.FUTURES_QUERIES:
            results = self.search(query, max_results=4)
            for item in results:
                if item["video_id"] not in seen_ids:
                    seen_ids.add(item["video_id"])
                    all_results.append(item)

        print(f"  [YouTube] Found {len(all_results)} unique videos")
        return all_results


# ============================================================
# KNOWLEDGE STUDIO COLLECTOR (Futures/Macro)
# ============================================================

class KnowledgeStudioCollector:
    """Pull recent futures/macro content from Knowledge Studio database."""

    FUTURES_KEYWORDS = [
        "future", "futurism", "futurist", "prediction", "forecast",
        "disruption", "paradigm", "macro", "geopolitics", "demographics",
        "singularity", "exponential", "automation", "labor", "workforce",
        "civilization", "deglobalization", "energy transition", "climate",
        "diamandis", "zeihan", "kurzweil", "rifkin", "seba", "bremmer",
        "attia", "harari", "altman", "moonshots",
    ]

    def __init__(self, db_path: str, hours_back: int = 168):
        self.db_path = db_path
        self.hours_back = hours_back  # 7 days

    def collect(self) -> list[dict]:
        """Get recently processed futures-relevant content from KS."""
        print(f"[KS] Collecting futures/macro content (last {self.hours_back}h)...")
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
                if any(kw in text for kw in self.FUTURES_KEYWORDS):
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
                if any(kw in text for kw in self.FUTURES_KEYWORDS):
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

        print(f"  [KS] Found {len(results)} futures-relevant items")
        return results


# ============================================================
# MASTER COLLECTOR — Run all sources
# ============================================================

def collect_all(vertical: str = "futures_trends",
                hours_back: int = 96,
                db_path: str = None,
                youtube_api_key: str = None) -> dict:
    """
    Run all collectors for the Futures & Trends vertical.
    Wider time windows than daily briefs (twice-weekly cadence).
    """
    print(f"\n{'='*60}")
    print(f"  FUTURES & TRENDS BRIEF — Collecting")
    print(f"  Window: last {hours_back} hours (research: 7 days)")
    print(f"  Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    results = {
        "vertical": vertical,
        "collected_at": datetime.utcnow().isoformat(),
        "hours_back": hours_back,
        "sources": {},
    }

    # Tier 0: Internal briefs (unique to this vertical)
    if db_path:
        internal = InternalBriefsCollector(db_path=db_path, days_back=4)
        results["sources"]["internal_briefs"] = internal.collect()

    # Tier 1: Publications & think tank RSS (4-day window)
    rss = RSSAggregatorCollector(days_back=4)
    results["sources"]["rss_aggregators"] = rss.collect()

    # Tier 1: arXiv (7-day window)
    arxiv = ArXivCollector(days_back=7)
    results["sources"]["arxiv"] = arxiv.collect()

    # Tier 2: Community signals (wider window for twice-weekly)
    reddit = RedditCollector(hours_back=96)
    results["sources"]["reddit"] = reddit.collect()

    # Tier 2: YouTube futurist voices (7-day window)
    if youtube_api_key:
        yt = YouTubeSearchCollector(api_key=youtube_api_key, hours_back=168)
        results["sources"]["youtube_search"] = yt.collect()

    # Tier 3: Knowledge Studio (7-day window)
    if db_path:
        ks = KnowledgeStudioCollector(db_path=db_path, hours_back=168)
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
    YT_API_KEY = "AIzaSyA5VGDmqxRfYzgab5kqcRwxtLckH35BHNQ"

    data = collect_all(
        vertical="futures_trends",
        hours_back=96,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
    )

    for source, items in data["sources"].items():
        print(f"\n--- TOP {source.upper()} ---")
        for item in items[:3]:
            print(f"  {item.get('title', '')[:80]}")
            print(f"  {item.get('url', '')[:80]}")

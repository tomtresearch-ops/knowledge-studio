"""
Life-Stage Verticals — Shared Collectors
Common collection functions used by all 9 life-stage verticals.
Each stage-specific collectors.py imports from here and adds its own sources.
"""

import requests
import json
import re
import time
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional


# ============================================================
# PUBMED COLLECTOR (Parameterized)
# Uses NCBI E-utilities API (free, no auth for moderate use)
# ============================================================

class PubMedCollector:
    """Collect recent research from PubMed with stage-specific queries."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, queries: list[str], days_back: int = 7):
        self.queries = queries
        self.days_back = days_back
        self.min_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y/%m/%d")
        self.max_date = datetime.utcnow().strftime("%Y/%m/%d")

    def search(self, query: str, max_results: int = 15) -> list[str]:
        """Search PubMed, return list of PMIDs."""
        try:
            params = {
                "db": "pubmed",
                "term": query,
                "retmax": max_results,
                "sort": "date",
                "retmode": "json",
                "datetype": "edat",
                "mindate": self.min_date,
                "maxdate": self.max_date,
            }
            resp = requests.get(f"{self.BASE_URL}/esearch.fcgi", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            return data.get("esearchresult", {}).get("idlist", [])
        except Exception as e:
            print(f"  [PubMed] Search error for '{query[:40]}': {e}")
            return []

    def fetch_summaries(self, pmids: list[str]) -> list[dict]:
        """Fetch article summaries for a list of PMIDs."""
        if not pmids:
            return []
        try:
            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
            }
            resp = requests.get(f"{self.BASE_URL}/esummary.fcgi", params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for pmid in pmids:
                article = data.get("result", {}).get(pmid, {})
                if not article or "error" in article:
                    continue
                authors = article.get("authors", [])
                author_str = authors[0].get("name", "") if authors else ""
                if len(authors) > 1:
                    author_str += " et al."

                results.append({
                    "source": "pubmed",
                    "pmid": pmid,
                    "title": article.get("title", ""),
                    "authors": author_str,
                    "journal": article.get("fulljournalname", article.get("source", "")),
                    "pub_date": article.get("pubdate", ""),
                    "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    "doi": article.get("elocationid", ""),
                })
            return results
        except Exception as e:
            print(f"  [PubMed] Fetch error: {e}")
            return []

    def collect(self) -> list[dict]:
        """Run all queries, deduplicate, return results."""
        print(f"[PubMed] Collecting research (last {self.days_back} days, {len(self.queries)} queries)...")
        all_pmids = []
        seen = set()

        for i, query in enumerate(self.queries):
            if i > 0:
                time.sleep(0.4)  # Respect NCBI rate limit
            pmids = self.search(query, max_results=10)
            for pmid in pmids:
                if pmid not in seen:
                    seen.add(pmid)
                    all_pmids.append(pmid)

        # Fetch summaries in batches of 50
        results = []
        for i in range(0, len(all_pmids), 50):
            batch = all_pmids[i:i+50]
            results.extend(self.fetch_summaries(batch))

        print(f"  [PubMed] Found {len(results)} unique papers")
        return results


# ============================================================
# RSS COLLECTOR (Parameterized)
# ============================================================

class RSSCollector:
    """Collect signal from RSS feeds. Feeds are stage-specific."""

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 LifeStageBrief"}

    def __init__(self, feeds: dict[str, str], days_back: int = 3):
        self.feeds = feeds
        self.days_back = days_back

    def parse_rss(self, feed_name: str, feed_url: str) -> list[dict]:
        """Parse an RSS feed and return items."""
        try:
            resp = requests.get(feed_url, headers=self.HEADERS, timeout=15)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)

            items = root.findall('.//item')
            if not items:
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                items = root.findall('.//atom:entry', ns)

            results = []
            for item in items[:20]:
                title = self._get_text(item, 'title')
                link = self._get_text(item, 'link')
                if not link:
                    link_el = item.find('link')
                    if link_el is not None:
                        link = link_el.get('href', '')
                description = self._get_text(item, 'description') or self._get_text(item, 'summary') or ""
                pub_date = self._get_text(item, 'pubDate') or self._get_text(item, 'published') or ""

                description = re.sub(r'<[^>]+>', '', description).strip()[:300]

                if title and link:
                    results.append({
                        "source": "rss_feed",
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
        print(f"[RSS] Collecting from {len(self.feeds)} feeds (last {self.days_back} days)...")
        all_results = []
        seen_urls = set()

        for feed_name, feed_url in self.feeds.items():
            items = self.parse_rss(feed_name, feed_url)
            for item in items:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    all_results.append(item)

        print(f"  [RSS] Found {len(all_results)} unique articles")
        return all_results


# ============================================================
# HACKER NEWS COLLECTOR (Parameterized)
# ============================================================

class HNCollector:
    """Collect signal from Hacker News with stage-specific queries."""

    BASE_URL = "https://hn.algolia.com/api/v1"

    def __init__(self, queries: list[str], hours_back: int = 48):
        self.queries = queries
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
        print(f"[HN] Collecting signal (last {self.hours_back}h, {len(self.queries)} queries)...")
        all_results = []
        seen_urls = set()

        for query in self.queries:
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
# REDDIT COLLECTOR (Parameterized)
# ============================================================

class RedditCollector:
    """Collect signal from Reddit with stage-specific subreddits."""

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 LifeStageBrief"}

    def __init__(self, subreddits: list[str], hours_back: int = 24):
        self.subreddits = subreddits
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
        print(f"[Reddit] Collecting from {len(self.subreddits)} subreddits (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for sub in self.subreddits:
            posts = self.get_subreddit_top(sub)
            for post in posts:
                if post["url"] not in seen_urls:
                    seen_urls.add(post["url"])
                    all_results.append(post)

        print(f"  [Reddit] Found {len(all_results)} unique items")
        return all_results


# ============================================================
# YOUTUBE HEADLINE SCANNER (Parameterized)
# Scans curated YouTube channels for recent uploads as signal
# ============================================================

class QuotaExceededError(Exception):
    """Raised when YouTube API quota is exceeded."""
    pass


class YouTubeHeadlineCollector:
    """Scan curated YouTube channels for recent upload headlines."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, channels_json_path: str, api_key: str = None,
                 hours_back: int = 72, max_videos_per_channel: int = 5):
        self.channels_json_path = channels_json_path
        self.api_key = api_key
        self.hours_back = hours_back
        self.max_videos_per_channel = max_videos_per_channel
        self.cutoff = datetime.utcnow() - timedelta(hours=hours_back)

    def _load_channels(self) -> list:
        try:
            if os.path.exists(self.channels_json_path):
                with open(self.channels_json_path, "r") as f:
                    channels = json.load(f)
                print(f"  [YT Headlines] Loaded {len(channels)} channels")
                return channels
        except Exception as e:
            print(f"  [YT Headlines] Error loading channel list: {e}")
        return []

    @staticmethod
    def _derive_uploads_playlist(channel_id: str) -> str:
        if channel_id.startswith("UC"):
            return "UU" + channel_id[2:]
        return ""

    def _fetch_playlist_items(self, playlist_id: str, max_results: int = 5) -> list:
        try:
            params = {
                "part": "snippet",
                "playlistId": playlist_id,
                "maxResults": min(max_results, 50),
                "key": self.api_key,
            }
            resp = requests.get(f"{self.BASE_URL}/playlistItems", params=params, timeout=10)
            resp.raise_for_status()
            return resp.json().get("items", [])
        except requests.exceptions.HTTPError as e:
            if e.response is not None:
                if e.response.status_code == 404:
                    return []
                elif e.response.status_code == 403:
                    error_body = e.response.json() if e.response.text else {}
                    for err in error_body.get("error", {}).get("errors", []):
                        if err.get("reason") == "quotaExceeded":
                            print("  [YT Headlines] API quota exceeded — stopping")
                            raise QuotaExceededError()
                    return []
            return []
        except QuotaExceededError:
            raise
        except Exception:
            return []

    def collect(self) -> list:
        if not self.api_key:
            print("[YT Headlines] No API key — skipping YouTube headlines")
            return []

        print(f"[YT Headlines] Scanning channels (last {self.hours_back}h)...")
        channels = self._load_channels()
        if not channels:
            return []

        all_results = []
        seen_ids = set()
        scanned = 0

        for ch in channels:
            channel_id = ch.get("channel_id", "")
            channel_name = ch.get("channel_name", "")
            category = ch.get("category", "")

            playlist_id = self._derive_uploads_playlist(channel_id)
            if not playlist_id:
                continue

            try:
                items = self._fetch_playlist_items(playlist_id, self.max_videos_per_channel)
            except QuotaExceededError:
                break

            scanned += 1
            for item in items:
                snippet = item.get("snippet", {})
                published_str = snippet.get("publishedAt", "")
                if published_str:
                    try:
                        published_dt = datetime.strptime(published_str, "%Y-%m-%dT%H:%M:%SZ")
                        if published_dt < self.cutoff:
                            continue
                    except ValueError:
                        pass

                video_id = snippet.get("resourceId", {}).get("videoId", "")
                title = snippet.get("title", "")
                if not video_id or title in ("Private video", "Deleted video", ""):
                    continue
                if video_id in seen_ids:
                    continue

                seen_ids.add(video_id)
                all_results.append({
                    "source": "youtube_headlines",
                    "title": title,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "video_id": video_id,
                    "channel": channel_name or snippet.get("channelTitle", ""),
                    "description": (snippet.get("description", "") or "")[:300],
                    "published_at": published_str,
                    "category": category,
                })

        all_results.sort(key=lambda x: x.get("published_at", ""), reverse=True)
        print(f"  [YT Headlines] Scanned {scanned} channels, {len(all_results)} recent videos")
        return all_results


# ============================================================
# CROSS-VERTICAL BRIEF COLLECTOR
# Pulls recent briefs from other verticals as context signal
# ============================================================

class CrossVerticalCollector:
    """Pull recent briefs from AI and Health verticals as context signal."""

    def __init__(self, db_path: str, verticals: list[str] = None, days_back: int = 3):
        self.db_path = db_path
        self.verticals = verticals or ["ai_tech", "health_longevity"]
        self.days_back = days_back

    def collect(self) -> list[dict]:
        """Get recent briefs from other verticals."""
        import sqlite3

        print(f"[CrossVertical] Pulling recent briefs from {self.verticals}...")
        cutoff = (datetime.utcnow() - timedelta(days=self.days_back)).strftime("%Y-%m-%d %H:%M:%S")

        results = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            placeholders = ",".join("?" * len(self.verticals))
            cursor.execute(f"""
                SELECT vertical, title, content, created_at
                FROM daily_briefs
                WHERE vertical IN ({placeholders}) AND created_at > ?
                ORDER BY created_at DESC
                LIMIT 5
            """, (*self.verticals, cutoff))

            for row in cursor.fetchall():
                # Truncate content to keep signal digest manageable
                content = (row["content"] or "")[:1500]
                results.append({
                    "source": "cross_vertical",
                    "vertical": row["vertical"],
                    "title": row["title"] or "",
                    "content_summary": content,
                    "created_at": row["created_at"] or "",
                })

            conn.close()
        except Exception as e:
            print(f"  [CrossVertical] Error: {e}")

        print(f"  [CrossVertical] Found {len(results)} recent briefs from other verticals")
        return results


# ============================================================
# SIGNAL DIGEST BUILDER
# Converts collected data into text for Claude to synthesize
# ============================================================

def prepare_signal_digest(collected_data: dict) -> str:
    """
    Compress collected signals into a text digest for Claude to synthesize.
    Organized by source tier: research → aggregators → community → cross-vertical.
    """
    sections = []

    # Tier 1: PubMed
    pubmed_items = collected_data.get("sources", {}).get("pubmed", [])
    if pubmed_items:
        lines = []
        for item in pubmed_items[:30]:
            title = item.get("title", "")
            authors = item.get("authors", "")
            journal = item.get("journal", "")
            url = item.get("url", "")
            pub_date = item.get("pub_date", "")
            lines.append(f"- {title}\n  {authors} | {journal} | {pub_date}\n  URL: {url}")
        sections.append(f"## PUBMED — Published Research ({len(lines)} papers)\n" + "\n".join(lines))

    # Tier 2: RSS Feeds
    rss_items = collected_data.get("sources", {}).get("rss_feeds", [])
    if rss_items:
        lines = []
        for item in rss_items[:25]:
            feed = item.get("feed", "")
            title = item.get("title", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            line = f"- [{feed}] {title}\n  URL: {url}"
            if desc:
                line += f"\n  Summary: {desc[:200]}"
            lines.append(line)
        sections.append(f"## NEWS & AGGREGATORS ({len(lines)} articles)\n" + "\n".join(lines))

    # Tier 3: Hacker News
    hn_items = collected_data.get("sources", {}).get("hacker_news", [])
    if hn_items:
        lines = []
        for item in hn_items[:20]:
            title = item.get("title", "")
            url = item.get("url", "")
            points = item.get("points", 0)
            comments = item.get("comments", 0)
            lines.append(f"- [{points}pts, {comments}c] {title}\n  URL: {url}")
        sections.append(f"## HACKER NEWS ({len(lines)} stories)\n" + "\n".join(lines))

    # Tier 3: Reddit
    reddit_items = collected_data.get("sources", {}).get("reddit", [])
    if reddit_items:
        lines = []
        for item in reddit_items[:25]:
            title = item.get("title", "")
            sub = item.get("subreddit", "")
            url = item.get("reddit_url", item.get("url", ""))
            lines.append(f"- [r/{sub}] {title}\n  URL: {url}")
        sections.append(f"## REDDIT ({len(lines)} posts)\n" + "\n".join(lines))

    # YouTube Headlines
    yt_items = collected_data.get("sources", {}).get("youtube_headlines", [])
    if yt_items:
        lines = []
        for item in yt_items[:20]:
            channel = item.get("channel", "")
            title = item.get("title", "")
            url = item.get("url", "")
            desc = item.get("description", "")
            line = f"- [{channel}] {title}\n  URL: {url}"
            if desc:
                line += f"\n  Description: {desc[:200]}"
            lines.append(line)
        sections.append(f"## YOUTUBE — Creator Headlines ({len(lines)} recent videos)\n" + "\n".join(lines))

    # Cross-vertical context
    cv_items = collected_data.get("sources", {}).get("cross_vertical", [])
    if cv_items:
        lines = []
        for item in cv_items:
            vertical = item.get("vertical", "")
            title = item.get("title", "")
            content = item.get("content_summary", "")
            lines.append(f"- [{vertical}] {title}\n  Key findings: {content[:500]}")
        sections.append(f"## CROSS-VERTICAL CONTEXT — Recent briefs from other verticals\n" + "\n".join(lines))

    return "\n\n".join(sections)


# ============================================================
# COMMON SYNTHESIS UTILITIES
# ============================================================

def get_previous_brief(vertical: str, db_path: str = None) -> Optional[str]:
    """Fetch the most recent brief for this vertical from the database."""
    import sqlite3
    if db_path is None:
        db_path = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/youtube_intelligence.db"
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


def build_dedup_section(previous_brief: Optional[str]) -> str:
    """Build the dedup instruction section for the synthesis prompt."""
    if not previous_brief:
        return ""
    return f"""
## PREVIOUS BRIEF (DO NOT REPEAT)

The following is the most recent brief that was already published. DO NOT repeat the same stories, findings, or framings. If a topic appeared in the previous brief:
- SKIP it entirely unless there is genuinely new data, a new study, or a meaningful update
- If there IS a meaningful update, frame it as "Update on [topic]: [new development]"
- Fill the brief with OTHER signals and findings instead

Previous brief:
{previous_brief}

---

"""


# ============================================================
# STANDARD COLLECT_ALL BUILDER
# Each stage's collectors.py calls this with its specific config
# ============================================================

def collect_all_for_stage(
    stage_name: str,
    pubmed_queries: list[str],
    rss_feeds: dict[str, str],
    hn_queries: list[str],
    subreddits: list[str],
    hours_back: int = 24,
    db_path: str = None,
    youtube_channels_json: str = None,
    youtube_api_key: str = None,
) -> dict:
    """
    Run all collectors for a life-stage vertical.
    Each stage provides its own queries/feeds/subreddits.
    Returns a dict with items grouped by source.
    """
    print(f"\n{'='*60}")
    print(f"  {stage_name} — Collecting")
    print(f"  Window: last {hours_back} hours (research: 7 days)")
    print(f"  Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    results = {
        "vertical": stage_name,
        "collected_at": datetime.utcnow().isoformat(),
        "hours_back": hours_back,
        "sources": {},
    }

    # Tier 1: Research (7-day window)
    if pubmed_queries:
        pubmed = PubMedCollector(queries=pubmed_queries, days_back=7)
        results["sources"]["pubmed"] = pubmed.collect()

    # Tier 2: RSS feeds (3-day window)
    if rss_feeds:
        rss = RSSCollector(feeds=rss_feeds, days_back=3)
        results["sources"]["rss_feeds"] = rss.collect()

    # Tier 3: Community
    if hn_queries:
        hn = HNCollector(queries=hn_queries, hours_back=48)
        results["sources"]["hacker_news"] = hn.collect()

    if subreddits:
        reddit = RedditCollector(subreddits=subreddits, hours_back=hours_back)
        results["sources"]["reddit"] = reddit.collect()

    # YouTube headline scanner (if configured)
    if youtube_channels_json and youtube_api_key:
        yt = YouTubeHeadlineCollector(
            channels_json_path=youtube_channels_json,
            api_key=youtube_api_key,
            hours_back=72,
        )
        results["sources"]["youtube_headlines"] = yt.collect()

    # Cross-vertical context (always)
    if db_path:
        cv = CrossVerticalCollector(db_path=db_path)
        results["sources"]["cross_vertical"] = cv.collect()

    # Summary
    total = sum(len(v) for v in results["sources"].values())
    print(f"\n{'='*60}")
    print(f"  COLLECTION COMPLETE — {total} total items")
    for source, items in results["sources"].items():
        print(f"    {source}: {len(items)}")
    print(f"{'='*60}\n")

    return results

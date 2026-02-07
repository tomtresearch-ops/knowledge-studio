"""
Daily Brief — Source Collectors
Gather signal from multiple sources for synthesis into daily briefs.
"""

import requests
import json
from datetime import datetime, timedelta
from typing import Optional


# ============================================================
# HACKER NEWS COLLECTOR
# Uses Algolia HN Search API (free, no auth required)
# ============================================================

class HNCollector:
    """Collect AI/tech signal from Hacker News."""

    BASE_URL = "https://hn.algolia.com/api/v1"

    # Search terms for AI & Tech vertical
    AI_TECH_QUERIES = [
        "artificial intelligence",
        "LLM",
        "GPT",
        "Claude",
        "Anthropic",
        "OpenAI",
        "machine learning",
        "AI agent",
        "transformer model",
        "neural network",
        "AI startup",
        "foundation model",
    ]

    def __init__(self, hours_back: int = 24):
        self.hours_back = hours_back
        self.cutoff = int((datetime.utcnow() - timedelta(hours=hours_back)).timestamp())

    def search(self, query: str, min_points: int = 5, num_results: int = 20) -> list[dict]:
        """Search HN for a query, return scored results."""
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

    def get_top_stories(self, min_points: int = 50) -> list[dict]:
        """Get top HN stories from the last N hours (any topic)."""
        try:
            params = {
                "tags": "front_page",
                "numericFilters": f"created_at_i>{self.cutoff},points>{min_points}",
                "hitsPerPage": 30,
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
                    "query_matched": "front_page",
                })
            return results
        except Exception as e:
            print(f"  [HN] Error fetching top stories: {e}")
            return []

    def collect_ai_tech(self) -> list[dict]:
        """Run all AI & Tech queries and deduplicate results."""
        print(f"[HN] Collecting AI & Tech signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        # Get front page stories first (high signal)
        top = self.get_top_stories(min_points=50)
        for item in top:
            if item["url"] not in seen_urls:
                seen_urls.add(item["url"])
                item["signal_score"] = self._score(item)
                all_results.append(item)

        # Then targeted AI searches
        for query in self.AI_TECH_QUERIES:
            results = self.search(query, min_points=3, num_results=10)
            for item in results:
                if item["url"] not in seen_urls:
                    seen_urls.add(item["url"])
                    item["signal_score"] = self._score(item)
                    all_results.append(item)

        # Sort by signal score
        all_results.sort(key=lambda x: x["signal_score"], reverse=True)
        print(f"  [HN] Found {len(all_results)} unique items")
        return all_results

    def _score(self, item: dict) -> float:
        """Score an item by engagement and recency."""
        points = item.get("points", 0)
        comments = item.get("comments", 0)
        # Engagement score: points + comments weighted
        engagement = points + (comments * 1.5)
        # Boost AI-specific queries vs front_page
        if item.get("query_matched") != "front_page":
            engagement *= 1.3
        return round(engagement, 1)


# ============================================================
# REDDIT COLLECTOR
# Uses Reddit JSON API (no auth needed for public subreddits)
# ============================================================

class RedditCollector:
    """Collect AI/tech signal from Reddit."""

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 DailyBrief"}

    AI_SUBREDDITS = [
        "MachineLearning",
        "artificial",
        "LocalLLaMA",
        "singularity",
        "ClaudeAI",
        "ChatGPT",
        "OpenAI",
    ]

    def __init__(self, hours_back: int = 24):
        self.hours_back = hours_back
        self.cutoff = (datetime.utcnow() - timedelta(hours=hours_back)).timestamp()

    def _get_oauth_token(self) -> Optional[str]:
        """Get Reddit OAuth token using client credentials (script app)."""
        if not hasattr(self, '_client_id') or not self._client_id:
            return None
        try:
            auth = requests.auth.HTTPBasicAuth(self._client_id, self._client_secret)
            data = {"grant_type": "client_credentials"}
            headers = {"User-Agent": self.HEADERS["User-Agent"]}
            resp = requests.post("https://www.reddit.com/api/v1/access_token",
                                 auth=auth, data=data, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json().get("access_token")
        except Exception as e:
            print(f"  [Reddit] OAuth error: {e}")
            return None

    def get_subreddit_top(self, subreddit: str, time_filter: str = "day", limit: int = 15) -> list[dict]:
        """Get top posts from a subreddit. Tries OAuth first, falls back to RSS."""
        # Try OAuth API if credentials available
        if hasattr(self, '_token') and self._token:
            return self._get_via_oauth(subreddit, time_filter, limit)
        # Fallback: RSS feed (always works, limited data)
        return self._get_via_rss(subreddit, limit)

    def _get_via_rss(self, subreddit: str, limit: int = 15) -> list[dict]:
        """Fallback: get posts via RSS feed."""
        try:
            url = f"https://www.reddit.com/r/{subreddit}/top.rss?t=day&limit={limit}"
            resp = requests.get(url, headers=self.HEADERS, timeout=10)
            resp.raise_for_status()

            # Parse RSS (simple XML parsing)
            import re
            entries = re.findall(r'<entry>(.*?)</entry>', resp.text, re.DOTALL)
            results = []
            for entry in entries[:limit]:
                title_match = re.search(r'<title[^>]*>(.*?)</title>', entry)
                link_match = re.search(r'<link[^>]*href="([^"]*)"', entry)
                updated_match = re.search(r'<updated>(.*?)</updated>', entry)
                author_match = re.search(r'<name>(.*?)</name>', entry)

                if title_match and link_match:
                    title = title_match.group(1).replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
                    reddit_url = link_match.group(1)
                    results.append({
                        "source": "reddit",
                        "subreddit": subreddit,
                        "title": title,
                        "url": reddit_url,
                        "reddit_url": reddit_url,
                        "score": 0,  # Not available in RSS
                        "comments": 0,
                        "author": author_match.group(1).replace('/u/', '') if author_match else "",
                        "created_at": updated_match.group(1) if updated_match else "",
                        "selftext": "",
                        "is_self": False,
                        "flair": "",
                    })
            return results
        except Exception as e:
            print(f"  [Reddit] RSS fallback error for r/{subreddit}: {e}")
            return []

    def _get_via_oauth(self, subreddit: str, time_filter: str = "day", limit: int = 15) -> list[dict]:
        """Get posts via OAuth API."""
        try:
            url = f"https://oauth.reddit.com/r/{subreddit}/top?t={time_filter}&limit={limit}"
            headers = {**self.HEADERS, "Authorization": f"Bearer {self._token}"}
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for post in data.get("data", {}).get("children", []):
                d = post["data"]
                # Skip stickied/pinned posts
                if d.get("stickied"):
                    continue
                created = d.get("created_utc", 0)
                if created < self.cutoff:
                    continue
                results.append({
                    "source": "reddit",
                    "subreddit": subreddit,
                    "title": d.get("title", ""),
                    "url": d.get("url", ""),
                    "reddit_url": f"https://reddit.com{d.get('permalink', '')}",
                    "score": d.get("score", 0),
                    "comments": d.get("num_comments", 0),
                    "author": d.get("author", ""),
                    "created_at": datetime.utcfromtimestamp(created).isoformat(),
                    "selftext": (d.get("selftext", "") or "")[:500],  # First 500 chars of self posts
                    "is_self": d.get("is_self", False),
                    "flair": d.get("link_flair_text", ""),
                })
            return results
        except Exception as e:
            print(f"  [Reddit] Error fetching r/{subreddit}: {e}")
            return []

    def collect_ai_tech(self) -> list[dict]:
        """Collect top AI posts across subreddits, deduplicated."""
        print(f"[Reddit] Collecting AI & Tech signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for sub in self.AI_SUBREDDITS:
            posts = self.get_subreddit_top(sub)
            for post in posts:
                # Dedupe by URL (cross-posts)
                url_key = post["url"] if not post["is_self"] else post["reddit_url"]
                if url_key not in seen_urls:
                    seen_urls.add(url_key)
                    post["signal_score"] = self._score(post)
                    all_results.append(post)

        all_results.sort(key=lambda x: x["signal_score"], reverse=True)
        print(f"  [Reddit] Found {len(all_results)} unique items")
        return all_results

    def _score(self, item: dict) -> float:
        """Score by upvotes and comment engagement."""
        score = item.get("score", 0)
        comments = item.get("comments", 0)
        # Weight: upvotes + comments * 2 (discussion = high signal)
        return round(score + (comments * 2), 1)


# ============================================================
# YOUTUBE SEARCH COLLECTOR
# Uses YouTube Data API v3
# ============================================================

class YouTubeSearchCollector:
    """Search YouTube for trending AI content beyond subscribed channels."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    AI_SEARCH_QUERIES = [
        "AI news today",
        "artificial intelligence breakthrough",
        "LLM update",
        "AI agents",
        "Claude Anthropic",
        "OpenAI news",
    ]

    def __init__(self, api_key: Optional[str] = None, hours_back: int = 48):
        self.api_key = api_key
        self.hours_back = hours_back
        # YouTube search is broader — look back 48h by default
        self.published_after = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Search YouTube for recent videos matching query."""
        if not self.api_key:
            print("  [YouTube] No API key — skipping")
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
                    "thumbnail": snippet.get("thumbnails", {}).get("high", {}).get("url", ""),
                    "video_id": video_id,
                    "query_matched": query,
                })
            return results
        except Exception as e:
            print(f"  [YouTube] Error searching '{query}': {e}")
            return []

    def collect_ai_tech(self) -> list[dict]:
        """Run all AI search queries, deduplicate."""
        if not self.api_key:
            print("[YouTube] No API key configured — skipping YouTube search")
            return []

        print(f"[YouTube] Collecting AI & Tech signal (last {self.hours_back}h)...")
        all_results = []
        seen_ids = set()

        for query in self.AI_SEARCH_QUERIES:
            results = self.search(query, max_results=5)  # Conservative to stay within quota
            for item in results:
                if item["video_id"] not in seen_ids:
                    seen_ids.add(item["video_id"])
                    all_results.append(item)

        print(f"  [YouTube] Found {len(all_results)} unique videos")
        return all_results


# ============================================================
# KNOWLEDGE STUDIO COLLECTOR
# Pull recently processed content from the local KS database
# ============================================================

class KnowledgeStudioCollector:
    """Pull recent AI/tech content from Knowledge Studio database."""

    def __init__(self, db_path: str, hours_back: int = 24):
        self.db_path = db_path
        self.hours_back = hours_back

    def collect_recent(self) -> list[dict]:
        """Get recently processed videos and articles from KS."""
        import sqlite3

        print(f"[KS] Collecting recent content (last {self.hours_back}h)...")
        cutoff = (datetime.utcnow() - timedelta(hours=self.hours_back)).strftime("%Y-%m-%d %H:%M:%S")

        results = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get recent videos
            cursor.execute("""
                SELECT id, title, channel, ai_summary, summary_15, tags, video_url, processing_date
                FROM videos
                WHERE processing_date > ? AND status = 'completed'
                ORDER BY processing_date DESC
                LIMIT 50
            """, (cutoff,))

            for row in cursor.fetchall():
                results.append({
                    "source": "knowledge_studio",
                    "content_type": "video",
                    "id": row["id"],
                    "title": row["title"] or "",
                    "channel": row["channel"] or "",
                    "summary": row["ai_summary"] or "",
                    "summary_short": row["summary_15"] or "",
                    "tags": row["tags"] or "",
                    "url": row["video_url"] or "",
                    "processed_at": row["processing_date"] or "",
                })

            # Get recent articles
            cursor.execute("""
                SELECT id, title, url, summary, summary_15, tags, created_at
                FROM articles
                WHERE created_at > ?
                ORDER BY created_at DESC
                LIMIT 30
            """, (cutoff,))

            for row in cursor.fetchall():
                results.append({
                    "source": "knowledge_studio",
                    "content_type": "article",
                    "id": row["id"],
                    "title": row["title"] or "",
                    "channel": "",
                    "summary": row["summary"] or "",
                    "summary_short": row["summary_15"] or "",
                    "tags": row["tags"] or "",
                    "url": row["url"] or "",
                    "processed_at": row["created_at"] or "",
                })

            conn.close()
        except Exception as e:
            print(f"  [KS] Error: {e}")

        print(f"  [KS] Found {len(results)} recent items")
        return results


# ============================================================
# MASTER COLLECTOR — Run all sources
# ============================================================

def collect_all(vertical: str = "ai_tech",
                hours_back: int = 24,
                db_path: str = None,
                youtube_api_key: str = None) -> dict:
    """
    Run all collectors for a given vertical.
    Returns a dict with items grouped by source.
    """
    print(f"\n{'='*60}")
    print(f"  DAILY BRIEF — Collecting: {vertical}")
    print(f"  Window: last {hours_back} hours")
    print(f"  Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    results = {
        "vertical": vertical,
        "collected_at": datetime.utcnow().isoformat(),
        "hours_back": hours_back,
        "sources": {},
    }

    if vertical == "ai_tech":
        # Hacker News
        hn = HNCollector(hours_back=hours_back)
        results["sources"]["hacker_news"] = hn.collect_ai_tech()

        # Reddit
        reddit = RedditCollector(hours_back=hours_back)
        results["sources"]["reddit"] = reddit.collect_ai_tech()

        # YouTube Search
        if youtube_api_key:
            yt = YouTubeSearchCollector(api_key=youtube_api_key, hours_back=48)
            results["sources"]["youtube_search"] = yt.collect_ai_tech()

        # Knowledge Studio
        if db_path:
            ks = KnowledgeStudioCollector(db_path=db_path, hours_back=hours_back)
            results["sources"]["knowledge_studio"] = ks.collect_recent()

    # Summary
    total = sum(len(v) for v in results["sources"].values())
    print(f"\n{'='*60}")
    print(f"  COLLECTION COMPLETE — {total} total items")
    for source, items in results["sources"].items():
        print(f"    {source}: {len(items)}")
    print(f"{'='*60}\n")

    return results


if __name__ == "__main__":
    # Test run
    DB_PATH = "/Users/bossmdaddy/Desktop/Coding Projects Master/youtube-intelligence/youtube_intelligence.db"

    data = collect_all(
        vertical="ai_tech",
        hours_back=24,
        db_path=DB_PATH,
        youtube_api_key=None,  # Add key later
    )

    # Show top items from each source
    for source, items in data["sources"].items():
        print(f"\n--- TOP {source.upper()} ---")
        for item in items[:5]:
            score = item.get("signal_score", item.get("score", "N/A"))
            print(f"  [{score}] {item['title'][:80]}")
            print(f"        {item['url'][:80]}")

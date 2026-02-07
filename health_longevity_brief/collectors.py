"""
Health & Longevity Brief — Source Collectors
Gather signal from research databases, aggregators, communities, and creators.
"""

import requests
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional


# ============================================================
# PUBMED COLLECTOR
# Uses NCBI E-utilities API (free, no auth for moderate use)
# ============================================================

class PubMedCollector:
    """Collect recent longevity/aging research from PubMed."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    SEARCH_QUERIES = [
        "longevity AND (aging OR anti-aging OR rejuvenation)",
        "senescence AND (therapy OR reversal OR clearance)",
        "rapamycin OR metformin OR NAD+ OR NMN OR senolytics",
        "GLP-1 AND (aging OR longevity OR healthspan)",
        "gene therapy AND (aging OR age-related)",
        "telomere AND (extension OR telomerase)",
        "epigenetic clock OR biological age",
        "CRISPR AND (aging OR disease)",
        "caloric restriction OR intermittent fasting AND longevity",
        "stem cell AND (rejuvenation OR regeneration)",
    ]

    def __init__(self, days_back: int = 7):
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
                    author_str += f" et al."

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
        print(f"[PubMed] Collecting longevity research (last {self.days_back} days)...")
        all_pmids = []
        seen = set()

        for i, query in enumerate(self.SEARCH_QUERIES):
            if i > 0:
                time.sleep(0.4)  # Respect NCBI rate limit (3 req/sec without API key)
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
# BIORXIV COLLECTOR
# Uses bioRxiv Content API (free, no auth)
# ============================================================

class BioRxivCollector:
    """Collect recent preprints from bioRxiv related to aging/longevity."""

    BASE_URL = "https://api.biorxiv.org/details/biorxiv"

    # Categories relevant to longevity
    RELEVANT_CATEGORIES = {
        "cell biology", "genetics", "genomics", "molecular biology",
        "neuroscience", "pharmacology and toxicology", "physiology",
        "systems biology", "biochemistry", "bioinformatics",
        "developmental biology", "immunology", "pathology",
    }

    LONGEVITY_KEYWORDS = [
        "aging", "ageing", "longevity", "senescence", "senolytic",
        "rejuvenation", "lifespan", "healthspan", "telomere", "epigenetic",
        "NAD", "rapamycin", "metformin", "caloric restriction", "autophagy",
        "mitochondri", "stem cell", "regenerat", "inflammag", "geroprot",
        "biological age", "clock", "anti-aging", "age-related",
    ]

    def __init__(self, days_back: int = 7):
        self.days_back = days_back
        self.start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        self.end_date = datetime.utcnow().strftime("%Y-%m-%d")

    def fetch_preprints(self, cursor: int = 0) -> tuple[list[dict], int]:
        """Fetch a page of recent preprints."""
        try:
            url = f"{self.BASE_URL}/{self.start_date}/{self.end_date}/{cursor}"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            papers = data.get("collection", [])
            total = int(data.get("messages", [{}])[0].get("total", 0))
            return papers, total
        except Exception as e:
            print(f"  [bioRxiv] Fetch error at cursor {cursor}: {e}")
            return [], 0

    def is_relevant(self, paper: dict) -> bool:
        """Check if a preprint is relevant to longevity/aging."""
        category = paper.get("category", "").lower()
        title = paper.get("title", "").lower()
        abstract = paper.get("abstract", "").lower()
        text = f"{title} {abstract}"

        # Must be in a relevant category
        if category not in self.RELEVANT_CATEGORIES:
            return False

        # Must match at least one longevity keyword
        for kw in self.LONGEVITY_KEYWORDS:
            if kw in text:
                return True
        return False

    def collect(self) -> list[dict]:
        """Fetch recent preprints and filter for longevity relevance."""
        print(f"[bioRxiv] Collecting longevity preprints (last {self.days_back} days)...")
        results = []
        cursor = 0
        pages_checked = 0
        max_pages = 10  # Safety limit

        while pages_checked < max_pages:
            papers, total = self.fetch_preprints(cursor)
            if not papers:
                break

            for paper in papers:
                if self.is_relevant(paper):
                    results.append({
                        "source": "biorxiv",
                        "title": paper.get("title", ""),
                        "authors": paper.get("authors", ""),
                        "abstract": paper.get("abstract", "")[:500],
                        "category": paper.get("category", ""),
                        "doi": paper.get("doi", ""),
                        "url": f"https://www.biorxiv.org/content/{paper.get('doi', '')}",
                        "pub_date": paper.get("date", ""),
                    })

            cursor += len(papers)
            pages_checked += 1

            # Stop if we've seen all papers
            if cursor >= total:
                break

        print(f"  [bioRxiv] Found {len(results)} relevant preprints")
        return results


# ============================================================
# RSS AGGREGATOR COLLECTOR
# Medical Xpress, ScienceDaily, New Scientist
# ============================================================

class RSSAggregatorCollector:
    """Collect health/longevity signal from science news aggregators via RSS."""

    FEEDS = {
        "Medical Xpress — Aging": "https://medicalxpress.com/rss-feed/search/?search=aging+longevity",
        "Medical Xpress — Genetics": "https://medicalxpress.com/rss-feed/search/?search=gene+therapy+aging",
        "ScienceDaily — Aging": "https://www.sciencedaily.com/rss/health_medicine/healthy_aging.xml",
        "ScienceDaily — Stem Cells": "https://www.sciencedaily.com/rss/health_medicine/stem_cells.xml",
        "New Scientist — Health": "https://www.newscientist.com/subject/health/feed/",
        "New Atlas — Health": "https://newatlas.com/health-wellbeing/index.rss",
    }

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 HealthBrief"}

    def __init__(self, days_back: int = 3):
        self.days_back = days_back
        self.cutoff = datetime.utcnow() - timedelta(days=days_back)

    def parse_rss(self, feed_name: str, feed_url: str) -> list[dict]:
        """Parse an RSS feed and return items."""
        try:
            resp = requests.get(feed_url, headers=self.HEADERS, timeout=15)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)

            # Handle both RSS 2.0 and Atom formats
            items = root.findall('.//item')
            if not items:
                # Try Atom format
                ns = {'atom': 'http://www.w3.org/2005/Atom'}
                items = root.findall('.//atom:entry', ns)

            results = []
            for item in items[:20]:  # Max 20 per feed
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
        # Try with common namespaces
        for ns_prefix in ['', '{http://www.w3.org/2005/Atom}', '{http://purl.org/dc/elements/1.1/}']:
            el = element.find(f'{ns_prefix}{tag}')
            if el is not None and el.text:
                return el.text.strip()
        return ""

    def collect(self) -> list[dict]:
        """Collect from all RSS feeds."""
        print(f"[RSS] Collecting from science aggregators (last {self.days_back} days)...")
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
# HACKER NEWS COLLECTOR (Health/Longevity)
# ============================================================

class HNCollector:
    """Collect health/longevity signal from Hacker News."""

    BASE_URL = "https://hn.algolia.com/api/v1"

    HEALTH_QUERIES = [
        "longevity",
        "anti-aging",
        "aging research",
        "senolytic",
        "rapamycin",
        "GLP-1",
        "gene therapy",
        "CRISPR health",
        "rejuvenation",
        "biological age",
        "stem cell therapy",
        "clinical trial",
    ]

    def __init__(self, hours_back: int = 48):
        self.hours_back = hours_back
        self.cutoff = int((datetime.utcnow() - timedelta(hours=hours_back)).timestamp())

    def search(self, query: str, min_points: int = 3, num_results: int = 15) -> list[dict]:
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
        """Run all health/longevity queries and deduplicate."""
        print(f"[HN] Collecting health/longevity signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for query in self.HEALTH_QUERIES:
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
# REDDIT COLLECTOR (Health/Longevity)
# ============================================================

class RedditCollector:
    """Collect health/longevity signal from Reddit."""

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 HealthBrief"}

    HEALTH_SUBREDDITS = [
        "longevity",
        "Biohackers",
        "ScientificNutrition",
        "supplements",
        "Nootropics",
        "aging",
    ]

    def __init__(self, hours_back: int = 24):
        self.hours_back = hours_back

    def get_subreddit_top(self, subreddit: str, limit: int = 15) -> list[dict]:
        """Get top posts via RSS feed."""
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
        """Collect top posts across health subreddits."""
        print(f"[Reddit] Collecting health/longevity signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for sub in self.HEALTH_SUBREDDITS:
            posts = self.get_subreddit_top(sub)
            for post in posts:
                if post["url"] not in seen_urls:
                    seen_urls.add(post["url"])
                    all_results.append(post)

        print(f"  [Reddit] Found {len(all_results)} unique items")
        return all_results


# ============================================================
# YOUTUBE SEARCH COLLECTOR (Health/Longevity)
# ============================================================

class YouTubeSearchCollector:
    """Search YouTube for trending longevity/health content."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    HEALTH_QUERIES = [
        "longevity research news",
        "anti-aging breakthrough",
        "Peter Attia longevity",
        "Andrew Huberman health",
        "Bryan Johnson blueprint",
        "David Sinclair aging",
        "longevity supplements",
        "biohacking health",
    ]

    def __init__(self, api_key: Optional[str] = None, hours_back: int = 72):
        self.api_key = api_key
        self.hours_back = hours_back
        self.published_after = (datetime.utcnow() - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def search(self, query: str, max_results: int = 8) -> list[dict]:
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
        """Run all health search queries, deduplicate."""
        if not self.api_key:
            print("[YouTube] No API key — skipping YouTube search")
            return []

        print(f"[YouTube] Collecting health/longevity signal (last {self.hours_back}h)...")
        all_results = []
        seen_ids = set()

        for query in self.HEALTH_QUERIES:
            results = self.search(query, max_results=5)
            for item in results:
                if item["video_id"] not in seen_ids:
                    seen_ids.add(item["video_id"])
                    all_results.append(item)

        print(f"  [YouTube] Found {len(all_results)} unique videos")
        return all_results


# ============================================================
# KNOWLEDGE STUDIO COLLECTOR (Health/Longevity)
# ============================================================

class KnowledgeStudioCollector:
    """Pull recent health/longevity content from Knowledge Studio database."""

    HEALTH_KEYWORDS = [
        "longevity", "aging", "anti-aging", "health", "medicine",
        "biotech", "pharmaceutical", "clinical", "therapy", "supplement",
        "nutrition", "exercise", "sleep", "fasting", "biohack",
        "attia", "huberman", "sinclair", "bryan johnson",
    ]

    def __init__(self, db_path: str, hours_back: int = 72):
        self.db_path = db_path
        self.hours_back = hours_back

    def collect(self) -> list[dict]:
        """Get recently processed health-related content from KS."""
        import sqlite3

        print(f"[KS] Collecting health/longevity content (last {self.hours_back}h)...")
        cutoff = (datetime.utcnow() - timedelta(hours=self.hours_back)).strftime("%Y-%m-%d %H:%M:%S")

        results = []
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get recent videos — filter by keywords in title/tags
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
                if any(kw in text for kw in self.HEALTH_KEYWORDS):
                    results.append({
                        "source": "knowledge_studio",
                        "content_type": "video",
                        "title": row["title"] or "",
                        "channel": row["channel"] or "",
                        "summary_short": row["summary_15"] or "",
                        "url": row["video_url"] or "",
                        "processed_at": row["processing_date"] or "",
                    })

            # Get recent articles — same keyword filter
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
                if any(kw in text for kw in self.HEALTH_KEYWORDS):
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

        print(f"  [KS] Found {len(results)} health-related items")
        return results


# ============================================================
# MASTER COLLECTOR — Run all sources
# ============================================================

def collect_all(vertical: str = "health_longevity",
                hours_back: int = 24,
                db_path: str = None,
                youtube_api_key: str = None) -> dict:
    """
    Run all collectors for the health/longevity vertical.
    Returns a dict with items grouped by source.
    """
    print(f"\n{'='*60}")
    print(f"  HEALTH & LONGEVITY BRIEF — Collecting")
    print(f"  Window: last {hours_back} hours (research: 7 days)")
    print(f"  Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    results = {
        "vertical": vertical,
        "collected_at": datetime.utcnow().isoformat(),
        "hours_back": hours_back,
        "sources": {},
    }

    # Tier 1: Research databases (7-day window)
    pubmed = PubMedCollector(days_back=7)
    results["sources"]["pubmed"] = pubmed.collect()

    biorxiv = BioRxivCollector(days_back=7)
    results["sources"]["biorxiv"] = biorxiv.collect()

    # Tier 2: Curated aggregators (3-day window)
    rss = RSSAggregatorCollector(days_back=3)
    results["sources"]["rss_aggregators"] = rss.collect()

    # Tier 3: Community + creators
    hn = HNCollector(hours_back=48)
    results["sources"]["hacker_news"] = hn.collect()

    reddit = RedditCollector(hours_back=hours_back)
    results["sources"]["reddit"] = reddit.collect()

    if youtube_api_key:
        yt = YouTubeSearchCollector(api_key=youtube_api_key, hours_back=72)
        results["sources"]["youtube_search"] = yt.collect()

    if db_path:
        ks = KnowledgeStudioCollector(db_path=db_path, hours_back=72)
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
        vertical="health_longevity",
        hours_back=24,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
    )

    for source, items in data["sources"].items():
        print(f"\n--- TOP {source.upper()} ---")
        for item in items[:3]:
            print(f"  {item['title'][:80]}")
            print(f"  {item.get('url', '')[:80]}")

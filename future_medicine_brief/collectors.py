"""
Future of Medicine Brief — Source Collectors
High-fidelity signal collection for frontier medical science, biotech breakthroughs,
regulatory shifts, AI-medicine convergence, gene therapy, and personalized medicine.

Editorial lens: "Lab to Fab" — tracking what's moving from lab bench to real-world accessibility.
Not personal optimization (that's Health & Longevity). This is paradigm shifts.

Cadence: Monday / Thursday
"""

import os
import requests
import json
import re
import time
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional


# ============================================================
# INTERNAL BRIEFS COLLECTOR
# Pulls recent Health & Longevity briefs for cross-vertical context
# ============================================================

class InternalBriefsCollector:
    """Ingest recent Health & Longevity briefs as source material for cross-pollination."""

    TARGET_VERTICALS = ["health_longevity"]

    def __init__(self, db_path: str, days_back: int = 4):
        self.db_path = db_path
        self.days_back = days_back

    def collect(self) -> list[dict]:
        """Get recent briefs from the database."""
        print(f"[Internal] Collecting recent H&L briefs (last {self.days_back} days)...")
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
# PUBMED COLLECTOR — Frontier Medicine
# Uses NCBI E-utilities API (free, no auth for moderate use)
# ============================================================

class PubMedCollector:
    """Collect recent frontier medicine research from PubMed."""

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    SEARCH_QUERIES = [
        # mRNA & gene therapy
        "mRNA therapeutics OR mRNA vaccine AND (cancer OR tumor OR genetic)",
        "CRISPR AND (gene therapy OR gene editing OR clinical trial)",
        "gene therapy AND (FDA OR approval OR clinical trial phase)",
        "CAR-T cell therapy AND (solid tumor OR cancer)",
        # AI + medicine convergence
        "artificial intelligence AND (drug discovery OR drug design)",
        "machine learning AND (clinical trial OR diagnostics OR pathology)",
        "AI AND (protein folding OR drug repurposing OR biomarker)",
        "large language model AND (medicine OR clinical OR diagnosis)",
        # Personalized medicine
        "personalized medicine AND (genomics OR pharmacogenomics)",
        "precision oncology AND (targeted therapy OR biomarker)",
        "liquid biopsy AND (early detection OR cancer screening)",
        # Frontier biotech
        "xenotransplantation AND (pig kidney OR organ transplant)",
        "synthetic biology AND (therapeutics OR biosynthesis)",
        "organ on chip OR organoid AND (drug testing OR disease model)",
        "nanomedicine AND (targeted delivery OR nanoparticle therapy)",
        "brain computer interface AND (clinical OR paralysis OR neural)",
        # Regenerative medicine
        "stem cell therapy AND (clinical trial OR regenerative)",
        "tissue engineering AND (3D bioprinting OR scaffold)",
        # Digital & regulatory
        "digital therapeutics AND (FDA OR clinical trial OR approval)",
        "decentralized clinical trial AND (remote monitoring OR wearable)",
        "FDA breakthrough therapy AND designation",
        # Emerging paradigms
        "microbiome AND (therapy OR fecal transplant OR engineered)",
        "epigenetic therapy AND (cancer OR aging)",
        "antisense oligonucleotide OR siRNA AND (therapy OR clinical)",
        "cell-free DNA AND (prenatal OR cancer OR transplant)",
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
            print(f"  [PubMed] Search error for '{query[:50]}': {e}")
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
        print(f"[PubMed] Collecting frontier medicine research (last {self.days_back} days)...")
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
# BIORXIV / MEDRXIV COLLECTOR — Frontier Medicine
# Uses bioRxiv Content API (free, no auth)
# ============================================================

class BioRxivCollector:
    """Collect recent preprints from bioRxiv AND medRxiv related to frontier medicine."""

    BIORXIV_URL = "https://api.biorxiv.org/details/biorxiv"
    MEDRXIV_URL = "https://api.biorxiv.org/details/medrxiv"

    RELEVANT_CATEGORIES = {
        "cell biology", "genetics", "genomics", "molecular biology",
        "immunology", "bioengineering", "synthetic biology",
        "pharmacology and toxicology", "bioinformatics",
        "biochemistry", "developmental biology", "pathology",
        "microbiology", "neuroscience", "cancer biology",
    }

    MEDICINE_KEYWORDS = [
        "mRNA", "CRISPR", "gene therapy", "gene editing", "CAR-T",
        "immunotherapy", "checkpoint inhibitor", "personalized medicine",
        "precision oncology", "liquid biopsy", "xenotransplant",
        "organ on chip", "organoid", "nanomedicine", "nanoparticle",
        "drug discovery", "drug design", "clinical trial",
        "brain computer interface", "neural implant", "neuralink",
        "synthetic biology", "biosynthesis", "cell therapy",
        "stem cell", "regenerat", "tissue engineer", "3D bioprint",
        "digital therapeutic", "AI diagnos", "machine learning",
        "deep learning", "protein fold", "alphafold",
        "antisense", "siRNA", "oligonucleotide",
        "microbiome", "fecal transplant", "epigenetic therap",
        "cell-free DNA", "FDA", "regulatory", "approval",
        "biomarker", "companion diagnostic",
    ]

    def __init__(self, days_back: int = 7):
        self.days_back = days_back
        self.start_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
        self.end_date = datetime.utcnow().strftime("%Y-%m-%d")

    def fetch_preprints(self, base_url: str, cursor: int = 0) -> tuple[list[dict], int]:
        """Fetch a page of recent preprints."""
        try:
            url = f"{base_url}/{self.start_date}/{self.end_date}/{cursor}"
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            papers = data.get("collection", [])
            total = int(data.get("messages", [{}])[0].get("total", 0))
            return papers, total
        except Exception as e:
            print(f"  [bioRxiv/medRxiv] Fetch error at cursor {cursor}: {e}")
            return [], 0

    def is_relevant(self, paper: dict) -> bool:
        """Check if a preprint is relevant to frontier medicine."""
        category = paper.get("category", "").lower()
        title = paper.get("title", "").lower()
        abstract = paper.get("abstract", "").lower()
        text = f"{title} {abstract}"

        # Must be in a relevant category
        if category not in self.RELEVANT_CATEGORIES:
            return False

        # Must match at least one medicine keyword
        for kw in self.MEDICINE_KEYWORDS:
            if kw.lower() in text:
                return True
        return False

    def _collect_from(self, base_url: str, label: str) -> list[dict]:
        """Collect from a single preprint server."""
        results = []
        cursor = 0
        pages_checked = 0
        max_pages = 10

        while pages_checked < max_pages:
            papers, total = self.fetch_preprints(base_url, cursor)
            if not papers:
                break

            for paper in papers:
                if self.is_relevant(paper):
                    server = "biorxiv" if "biorxiv" in base_url else "medrxiv"
                    results.append({
                        "source": server,
                        "title": paper.get("title", ""),
                        "authors": paper.get("authors", ""),
                        "abstract": paper.get("abstract", "")[:500],
                        "category": paper.get("category", ""),
                        "doi": paper.get("doi", ""),
                        "url": f"https://www.{server}.org/content/{paper.get('doi', '')}",
                        "pub_date": paper.get("date", ""),
                    })

            cursor += len(papers)
            pages_checked += 1
            if cursor >= total:
                break

        print(f"  [{label}] Found {len(results)} relevant preprints")
        return results

    def collect(self) -> list[dict]:
        """Fetch from BOTH bioRxiv and medRxiv."""
        print(f"[bioRxiv+medRxiv] Collecting frontier medicine preprints (last {self.days_back} days)...")
        results = []
        results.extend(self._collect_from(self.BIORXIV_URL, "bioRxiv"))
        results.extend(self._collect_from(self.MEDRXIV_URL, "medRxiv"))
        print(f"  [Total preprints] {len(results)} relevant papers")
        return results


# ============================================================
# RSS AGGREGATOR COLLECTOR — Comprehensive Medicine/Biotech
# 14+ feeds — most comprehensive of any vertical
# ============================================================

class RSSAggregatorCollector:
    """Collect frontier medicine signal from science news, biotech industry, and regulatory feeds."""

    FEEDS = {
        # Science news aggregators
        "Medical Xpress — Gene Therapy": "https://medicalxpress.com/rss-feed/search/?search=gene+therapy+CRISPR+mRNA",
        "Medical Xpress — Clinical Trials": "https://medicalxpress.com/rss-feed/search/?search=clinical+trial+breakthrough+therapy",
        "Medical Xpress — Biotech": "https://medicalxpress.com/rss-feed/search/?search=biotech+personalized+medicine",
        "Medical Xpress — AI Medicine": "https://medicalxpress.com/rss-feed/search/?search=artificial+intelligence+medicine+diagnosis",
        "EurekAlert — Medicine": "https://www.eurekalert.org/api/rss/find/category/medicine-health",
        "EurekAlert — Biology": "https://www.eurekalert.org/api/rss/find/category/biology",
        "ScienceDaily — Gene Therapy": "https://www.sciencedaily.com/rss/health_medicine/gene_therapy.xml",
        "ScienceDaily — Stem Cells": "https://www.sciencedaily.com/rss/health_medicine/stem_cells.xml",
        "ScienceDaily — Cancer": "https://www.sciencedaily.com/rss/health_medicine/cancer.xml",
        "ScienceDaily — Medical Devices": "https://www.sciencedaily.com/rss/health_medicine/medical_devices.xml",
        "New Atlas — Health": "https://newatlas.com/health-wellbeing/index.rss",
        "New Atlas — Science": "https://newatlas.com/science/index.rss",
        # Biotech/pharma industry
        "STAT News": "https://www.statnews.com/feed/",
        "Fierce Biotech": "https://www.fiercebiotech.com/rss/xml",
        "GEN — Genetic Engineering News": "https://www.genengnews.com/feed/",
        "BioPharma Dive": "https://www.biopharmadive.com/feeds/news/",
        # Frontier/convergence
        "Singularity Hub": "https://singularityhub.com/feed/",
        "Nature Medicine": "https://www.nature.com/nm.rss",
        "MIT Technology Review — Biotech": "https://www.technologyreview.com/topic/biotechnology/feed",
        "Science Translational Medicine": "https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=stm",
        # Regulatory
        "FDA Press Releases": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
    }

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 FutureMedicineBrief"}

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
        for ns_prefix in ['', '{http://www.w3.org/2005/Atom}', '{http://purl.org/dc/elements/1.1/}']:
            el = element.find(f'{ns_prefix}{tag}')
            if el is not None and el.text:
                return el.text.strip()
        return ""

    def collect(self) -> list[dict]:
        """Collect from all RSS feeds."""
        print(f"[RSS] Collecting from {len(self.FEEDS)} science/biotech feeds (last {self.days_back} days)...")
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
# HACKER NEWS COLLECTOR — Frontier Medicine
# ============================================================

class HNCollector:
    """Collect frontier medicine signal from Hacker News."""

    BASE_URL = "https://hn.algolia.com/api/v1"

    MEDICINE_QUERIES = [
        "mRNA vaccine",
        "mRNA therapy",
        "CRISPR therapy",
        "CRISPR clinical",
        "gene editing",
        "gene therapy",
        "AI drug discovery",
        "AI medicine",
        "AI diagnostics",
        "personalized medicine",
        "precision oncology",
        "synthetic biology",
        "biotech FDA",
        "clinical trial AI",
        "digital health",
        "xenotransplant",
        "brain computer interface",
        "organ transplant breakthrough",
        "CAR-T therapy",
        "liquid biopsy",
        "nanomedicine",
        "medical tourism",
        "FDA approval",
        "biotech breakthrough",
        "AlphaFold medicine",
        "protein design therapy",
        "stem cell therapy",
        "3D bioprinting",
        "organoid",
    ]

    def __init__(self, hours_back: int = 72):
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
        """Run all medicine queries and deduplicate."""
        print(f"[HN] Collecting frontier medicine signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for query in self.MEDICINE_QUERIES:
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
# REDDIT COLLECTOR — Frontier Medicine
# ============================================================

class RedditCollector:
    """Collect frontier medicine signal from Reddit."""

    HEADERS = {"User-Agent": "KnowledgeStudio/1.0 FutureMedicineBrief"}

    MEDICINE_SUBREDDITS = [
        "biotech",
        "genetics",
        "CRISPR",
        "medicine",
        "science",
        "Futurology",
        "genomics",
        "Nootropics",
        "medicalschool",
        "bioinformatics",
    ]

    def __init__(self, hours_back: int = 48):
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
        """Collect top posts across medicine/biotech subreddits."""
        print(f"[Reddit] Collecting frontier medicine signal (last {self.hours_back}h)...")
        all_results = []
        seen_urls = set()

        for sub in self.MEDICINE_SUBREDDITS:
            posts = self.get_subreddit_top(sub)
            for post in posts:
                if post["url"] not in seen_urls:
                    seen_urls.add(post["url"])
                    all_results.append(post)

        print(f"  [Reddit] Found {len(all_results)} unique items")
        return all_results


# ============================================================
# YOUTUBE SEARCH COLLECTOR — Frontier Medicine
# ============================================================

class YouTubeSearchCollector:
    """Search YouTube for trending frontier medicine content."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    MEDICINE_QUERIES = [
        "CRISPR gene therapy news",
        "mRNA vaccine breakthrough",
        "AI drug discovery",
        "personalized medicine genomics",
        "biotech breakthrough news",
        "David Sinclair",
        "Peter Attia medicine",
        "clinical trial results",
        "FDA approval new drug",
        "brain computer interface medical",
        "stem cell therapy breakthrough",
        "future of medicine",
        "synthetic biology therapeutic",
        "medical tourism treatment",
        "xenotransplantation pig organ",
    ]

    def __init__(self, api_key: Optional[str] = None, hours_back: int = 96):
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
        """Run all medicine search queries, deduplicate."""
        if not self.api_key:
            print("[YouTube] No API key — skipping YouTube search")
            return []

        print(f"[YouTube] Collecting frontier medicine signal (last {self.hours_back}h)...")
        all_results = []
        seen_ids = set()

        for query in self.MEDICINE_QUERIES:
            results = self.search(query, max_results=5)
            for item in results:
                if item["video_id"] not in seen_ids:
                    seen_ids.add(item["video_id"])
                    all_results.append(item)

        print(f"  [YouTube] Found {len(all_results)} unique videos")
        return all_results


# ============================================================
# KNOWLEDGE STUDIO COLLECTOR — Frontier Medicine
# ============================================================

class KnowledgeStudioCollector:
    """Pull recent frontier medicine content from Knowledge Studio database."""

    MEDICINE_KEYWORDS = [
        "medicine", "medical", "biotech", "biotechnology", "pharmaceutical",
        "clinical trial", "FDA", "gene therapy", "CRISPR", "mRNA",
        "cancer", "oncology", "immunotherapy", "CAR-T",
        "personalized medicine", "precision medicine", "genomics",
        "drug discovery", "drug design", "vaccine",
        "stem cell", "regenerative", "transplant",
        "brain computer interface", "neural", "neuralink",
        "synthetic biology", "bioengineering",
        "digital health", "digital therapeutics",
        "sinclair", "attia", "huberman",
        "regulation", "approval", "breakthrough therapy",
    ]

    def __init__(self, db_path: str, hours_back: int = 96):
        self.db_path = db_path
        self.hours_back = hours_back

    def collect(self) -> list[dict]:
        """Get recently processed medicine-related content from KS."""
        print(f"[KS] Collecting frontier medicine content (last {self.hours_back}h)...")
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
                summary_lower = (row["ai_summary"] or "").lower()[:500]
                text = f"{title_lower} {tags_lower} {summary_lower}"
                if any(kw in text for kw in self.MEDICINE_KEYWORDS):
                    results.append({
                        "source": "knowledge_studio",
                        "content_type": "video",
                        "title": row["title"] or "",
                        "channel": row["channel"] or "",
                        "summary_short": row["summary_15"] or "",
                        "url": row["video_url"] or "",
                        "processed_at": row["processing_date"] or "",
                    })

            # Get recent articles
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
                if any(kw in text for kw in self.MEDICINE_KEYWORDS):
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

        print(f"  [KS] Found {len(results)} medicine-related items")
        return results


# ============================================================
# CLINICALTRIALS.GOV COLLECTOR — Pipeline Tracker
# Free API, tracks every clinical trial in the US
# ============================================================

class ClinicalTrialsCollector:
    """Track notable clinical trials moving through the pipeline — the 'Lab to Fab' tracker."""

    BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

    # High-interest therapeutic areas
    SEARCH_QUERIES = [
        "CRISPR gene editing",
        "mRNA therapeutic",
        "CAR-T solid tumor",
        "xenotransplantation",
        "brain computer interface",
        "AI-designed drug",
        "personalized cancer vaccine",
        "gene therapy rare disease",
        "stem cell therapy",
        "digital therapeutic",
        "nanomedicine",
    ]

    def __init__(self, days_back: int = 14):
        self.days_back = days_back
        self.min_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Search ClinicalTrials.gov for recent studies."""
        try:
            params = {
                "query.term": query,
                "filter.advanced": f"AREA[LastUpdatePostDate]RANGE[{self.min_date},MAX]",
                "pageSize": max_results,
                "sort": "LastUpdatePostDate:desc",
                "fields": "NCTId,BriefTitle,OverallStatus,Phase,Condition,InterventionName,LastUpdatePostDate,LeadSponsorName",
                "format": "json",
            }
            resp = requests.get(self.BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            results = []
            for study in data.get("studies", []):
                protocol = study.get("protocolSection", {})
                id_module = protocol.get("identificationModule", {})
                status_module = protocol.get("statusModule", {})
                design_module = protocol.get("designModule", {})
                conditions_module = protocol.get("conditionsModule", {})
                interventions_module = protocol.get("armsInterventionsModule", {})
                sponsor_module = protocol.get("sponsorCollaboratorsModule", {})

                nct_id = id_module.get("nctId", "")
                phases = design_module.get("phases", [])
                conditions = conditions_module.get("conditions", [])
                interventions = []
                for arm in interventions_module.get("interventions", []):
                    interventions.append(arm.get("name", ""))

                lead_sponsor = sponsor_module.get("leadSponsor", {}).get("name", "")

                results.append({
                    "source": "clinicaltrials_gov",
                    "nct_id": nct_id,
                    "title": id_module.get("briefTitle", ""),
                    "status": status_module.get("overallStatus", ""),
                    "phase": ", ".join(phases) if phases else "N/A",
                    "conditions": ", ".join(conditions[:3]) if conditions else "",
                    "interventions": ", ".join(interventions[:3]) if interventions else "",
                    "sponsor": lead_sponsor,
                    "last_updated": status_module.get("lastUpdateSubmitDate", ""),
                    "url": f"https://clinicaltrials.gov/study/{nct_id}",
                    "query_matched": query,
                })
            return results
        except Exception as e:
            print(f"  [ClinicalTrials] Error searching '{query}': {e}")
            return []

    def collect(self) -> list[dict]:
        """Run all queries, deduplicate by NCT ID."""
        print(f"[ClinicalTrials.gov] Collecting pipeline activity (last {self.days_back} days)...")
        all_results = []
        seen_ids = set()

        for query in self.SEARCH_QUERIES:
            results = self.search(query, max_results=8)
            for item in results:
                if item["nct_id"] not in seen_ids:
                    seen_ids.add(item["nct_id"])
                    all_results.append(item)
            time.sleep(0.5)  # Be polite to the API

        print(f"  [ClinicalTrials.gov] Found {len(all_results)} unique studies")
        return all_results


# ============================================================
# MASTER COLLECTOR — Run all sources
# ============================================================

def collect_all(vertical: str = "future_medicine",
                hours_back: int = 48,
                db_path: str = None,
                youtube_api_key: str = None) -> dict:
    """
    Run all collectors for the Future of Medicine vertical.
    Returns a dict with items grouped by source.
    Most comprehensive vertical in the system.
    """
    print(f"\n{'='*60}")
    print(f"  FUTURE OF MEDICINE BRIEF — Collecting")
    print(f"  Window: last {hours_back} hours (research: 7-14 days)")
    print(f"  Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    results = {
        "vertical": vertical,
        "collected_at": datetime.utcnow().isoformat(),
        "hours_back": hours_back,
        "sources": {},
    }

    # Tier 0: Internal briefs (cross-vertical context)
    if db_path:
        internal = InternalBriefsCollector(db_path=db_path, days_back=4)
        results["sources"]["internal_briefs"] = internal.collect()

    # Tier 1: Research databases (7-day window)
    pubmed = PubMedCollector(days_back=7)
    results["sources"]["pubmed"] = pubmed.collect()

    biorxiv = BioRxivCollector(days_back=7)
    results["sources"]["biorxiv"] = biorxiv.collect()

    # Tier 1.5: Clinical trials pipeline (14-day window)
    ct = ClinicalTrialsCollector(days_back=14)
    results["sources"]["clinical_trials"] = ct.collect()

    # Tier 2: Curated aggregators (3-day window)
    rss = RSSAggregatorCollector(days_back=3)
    results["sources"]["rss_aggregators"] = rss.collect()

    # Tier 3: Community + creators
    hn = HNCollector(hours_back=72)
    results["sources"]["hacker_news"] = hn.collect()

    reddit = RedditCollector(hours_back=hours_back)
    results["sources"]["reddit"] = reddit.collect()

    if youtube_api_key:
        yt = YouTubeSearchCollector(api_key=youtube_api_key, hours_back=96)
        results["sources"]["youtube_search"] = yt.collect()

    # Tier 4: Internal knowledge base
    if db_path:
        ks = KnowledgeStudioCollector(db_path=db_path, hours_back=96)
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
        vertical="future_medicine",
        hours_back=48,
        db_path=DB_PATH,
        youtube_api_key=YT_API_KEY,
    )

    for source, items in data["sources"].items():
        print(f"\n--- TOP {source.upper()} ---")
        for item in items[:3]:
            print(f"  {item.get('title', '')[:80]}")
            print(f"  {item.get('url', '')[:80]}")

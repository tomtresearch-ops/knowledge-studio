"""
X/Twitter Collector for AI Agents Brief
Uses Playwright to scrape search results from X.
Logs in once, stores cookies for reuse.
Designed for once-daily runs — not aggressive scraping.
"""

import json
import os
import re
import time
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# Cookie storage location
COOKIE_PATH = os.path.join(os.path.dirname(__file__), ".x_cookies.json")


def _human_delay(min_s: float = 1.0, max_s: float = 3.0):
    """Random delay to mimic human browsing."""
    time.sleep(random.uniform(min_s, max_s))


def _save_cookies(context):
    """Save browser cookies to disk."""
    cookies = context.cookies()
    with open(COOKIE_PATH, "w") as f:
        json.dump(cookies, f)


def _load_cookies() -> list[dict] | None:
    """Load saved cookies if they exist and aren't too old."""
    if not os.path.exists(COOKIE_PATH):
        return None
    try:
        # If cookies are older than 7 days, re-login
        age = time.time() - os.path.getmtime(COOKIE_PATH)
        if age > 7 * 86400:
            return None
        with open(COOKIE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _extract_tweets(page) -> list[dict]:
    """Extract tweet data from the current page DOM."""
    tweets = []
    seen_texts = set()

    # X uses article elements for tweets
    articles = page.query_selector_all('article[data-testid="tweet"]')

    for article in articles:
        try:
            # Get tweet text
            text_el = article.query_selector('[data-testid="tweetText"]')
            text = text_el.inner_text().strip() if text_el else ""
            if not text or text in seen_texts:
                continue
            seen_texts.add(text)

            # Get author
            author = ""
            handle = ""
            user_links = article.query_selector_all('a[role="link"]')
            for link in user_links:
                href = link.get_attribute("href") or ""
                if href.startswith("/") and not href.startswith("/i/") and len(href.split("/")) == 2:
                    handle = href.lstrip("/")
                    # Try to get display name from nearby span
                    name_span = link.query_selector('span')
                    if name_span:
                        author = name_span.inner_text().strip()
                    break

            # Get timestamp
            time_el = article.query_selector('time')
            timestamp = ""
            tweet_url = ""
            if time_el:
                timestamp = time_el.get_attribute("datetime") or ""
                # The parent <a> of <time> usually contains the tweet URL
                parent_link = time_el.evaluate('el => el.closest("a")?.href || ""')
                if parent_link:
                    tweet_url = parent_link

            # Get engagement metrics (likes, retweets, replies)
            metrics = {}
            # Reply count
            reply_el = article.query_selector('[data-testid="reply"]')
            if reply_el:
                reply_text = reply_el.inner_text().strip()
                metrics["replies"] = _parse_metric(reply_text)

            # Retweet count
            rt_el = article.query_selector('[data-testid="retweet"]')
            if rt_el:
                rt_text = rt_el.inner_text().strip()
                metrics["retweets"] = _parse_metric(rt_text)

            # Like count
            like_el = article.query_selector('[data-testid="like"]')
            if like_el:
                like_text = like_el.inner_text().strip()
                metrics["likes"] = _parse_metric(like_text)

            # Extract any URLs from the tweet
            links = []
            link_els = article.query_selector_all('a[href*="http"]')
            for le in link_els:
                href = le.get_attribute("href") or ""
                # Skip X internal links
                if "x.com" in href or "twitter.com" in href or "t.co" in href:
                    # But check if it's a t.co redirect (external link)
                    if "t.co" in href:
                        link_text = le.inner_text().strip()
                        if link_text and not link_text.startswith("@"):
                            links.append(link_text)
                else:
                    links.append(href)

            tweets.append({
                "source": "x_twitter",
                "text": text[:500],
                "author": author,
                "handle": handle,
                "timestamp": timestamp,
                "url": tweet_url,
                "metrics": metrics,
                "signal_score": metrics.get("likes", 0) + (metrics.get("retweets", 0) * 2),
                "external_links": links[:3],
            })

        except Exception as e:
            continue

    return tweets


def _parse_metric(text: str) -> int:
    """Parse engagement metric text like '1.2K' -> 1200."""
    text = text.strip()
    if not text:
        return 0
    try:
        text = text.replace(",", "")
        if "K" in text.upper():
            return int(float(text.upper().replace("K", "")) * 1000)
        elif "M" in text.upper():
            return int(float(text.upper().replace("M", "")) * 1_000_000)
        return int(text)
    except (ValueError, TypeError):
        return 0


class XCollector:
    """Collect AI agent signal from X/Twitter via Playwright."""

    # Searches to run — hashtags, keywords, phrases
    SEARCHES = [
        "#AIAgents",
        "#AIAgent",
        "AI agent framework",
        "Claude Code agent",
        "MCP server",
    ]

    def __init__(self, username: str = "", password: str = "",
                 max_scrolls: int = 3, headless: bool = True):
        """
        Args:
            username: X username or email
            password: X password
            max_scrolls: How many times to scroll each search (more = more tweets, slower)
            headless: Run browser invisibly
        """
        self.username = username or os.getenv("X_USERNAME", "")
        self.password = password or os.getenv("X_PASSWORD", "")
        self.max_scrolls = max_scrolls
        self.headless = headless

    def _login(self, page, context):
        """Log in to X if needed."""
        page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=30000)
        _human_delay(2, 4)

        # Check if already logged in (via cookies)
        if "home" in page.url.lower() and page.query_selector('[data-testid="primaryColumn"]'):
            print("  [X] Already logged in via cookies")
            return True

        # Need to log in
        if not self.username or not self.password:
            print("  [X] No credentials — set X_USERNAME and X_PASSWORD in .env")
            return False

        print("  [X] Logging in...")
        page.goto("https://x.com/i/flow/login", wait_until="domcontentloaded", timeout=30000)
        _human_delay(2, 4)

        # Enter username
        username_input = page.wait_for_selector('input[autocomplete="username"]', timeout=15000)
        if not username_input:
            print("  [X] Could not find username input")
            return False
        username_input.fill(self.username)
        _human_delay(0.5, 1.0)

        # Click Next
        next_btn = page.query_selector('button:has-text("Next")')
        if next_btn:
            next_btn.click()
        else:
            username_input.press("Enter")
        _human_delay(1.5, 3.0)

        # Sometimes X asks for phone/email verification
        unusual_el = page.query_selector('input[data-testid="ocfEnterTextTextInput"]')
        if unusual_el:
            print("  [X] Unusual activity check — may need phone/email")
            # Try entering username again as verification
            unusual_el.fill(self.username)
            _human_delay(0.5, 1.0)
            verify_next = page.query_selector('button[data-testid="ocfEnterTextNextButton"]')
            if verify_next:
                verify_next.click()
            _human_delay(1.5, 3.0)

        # Enter password
        try:
            password_input = page.wait_for_selector('input[type="password"]', timeout=10000)
            if password_input:
                password_input.fill(self.password)
                _human_delay(0.5, 1.0)

                login_btn = page.query_selector('button[data-testid="LoginForm_Login_Button"]')
                if login_btn:
                    login_btn.click()
                else:
                    password_input.press("Enter")
                _human_delay(3, 5)
        except Exception as e:
            print(f"  [X] Password entry failed: {e}")
            return False

        # Verify login succeeded
        if "home" in page.url.lower():
            print("  [X] Login successful")
            _save_cookies(context)
            return True
        else:
            print(f"  [X] Login may have failed — URL: {page.url}")
            # Save cookies anyway in case it worked
            _save_cookies(context)
            return True  # Optimistic — search might still work

    def _search_and_collect(self, page, query: str) -> list[dict]:
        """Run a single search query and extract tweets."""
        import urllib.parse
        encoded = urllib.parse.quote(query)
        url = f"https://x.com/search?q={encoded}&src=typed_query&f=live"

        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        _human_delay(2, 4)

        # Scroll to load more tweets
        all_tweets = []
        for scroll_num in range(self.max_scrolls):
            new_tweets = _extract_tweets(page)
            for tweet in new_tweets:
                tweet["query_matched"] = query
            all_tweets.extend(new_tweets)

            # Scroll down
            page.evaluate("window.scrollBy(0, window.innerHeight * 2)")
            _human_delay(1.5, 3.0)

        return all_tweets

    def collect(self) -> list[dict]:
        """Run all searches and return deduplicated tweets."""
        from playwright.sync_api import sync_playwright

        print(f"[X] Collecting AI agent signal from X/Twitter...")

        all_tweets = []
        seen_texts = set()

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                )

                # Load saved cookies if available
                saved_cookies = _load_cookies()
                if saved_cookies:
                    context.add_cookies(saved_cookies)
                    print("  [X] Loaded saved cookies")

                page = context.new_page()

                # Login
                if not self._login(page, context):
                    browser.close()
                    return []

                # Run each search
                for query in self.SEARCHES:
                    print(f"  [X] Searching: {query}")
                    try:
                        tweets = self._search_and_collect(page, query)
                        for tweet in tweets:
                            # Deduplicate by text content
                            text_key = tweet["text"][:100]
                            if text_key not in seen_texts:
                                seen_texts.add(text_key)
                                all_tweets.append(tweet)
                        print(f"    Found {len(tweets)} tweets")
                        _human_delay(2, 4)  # Pause between searches
                    except Exception as e:
                        print(f"    Error: {e}")
                        continue

                # Save cookies for next time
                _save_cookies(context)
                browser.close()

        except Exception as e:
            print(f"  [X] Browser error: {e}")
            return []

        # Sort by engagement
        all_tweets.sort(key=lambda x: x.get("signal_score", 0), reverse=True)
        print(f"  [X] Found {len(all_tweets)} unique tweets total")
        return all_tweets


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

    collector = XCollector(headless=False)  # Visible for testing
    tweets = collector.collect()

    print(f"\n--- TOP TWEETS ({len(tweets)} total) ---")
    for tweet in tweets[:15]:
        score = tweet.get("signal_score", 0)
        handle = tweet.get("handle", "?")
        text = tweet["text"][:100].replace("\n", " ")
        print(f"  [{score}] @{handle}: {text}")
        if tweet.get("external_links"):
            print(f"    Links: {tweet['external_links']}")
        print()

"""
Newsletter Auto-Subscriber Agent

Playwright-based agent that automatically subscribes a Kill the Newsletter email
to a newsletter's signup form, handling URL discovery, form submission, and
double opt-in confirmation.
"""

import os
import re
import time
import traceback

import anthropic
import claude_cli_client  # routes inference to the subscription (see module docstring)
import feedparser
import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY")


class NewsletterAutoSubscriber:
    """Orchestrates auto-subscribing a KtN email to a newsletter."""

    def __init__(self, db_service):
        self.db = db_service
        self.client = claude_cli_client.make_client(api_key=CLAUDE_API_KEY)

    def _update_status(self, sub_id, status, message, **extra):
        """Update subscription status in DB."""
        self.db.update_newsletter_subscription(
            sub_id,
            auto_subscribe_status=status,
            auto_subscribe_message=message,
            **extra
        )

    def auto_subscribe(self, subscription_id, manual_signup_url=None):
        """Main entry point. Runs the full auto-subscribe flow."""
        if not PLAYWRIGHT_AVAILABLE:
            self._update_status(subscription_id, 'failed',
                                'Playwright not installed. Run: pip install playwright && python -m playwright install chromium')
            return

        sub = self.db.get_newsletter_subscription(subscription_id)
        if not sub:
            return
        if not sub.get('ktn_email'):
            self._update_status(subscription_id, 'failed', 'No KtN email address on this subscription')
            return

        ktn_email = sub['ktn_email']
        newsletter_name = sub.get('newsletter_name', '')
        website_url = sub.get('website_url')
        feed_url = sub.get('feed_url')

        self._update_status(subscription_id, 'running', 'Finding signup page...')

        # Step 1: Find the signup URL
        signup_url = manual_signup_url or sub.get('signup_url')
        if not signup_url:
            signup_url = self._find_signup_url(newsletter_name, website_url)

        if not signup_url:
            self._update_status(subscription_id, 'failed',
                                'Could not find signup page. Paste the signup URL manually.')
            return

        self._update_status(subscription_id, 'running', f'Subscribing at {signup_url}...',
                            signup_url=signup_url)

        # Step 2: Submit the signup form
        result = self._submit_signup_form(signup_url, ktn_email)
        if not result['success']:
            self._update_status(subscription_id, 'failed', result['message'], signup_url=signup_url)
            return

        self._update_status(subscription_id, 'subscribed',
                            'Subscribed. Checking for confirmation email...',
                            signup_url=signup_url)

        # Step 3: Check for and handle confirmation
        if feed_url:
            confirmed = self._check_and_confirm(feed_url, subscription_id)
            if confirmed:
                self._update_status(subscription_id, 'confirmed',
                                    'Subscribed and confirmed.',
                                    signup_url=signup_url)
                return

        # No confirmation needed or couldn't confirm — still subscribed
        current = self.db.get_newsletter_subscription(subscription_id)
        if current and current.get('auto_subscribe_status') == 'subscribed':
            self._update_status(subscription_id, 'subscribed',
                                'Subscribed. No confirmation email detected (may not require double opt-in).',
                                signup_url=signup_url)

    def _find_signup_url(self, newsletter_name, website_url):
        """Try multiple strategies to find the newsletter signup URL."""
        # Strategy 1: Derive from website URL
        if website_url:
            derived = self._derive_signup_url(website_url)
            if derived and self._url_loads(derived):
                return derived

        # Strategy 2: Ask Claude
        url = self._ask_claude_for_url(newsletter_name, website_url)
        if url and self._url_loads(url):
            return url

        # Strategy 3: Claude retry with more context
        url = self._ask_claude_retry(newsletter_name, website_url)
        if url and self._url_loads(url):
            return url

        # Strategy 4: Slug-based guessing
        slug = re.sub(r'[^a-z0-9]', '', newsletter_name.lower().replace(' ', ''))
        slug_dash = re.sub(r'[^a-z0-9-]', '', newsletter_name.lower().replace(' ', '-'))
        patterns = [
            f'https://{slug_dash}.substack.com/subscribe',
            f'https://{slug_dash}.substack.com',
            f'https://{slug_dash}.beehiiv.com/subscribe',
            f'https://{slug_dash}.beehiiv.com',
            f'https://www.{slug_dash}.com',
            f'https://{slug_dash}.com',
        ]
        for p in patterns:
            if self._url_loads(p):
                return p

        return None

    def _derive_signup_url(self, website_url):
        """Derive signup URL from known platform patterns."""
        url = website_url.rstrip('/')
        if 'substack.com' in url:
            return url.split('?')[0].rstrip('/') + '/subscribe'
        if 'beehiiv.com' in url:
            return url.split('?')[0].rstrip('/') + '/subscribe'
        if 'ghost' in url.lower():
            return url.split('?')[0].rstrip('/') + '/#/portal/signup'
        # Generic — just return the site root, signup forms are often on homepage
        return url

    def _ask_claude_for_url(self, name, website_url=None):
        """Ask Claude Haiku for the newsletter signup URL."""
        try:
            extra = f" Their website might be {website_url}." if website_url else ""
            resp = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"What is the newsletter signup URL for '{name}'?{extra} "
                               f"Return ONLY the URL, nothing else. If you're not sure, give your best guess."
                }]
            )
            text = resp.content[0].text.strip()
            # Extract URL from response
            match = re.search(r'https?://[^\s<>"\']+', text)
            return match.group(0) if match else None
        except Exception as e:
            print(f"⚠️ Claude URL lookup failed: {e}")
            return None

    def _ask_claude_retry(self, name, website_url=None):
        """Second attempt with more context after first guess failed."""
        try:
            extra = f" Website: {website_url}." if website_url else ""
            resp = self.client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": f"I'm looking for the newsletter signup page for '{name}'.{extra} "
                               f"The obvious URL didn't work. Try alternative names, spellings, or platforms "
                               f"(Substack, Beehiiv, ConvertKit, Mailchimp, Ghost, personal site). "
                               f"Return ONLY the URL."
                }]
            )
            text = resp.content[0].text.strip()
            match = re.search(r'https?://[^\s<>"\']+', text)
            return match.group(0) if match else None
        except Exception:
            return None

    def _url_loads(self, url):
        """Quick check if a URL returns a 2xx/3xx response."""
        try:
            resp = requests.head(url, timeout=8, allow_redirects=True,
                                 headers={'User-Agent': 'Mozilla/5.0'})
            return resp.status_code < 400
        except Exception:
            return False

    def _submit_signup_form(self, signup_url, email):
        """Use Playwright to find and submit the email signup form."""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                               'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                page = context.new_page()
                page.set_default_timeout(15000)

                try:
                    page.goto(signup_url, wait_until='domcontentloaded', timeout=20000)
                except PlaywrightTimeout:
                    browser.close()
                    return {'success': False, 'message': f'Page timed out loading: {signup_url}'}

                # Wait for page to settle
                page.wait_for_timeout(2000)

                # Dismiss cookie banners
                self._dismiss_overlays(page)

                # Find email input
                email_input = self._find_email_input(page)
                if not email_input:
                    browser.close()
                    return {'success': False,
                            'message': 'No email input field found on page. Try a different signup URL.'}

                # Fill and submit
                email_input.fill(email)
                page.wait_for_timeout(500)

                submitted = self._submit_form(page, email_input)
                if not submitted:
                    browser.close()
                    return {'success': False, 'message': 'Could not find submit button.'}

                # Wait for response
                page.wait_for_timeout(3000)

                # Check for CAPTCHA widgets (look for actual elements, not just text in scripts)
                captcha_selectors = [
                    '.cf-turnstile', '#cf-turnstile',           # Cloudflare Turnstile
                    '.g-recaptcha', '#g-recaptcha',             # reCAPTCHA
                    '.h-captcha', '#h-captcha',                 # hCaptcha
                    'iframe[src*="recaptcha"]',
                    'iframe[src*="hcaptcha"]',
                    'iframe[src*="turnstile"]',
                ]
                for sel in captcha_selectors:
                    if page.query_selector(sel):
                        browser.close()
                        return {'success': False,
                                'message': 'CAPTCHA detected. Subscribe manually or try a different URL.'}

                error_patterns = ['invalid email', 'enter a valid', 'please enter', 'error']
                body_text = page.inner_text('body').lower()
                # Only flag errors if they appear prominently (not just in footer/nav)
                for pattern in error_patterns:
                    if pattern in body_text[:2000]:
                        # Check it's not a pre-existing error message
                        if 'thank' not in body_text[:2000] and 'check your' not in body_text[:2000]:
                            pass  # Could be error, but don't fail — many sites show form + error text pre-submit

                # Check for success indicators
                success_indicators = ['check your email', 'thank you', 'thanks for subscribing',
                                      'confirm your', 'subscribed', 'almost done', 'one more step',
                                      'verify your', 'welcome']
                for indicator in success_indicators:
                    if indicator in body_text:
                        browser.close()
                        return {'success': True, 'message': f'Form submitted. Detected: "{indicator}"'}

                # No clear success/failure — assume it worked (form submitted without error)
                browser.close()
                return {'success': True, 'message': 'Form submitted (no explicit confirmation detected).'}

        except Exception as e:
            return {'success': False, 'message': f'Browser error: {str(e)}'}

    def _dismiss_overlays(self, page):
        """Try to dismiss cookie banners and popups."""
        dismiss_selectors = [
            'button:has-text("Accept")',
            'button:has-text("Got it")',
            'button:has-text("OK")',
            'button:has-text("Close")',
            'button:has-text("Dismiss")',
            '[class*="cookie"] button',
            '[id*="cookie"] button',
            '[class*="consent"] button',
            '[class*="banner"] button:has-text("Accept")',
        ]
        for selector in dismiss_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=500):
                    btn.click(timeout=1000)
                    page.wait_for_timeout(500)
                    break
            except Exception:
                continue

    def _find_email_input(self, page):
        """Find email input using cascade of selectors."""
        selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[name="EMAIL"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="Email"]',
            'input[aria-label*="email" i]',
            'input[id*="email" i]',
            'input[class*="email" i]',
            'input[name="subscribe-email"]',
        ]
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible(timeout=1000):
                    return el
            except Exception:
                continue

        # Last resort: look for any visible text input near "subscribe" text
        try:
            inputs = page.locator('input[type="text"]').all()
            for inp in inputs:
                try:
                    if inp.is_visible(timeout=500):
                        parent_text = page.evaluate(
                            '(el) => el.closest("form")?.innerText || ""', inp.element_handle()
                        ).lower()
                        if any(w in parent_text for w in ['subscribe', 'newsletter', 'email', 'sign up']):
                            return inp
                except Exception:
                    continue
        except Exception:
            pass

        return None

    def _submit_form(self, page, email_input):
        """Submit the form containing the email input."""
        # Try clicking a submit button near the input
        submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Subscribe")',
            'button:has-text("Sign up")',
            'button:has-text("Sign Up")',
            'button:has-text("Get")',
            'button:has-text("Join")',
            'button:has-text("Submit")',
            '[class*="subscribe" i] button',
            'form button',
        ]

        # Try to find submit within the same form
        try:
            form = page.evaluate(
                '(el) => { const f = el.closest("form"); return f ? true : false; }',
                email_input.element_handle()
            )
            if form:
                for sel in submit_selectors:
                    try:
                        # Scope to the form containing our input
                        form_sel = page.evaluate(
                            '(el) => { const f = el.closest("form"); if(f) { f.dataset._autoSubForm = "1"; return true; } return false; }',
                            email_input.element_handle()
                        )
                        if form_sel:
                            btn = page.locator(f'form[data-_auto-sub-form="1"] {sel}, form {sel}').first
                            if btn.is_visible(timeout=500):
                                btn.click(timeout=3000)
                                return True
                    except Exception:
                        continue
        except Exception:
            pass

        # Fallback: any visible submit button on page
        for sel in submit_selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=500):
                    btn.click(timeout=3000)
                    return True
            except Exception:
                continue

        # Last resort: press Enter on the email input
        try:
            email_input.press('Enter')
            return True
        except Exception:
            return False

    def _check_and_confirm(self, feed_url, subscription_id):
        """Poll KtN feed for confirmation email, extract and click confirm link."""
        print(f"🔍 Polling KtN feed for confirmation email...")

        # Get baseline entries
        try:
            baseline_feed = feedparser.parse(feed_url)
            baseline_ids = {e.get('id', e.get('link', '')) for e in baseline_feed.entries}
        except Exception:
            baseline_ids = set()

        # Poll for new entries
        for attempt in range(9):  # 9 attempts × 10s = 90s
            time.sleep(10)
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries:
                    entry_id = entry.get('id', entry.get('link', ''))
                    if entry_id in baseline_ids:
                        continue

                    # New entry — check if it's a confirmation email
                    title = (entry.get('title') or '').lower()
                    content = entry.get('summary') or entry.get('description') or ''
                    content_lower = content.lower()

                    confirm_keywords = ['confirm', 'verify', 'activate', 'opt-in', 'double opt']
                    if any(kw in title or kw in content_lower for kw in confirm_keywords):
                        # Extract confirmation link
                        confirm_url = self._extract_confirm_link(content)
                        if confirm_url:
                            print(f"✅ Found confirmation link: {confirm_url[:80]}...")
                            self._update_status(subscription_id, 'running', 'Clicking confirmation link...')
                            success = self._click_confirm(confirm_url)
                            if success:
                                return True

                    # Even if not a "confirm" email, any new entry means subscription worked
                    # But keep polling for actual confirmation if there is one

            except Exception as e:
                print(f"⚠️ Feed poll error: {e}")
                continue

        return False

    def _extract_confirm_link(self, html_content):
        """Extract confirmation URL from email HTML."""
        soup = BeautifulSoup(html_content, 'html.parser')

        # Look for links with confirmation-related text
        for a in soup.find_all('a', href=True):
            href = a['href']
            link_text = a.get_text().lower()
            href_lower = href.lower()
            if any(kw in link_text or kw in href_lower
                   for kw in ['confirm', 'verify', 'activate', 'yes', 'opt-in']):
                return href

        # Fallback: look for any link that looks like a confirmation URL
        for a in soup.find_all('a', href=True):
            href = a['href']
            if any(kw in href.lower() for kw in ['confirm', 'verify', 'token=', 'activate', 'opt']):
                return href

        # Last resort: regex for URLs with confirm patterns in raw content
        matches = re.findall(r'https?://[^\s<>"\']+(?:confirm|verify|activate|token)[^\s<>"\']*', html_content, re.I)
        return matches[0] if matches else None

    def _click_confirm(self, confirm_url):
        """Click the confirmation link."""
        # Try simple GET first (works for most)
        try:
            resp = requests.get(confirm_url, timeout=15, allow_redirects=True,
                                headers={'User-Agent': 'Mozilla/5.0'})
            if resp.status_code < 400:
                print(f"✅ Confirmation link clicked (HTTP {resp.status_code})")
                return True
        except Exception:
            pass

        # Fallback: use Playwright if GET didn't work (some need JS)
        if PLAYWRIGHT_AVAILABLE:
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(confirm_url, wait_until='domcontentloaded', timeout=15000)
                    page.wait_for_timeout(3000)
                    browser.close()
                    print(f"✅ Confirmation link clicked via browser")
                    return True
            except Exception as e:
                print(f"⚠️ Browser confirm failed: {e}")

        return False

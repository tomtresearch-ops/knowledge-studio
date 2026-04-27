"""
Website Auditor — Lightweight site analysis for AI consulting prospects.
Uses requests + BeautifulSoup (no browser needed).

Checks: SSL, contact form, chatbot, scheduling, blog, social links, mobile viewport.
Produces a 0-100 "digital maturity" score — LOWER score = BETTER prospect (more room for AI).

Usage:
    from website_auditor import WebsiteAuditor
    auditor = WebsiteAuditor()
    result = auditor.audit_website("https://example.com")
    # result = {"score": 35, "has_ssl": True, "has_chatbot": False, ...}

    # Batch audit all prospects:
    auditor.audit_all_prospects(max_concurrent=5, limit=100)
"""

import os
import re
import sqlite3
import requests
import time
from datetime import datetime
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise ImportError("pip3 install beautifulsoup4")

DB_PATH = os.path.join(os.path.dirname(__file__), "youtube_intelligence.db")

# Common chatbot/live chat providers — look for these in script src or page content
CHATBOT_SIGNATURES = [
    'tawk.to', 'livechat', 'drift.com', 'intercom.io', 'intercom-',
    'crisp.chat', 'zendesk', 'freshdesk', 'hubspot', 'liveperson',
    'tidio', 'olark', 'chatra', 'smartsupp', 'jivochat',
    'podium', 'birdeye', 'webchat', 'chatwidget',
]

# Scheduling/booking platforms
SCHEDULING_SIGNATURES = [
    'calendly.com', 'acuityscheduling', 'squareup.com/appointments',
    'schedulicity', 'booksy', 'vagaro', 'mindbodyonline', 'mindbody',
    'setmore', 'appointy', 'timely', 'booker.com', 'fresha.com',
    'housecallpro', 'jobber', 'servicetitan', 'schedule-now',
    'online-booking', 'book-now', 'book-online', 'schedule-appointment',
    'request-appointment', 'booknow', 'bookappointment',
]

# Social media domains
SOCIAL_DOMAINS = [
    'facebook.com', 'instagram.com', 'twitter.com', 'x.com',
    'linkedin.com', 'youtube.com', 'tiktok.com', 'yelp.com',
    'nextdoor.com', 'pinterest.com',
]

# CMS detection
CMS_SIGNATURES = {
    'wordpress': ['wp-content', 'wp-includes', 'wordpress'],
    'wix': ['wix.com', 'wixsite', 'parastorage.com'],
    'squarespace': ['squarespace.com', 'sqsp.net', 'squarespace-cdn'],
    'godaddy': ['godaddy.com', 'secureserver.net', 'godaddysites'],
    'weebly': ['weebly.com'],
    'shopify': ['shopify.com', 'cdn.shopify'],
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


class WebsiteAuditor:

    def __init__(self, db_path=None, timeout=10):
        self.db_path = db_path or DB_PATH
        self.timeout = timeout

    def _get_db(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    def _normalize_url(self, url):
        """Ensure URL has scheme and is clean."""
        if not url:
            return None
        url = url.strip().rstrip('/')
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        return url

    def _fetch_page(self, url):
        """Fetch a page, following redirects. Returns (final_url, html, is_ssl)."""
        # Try HTTPS first
        https_url = url.replace('http://', 'https://')
        try:
            resp = requests.get(https_url, headers=HEADERS, timeout=self.timeout,
                              allow_redirects=True, verify=True)
            resp.raise_for_status()
            return resp.url, resp.text, True
        except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
            pass
        except requests.exceptions.HTTPError:
            pass
        except requests.exceptions.Timeout:
            pass

        # Fall back to HTTP
        http_url = url.replace('https://', 'http://')
        try:
            resp = requests.get(http_url, headers=HEADERS, timeout=self.timeout,
                              allow_redirects=True, verify=False)
            resp.raise_for_status()
            is_ssl = resp.url.startswith('https://')
            return resp.url, resp.text, is_ssl
        except Exception:
            return None, None, False

    def audit_website(self, url):
        """
        Audit a single website. Returns dict with all findings.
        Score is 0-100 "digital maturity" — higher = more sophisticated.
        For prospecting: LOW score = better prospect (more room for AI services).
        """
        url = self._normalize_url(url)
        if not url:
            return None

        result = {
            'url': url,
            'has_ssl': False,
            'has_contact_form': False,
            'has_chatbot': False,
            'has_scheduling': False,
            'has_blog': False,
            'has_social': False,
            'mobile_friendly': False,
            'cms': None,
            'social_platforms': [],
            'chatbot_provider': None,
            'scheduling_provider': None,
            'page_title': None,
            'email_found': None,
            'phone_found': None,
            'score': 0,
            'notes': [],
            'error': None,
        }

        # Fetch homepage
        final_url, html, is_ssl = self._fetch_page(url)
        if not html:
            result['error'] = 'Could not reach website'
            result['notes'].append('Site unreachable')
            return result

        result['has_ssl'] = is_ssl
        result['url'] = final_url

        soup = BeautifulSoup(html, 'html.parser')
        html_lower = html.lower()

        # Page title
        title_tag = soup.find('title')
        if title_tag:
            result['page_title'] = title_tag.get_text(strip=True)[:200]

        # --- Mobile friendly (viewport meta tag) ---
        viewport = soup.find('meta', attrs={'name': 'viewport'})
        if viewport:
            result['mobile_friendly'] = True

        # --- Contact form ---
        forms = soup.find_all('form')
        for form in forms:
            form_html = str(form).lower()
            # Look for email/message fields in forms (not search forms)
            if any(kw in form_html for kw in ['email', 'message', 'contact', 'inquiry', 'quote', 'estimate']):
                result['has_contact_form'] = True
                break
            # Check for textarea (usually contact/message forms)
            if form.find('textarea'):
                result['has_contact_form'] = True
                break

        # --- Chatbot detection ---
        scripts = soup.find_all('script', src=True)
        all_script_srcs = ' '.join(s.get('src', '').lower() for s in scripts)
        inline_scripts = ' '.join(s.get_text().lower() for s in soup.find_all('script') if not s.get('src'))

        for sig in CHATBOT_SIGNATURES:
            if sig in all_script_srcs or sig in html_lower or sig in inline_scripts:
                result['has_chatbot'] = True
                result['chatbot_provider'] = sig.split('.')[0].split('-')[0]
                break

        # --- Scheduling / booking detection ---
        all_links = ' '.join(a.get('href', '').lower() for a in soup.find_all('a', href=True))
        all_iframes = ' '.join(iframe.get('src', '').lower() for iframe in soup.find_all('iframe'))
        combined_text = all_links + ' ' + all_iframes + ' ' + all_script_srcs + ' ' + html_lower

        for sig in SCHEDULING_SIGNATURES:
            if sig in combined_text:
                result['has_scheduling'] = True
                result['scheduling_provider'] = sig.split('.')[0].split('/')[0]
                break

        # Also check button/link text for booking keywords
        if not result['has_scheduling']:
            link_texts = ' '.join(a.get_text(strip=True).lower() for a in soup.find_all('a'))
            button_texts = ' '.join(b.get_text(strip=True).lower() for b in soup.find_all('button'))
            all_cta_text = link_texts + ' ' + button_texts
            booking_phrases = ['book online', 'book now', 'schedule now', 'schedule appointment',
                             'request appointment', 'book appointment', 'online booking',
                             'schedule a call', 'free estimate', 'get a quote online']
            for phrase in booking_phrases:
                if phrase in all_cta_text:
                    result['has_scheduling'] = True
                    result['scheduling_provider'] = 'custom'
                    break

        # --- Blog detection ---
        blog_patterns = ['/blog', '/news', '/articles', '/resources', '/insights', '/tips']
        for a in soup.find_all('a', href=True):
            href = a.get('href', '').lower()
            if any(p in href for p in blog_patterns):
                result['has_blog'] = True
                break

        # --- Social media links ---
        found_socials = set()
        for a in soup.find_all('a', href=True):
            href = a.get('href', '').lower()
            for domain in SOCIAL_DOMAINS:
                if domain in href:
                    found_socials.add(domain.split('.')[0])
        result['social_platforms'] = sorted(found_socials)
        result['has_social'] = len(found_socials) > 0

        # --- CMS detection ---
        for cms_name, signatures in CMS_SIGNATURES.items():
            for sig in signatures:
                if sig in html_lower:
                    result['cms'] = cms_name
                    break
            if result['cms']:
                break

        # --- Email extraction ---
        email_pattern = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
        emails = email_pattern.findall(html)
        # Filter out common non-business emails
        junk = {'example.com', 'sentry.io', 'wixpress.com', 'wordpress.org', 'w3.org', 'schema.org', 'gravatar.com'}
        real_emails = [e for e in emails if not any(j in e.lower() for j in junk)]
        if real_emails:
            result['email_found'] = real_emails[0]

        # --- Phone extraction from page ---
        phone_pattern = re.compile(r'[\(]?\d{3}[\)]?[\s\-\.]?\d{3}[\s\-\.]?\d{4}')
        phones = phone_pattern.findall(soup.get_text())
        if phones:
            result['phone_found'] = phones[0]

        # --- Compute digital maturity score (0-100) ---
        score = 0
        notes = []

        if is_ssl:
            score += 10
        else:
            notes.append('No SSL')

        if result['mobile_friendly']:
            score += 10
        else:
            notes.append('Not mobile-optimized')

        if result['has_contact_form']:
            score += 15
        else:
            notes.append('No contact form')

        if result['has_chatbot']:
            score += 20
            notes.append(f'Has chatbot ({result["chatbot_provider"]})')
        else:
            notes.append('No chatbot/live chat')

        if result['has_scheduling']:
            score += 20
            notes.append(f'Has online scheduling ({result["scheduling_provider"]})')
        else:
            notes.append('No online scheduling')

        if result['has_blog']:
            score += 10
        else:
            notes.append('No blog/content')

        if result['has_social']:
            score += 5
            if len(found_socials) >= 3:
                score += 5
        else:
            notes.append('No social media links')

        # CMS bonus — modern CMS = some digital sophistication
        if result['cms'] in ('squarespace', 'shopify'):
            score += 5
        elif result['cms'] == 'wordpress':
            score += 3

        result['score'] = min(100, score)
        result['notes'] = notes
        return result

    def audit_prospect(self, prospect_id):
        """Audit a single prospect by ID. Updates DB directly."""
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT id, website, business_name FROM consulting_prospects WHERE id = ?', (prospect_id,))
        row = cursor.fetchone()
        if not row or not row['website']:
            conn.close()
            return None

        result = self.audit_website(row['website'])
        if not result:
            conn.close()
            return None

        self._save_audit(cursor, row['id'], result)
        conn.commit()
        conn.close()
        return result

    def _save_audit(self, cursor, prospect_id, result):
        """Save audit results to DB."""
        notes_str = '; '.join(result.get('notes', []))
        if result.get('email_found'):
            notes_str += f" | Email: {result['email_found']}"
        if result.get('cms'):
            notes_str += f" | CMS: {result['cms']}"

        cursor.execute('''
            UPDATE consulting_prospects SET
                website_audit_score = ?,
                website_has_ssl = ?,
                website_has_scheduling = ?,
                website_has_chatbot = ?,
                website_has_contact_form = ?,
                website_has_blog = ?,
                website_has_social = ?,
                website_mobile_friendly = ?,
                website_audit_notes = ?,
                website_audit_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (
            result['score'],
            1 if result['has_ssl'] else 0,
            1 if result['has_scheduling'] else 0,
            1 if result['has_chatbot'] else 0,
            1 if result['has_contact_form'] else 0,
            1 if result['has_blog'] else 0,
            1 if result['has_social'] else 0,
            1 if result['mobile_friendly'] else 0,
            notes_str[:500],
            datetime.now().strftime('%Y-%m-%d'),
            prospect_id,
        ))

        # Also save email if we found one and prospect doesn't have one
        if result.get('email_found'):
            cursor.execute('''
                UPDATE consulting_prospects SET email = ?
                WHERE id = ? AND (email IS NULL OR email = '')
            ''', (result['email_found'], prospect_id))

    def audit_all_prospects(self, max_concurrent=5, limit=None, vertical_id=None, tier=None, force=False):
        """
        Audit all prospects with websites. Uses thread pool for speed.
        - force: re-audit even if already audited
        - limit: max number to audit
        - vertical_id/tier: filter to specific segments
        """
        conn = self._get_db()
        cursor = conn.cursor()

        query = "SELECT id, website, business_name FROM consulting_prospects WHERE website IS NOT NULL AND length(website) > 0"
        params = []

        if not force:
            query += " AND (website_audit_date IS NULL OR website_audit_date = '')"
        if vertical_id:
            query += " AND vertical_id = ?"
            params.append(vertical_id)
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        prospects = [dict(row) for row in cursor.fetchall()]
        conn.close()

        total = len(prospects)
        if total == 0:
            return {"audited": 0, "errors": 0, "message": "No prospects to audit"}

        print(f"Auditing {total} websites (concurrency: {max_concurrent})...")

        audited = 0
        errors = 0
        results_summary = {
            'no_ssl': 0, 'no_chatbot': 0, 'no_scheduling': 0,
            'no_contact_form': 0, 'no_blog': 0, 'emails_found': 0,
        }

        def _audit_one(prospect):
            try:
                result = self.audit_website(prospect['website'])
                if result and not result.get('error'):
                    return (prospect['id'], prospect['business_name'], result)
                else:
                    return (prospect['id'], prospect['business_name'], None)
            except Exception as e:
                return (prospect['id'], prospect['business_name'], None)

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {executor.submit(_audit_one, p): p for p in prospects}

            for future in as_completed(futures):
                pid, name, result = future.result()
                if result:
                    # Save to DB
                    conn = self._get_db()
                    cursor = conn.cursor()
                    self._save_audit(cursor, pid, result)
                    conn.commit()
                    conn.close()
                    audited += 1

                    # Track stats
                    if not result['has_ssl']:
                        results_summary['no_ssl'] += 1
                    if not result['has_chatbot']:
                        results_summary['no_chatbot'] += 1
                    if not result['has_scheduling']:
                        results_summary['no_scheduling'] += 1
                    if not result['has_contact_form']:
                        results_summary['no_contact_form'] += 1
                    if not result['has_blog']:
                        results_summary['no_blog'] += 1
                    if result.get('email_found'):
                        results_summary['emails_found'] += 1

                    if audited % 25 == 0:
                        print(f"  ...{audited}/{total} audited")
                else:
                    errors += 1

        print(f"\nAudit complete: {audited} audited, {errors} errors")
        print(f"  No SSL: {results_summary['no_ssl']}")
        print(f"  No chatbot: {results_summary['no_chatbot']}")
        print(f"  No scheduling: {results_summary['no_scheduling']}")
        print(f"  No contact form: {results_summary['no_contact_form']}")
        print(f"  No blog: {results_summary['no_blog']}")
        print(f"  Emails extracted: {results_summary['emails_found']}")

        return {
            "audited": audited,
            "errors": errors,
            "summary": results_summary,
        }


    def monitor_competitors(self, max_concurrent=5, limit=None):
        """
        Re-audit prospects and detect changes. When a business GAINS a feature
        (chatbot, scheduling, etc.), generate alerts for competitors in the
        same vertical + city who DON'T have that feature yet.

        Returns: dict with counts of re-audited, changes detected, alerts generated.
        """
        conn = self._get_db()
        cursor = conn.cursor()

        # Get prospects that have been audited before (re-audit candidates)
        query = """
            SELECT id, website, business_name, vertical_id, vertical_name, city,
                   website_has_chatbot, website_has_scheduling, website_has_contact_form,
                   website_has_blog, website_audit_score
            FROM consulting_prospects
            WHERE website IS NOT NULL AND length(website) > 0
              AND website_audit_date IS NOT NULL
        """
        params = []
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        prospects = [dict(row) for row in cursor.fetchall()]
        conn.close()

        total = len(prospects)
        if total == 0:
            return {"re_audited": 0, "changes": 0, "alerts": 0}

        print(f"Re-auditing {total} prospects for competitor monitoring...")

        re_audited = 0
        changes_detected = 0
        alerts_generated = 0
        change_log = []  # Track what changed for alert generation

        def _reaudit_one(prospect):
            try:
                result = self.audit_website(prospect['website'])
                if result and not result.get('error'):
                    return (prospect, result)
                return (prospect, None)
            except Exception:
                return (prospect, None)

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            futures = {executor.submit(_reaudit_one, p): p for p in prospects}

            for future in as_completed(futures):
                old_data, new_result = future.result()
                if not new_result:
                    continue

                re_audited += 1

                # Detect what CHANGED (specifically what was GAINED)
                gained = []
                if not old_data['website_has_chatbot'] and new_result['has_chatbot']:
                    gained.append(('chatbot', new_result.get('chatbot_provider', 'unknown')))
                if not old_data['website_has_scheduling'] and new_result['has_scheduling']:
                    gained.append(('scheduling', new_result.get('scheduling_provider', 'unknown')))
                if not old_data['website_has_contact_form'] and new_result['has_contact_form']:
                    gained.append('contact_form')
                if not old_data.get('website_has_blog', 0) and new_result['has_blog']:
                    gained.append('blog')

                if gained:
                    changes_detected += 1
                    change_log.append({
                        'prospect_id': old_data['id'],
                        'business_name': old_data['business_name'],
                        'vertical_id': old_data['vertical_id'],
                        'vertical_name': old_data['vertical_name'],
                        'city': old_data.get('city', ''),
                        'gained': gained,
                    })

                # Save updated audit + history snapshot
                conn = self._get_db()
                cur = conn.cursor()
                self._save_audit(cur, old_data['id'], new_result)

                # Save history row
                cur.execute('''
                    INSERT INTO consulting_audit_history
                    (prospect_id, audit_date, has_chatbot, has_scheduling, has_contact_form,
                     has_blog, has_ssl, mobile_friendly, audit_score, chatbot_provider, scheduling_provider)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    old_data['id'],
                    datetime.now().strftime('%Y-%m-%d'),
                    1 if new_result['has_chatbot'] else 0,
                    1 if new_result['has_scheduling'] else 0,
                    1 if new_result['has_contact_form'] else 0,
                    1 if new_result['has_blog'] else 0,
                    1 if new_result['has_ssl'] else 0,
                    1 if new_result['mobile_friendly'] else 0,
                    new_result['score'],
                    new_result.get('chatbot_provider'),
                    new_result.get('scheduling_provider'),
                ))
                conn.commit()
                conn.close()

                if re_audited % 50 == 0:
                    print(f"  ...{re_audited}/{total} re-audited, {changes_detected} changes found")

        # Now generate competitor alerts from changes
        if change_log:
            print(f"\nGenerating competitor alerts from {len(change_log)} changes...")
            conn = self._get_db()
            cur = conn.cursor()

            for change in change_log:
                for gained_item in change['gained']:
                    # Figure out feature name and column
                    if isinstance(gained_item, tuple):
                        feature, provider = gained_item
                    else:
                        feature = gained_item
                        provider = None

                    feature_col = {
                        'chatbot': 'website_has_chatbot',
                        'scheduling': 'website_has_scheduling',
                        'contact_form': 'website_has_contact_form',
                        'blog': 'website_has_blog',
                    }.get(feature)

                    if not feature_col:
                        continue

                    feature_label = {
                        'chatbot': 'an AI chatbot',
                        'scheduling': 'online scheduling',
                        'contact_form': 'a contact form',
                        'blog': 'a blog',
                    }.get(feature, feature)

                    # Find competitors: same vertical + same city, who DON'T have this feature
                    cur.execute(f'''
                        SELECT id, business_name FROM consulting_prospects
                        WHERE vertical_id = ? AND city = ? AND id != ?
                          AND {feature_col} = 0
                          AND status NOT IN ('won', 'lost', 'do_not_contact')
                          AND website_audit_date IS NOT NULL
                    ''', (change['vertical_id'], change['city'], change['prospect_id']))

                    competitors_without = cur.fetchall()
                    for comp in competitors_without:
                        message = (
                            f"{change['business_name']} in {change['city']} just added "
                            f"{feature_label}{' (' + provider + ')' if provider else ''} to their website. "
                            f"You offer the same services — are you ready to keep up?"
                        )
                        # Don't create duplicate alerts
                        cur.execute('''
                            SELECT COUNT(*) FROM consulting_competitor_alerts
                            WHERE prospect_id = ? AND competitor_id = ? AND alert_type = ?
                              AND created_at > datetime('now', '-30 days')
                        ''', (comp['id'], change['prospect_id'], feature))
                        if cur.fetchone()[0] == 0:
                            cur.execute('''
                                INSERT INTO consulting_competitor_alerts
                                (prospect_id, competitor_id, alert_type, message)
                                VALUES (?, ?, ?, ?)
                            ''', (comp['id'], change['prospect_id'], feature, message))
                            alerts_generated += 1

            conn.commit()
            conn.close()

        print(f"\nMonitoring complete: {re_audited} re-audited, {changes_detected} changes, {alerts_generated} alerts")
        return {
            "re_audited": re_audited,
            "changes": changes_detected,
            "alerts": alerts_generated,
            "change_log": change_log,
        }


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

    auditor = WebsiteAuditor()

    if len(sys.argv) > 1 and sys.argv[1] == '--all':
        limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
        auditor.audit_all_prospects(max_concurrent=5, limit=limit)
    elif len(sys.argv) > 1:
        result = auditor.audit_website(sys.argv[1])
        if result:
            print(f"\nAudit: {result['url']}")
            print(f"  Score: {result['score']}/100 (lower = better prospect)")
            print(f"  SSL: {'Yes' if result['has_ssl'] else 'NO'}")
            print(f"  Mobile: {'Yes' if result['mobile_friendly'] else 'NO'}")
            print(f"  Contact form: {'Yes' if result['has_contact_form'] else 'NO'}")
            print(f"  Chatbot: {'Yes' if result['has_chatbot'] else 'NO'} {('(' + result['chatbot_provider'] + ')') if result['chatbot_provider'] else ''}")
            print(f"  Scheduling: {'Yes' if result['has_scheduling'] else 'NO'} {('(' + result['scheduling_provider'] + ')') if result['scheduling_provider'] else ''}")
            print(f"  Blog: {'Yes' if result['has_blog'] else 'NO'}")
            print(f"  Social: {', '.join(result['social_platforms']) if result['social_platforms'] else 'None'}")
            print(f"  CMS: {result['cms'] or 'Unknown'}")
            print(f"  Email: {result['email_found'] or 'Not found'}")
            print(f"  Notes: {'; '.join(result['notes'])}")
        else:
            print("Could not audit website")
    else:
        print("Usage: python3 website_auditor.py <url>")
        print("       python3 website_auditor.py --all [limit]")

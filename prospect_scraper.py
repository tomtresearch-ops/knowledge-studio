"""
Prospect Scraper — Google Places (primary) + Yelp Fusion (secondary)
Scrapes local businesses by vertical for AI consulting outreach.

Usage:
    from prospect_scraper import ProspectScraper
    scraper = ProspectScraper()  # reads keys from .env
    results = scraper.scrape_all_verticals(source="google", location="Gwinnett County, GA")
"""

import os
import time
import sqlite3
import requests
from datetime import datetime

YELP_API_URL = "https://api.yelp.com/v3/businesses/search"
GOOGLE_PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
GOOGLE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
DB_PATH = os.path.join(os.path.dirname(__file__), "youtube_intelligence.db")

# Gwinnett County center coordinates (for radius-based search)
GWINNETT_CENTER = {"lat": 33.9608, "lng": -84.0181}
ATLANTA_METRO_CENTER = {"lat": 33.7490, "lng": -84.3880}

# Google Places search terms per vertical (optimized for text search)
GOOGLE_SEARCH_TERMS = {
    "HVAC Contractors": "HVAC contractor",
    "Plumbing Companies": "plumbing company plumber",
    "Electrical Contractors": "electrical contractor electrician",
    "Roofing Companies": "roofing company roofer",
    "Landscaping / Lawn Care": "landscaping company lawn care",
    "Pest Control": "pest control company exterminator",
    "Commercial Cleaning": "commercial cleaning company janitorial",
    "General Contractors": "general contractor construction company",
    "Custom Home Builders": "custom home builder",
    "Specialty Subcontractors": "flooring contractor tile contractor painting contractor",
    "Dental Practices": "dentist dental practice",
    "Chiropractic Offices": "chiropractor chiropractic",
    "Med Spas / Aesthetics": "med spa medical spa aesthetics",
    "Veterinary Clinics": "veterinarian vet clinic",
    "Physical Therapy / Rehab": "physical therapy rehabilitation",
    "Law Firms (Small)": "law firm attorney lawyer",
    "Accounting / CPA Firms": "accountant CPA tax preparation",
    "Real Estate Brokerages": "real estate broker real estate agency",
    "Insurance Agencies": "insurance agency insurance broker",
    "Restaurants (Multi-Location)": "restaurant",
    "Catering Companies": "catering company",
    "Auto Repair Shops": "auto repair shop mechanic",
    "Auto Dealerships (Independent)": "used car dealership independent auto dealer",
    "Gyms / Fitness Studios": "gym fitness studio",
    "Tutoring / Learning Centers": "tutoring center learning center",
    "Property Management": "property management company",
    "Self-Storage Facilities": "self storage facility",
}


class ProspectScraper:
    def __init__(self, google_api_key=None, yelp_api_key=None, db_path=None):
        self.google_api_key = google_api_key or os.environ.get("GOOGLE_PLACES_API_KEY", "")
        self.yelp_api_key = yelp_api_key or os.environ.get("YELP_API_KEY", "")
        self.db_path = db_path or DB_PATH

    def _get_db(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        return conn

    # ══════════════════════════════════════════════════════════════
    # GOOGLE PLACES API
    # ══════════════════════════════════════════════════════════════

    def _google_text_search(self, query, location_str, page_token=None):
        """Google Places Text Search — returns up to 20 results per page, 60 max (3 pages)"""
        params = {
            "query": query,
            "key": self.google_api_key,
        }
        if page_token:
            params["pagetoken"] = page_token
        else:
            # Only set location bias on first request (pagetoken includes it)
            params["query"] = f"{query} in {location_str}"

        resp = requests.get(GOOGLE_PLACES_URL, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _google_place_details(self, place_id):
        """Get phone number and website from Place Details (costs $17/1K)"""
        params = {
            "place_id": place_id,
            "fields": "formatted_phone_number,website,opening_hours,business_status",
            "key": self.google_api_key,
        }
        resp = requests.get(GOOGLE_DETAILS_URL, params=params, timeout=15)
        resp.raise_for_status()
        result = resp.json().get("result", {})
        return {
            "phone": result.get("formatted_phone_number"),
            "website": result.get("website"),
            "business_status": result.get("business_status"),
        }

    def _parse_google_place(self, place, vertical_id, vertical_name, details=None):
        """Convert Google Places result to prospect dict"""
        address = place.get("formatted_address", "")
        # Parse city/state/zip from address string
        parts = [p.strip() for p in address.split(",")]
        city = parts[1] if len(parts) > 1 else ""
        state_zip = parts[2].strip() if len(parts) > 2 else "GA"
        state = state_zip.split()[0] if state_zip else "GA"
        zip_code = state_zip.split()[1] if len(state_zip.split()) > 1 else ""

        phone = details.get("phone") if details else None
        website = details.get("website") if details else None

        biz = {
            "business_name": place.get("name", ""),
            "vertical_id": vertical_id,
            "vertical_name": vertical_name,
            "phone": phone,
            "website": website,
            "address": address,
            "city": city,
            "state": state,
            "zip": zip_code,
            "county": "Gwinnett",  # Default — refine based on city later
            "google_rating": place.get("rating"),
            "google_review_count": place.get("user_ratings_total"),
            "google_place_id": place.get("place_id"),
            "source": "google",
            "source_url": None,
            "ai_readiness_score": self._compute_ai_readiness_google(place, details),
        }
        return biz

    def _compute_ai_readiness_google(self, place, details=None):
        """Score 0-100 for Google Places results"""
        score = 0
        if details and details.get("website"):
            score += 25
        reviews = place.get("user_ratings_total", 0)
        if reviews > 100:
            score += 20
        elif reviews > 50:
            score += 15
        elif reviews > 20:
            score += 12
        elif reviews > 5:
            score += 8
        rating = place.get("rating", 0)
        if rating >= 4.5:
            score += 15
        elif rating >= 4.0:
            score += 10
        elif rating >= 3.5:
            score += 5
        if details and details.get("phone"):
            score += 15
        # Operating business bonus
        if place.get("business_status") == "OPERATIONAL" or (details and details.get("business_status") == "OPERATIONAL"):
            score += 10
        elif not place.get("business_status"):
            score += 5  # Assume operational if not specified
        return min(100, score)

    def scrape_google_vertical(self, vertical_id, vertical_name, search_terms, location="Gwinnett County, GA", max_results=60, fetch_details=True):
        """Scrape Google Places for a single vertical. Max 60 results per query (API limit)."""
        if not self.google_api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY required")

        prospects = []
        seen_ids = set()
        page_token = None

        for page in range(3):  # Google allows max 3 pages of 20 = 60 results
            try:
                data = self._google_text_search(search_terms, location, page_token=page_token)
                status = data.get("status")
                if status not in ("OK", "ZERO_RESULTS"):
                    print(f"  Google API status: {status} — {data.get('error_message', '')}")
                    break

                results = data.get("results", [])
                if not results:
                    break

                for place in results:
                    pid = place.get("place_id")
                    if pid in seen_ids:
                        continue
                    seen_ids.add(pid)

                    # Skip permanently closed
                    if place.get("business_status") == "CLOSED_PERMANENTLY":
                        continue

                    # Fetch phone + website from Details API
                    details = None
                    if fetch_details and pid:
                        try:
                            details = self._google_place_details(pid)
                            time.sleep(0.1)  # Light rate limiting for details
                        except Exception as e:
                            print(f"  Details error for {place.get('name')}: {e}")

                    prospects.append(self._parse_google_place(place, vertical_id, vertical_name, details))

                # Next page — Google requires a short delay before token is valid
                page_token = data.get("next_page_token")
                if not page_token:
                    break
                time.sleep(3)  # Google needs 2-3s before next_page_token works

            except requests.exceptions.HTTPError as e:
                print(f"Google API error for '{search_terms}': {e}")
                break
            except Exception as e:
                print(f"Error scraping '{search_terms}': {e}")
                break

        return prospects[:max_results]

    # ══════════════════════════════════════════════════════════════
    # YELP FUSION API
    # ══════════════════════════════════════════════════════════════

    def _yelp_search(self, term, location, offset=0, limit=50):
        headers = {"Authorization": f"Bearer {self.yelp_api_key}"}
        params = {
            "term": term,
            "location": location,
            "limit": min(limit, 50),
            "offset": offset,
            "sort_by": "best_match",
        }
        resp = requests.get(YELP_API_URL, headers=headers, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _parse_yelp_business(self, biz, vertical_id, vertical_name):
        location = biz.get("location", {})
        return {
            "business_name": biz.get("name", ""),
            "vertical_id": vertical_id,
            "vertical_name": vertical_name,
            "phone": biz.get("display_phone") or biz.get("phone") or None,
            "website": None,
            "address": ", ".join(location.get("display_address", [])),
            "city": location.get("city", ""),
            "state": location.get("state", "GA"),
            "zip": location.get("zip_code", ""),
            "county": "Gwinnett",
            "yelp_rating": biz.get("rating"),
            "yelp_review_count": biz.get("review_count"),
            "yelp_id": biz.get("id"),
            "source": "yelp",
            "source_url": biz.get("url"),
            "ai_readiness_score": self._compute_ai_readiness_yelp(biz),
        }

    def _compute_ai_readiness_yelp(self, biz):
        score = 0
        if biz.get("url"):
            score += 20
        if biz.get("website"):
            score += 20
        reviews = biz.get("review_count", 0)
        if reviews > 50:
            score += 20
        elif reviews > 20:
            score += 15
        elif reviews > 5:
            score += 10
        rating = biz.get("rating", 0)
        if rating >= 4.5:
            score += 15
        elif rating >= 4.0:
            score += 10
        elif rating >= 3.5:
            score += 5
        if biz.get("phone"):
            score += 10
        return min(100, score)

    def scrape_yelp_vertical(self, vertical_id, vertical_name, search_terms, location="Gwinnett County, GA", max_results=200):
        if not self.yelp_api_key:
            raise ValueError("YELP_API_KEY required")

        prospects = []
        offset = 0
        seen_ids = set()

        while offset < max_results:
            try:
                data = self._yelp_search(search_terms, location, offset=offset, limit=50)
                businesses = data.get("businesses", [])
                if not businesses:
                    break
                for biz in businesses:
                    if biz["id"] not in seen_ids:
                        seen_ids.add(biz["id"])
                        prospects.append(self._parse_yelp_business(biz, vertical_id, vertical_name))
                offset += 50
                if offset >= data.get("total", 0):
                    break
                time.sleep(0.5)
            except requests.exceptions.HTTPError as e:
                if e.response and e.response.status_code == 429:
                    print(f"Rate limited — waiting 30s...")
                    time.sleep(30)
                    continue
                print(f"Yelp API error for '{search_terms}': {e}")
                break
            except Exception as e:
                print(f"Error scraping '{search_terms}': {e}")
                break

        return prospects[:max_results]

    # ══════════════════════════════════════════════════════════════
    # DEEP SCRAPE — CITY-BY-CITY
    # ══════════════════════════════════════════════════════════════

    GWINNETT_CITIES = [
        "Lawrenceville, GA", "Duluth, GA", "Suwanee, GA", "Buford, GA",
        "Snellville, GA", "Lilburn, GA", "Norcross, GA", "Dacula, GA",
        "Grayson, GA", "Loganville, GA", "Auburn, GA", "Sugar Hill, GA",
        "Peachtree Corners, GA", "Berkeley Lake, GA", "Braselton, GA",
    ]

    def scrape_deep(self, vertical_ids=None, skip_verticals=None, locations=None, max_per_query=60):
        """Deep scrape — searches each vertical across multiple cities for better coverage.
        Dedup handles overlap. Gets the mid-tier businesses that county-wide search misses.

        vertical_ids: list of vertical IDs to scrape (None = all active)
        skip_verticals: set of vertical names to skip (e.g. Tier 4)
        locations: list of location strings (None = GWINNETT_CITIES)
        """
        if not self.google_api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY required")

        skip_verticals = skip_verticals or set()
        locations = locations or self.GWINNETT_CITIES

        conn = self._get_db()
        cursor = conn.cursor()
        if vertical_ids:
            placeholders = ','.join('?' * len(vertical_ids))
            cursor.execute(f"SELECT id, name, yelp_search_terms FROM consulting_verticals WHERE id IN ({placeholders}) AND active = 1", vertical_ids)
        else:
            cursor.execute("SELECT id, name, yelp_search_terms FROM consulting_verticals WHERE active = 1 AND yelp_search_terms IS NOT NULL")
        verticals = cursor.fetchall()
        conn.close()

        total_created = 0
        total_skipped = 0
        total_api_calls = 0
        results = []

        for v in verticals:
            v_name = v["name"]
            if v_name in skip_verticals:
                print(f"[SKIP] {v_name}")
                continue

            search_terms = GOOGLE_SEARCH_TERMS.get(v_name, v["yelp_search_terms"])
            v_created = 0
            v_scraped = 0

            for loc in locations:
                print(f"[Google] {v_name} in {loc}...")
                prospects = self.scrape_google_vertical(
                    vertical_id=v["id"],
                    vertical_name=v_name,
                    search_terms=search_terms,
                    location=loc,
                    max_results=max_per_query,
                )
                est_calls = min(3, (len(prospects) // 20) + 1) + len(prospects)
                total_api_calls += est_calls
                v_scraped += len(prospects)

                if prospects:
                    result = self._bulk_insert(prospects, source="google")
                    v_created += result["created"]
                    total_skipped += result["skipped"]

                time.sleep(1)

            total_created += v_created
            results.append({"vertical": v_name, "created": v_created, "scraped": v_scraped})
            print(f"  => {v_name} total: {v_created} new from {v_scraped} found across {len(locations)} cities")

        # Update vertical prospect counts
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE consulting_verticals SET prospect_count = (
                SELECT COUNT(*) FROM consulting_prospects WHERE consulting_prospects.vertical_id = consulting_verticals.id
            )
        ''')
        conn.commit()
        conn.close()

        return {
            "total_created": total_created,
            "total_skipped": total_skipped,
            "estimated_api_calls": total_api_calls,
            "locations": locations,
            "verticals": results,
        }

    # ══════════════════════════════════════════════════════════════
    # UNIFIED SCRAPE INTERFACE
    # ══════════════════════════════════════════════════════════════

    def scrape_all_verticals(self, source="google", location="Gwinnett County, GA", max_per_vertical=60):
        """Scrape all active verticals from specified source, bulk-insert into DB.

        source: "google" (primary, uses $200/mo free credit) or "yelp" (backup, fully free)
        """
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, yelp_search_terms FROM consulting_verticals WHERE active = 1 AND yelp_search_terms IS NOT NULL")
        verticals = cursor.fetchall()
        conn.close()

        total_created = 0
        total_skipped = 0
        total_api_calls = 0
        results = []

        for v in verticals:
            v_name = v["name"]

            if source == "google":
                search_terms = GOOGLE_SEARCH_TERMS.get(v_name, v["yelp_search_terms"])
                print(f"[Google] Scraping: {v_name} (query: {search_terms})...")
                prospects = self.scrape_google_vertical(
                    vertical_id=v["id"],
                    vertical_name=v_name,
                    search_terms=search_terms,
                    location=location,
                    max_results=max_per_vertical,
                )
                # Estimate API calls: 1 text search + up to 3 pages + 1 detail per result
                est_calls = min(3, (len(prospects) // 20) + 1) + len(prospects)
                total_api_calls += est_calls
            else:
                print(f"[Yelp] Scraping: {v_name} (terms: {v['yelp_search_terms']})...")
                prospects = self.scrape_yelp_vertical(
                    vertical_id=v["id"],
                    vertical_name=v_name,
                    search_terms=v["yelp_search_terms"],
                    location=location,
                    max_results=max_per_vertical,
                )

            if prospects:
                result = self._bulk_insert(prospects, source=source)
                total_created += result["created"]
                total_skipped += result["skipped"]
                results.append({
                    "vertical": v_name,
                    "scraped": len(prospects),
                    "created": result["created"],
                    "skipped": result["skipped"],
                })
                print(f"  -> {result['created']} new, {result['skipped']} duplicates (from {len(prospects)} scraped)")
            else:
                results.append({"vertical": v_name, "scraped": 0, "created": 0, "skipped": 0})
                print(f"  -> no results")

            time.sleep(1)

        # Update vertical prospect counts
        conn = self._get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE consulting_verticals SET prospect_count = (
                SELECT COUNT(*) FROM consulting_prospects WHERE consulting_prospects.vertical_id = consulting_verticals.id
            )
        ''')
        conn.commit()
        conn.close()

        summary = {
            "source": source,
            "location": location,
            "total_created": total_created,
            "total_skipped": total_skipped,
            "verticals": results,
        }
        if source == "google":
            summary["estimated_api_calls"] = total_api_calls
            # Text search: $32/1K, Details: $17/1K
            est_cost = (total_api_calls * 0.025)  # Blended average ~$25/1K
            summary["estimated_cost"] = f"${est_cost:.2f} (covered by $200/mo free credit)"

        return summary

    def _bulk_insert(self, prospects, source="google"):
        """Insert prospects into DB, deduplicating by name+phone or place_id"""
        conn = self._get_db()
        cursor = conn.cursor()
        created = 0
        skipped = 0

        for p in prospects:
            # Dedup: check google_place_id first, then name+phone
            if source == "google" and p.get("google_place_id"):
                cursor.execute(
                    "SELECT id FROM consulting_prospects WHERE google_place_id = ?",
                    (p["google_place_id"],)
                )
                if cursor.fetchone():
                    skipped += 1
                    continue
            if p.get("phone"):
                cursor.execute(
                    "SELECT id FROM consulting_prospects WHERE business_name = ? AND phone = ?",
                    (p["business_name"], p["phone"])
                )
                if cursor.fetchone():
                    skipped += 1
                    continue
            if source == "yelp" and p.get("yelp_id"):
                cursor.execute(
                    "SELECT id FROM consulting_prospects WHERE yelp_id = ?",
                    (p["yelp_id"],)
                )
                if cursor.fetchone():
                    skipped += 1
                    continue

            cursor.execute('''
                INSERT INTO consulting_prospects (
                    business_name, vertical_id, vertical_name, phone, website,
                    address, city, state, zip, county,
                    yelp_rating, yelp_review_count, yelp_id,
                    google_rating, google_review_count, google_place_id,
                    ai_readiness_score, priority, status, source, source_url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                p["business_name"], p["vertical_id"], p["vertical_name"],
                p.get("phone"), p.get("website"),
                p["address"], p["city"], p["state"], p["zip"], p["county"],
                p.get("yelp_rating"), p.get("yelp_review_count"), p.get("yelp_id"),
                p.get("google_rating"), p.get("google_review_count"), p.get("google_place_id"),
                p.get("ai_readiness_score", 0), "medium", "new",
                source, p.get("source_url"),
            ))
            created += 1

        conn.commit()
        conn.close()
        return {"created": created, "skipped": skipped}


def scrape_location(source="google", location="Gwinnett County, GA", max_per_vertical=60):
    """Convenience function for running from API or CLI"""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

    scraper = ProspectScraper()

    if source == "google" and not scraper.google_api_key:
        return {"error": "GOOGLE_PLACES_API_KEY not set in .env"}
    if source == "yelp" and not scraper.yelp_api_key:
        return {"error": "YELP_API_KEY not set in .env"}

    return scraper.scrape_all_verticals(source=source, location=location, max_per_vertical=max_per_vertical)


if __name__ == "__main__":
    import sys
    source = sys.argv[1] if len(sys.argv) > 1 else "google"
    location = sys.argv[2] if len(sys.argv) > 2 else "Gwinnett County, GA"
    print(f"\nScraping all verticals via {source.upper()} for: {location}\n")
    results = scrape_location(source=source, location=location)
    if "error" in results:
        print(f"ERROR: {results['error']}")
    else:
        print(f"\nDone! Source: {results.get('source', source)}")
        print(f"Created: {results['total_created']}, Skipped: {results['total_skipped']}")
        if "estimated_cost" in results:
            print(f"Estimated cost: {results['estimated_cost']}")
        for v in results["verticals"]:
            print(f"  {v['vertical']}: {v['created']} new / {v['scraped']} scraped")

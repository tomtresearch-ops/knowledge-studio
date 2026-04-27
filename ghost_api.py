"""
Ghost API Integration — Post newsletters to Ghost CMS
Uses Ghost Admin API with JWT authentication.

Setup:
1. Go to Ghost Admin > Settings > Integrations > Add custom integration
2. Name it "Jarvis"
3. Copy the Admin API key
4. Set GHOST_ADMIN_API_KEY in .env (format: {id}:{secret})
5. Set GHOST_URL in .env (default: http://localhost:2368)
"""

import os
import sys
import json
import jwt
import requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

GHOST_URL = os.getenv("GHOST_URL", "http://localhost:2368")
GHOST_ADMIN_API_KEY = os.getenv("GHOST_ADMIN_API_KEY", "")


def get_ghost_token():
    """Generate a JWT token for Ghost Admin API authentication."""
    if not GHOST_ADMIN_API_KEY or ":" not in GHOST_ADMIN_API_KEY:
        raise ValueError(
            "GHOST_ADMIN_API_KEY not set or invalid format. "
            "Expected format: {id}:{secret}. "
            "Get this from Ghost Admin > Settings > Integrations > Jarvis"
        )

    key_id, secret = GHOST_ADMIN_API_KEY.split(":")

    iat = int(datetime.now().timestamp())
    header = {"alg": "HS256", "typ": "JWT", "kid": key_id}
    payload = {"iat": iat, "exp": iat + 300, "aud": "/admin/"}

    token = jwt.encode(payload, bytes.fromhex(secret), algorithm="HS256", headers=header)
    return token


def ghost_request(method, endpoint, data=None):
    """Make an authenticated request to the Ghost Admin API."""
    token = get_ghost_token()
    url = f"{GHOST_URL}/ghost/api/admin/{endpoint}"
    headers = {
        "Authorization": f"Ghost {token}",
        "Content-Type": "application/json",
    }

    if method == "GET":
        resp = requests.get(url, headers=headers)
    elif method == "POST":
        resp = requests.post(url, headers=headers, json=data)
    elif method == "PUT":
        resp = requests.put(url, headers=headers, json=data)
    elif method == "DELETE":
        resp = requests.delete(url, headers=headers)
    else:
        raise ValueError(f"Unsupported method: {method}")

    if resp.status_code >= 400:
        print(f"Ghost API error ({resp.status_code}): {resp.text[:500]}")
    return resp


def list_newsletters():
    """List all newsletters configured in Ghost."""
    resp = ghost_request("GET", "newsletters/")
    if resp.status_code == 200:
        newsletters = resp.json().get("newsletters", [])
        for nl in newsletters:
            print(f"  - {nl['name']} (id: {nl['id']}, status: {nl['status']})")
        return newsletters
    return []


def create_newsletter(name, description="", sender_name="Skiff"):
    """Create a new newsletter in Ghost."""
    data = {
        "newsletters": [{
            "name": name,
            "description": description,
            "sender_name": sender_name,
            "status": "active",
            "subscribe_on_signup": False,
            "sort_order": 0,
        }]
    }
    resp = ghost_request("POST", "newsletters/", data)
    if resp.status_code == 201:
        nl = resp.json()["newsletters"][0]
        print(f"  Created newsletter: {nl['name']} (id: {nl['id']})")
        return nl
    return None


def create_post(title, html_content, newsletter_id=None, status="draft",
                tags=None, excerpt=None):
    """
    Create a post in Ghost.
    status: 'draft' (saved, not sent), 'published' (visible on site),
            or 'sent' (email only, via newsletter)
    """
    post_data = {
        "title": title,
        "html": html_content,
        "status": status,
    }

    if tags:
        post_data["tags"] = [{"name": t} for t in tags]
    if excerpt:
        post_data["custom_excerpt"] = excerpt

    # If publishing as newsletter email, set the newsletter
    if newsletter_id:
        post_data["newsletter"] = {"id": newsletter_id}
        if status == "published":
            post_data["email_segment"] = "all"

    data = {"posts": [post_data], "source": "html"}
    resp = ghost_request("POST", "posts/?source=html", data)
    if resp.status_code == 201:
        post = resp.json()["posts"][0]
        print(f"  Created post: {post['title']} (id: {post['id']}, status: {post['status']})")
        return post
    return None


def publish_newsletter_from_json(json_path, vertical, as_draft=True):
    """
    Load a newsletter JSON file and post it to Ghost.
    By default creates as draft for review.
    """
    with open(json_path) as f:
        editorial = json.load(f)

    # Get newsletter ID for this vertical
    newsletters = list_newsletters()
    vertical_names = {
        "ai_tech": "AI & Tech",
        "health_longevity": "Health & Longevity",
        "futures_trends": "Futures & Trends",
    }
    target_name = vertical_names.get(vertical, vertical)
    newsletter = next((nl for nl in newsletters if target_name in nl["name"]), None)

    # Format the date
    meta = editorial.get("_meta", {})
    brief_date = meta.get("brief_date", "")
    try:
        dt = datetime.strptime(brief_date[:10], "%Y-%m-%d")
        display_date = dt.strftime("%B %d, %Y").replace(" 0", " ")
    except (ValueError, TypeError):
        display_date = datetime.now().strftime("%B %d, %Y").replace(" 0", " ")

    # Build HTML content for Ghost (Ghost uses its own styling, so we send clean HTML)
    signals_html = ""
    for i, sig in enumerate(editorial["signals"]):
        signals_html += f"""
<h3>{sig['headline']}</h3>
<p>{sig['body']}</p>
<p><strong>{sig['whycare']}</strong></p>
<hr>
"""

    masthead = vertical_names.get(vertical, vertical) + " Brief"
    signal_count = meta.get("signal_count", "")
    source_count = meta.get("source_count", "")
    stats_line = f" &middot; {signal_count} signals from {source_count} sources" if signal_count else ""

    html = f"""
<p><small>{masthead} &middot; {display_date}{stats_line}</small></p>
<p><em>{editorial['editorial_intro']}</em></p>
{signals_html}
<blockquote><strong>The Bigger Picture</strong><br>{editorial['bigger_picture']}</blockquote>
"""
    tags = [vertical_names.get(vertical, vertical), "newsletter"]

    status = "draft" if as_draft else "published"
    post = create_post(
        title=editorial["headline"],
        html_content=html,
        newsletter_id=newsletter["id"] if newsletter else None,
        status=status,
        tags=tags,
        excerpt=editorial["subtitle"],
    )

    return post


def setup_newsletters():
    """Create the standard newsletters for all verticals."""
    configs = [
        ("AI & Tech Brief", "AI-curated intelligence on artificial intelligence, machine learning, and technology"),
        ("Health & Longevity Brief", "AI-curated intelligence on aging, longevity, and life extension research"),
        ("Futures & Trends Brief", "AI-curated intelligence on emerging trends, technology futures, and paradigm shifts"),
    ]

    print("\nSetting up Skiff newsletters...")
    for name, desc in configs:
        create_newsletter(name, desc)
    print("\nDone! Newsletters created.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 ghost_api.py setup          — Create newsletters for all verticals")
        print("  python3 ghost_api.py list            — List existing newsletters")
        print("  python3 ghost_api.py post <json>     — Post newsletter from JSON file")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "setup":
        setup_newsletters()
    elif cmd == "list":
        print("\nGhost newsletters:")
        list_newsletters()
    elif cmd == "post":
        if len(sys.argv) < 3:
            print("Provide path to newsletter JSON file")
            sys.exit(1)
        json_path = sys.argv[2]
        vertical = sys.argv[3] if len(sys.argv) > 3 else "health_longevity"
        print(f"\nPosting newsletter to Ghost ({vertical})...")
        publish_newsletter_from_json(json_path, vertical)
    else:
        print(f"Unknown command: {cmd}")

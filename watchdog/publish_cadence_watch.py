#!/usr/bin/env python3
"""Publish cadence watchdog: shouts when any brand feed goes stale."""
import re, sys, subprocess, pathlib, urllib.request
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

BASE = "https://media-verticals.github.io/podcasts/"
FEEDS = {
    "feed_ai_landscape":         ("AI Landscape", 2),
    "feed_longevity_edge":       ("Longevity Report", 5),
    "feed_breakthrough_medicine":("Breakthrough Medicine", 5),
    "feed_ai_agents":            ("AI Agents", 5),
    "feed_local_ai_intel":       ("Local AI Intel", 5),
}
OUT = pathlib.Path.home() / "publish_alerts"
OUT.mkdir(exist_ok=True)

def latest(slug):
    with urllib.request.urlopen(BASE + slug + ".xml", timeout=30) as r:
        xml = r.read().decode("utf-8", "replace")
    m = re.search(r"<pubDate>([^<]+)</pubDate>", xml)
    return parsedate_to_datetime(m.group(1)) if m else None

now = datetime.now(timezone.utc)
stale = []
for slug, (brand, limit) in FEEDS.items():
    try:
        d = latest(slug)
    except Exception as e:
        stale.append("%s: feed unreachable (%s)" % (brand, e))
        continue
    if d is None:
        stale.append("%s: feed has no episodes" % brand)
        continue
    age = (now - d).days
    if age > limit:
        stale.append("%s: %d days since last episode (limit %d)" % (brand, age, limit))

if stale:
    body = "PODCAST PUBLISHING STALLED\n" + "\n".join("- " + s for s in stale)
    (OUT / ("STALLED_%s.txt" % now.strftime("%Y-%m-%d"))).write_text(body + "\n")
    msg = "; ".join(stale)[:200].replace('"', "")
    subprocess.run(["/usr/bin/osascript", "-e",
                    'display notification "%s" with title "Podcast publishing stalled"' % msg],
                   check=False)
    print(body)
    sys.exit(1)
print("all feeds current")

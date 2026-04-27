#!/usr/bin/env python3
"""Bulk extract predictions from all library items and save to Intelligence."""
import requests
import sqlite3
import time
import json
import sys

BASE = "http://localhost:5001"
DB = "youtube_intelligence.db"

def get_items():
    """Get all items with extractable content."""
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    items = []

    # Videos with transcripts or summaries
    c.execute("""SELECT id, title, video_url as url, channel,
                 CASE WHEN full_transcript IS NOT NULL AND length(full_transcript) > 100 THEN 1 ELSE 0 END as has_transcript,
                 CASE WHEN ai_summary IS NOT NULL AND length(ai_summary) > 100 THEN 1 ELSE 0 END as has_summary
                 FROM videos
                 WHERE (full_transcript IS NOT NULL AND length(full_transcript) > 100)
                    OR (ai_summary IS NOT NULL AND length(ai_summary) > 100)""")
    for row in c.fetchall():
        items.append({'id': row['id'], 'title': row['title'], 'type': 'video'})

    # Articles with content or summaries
    c.execute("""SELECT id, title, url,
                 CASE WHEN content IS NOT NULL AND length(content) > 100 THEN 1 ELSE 0 END as has_content,
                 CASE WHEN summary IS NOT NULL AND length(summary) > 100 THEN 1 ELSE 0 END as has_summary
                 FROM articles
                 WHERE (content IS NOT NULL AND length(content) > 100)
                    OR (summary IS NOT NULL AND length(summary) > 100)""")
    for row in c.fetchall():
        items.append({'id': row['id'], 'title': row['title'], 'type': 'article'})

    conn.close()
    return items

def already_has_predictions(title):
    """Check if predictions already exist for this source."""
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM intelligence WHERE type='prediction' AND source_title=?", (title,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

def main():
    items = get_items()
    total = len(items)
    print(f"Found {total} items to scan")

    extracted = 0
    saved = 0
    skipped = 0
    empty = 0
    errors = 0

    for i, item in enumerate(items):
        # Progress
        pct = int((i / total) * 100)
        sys.stdout.write(f"\r[{pct:3d}%] {i}/{total} | extracted:{extracted} saved:{saved} empty:{empty} skipped:{skipped} errors:{errors} | {item['title'][:60]}")
        sys.stdout.flush()

        # Skip if already scanned
        if already_has_predictions(item['title']):
            skipped += 1
            continue

        # Extract predictions
        content_type = 'article' if item['type'] == 'article' else 'video'
        try:
            resp = requests.post(f"{BASE}/api/items/{item['id']}/extract-predictions",
                                json={'content_type': content_type}, timeout=30)
            data = resp.json()

            if not data.get('success'):
                errors += 1
                continue

            predictions = data.get('predictions', [])
            if not predictions:
                empty += 1
                continue

            extracted += len(predictions)

            # Save each prediction to Intelligence
            for pred in predictions:
                title_text = pred.get('prediction', '')
                if len(title_text) > 120:
                    cut = title_text.rfind(' ', 0, 120)
                    title_text = title_text[:cut if cut > 60 else 120] + '...'

                content = pred.get('prediction', '')
                if pred.get('timeframe') and pred['timeframe'] != 'unspecified':
                    content += '\n\nTimeframe: ' + pred['timeframe']
                if pred.get('confidence'):
                    content += '\nConfidence: ' + pred['confidence']

                tags = ', '.join(filter(None, [
                    pred.get('topic', ''),
                    pred.get('confidence', ''),
                    pred.get('timeframe', '') if pred.get('timeframe') != 'unspecified' else ''
                ]))

                try:
                    save_resp = requests.post(f"{BASE}/api/intelligence", json={
                        'type': 'prediction',
                        'title': title_text,
                        'content': content,
                        'tags': tags,
                        'source_title': data.get('source_title', ''),
                        'source_url': data.get('source_url', ''),
                        'source_channel': data.get('source_channel', ''),
                        'source_video_ids': [item['id']]
                    }, timeout=10)
                    if save_resp.json().get('success'):
                        saved += 1
                except:
                    errors += 1

            # Small delay to not hammer the API
            time.sleep(0.5)

        except requests.exceptions.Timeout:
            errors += 1
        except Exception as e:
            errors += 1
            print(f"\n  ERROR on {item['id']}: {e}")

    print(f"\n\n{'='*60}")
    print(f"DONE — Bulk Prediction Extraction Complete")
    print(f"{'='*60}")
    print(f"Items scanned:  {total}")
    print(f"Skipped (dupes): {skipped}")
    print(f"Empty (no preds): {empty}")
    print(f"Predictions found: {extracted}")
    print(f"Predictions saved: {saved}")
    print(f"Errors:          {errors}")

if __name__ == '__main__':
    main()

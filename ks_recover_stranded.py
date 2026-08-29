#!/usr/bin/env python3
"""Recover queue items stranded by the IP-block misclassification (2026-08-28).

Before the fix, a YouTube IP block was recorded as 'No transcript available', which
burned retries until the item was deferred forever. Those are good videos Tom
submitted on purpose. This puts them back in the queue.

  --dry-run   show what would change (default)
  --apply     perform the requeue
  --revert    restore the statuses this script last changed
"""
import sqlite3, sys, json, datetime, pathlib

DB = '/Users/max/knowledge-studio/youtube_intelligence.db'
UNDO = pathlib.Path('/Users/max/knowledge-studio/logs/recover_stranded_undo.json')
STUCK = ('deferred', 'pending_retry', 'no_transcript', 'failed')

def rows(cur):
    q = ','.join('?' * len(STUCK))
    cur.execute(f'SELECT id, status, video_id, substr(COALESCE(title,"-"),1,50) FROM processing_queue WHERE status IN ({q}) ORDER BY id', STUCK)
    return cur.fetchall()

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else '--dry-run'
    conn = sqlite3.connect(DB); cur = conn.cursor()

    if mode == '--revert':
        if not UNDO.exists():
            print('no undo file'); return 1
        saved = json.loads(UNDO.read_text())
        for item_id, status in saved['items']:
            cur.execute('UPDATE processing_queue SET status=? WHERE id=?', (status, item_id))
        conn.commit()
        print(f'reverted {len(saved["items"])} item(s) to their prior status')
        return 0

    found = rows(cur)
    print(f'{len(found)} stranded item(s):')
    by_status = {}
    for _id, st, _vid, _t in found:
        by_status[st] = by_status.get(st, 0) + 1
    for st, n in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f'   {st:<16} {n}')
    print()
    for _id, st, vid, t in found[:12]:
        print(f'   [{_id}] {st:<14} {vid or "(no id)":<12} {t}')
    if len(found) > 12:
        print(f'   ... and {len(found)-12} more')

    if mode != '--apply':
        print('\nDRY RUN — nothing changed. Re-run with --apply to requeue.')
        return 0

    UNDO.parent.mkdir(parents=True, exist_ok=True)
    UNDO.write_text(json.dumps({
        'saved_at': datetime.datetime.now().isoformat(timespec='seconds'),
        'items': [[r[0], r[1]] for r in found],
    }, indent=2))
    q = ','.join('?' * len(STUCK))
    cur.execute(f"""UPDATE processing_queue
           SET status='queued', next_attempt_at=NULL, started_at=NULL, retry_count=0,
               error_message='Recovered 2026-08-28: stranded by IP-block misclassification'
         WHERE status IN ({q})""", STUCK)
    conn.commit()
    print(f'\nrequeued {cur.rowcount} item(s). Undo: ks_recover_stranded.py --revert')
    return 0

if __name__ == '__main__':
    sys.exit(main())

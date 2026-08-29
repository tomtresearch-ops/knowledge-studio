#!/usr/bin/env python3
"""Requeue items parked as blocked_ip once the Mullvad exit IP has changed.

Tom's rule (2026-08-28): 'I just don't wanna lose whatever I submitted — I submitted
it for a reason.' Blocked items keep priority 100 so they go to the FRONT of the
queue the moment a clean relay is up.

Called by mullvad_rotate.sh after every rotation, and safe to run by hand.
"""
import sqlite3, sys, datetime

DB = '/Users/max/knowledge-studio/youtube_intelligence.db'

def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM processing_queue WHERE status = 'blocked_ip'")
    n = cur.fetchone()[0]
    if not n:
        print('no blocked_ip items to requeue')
        conn.close()
        return 0
    cur.execute("""
        UPDATE processing_queue
        SET status = 'queued',
            error_message = 'Requeued after relay rotation',
            next_attempt_at = NULL,
            started_at = NULL,
            priority = MAX(COALESCE(priority, 0), 100)
        WHERE status = 'blocked_ip'
    """)
    conn.commit()
    conn.close()
    print(f'{datetime.datetime.now().isoformat(timespec="seconds")} requeued {n} blocked_ip item(s) at top priority')
    return 0

if __name__ == '__main__':
    sys.exit(main())

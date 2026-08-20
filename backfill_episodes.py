#!/usr/bin/env python3
"""Backfill the episodes the Aug 2026 outage skipped, dated to the day they were due.

Between 2026-08-13 and 2026-08-19 the nightly run generated briefs normally but produced no
audio: a git recovery had deleted the (gitignored) voice roster, and the pipeline treated a
missing voice as a skip rather than a fault. The briefs survived. This turns each orphaned
brief into its episode and stamps it with the brief's OWN date, so the feed reads as the
run of days it actually was instead of ten episodes dumped on one afternoon.

Deliberately a separate file: podcast_pipeline.py works and publishes nightly. This imports
it and overrides only the two things that differ for a backfill — which brief to use, and
what date to stamp — so nothing in the live path changes shape.

Usage:
    backfill_episodes.py --list                     # what's missing, do nothing
    backfill_episodes.py --dry-run                  # full plan, still nothing
    backfill_episodes.py --vertical health_longevity
    backfill_episodes.py --all
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import podcast_pipeline as pp

# The hour an episode is stamped with. The nightly run lands them in the small hours; using a
# fixed morning time keeps a backfilled day ordering correctly against a real one.
PUBLISH_HOUR = "07:15:00"

# Only brands that actually publish. ai_agents / local_ai_intel / ks_youtube are switched off
# at the source and backfilling them would put episodes on feeds Tom has paused.
LIVE_VERTICALS = ("future_medicine", "health_longevity", "ai_tech")

# The gap. Briefs before this were already voiced; anything after is the live run's job.
GAP_START = "2026-08-13"


def orphan_briefs(conn, verticals):
    """Briefs in the gap with no episode — newest LAST, so the feed rebuilds in real order."""
    rows = []
    for v in verticals:
        rows += list(conn.execute(
            "SELECT b.id, b.vertical, b.title, b.signal_count, substr(b.created_at,1,10) "
            "FROM daily_briefs b "
            "LEFT JOIN brief_podcast_episodes e ON e.brief_id = b.id "
            "WHERE b.vertical = ? AND b.created_at >= ? AND e.id IS NULL "
            "ORDER BY b.created_at", (v, GAP_START)))
    # Generation order is a QUOTA decision, not a feed decision: the feed sorts on the
    # stamped date, so building rarest-brand-first costs the running order nothing and means
    # that if the subscription quota runs dry partway, what got made is what Tom pushes first.
    # Same priority the nightly run uses.
    rows.sort(key=lambda r: (LIVE_VERTICALS.index(r[1]) if r[1] in LIVE_VERTICALS else 99, r[4]))
    return rows


def brief_row(conn, brief_id):
    conn.row_factory = sqlite3.Row
    r = conn.execute("SELECT * FROM daily_briefs WHERE id = ?", (brief_id,)).fetchone()
    return dict(r) if r else None


def redate(episode_id, date_str):
    """Stamp the episode with the day it was due. pubDate in the feed reads created_at."""
    conn = sqlite3.connect(pp.DB_PATH, timeout=30)
    conn.execute("UPDATE brief_podcast_episodes SET created_at = ? WHERE id = ?",
                 (f"{date_str} {PUBLISH_HOUR}", episode_id))
    conn.commit()
    conn.close()


def build_one(conn, brief_id, date_str, vertical):
    """One episode, start to finish, minus the deploy — that runs once at the end."""
    brief = brief_row(conn, brief_id)
    if not brief:
        print(f"  brief #{brief_id} vanished — skipping")
        return False

    voice_ref = pp.get_voice_reference(vertical)
    if not voice_ref:
        raise RuntimeError(
            f"No voice reference for {vertical}. This is the exact fault that caused the "
            f"outage — restore the roster before backfilling.")

    print(f"\n  {date_str} · {vertical} · brief #{brief_id} ({brief['signal_count']} signals)")
    print(f"    voice: {os.path.basename(voice_ref)}")

    script, _ = pp.generate_script(brief)
    print(f"    script: {len(script.split())} words")

    wav_path = os.path.join(pp.AUDIO_DIR, f"podcast_{vertical}_{date_str}.wav")
    mp3_name = f"podcast_{vertical}_{date_str}.mp3"
    mp3_path = os.path.join(pp.AUDIO_DIR, mp3_name)

    duration, _ = pp.generate_audio_tts(script, voice_ref, wav_path)
    mp3_size = pp.convert_to_mp3(wav_path, mp3_path)

    # Same audio gate the live path uses. A backfilled episode is still an episode; it does
    # not get a lower bar because it is late.
    from podcast_qa import audio_integrity_check, _log as qa_log
    ok, issues = audio_integrity_check(mp3_path, len(script.split()))
    if not ok:
        for i in issues:
            qa_log(f"{vertical} BACKFILL: AUDIO GATE FAIL — {i}")
        raise RuntimeError(f"audio gate failed for {mp3_name}: {'; '.join(issues)}")
    qa_log(f"{vertical} BACKFILL: audio gate pass ({mp3_name})")

    episode_id = pp.register_episode(brief, script, mp3_name, mp3_size, duration)
    redate(episode_id, date_str)
    pp.copy_to_icloud(mp3_path)
    print(f"    registered #{episode_id}, dated {date_str}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vertical", choices=LIVE_VERTICALS)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="stop after N episodes")
    args = ap.parse_args()

    verticals = [args.vertical] if args.vertical else list(LIVE_VERTICALS)
    conn = sqlite3.connect(pp.DB_PATH, timeout=30)
    pending = orphan_briefs(conn, verticals)

    if not pending:
        print("Nothing to backfill — every brief in the gap already has its episode.")
        return 0

    print(f"{len(pending)} episode(s) missing:")
    for bid, v, title, signals, date_str in pending:
        print(f"   {date_str}  {v:18} brief #{bid}  {signals} signals  {title[:52]}")

    if args.list or args.dry_run:
        print("\nNothing was generated (list/dry-run).")
        return 0

    if args.limit:
        pending = pending[:args.limit]

    built, failed = 0, []
    for bid, v, _title, _signals, date_str in pending:
        try:
            if build_one(conn, bid, date_str, v):
                built += 1
        except Exception as exc:                                    # noqa: BLE001
            # One bad episode must not strand the other nine. Record and keep going; the
            # brief stays orphaned, so a later run picks it up again untouched.
            print(f"    FAILED {v} {date_str}: {exc}")
            failed.append(f"{v} {date_str}: {exc}")

    conn.close()

    if built:
        print(f"\nDeploying feeds once for all {built} episode(s)...")
        pp.deploy_to_github_pages()

    print(f"\nBackfill complete — {built} built, {len(failed)} failed.")
    for f in failed:
        print(f"   FAILED  {f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

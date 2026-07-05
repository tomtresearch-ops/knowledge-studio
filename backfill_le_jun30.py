#!/usr/bin/env python3
"""One-off backfill: produce the missing Longevity Edge (health_longevity) Jun 30
episode (brief #518) using the script that was already written that night.
Reuses podcast_pipeline functions; names the mp3 with the Jun-30 date and sets
created_at to the original production window so feed chronology stays correct.
Idempotent: refuses if brief #518 already has an episode."""
import os, sqlite3, sys
os.chdir(os.path.expanduser("~/knowledge-studio"))
sys.path.insert(0, os.path.expanduser("~/knowledge-studio"))
import podcast_pipeline as pp

BRIEF_ID = 518
DATE = "2026-06-30"
CREATED_AT = "2026-07-01 02:40:00"
SCRIPT_PATH = os.path.join(pp.AUDIO_DIR, f"podcast_script_health_longevity_{DATE}.txt")

conn = sqlite3.connect(pp.DB_PATH); conn.row_factory = sqlite3.Row
brief = dict(conn.execute("SELECT * FROM daily_briefs WHERE id=?", (BRIEF_ID,)).fetchone())
exists = conn.execute("SELECT id FROM brief_podcast_episodes WHERE brief_id=?", (BRIEF_ID,)).fetchone()
conn.close()
if exists:
    print(f"ABORT: brief #{BRIEF_ID} already has episode #{exists[0]}"); sys.exit(1)
print("Brief #" + str(BRIEF_ID) + ": " + brief["title"])

script = open(SCRIPT_PATH).read()
print(f"Reusing saved script: {len(script.split())} words")

voice_ref = pp.get_voice_reference("health_longevity")
print(f"Voice: {os.path.basename(voice_ref)} -> {os.path.realpath(voice_ref)}")

wav_path = os.path.join(pp.AUDIO_DIR, f"podcast_health_longevity_{DATE}.wav")
mp3_path = os.path.join(pp.AUDIO_DIR, f"podcast_health_longevity_{DATE}.mp3")
mp3_filename = f"podcast_health_longevity_{DATE}.mp3"

duration, sr = pp.generate_audio_tts(script, voice_ref, wav_path)
mp3_size = pp.convert_to_mp3(wav_path, mp3_path)

from podcast_scriptwriter import generate_episode_title, generate_episode_summary
title = generate_episode_title(script)
desc = generate_episode_summary(title, script, vertical="health_longevity")

conn = sqlite3.connect(pp.DB_PATH)
conn.execute(
  "INSERT INTO brief_podcast_episodes (brief_id, vertical, title, description, audio_filename, audio_size, duration_seconds, script_text, status, created_at) VALUES (?,?,?,?,?,?,?,?,'ready',?)",
  (BRIEF_ID, "health_longevity", title, desc, mp3_filename, mp3_size, int(duration), script, CREATED_AT))
conn.commit(); eid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]; conn.close()
print(f"Episode #{eid} registered: {title} (created_at={CREATED_AT})")

pp.copy_to_icloud(mp3_path)
pp.deploy_to_github_pages()
print("BACKFILL COMPLETE")

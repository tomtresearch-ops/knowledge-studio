"""
Podcast Pipeline — Automated brief-to-podcast conversion.

Chains: Brief → Script → TTS → MP3 → RSS Registration
Runs after nightly brief generation to produce a podcast episode.
"""

import os
import re
import sys
import time
import json
import sqlite3
import subprocess
import numpy as np
import soundfile as sf
from datetime import datetime
from pronounce_classes import normalize as normalize_sci_tokens
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))

# Paths
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(PROJECT_DIR, "podcast_audio")
DB_PATH = os.path.join(PROJECT_DIR, "youtube_intelligence.db")

# Enable automatic API usage logging
sys.path.insert(0, PROJECT_DIR)
import api_logger
api_logger.patch(DB_PATH)
VOICE_ROSTER_DIR = os.path.join(AUDIO_DIR, "voice_roster")
ICLOUD_DIR = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/Knowledge Studio Audio")


def get_voice_reference(vertical="ai_tech"):
    """Get the voice reference WAV for a given vertical.

    Falls back to the default reference if no vertical-specific voice exists.
    """
    # Check for vertical-specific voice first
    vertical_ref = os.path.join(VOICE_ROSTER_DIR, f"{vertical}_voice.wav")
    if os.path.exists(vertical_ref):
        return vertical_ref

    # Fall back to default (01 = Grounded Present, top-ranked voice)
    default_ref = os.path.join(VOICE_ROSTER_DIR, "01_grounded_present.wav")
    if os.path.exists(default_ref):
        return default_ref

    # Last resort — any voice reference
    backup = os.path.join(AUDIO_DIR, "voice_reference_Q_backup.wav")
    if os.path.exists(backup):
        return backup

    return None


def get_latest_brief(vertical="ai_tech"):
    """Get the most recent brief for a vertical from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM daily_briefs WHERE vertical = ? ORDER BY created_at DESC LIMIT 1",
        (vertical,)
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def episode_already_exists(brief_id):
    """Check if a podcast episode already exists for this brief."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM brief_podcast_episodes WHERE brief_id = ?",
        (brief_id,)
    )
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def generate_script(brief):
    """Convert a brief to a podcast script using the scriptwriter."""
    from podcast_scriptwriter import rewrite_brief_as_script

    print(f"  Generating script from brief #{brief['id']}...")
    script = rewrite_brief_as_script(brief['content'], vertical=brief['vertical'])
    word_count = len(script.split())
    print(f"  Script: {word_count} words (~{word_count // 150} min spoken)")

    # Save script to file
    date_str = datetime.now().strftime("%Y-%m-%d")
    script_filename = f"podcast_script_{brief['vertical']}_{date_str}.txt"
    script_path = os.path.join(AUDIO_DIR, script_filename)
    with open(script_path, 'w') as f:
        f.write(script)

    return script, script_path


_ROMAN_TO_WORD = {
    'I': 'one', 'II': 'two', 'III': 'three', 'IV': 'four',
    'V': 'five', 'VI': 'six', 'VII': 'seven', 'VIII': 'eight',
    'IX': 'nine', 'X': 'ten', 'XI': 'eleven', 'XII': 'twelve',
}

def _load_pronunciation_rules():
    """Load pronunciation rules from tts_pronunciation.json next to this file."""
    rules_path = os.path.join(PROJECT_DIR, 'tts_pronunciation.json')
    if not os.path.exists(rules_path):
        return [], []
    with open(rules_path) as f:
        data = json.load(f)
    return data.get('literal', []), data.get('pattern', [])


def normalize_text_for_tts(text):
    """Apply pronunciation normalization rules before text hits the TTS model.

    Rules are read from tts_pronunciation.json — edit that file to add/fix rules.
    No restart required; rules are reloaded each time this runs.
    """
    literal_rules, pattern_rules = _load_pronunciation_rules()

    # Apply literal (exact string) replacements first
    for rule in literal_rules:
        find = rule.get('find', '')
        replace = rule.get('replace', '')
        if find and find != replace:  # skip no-op rules (e.g. CRISPR note)
            text = text.replace(find, replace)

    # Catch-all: Phase + any roman numeral not already handled by literals
    def replace_phase_numeral(m):
        numeral = m.group(1)
        word = _ROMAN_TO_WORD.get(numeral.upper())
        return f"Phase {word}" if word else m.group(0)
    text = re.sub(r'\bPhase ([IVX]+)\b', replace_phase_numeral, text)

    # Apply pattern (regex) replacements — skip the Phase placeholder (handled above)
    for rule in pattern_rules:
        find = rule.get('find', '')
        replace = rule.get('replace', '')
        if find and 'PHASE_NUMERAL_PLACEHOLDER' not in find:
            try:
                text = re.sub(find, replace, text)
            except re.error:
                pass  # malformed pattern — skip silently

    return text


def clean_script_for_tts(script):
    """Strip markdown formatting, stage directions, then apply pronunciation normalization."""
    script = re.sub(r'^#+\s+.*$', '', script, flags=re.MULTILINE)
    script = re.sub(r'\*\*\[.*?\]\*\*', '', script)          # **[OPEN]**, **[CLOSE]**, **[SECTION HEADERS]**
    script = re.sub(r'\[.*?\]', '', script)                   # [OPEN], [CLOSE], any remaining bracketed directions
    script = re.sub(r'\*\*([^*]+)\*\*', r'\1', script)
    script = re.sub(r'\*([^*]+)\*', r'\1', script)
    script = re.sub(r'^---+\s*$', '', script, flags=re.MULTILINE)  # horizontal rules
    script = re.sub(r'\n{3,}', '\n\n', script)
    script = normalize_text_for_tts(script)
    script = normalize_sci_tokens(script)  # expand TMEM174-style gene/acronym tokens to spoken form
    return script.strip()


def chunk_script(script, max_words=150):
    """Split script into chunks for TTS processing."""
    paragraphs = [p.strip() for p in script.split('\n\n') if p.strip()]
    chunks = []
    current_chunk = []
    current_words = 0

    for para in paragraphs:
        word_count = len(para.split())
        if current_words + word_count > max_words and current_chunk:
            chunks.append('\n\n'.join(current_chunk))
            current_chunk = [para]
            current_words = word_count
        else:
            current_chunk.append(para)
            current_words += word_count

    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))

    return chunks


def generate_audio_tts(script, voice_ref_path, output_wav_path):
    """Generate audio using Qwen3-TTS voice cloning via mlx-audio.

    Uses MLX (Apple's native ML framework) instead of PyTorch MPS.
    ~3-6 GB RAM vs 48 GB, no GPU memory blowout risk.
    """
    from mlx_audio.tts.generate import generate_audio
    from mlx_audio.tts.utils import load_model
    import mlx.core as mx

    cleaned = clean_script_for_tts(script)
    chunks = chunk_script(cleaned)
    print(f"  TTS: {len(cleaned.split())} words, {len(chunks)} chunks")

    # Load model once — 0.6B for speed/safety, upgrade to 1.7B if quality needs it
    print("  Loading MLX TTS model...")
    model = load_model(model_path="mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16")
    sample_rate = model.sample_rate
    print(f"  Model loaded (sample rate: {sample_rate})")

    # Reference text for voice cloning — avoids loading Whisper for auto-transcription
    ref_text = "Hey, welcome back. Today we are looking at what might actually be the most important shift in AI in the past six months, and it is not what you would expect from reading the headlines."

    all_audio = []
    total_start = time.time()

    for i, chunk in enumerate(chunks):
        print(f"  Chunk {i+1}/{len(chunks)} ({len(chunk.split())} words)...", end="", flush=True)
        start = time.time()

        # Generate to a temp file, then read it back
        temp_prefix = os.path.join(AUDIO_DIR, f"_tts_chunk_{i}")
        generate_audio(
            text=chunk,
            model=model,
            ref_audio=voice_ref_path,
            ref_text=ref_text,
            lang_code="en",
            file_prefix=temp_prefix,
            audio_format="wav",
            join_audio=True,
            verbose=False,
            temperature=0.7,
            max_tokens=4096,
        )

        # Read back the generated chunk
        chunk_file = f"{temp_prefix}.wav"
        if os.path.exists(chunk_file):
            chunk_audio, chunk_sr = sf.read(chunk_file)
            elapsed = time.time() - start
            duration = len(chunk_audio) / chunk_sr
            print(f" {duration:.0f}s audio in {elapsed:.0f}s")

            all_audio.append(chunk_audio)
            silence = np.zeros(int(chunk_sr * 0.5), dtype=chunk_audio.dtype)
            all_audio.append(silence)

            # Clean up temp file
            os.remove(chunk_file)
        else:
            elapsed = time.time() - start
            print(f" FAILED ({elapsed:.0f}s)")

        # Clear MLX cache between chunks
        mx.clear_cache()

    if not all_audio:
        raise RuntimeError("No audio chunks were generated successfully")

    # Concatenate and save
    full_audio = np.concatenate(all_audio)
    total_duration = len(full_audio) / sample_rate
    total_elapsed = time.time() - total_start

    sf.write(output_wav_path, full_audio, sample_rate)

    print(f"  Audio: {total_duration:.0f}s ({total_duration/60:.1f} min) in {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")

    # Cleanup
    del model
    mx.clear_cache()

    return total_duration, sample_rate


def convert_to_mp3(wav_path, mp3_path):
    """Convert WAV to MP3 using ffmpeg."""
    result = subprocess.run(
        ["/opt/homebrew/bin/ffmpeg", "-y", "-i", wav_path, "-b:a", "192k", mp3_path],
        capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")

    size = os.path.getsize(mp3_path)
    print(f"  MP3: {size / 1024 / 1024:.1f} MB")
    return size


def register_episode(brief, script, mp3_filename, mp3_size, duration_seconds):
    """Register the podcast episode in the database and RSS feed."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    from podcast_scriptwriter import generate_episode_title, generate_episode_summary
    title = generate_episode_title(script)
    desc_text = generate_episode_summary(title, script, vertical=brief["vertical"])

    cursor.execute('''
        INSERT INTO brief_podcast_episodes
        (brief_id, vertical, title, description, audio_filename, audio_size, duration_seconds, script_text, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ready')
    ''', (brief['id'], brief['vertical'], title, desc_text, mp3_filename, mp3_size, int(duration_seconds), script))

    conn.commit()
    episode_id = cursor.lastrowid
    conn.close()

    print(f"  Episode #{episode_id} registered: {title}")
    return episode_id


def copy_to_icloud(mp3_path):
    """Copy MP3 to iCloud for phone sync."""
    if os.path.exists(ICLOUD_DIR):
        import shutil
        dest = os.path.join(ICLOUD_DIR, os.path.basename(mp3_path))
        shutil.copy2(mp3_path, dest)
        print(f"  iCloud copy saved")


def run_pipeline(vertical="ai_tech"):
    """Run the full podcast pipeline for a vertical.

    Returns True if an episode was generated, False if skipped.
    """
    print(f"\n🎙️  Podcast pipeline: {vertical}")

    # 1. Get latest brief
    brief = get_latest_brief(vertical)
    if not brief:
        print(f"  No brief found for {vertical}, skipping")
        return False

    # 2. Check if episode already exists for this brief
    if episode_already_exists(brief['id']):
        print(f"  Episode already exists for brief #{brief['id']}, skipping")
        return False

    print(f"  Brief #{brief['id']}: {brief['title']} ({brief['signal_count']} signals)")

    # 3. Check for voice reference
    voice_ref = get_voice_reference(vertical)
    if not voice_ref:
        print(f"  No voice reference found, skipping TTS")
        return False
    print(f"  Voice: {os.path.basename(voice_ref)}")

    # 4. Generate script
    script, script_path = generate_script(brief)

    # 5. Generate audio
    date_str = datetime.now().strftime("%Y-%m-%d")
    wav_filename = f"podcast_{vertical}_{date_str}.wav"
    wav_path = os.path.join(AUDIO_DIR, wav_filename)

    duration, sr = generate_audio_tts(script, voice_ref, wav_path)

    # 6. Convert to MP3
    mp3_filename = f"podcast_{vertical}_{date_str}.mp3"
    mp3_path = os.path.join(AUDIO_DIR, mp3_filename)
    mp3_size = convert_to_mp3(wav_path, mp3_path)

    # 7. Register episode
    register_episode(brief, script, mp3_filename, mp3_size, duration)

    # 8. Copy to iCloud
    copy_to_icloud(mp3_path)

    # 9. Deploy to GitHub Pages
    deploy_to_github_pages()

    print(f"  ✅ Done — {vertical} podcast episode ready")
    return True


def deploy_to_github_pages():
    """Run deploy_podcast.py to update RSS feeds and push to GitHub Pages."""
    try:
        deploy_script = os.path.join(PROJECT_DIR, "deploy_podcast.py")
        if os.path.exists(deploy_script):
            result = subprocess.run(
                [sys.executable, deploy_script],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                print("  📡 GitHub Pages deploy complete")
            else:
                print(f"  ⚠️  GitHub Pages deploy failed: {result.stderr[-200:]}")
        else:
            print("  ⚠️  deploy_podcast.py not found, skipping GitHub Pages deploy")
    except Exception as e:
        print(f"  ⚠️  GitHub Pages deploy error: {e}")


if __name__ == "__main__":
    vertical = sys.argv[1] if len(sys.argv) > 1 else "ai_tech"
    run_pipeline(vertical)

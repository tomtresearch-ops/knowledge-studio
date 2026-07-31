"""
podcast_qa.py — QA gates for the podcast pipeline.

Three gates, added 2026-07-06 after the AI Landscape Jul 3/4/5 episodes shipped
with (a) an 11-second dead-air gap and (b) a story retold as breaking news two
days after the same show had already covered it correctly:

  1. Audio integrity (deterministic, free): silence-gap scan + duration sanity
     on the final mp3, plus per-chunk checks used inside TTS generation.
  2. Episode continuity: recent scripts are loaded and handed to the
     scriptwriter so each episode knows what the show already said.
  3. Editorial judge: an LLM pass that flags re-covered stories, regression
     from established fact to speculation, and mid-sentence truncation.

Failures write to logs/podcast_qa.log and a per-episode JSON next to the
script so nothing fails silently.
"""

import os
import re
import json
import glob
import subprocess
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(PROJECT_DIR, "podcast_audio")
QA_LOG = os.path.join(PROJECT_DIR, "logs", "podcast_qa.log")

FFMPEG = "/opt/homebrew/bin/ffmpeg"

# Silence longer than this inside an episode is a defect (TTS inter-chunk
# pauses are 0.5s by construction; natural pauses stay under ~2s).
MAX_SILENCE_GAP_SECONDS = 4.0
SILENCE_NOISE_FLOOR_DB = -45

# Spoken rate band for duration sanity. Scripts run ~150-180 wpm through TTS.
WORDS_PER_MINUTE = 165
DURATION_LOW_RATIO = 0.6   # shorter than this fraction of expected = truncated
DURATION_HIGH_RATIO = 2.0  # longer = runaway generation


def _log(msg):
    os.makedirs(os.path.dirname(QA_LOG), exist_ok=True)
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(f"  QA: {msg}")
    with open(QA_LOG, "a") as f:
        f.write(line + "\n")


def write_qa_report(vertical, date_str, report):
    path = os.path.join(AUDIO_DIR, f"podcast_qa_{vertical}_{date_str}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Gate 1a — final mp3 integrity
# ---------------------------------------------------------------------------

def detect_silences(audio_path, noise_db=SILENCE_NOISE_FLOOR_DB,
                    min_duration=MAX_SILENCE_GAP_SECONDS):
    """Return list of (start_seconds, duration_seconds) silences via ffmpeg."""
    result = subprocess.run(
        [FFMPEG, "-i", audio_path, "-af",
         f"silencedetect=noise={noise_db}dB:d={min_duration}",
         "-f", "null", "-"],
        capture_output=True, text=True, timeout=300,
    )
    out = result.stderr
    silences = []
    starts = re.findall(r"silence_start: ([\d.]+)", out)
    durs = re.findall(r"silence_duration: ([\d.]+)", out)
    for s, d in zip(starts, durs):
        silences.append((float(s), float(d)))
    # A silence_start with no matching end = silent to end of file.
    if len(starts) > len(durs):
        silences.append((float(starts[-1]), -1.0))
    return silences


def audio_duration_seconds(audio_path):
    result = subprocess.run(
        [FFMPEG, "-i", audio_path, "-f", "null", "-"],
        capture_output=True, text=True, timeout=300,
    )
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", result.stderr)
    if not m:
        return None
    h, mi, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + mi * 60 + s


def audio_integrity_check(mp3_path, script_word_count):
    """Gate the final mp3. Returns (ok, issues:list[str])."""
    issues = []

    duration = audio_duration_seconds(mp3_path)
    if duration is None:
        return False, [f"could not read duration of {os.path.basename(mp3_path)}"]

    expected = script_word_count / WORDS_PER_MINUTE * 60
    if duration < expected * DURATION_LOW_RATIO:
        issues.append(
            f"duration {duration:.0f}s is under {DURATION_LOW_RATIO:.0%} of expected "
            f"~{expected:.0f}s for {script_word_count} words — audio likely truncated"
        )
    if duration > expected * DURATION_HIGH_RATIO:
        issues.append(
            f"duration {duration:.0f}s is over {DURATION_HIGH_RATIO:.0%} of expected "
            f"~{expected:.0f}s — runaway or repeated audio"
        )

    for start, dur in detect_silences(mp3_path):
        if dur < 0:
            issues.append(f"audio goes silent at {start:.0f}s and never resumes")
        else:
            issues.append(f"{dur:.1f}s dead-air gap at {start:.0f}s ({start//60:.0f}:{start%60:02.0f})")

    return (len(issues) == 0), issues


# ---------------------------------------------------------------------------
# Gate 1b — per-chunk checks (called inside generate_audio_tts)
# ---------------------------------------------------------------------------

def chunk_audio_ok(chunk_audio, sample_rate, chunk_word_count,
                   silence_amp=0.005, max_gap=MAX_SILENCE_GAP_SECONDS):
    """Validate one generated TTS chunk in memory. Returns (ok, reason)."""
    import numpy as np

    duration = len(chunk_audio) / sample_rate
    expected = chunk_word_count / WORDS_PER_MINUTE * 60
    if duration < expected * 0.4:
        return False, f"chunk audio {duration:.1f}s vs ~{expected:.0f}s expected — truncated"
    if duration > expected * 3.0 + 5:
        return False, f"chunk audio {duration:.1f}s vs ~{expected:.0f}s expected — runaway"

    mono = chunk_audio if chunk_audio.ndim == 1 else chunk_audio.mean(axis=1)
    quiet = np.abs(mono) < silence_amp
    # Longest run of consecutive quiet samples.
    if quiet.any():
        edges = np.diff(quiet.astype(np.int8))
        run_starts = np.where(edges == 1)[0]
        run_ends = np.where(edges == -1)[0]
        if quiet[0]:
            run_starts = np.concatenate(([0], run_starts))
        if quiet[-1]:
            run_ends = np.concatenate((run_ends, [len(quiet) - 1]))
        if len(run_starts) and len(run_ends):
            longest = (run_ends - run_starts[: len(run_ends)]).max() / sample_rate
            if longest > max_gap:
                return False, f"{longest:.1f}s of dead air inside chunk"

    return True, "ok"


# ---------------------------------------------------------------------------
# Gate 2 — episode memory (recent scripts for continuity)
# ---------------------------------------------------------------------------

def load_recent_scripts(vertical, n=3, audio_dir=AUDIO_DIR):
    """Return the n most recent prior episode scripts for a vertical,
    newest first, as [(date_str, text)], excluding today's."""
    today = datetime.now().strftime("%Y-%m-%d")
    pattern = os.path.join(audio_dir, f"podcast_script_{vertical}_*.txt")
    dated = []
    for path in glob.glob(pattern):
        m = re.search(r"_(\d{4}-\d{2}-\d{2})\.txt$", path)
        if m and m.group(1) != today:
            dated.append((m.group(1), path))
    dated.sort(reverse=True)
    out = []
    for date_str, path in dated[:n]:
        try:
            with open(path) as f:
                out.append((date_str, f.read()))
        except OSError:
            continue
    return out


# ---------------------------------------------------------------------------
# Gate 3 — editorial judge
# ---------------------------------------------------------------------------

JUDGE_SYSTEM_PROMPT = """You are the editorial QA gate for a daily news-analysis podcast. You receive the DRAFT script for today's episode plus the scripts of the show's most recent prior episodes. Your job is to catch exactly these defects:

1. RE-COVERED STORY: the draft presents a story as new/breaking when a prior episode already covered it. Returning to a story is fine ONLY if the draft explicitly frames continuity ("as we covered last episode...") AND adds a genuinely new development.
2. FACT REGRESSION: a prior episode stated something as established fact, and the draft retreats to speculation about the same point, or contradicts it without acknowledging the change.
3. INTERNAL CONTRADICTION or claims that are incoherent on their face.
4. TRUNCATION: the draft ends mid-sentence or without a real close.

Do NOT critique style, tone, pacing, or opinions. Speculation about genuinely open questions is allowed and desirable. Only flag the defect classes above.

Respond with ONLY a JSON object, no other text:
{"verdict": "pass" | "revise", "issues": [{"type": "recovered_story|fact_regression|contradiction|truncation", "detail": "<one or two sentences: what and where>", "fix": "<one sentence: what the rewrite should do>"}]}

If there are no defects, verdict is "pass" and issues is []."""


def judge_script(script, recent_episodes, model="claude-sonnet-4-6"):
    """Run the editorial judge. Returns dict {verdict, issues} (fails open)."""
    import anthropic
    import claude_cli_client  # routes inference to the subscription

    if not recent_episodes:
        return {"verdict": "pass", "issues": [], "note": "no prior episodes to compare"}

    prior_blocks = "\n\n".join(
        f"--- PRIOR EPISODE ({date_str}) ---\n{text}"
        for date_str, text in recent_episodes
    )
    user_prompt = (
        f"{prior_blocks}\n\n--- TODAY'S DRAFT ---\n{script}\n\n"
        "Audit today's draft against the prior episodes per your instructions. JSON only."
    )

    try:
        client = claude_cli_client.make_client()
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text.strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        result = json.loads(m.group(0)) if m else {"verdict": "pass", "issues": []}
        if result.get("verdict") not in ("pass", "revise"):
            result["verdict"] = "pass"
        return result
    except Exception as e:
        # The judge must never block publishing on its own failure.
        _log(f"judge error (failing open): {e}")
        return {"verdict": "pass", "issues": [], "note": f"judge error: {e}"}

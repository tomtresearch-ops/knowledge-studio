#!/usr/bin/env python3
"""Studio Claude-login probe (2026-09-02).

Runs in the GUI launchd context (the only one that can see the login keychain) every 30
minutes and asks the subscription CLI a one-word question. Writes logs/auth_status.json
so the MacBook's poller can ping Tom the moment the Studio is logged out — the Aug 28
expiry went unnoticed for three days and cost the Aug 31 Breakthrough Medicine episode.
"""
import json, os, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "logs", "auth_status.json")
CLAUDE = os.environ.get("CLAUDE_BIN", "/opt/homebrew/bin/claude")
env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
env.setdefault("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin")
status = {"ts": datetime.datetime.now().isoformat(timespec="seconds"), "ok": False, "error": ""}
try:
    r = subprocess.run([CLAUDE, "-p", "Reply with the single word OK.", "--model", "haiku",
                        "--output-format", "text"], capture_output=True, text=True, timeout=120, env=env, cwd=HERE)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    status["ok"] = r.returncode == 0 and "OK" in out.upper()
    if not status["ok"]:
        status["error"] = (err or out)[-300:]
except Exception as exc:
    status["error"] = str(exc)[-300:]
prev = {}
try:
    prev = json.load(open(OUT))
except Exception:
    pass
if status["ok"]:
    status["ok_since"] = prev.get("ok_since") if prev.get("ok") else status["ts"]
    status["failing_since"] = None
else:
    status["ok_since"] = None
    status["failing_since"] = prev.get("failing_since") if (prev and not prev.get("ok")) else status["ts"]
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(status, open(OUT, "w"), indent=2)
print(json.dumps(status))

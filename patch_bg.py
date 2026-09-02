import shutil
p = "/Users/max/knowledge-studio/run_background.py"
shutil.copy(p, p + ".bak-20260902-alerts")
s = open(p).read()
old_grace = "grace_days = {'future_medicine': 7, 'health_longevity': 7, 'ai_tech': 3}"
new_grace = ("# 2026-09-02: tightened so ONE missed slot is caught up the very next night.\n"
             "    # Mon/Thu and Tue/Fri brands are normally 3-4 days apart at the 2:30 run (age 3),\n"
             "    # so age 4 means a slot was missed. 7 let the Aug 31 miss sit for a week.\n"
             "    grace_days = {'future_medicine': 3, 'health_longevity': 3, 'ai_tech': 1}")
assert old_grace in s
s = s.replace(old_grace, new_grace)
old_notify = '''def notify_mattermost(channel, message):
    """Best-effort Mattermost notification. Never blocks the pipeline."""
    try:'''
new_notify = '''def notify_mattermost(channel, message):
    """Best-effort notification. Never blocks the pipeline.

    2026-09-02: Mattermost has no client on the Studio, so every alert since Aug was
    swallowed by the except below. Every call is now ALSO appended to logs/alerts.jsonl,
    which the MacBook's studio_alert_poller reads and escalates to a macOS ping.
    """
    try:
        import json as _json
        from datetime import datetime as _dt
        _log = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "alerts.jsonl")
        with open(_log, "a") as _f:
            _f.write(_json.dumps({"ts": _dt.now().isoformat(timespec="seconds"),
                                  "channel": channel, "message": message}) + "\\n")
    except Exception:
        pass
    try:'''
assert old_notify in s
s = s.replace(old_notify, new_notify)
open(p, "w").write(s)
import py_compile; py_compile.compile(p, doraise=True)
print("patched ok")

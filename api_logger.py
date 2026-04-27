"""
API Usage Logger — Automatic token tracking for all Claude API calls.

Monkey-patches anthropic.Messages.create at the class level so every call
in the process gets logged with zero changes to calling code.

Usage:
    import api_logger
    api_logger.patch()  # Call once at process startup
"""

import os
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'youtube_intelligence.db')

# Model pricing (per 1M tokens) — updated March 2026
MODEL_PRICING = {
    'haiku': {'input': 0.80, 'output': 4.00},
    'sonnet': {'input': 3.00, 'output': 15.00},
    'opus': {'input': 15.00, 'output': 75.00},
}

_patched = False


def ensure_table(db_path=None):
    """Create the api_usage table if it doesn't exist."""
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            call_type TEXT NOT NULL,
            caller_file TEXT,
            caller_function TEXT,
            model TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            cache_read_tokens INTEGER DEFAULT 0,
            cache_creation_tokens INTEGER DEFAULT 0,
            input_cost REAL,
            output_cost REAL,
            total_cost REAL,
            context TEXT
        )
    ''')
    # Index for fast stats queries
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_api_usage_timestamp
        ON api_usage(timestamp)
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_api_usage_call_type
        ON api_usage(call_type)
    ''')
    conn.commit()
    conn.close()


def _get_pricing(model_name):
    """Get input/output pricing for a model."""
    model_lower = (model_name or '').lower()
    for key, prices in MODEL_PRICING.items():
        if key in model_lower:
            return prices
    return MODEL_PRICING['haiku']  # default


def _get_caller():
    """Walk the call stack to find the actual calling code (not anthropic internals)."""
    stack = traceback.extract_stack()
    for frame in reversed(stack):
        fn = frame.filename
        # Skip anthropic SDK, this module, and Python internals
        if ('anthropic' in fn or 'api_logger' in fn or
            fn.startswith('<') or '/lib/python' in fn):
            continue
        filename = os.path.basename(frame.filename).replace('.py', '')
        return filename, frame.name
    return 'unknown', 'unknown'


def _classify_call(caller_file, caller_function):
    """Classify the API call type from caller info."""
    f = caller_file.lower()
    fn = caller_function.lower()

    # Video processing
    if 'youtube_processor' in f:
        if 'shortened' in fn or 'shorten' in fn:
            return 'video_signal_scan'
        if 'summary' in fn or 'generate' in fn:
            return 'video_summary'
        if 'chunk' in fn:
            return 'video_chunk'
        if 'ocr' in fn or 'screenshot' in fn or 'vision' in fn:
            return 'video_ocr'
        return 'video_processing'

    # Screenshot / visual processing
    if 'screenshot' in f or 'visual' in f:
        return 'visual_processing'

    # Brief synthesis
    if 'synthesizer' in f or 'brief' in f:
        return 'brief_synthesis'

    # Newsletter
    if 'newsletter' in f:
        return 'newsletter_generation'

    # Podcast
    if 'podcast' in f or 'scriptwriter' in f:
        return 'podcast_script'

    # Channel intelligence
    if 'channel_intelligence' in f:
        return 'channel_intelligence'

    # App.py — various features
    if f == 'app':
        if 'reprocess' in fn:
            return 'reprocess'
        if 'chat' in fn:
            return 'chat'
        if 'brief' in fn:
            return 'brief_synthesis'
        if 'article' in fn or 'pdf' in fn:
            return 'article_processing'
        if 'highlight' in fn:
            return 'highlight_generation'
        if 'intelligence' in fn:
            return 'intelligence'
        if 'summary' in fn:
            return 'summary'
        return 'app_other'

    return f'{f}:{fn}'


def log_api_usage(response, call_type=None, context="", db_path=None):
    """Log API usage from a Claude response object."""
    try:
        usage = response.usage
        model = response.model
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read = getattr(usage, 'cache_read_input_tokens', 0) or 0
        cache_creation = getattr(usage, 'cache_creation_input_tokens', 0) or 0

        pricing = _get_pricing(model)
        input_cost = (input_tokens / 1_000_000) * pricing['input']
        output_cost = (output_tokens / 1_000_000) * pricing['output']
        total_cost = input_cost + output_cost

        caller_file, caller_function = _get_caller()
        if not call_type:
            call_type = _classify_call(caller_file, caller_function)

        conn = sqlite3.connect(db_path or DB_PATH)
        conn.execute('''
            INSERT INTO api_usage (
                call_type, caller_file, caller_function, model,
                input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens,
                input_cost, output_cost, total_cost, context
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            call_type, caller_file, caller_function, model,
            input_tokens, output_tokens, cache_read, cache_creation,
            input_cost, output_cost, total_cost, context
        ))
        conn.commit()
        conn.close()

        print(f"💰 API: {call_type} | {model} | {input_tokens}in→{output_tokens}out | ${total_cost:.4f}")
    except Exception as e:
        print(f"⚠️ API log failed: {e}")


def patch(db_path=None):
    """Monkey-patch anthropic.Messages.create to auto-log all API calls.

    Call once at process startup. Safe to call multiple times (no-ops after first).
    """
    global _patched
    if _patched:
        return

    # Ensure table exists
    ensure_table(db_path)

    try:
        from anthropic.resources.messages import Messages
        original_create = Messages.create

        def logged_create(self, *args, **kwargs):
            response = original_create(self, *args, **kwargs)
            log_api_usage(response, db_path=db_path)
            return response

        Messages.create = logged_create
        _patched = True
        print("✅ API usage logging enabled")
    except ImportError:
        print("⚠️ anthropic package not found — API logging disabled")
    except Exception as e:
        print(f"⚠️ API logging patch failed: {e}")

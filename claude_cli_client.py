"""
claude_cli_client — drop-in stand-in for `anthropic.Anthropic()` that routes
through the Claude Code CLI (`claude -p`) and therefore Tom's subscription,
instead of the metered Anthropic API.

Why this exists: an exhausted API credit balance silently stopped all podcast
and brief generation on 2026-07-27 (and the pipeline had already been dark
since 2026-07-11 for an unrelated reason). Moving inference onto the
subscription removes the recurring billing failure entirely.

It deliberately mimics the small slice of the SDK surface this codebase
actually uses, verified by reading all 36 live call sites:

    resp = client.messages.create(model=..., max_tokens=..., messages=[...],
                                  system=...)
    text  = resp.content[0].text
    usage = resp.usage.input_tokens / .output_tokens   (14 sites, all counters)

Notes on fidelity:
  * `.usage` returns ESTIMATES. Every one of the 14 call sites only accumulates
    these into cost/stats counters — none branch on them (verified). Estimates
    keep those counters sane rather than crashing on a missing attribute.
  * Image blocks are supported: bytes are written to a temp file and referenced
    by path, which `claude -p` reads. Verified working 2026-07-30.
  * Failures raise ClaudeCLIError so existing `except Exception` blocks in the
    pipeline still catch something, rather than silently returning junk.

Kill switch: set KS_USE_API=1 in the environment to fall back to the real
metered API without editing or redeploying any code.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "/opt/homebrew/bin/claude")
DEFAULT_TIMEOUT = int(os.environ.get("CLAUDE_CLI_TIMEOUT", "600"))


class ClaudeCLIError(RuntimeError):
    """Raised when the CLI fails. Mirrors an SDK exception closely enough that
    existing broad `except` blocks in the pipeline behave the same way."""


class _Usage:
    """Estimated token usage. See module docstring — all consumers are counters."""

    __slots__ = ("input_tokens", "output_tokens")

    def __init__(self, input_tokens: int, output_tokens: int):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _TextBlock:
    __slots__ = ("type", "text")

    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _Response:
    """Shaped like anthropic's Message for the fields this codebase reads."""

    __slots__ = ("content", "usage", "stop_reason", "model")

    def __init__(self, text: str, usage: _Usage, model: str):
        self.content = [_TextBlock(text)]
        self.usage = usage
        self.stop_reason = "end_turn"
        self.model = model


def _estimate_tokens(s: str) -> int:
    # ~4 chars/token is close enough for a cost counter; never used for control flow.
    return max(1, len(s) // 4)


def _flatten_content(content, tmpdir: Path) -> str:
    """Turn SDK-style message content into a single prompt string.

    Image blocks are materialised to disk and referenced by path — `claude -p`
    reads local image files (verified 2026-07-30).
    """
    if isinstance(content, str):
        return content

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            parts.append(str(block))
            continue

        btype = block.get("type")
        if btype == "text":
            parts.append(block.get("text", ""))

        elif btype == "image":
            src = block.get("source", {}) or {}
            if src.get("type") == "base64":
                media = src.get("media_type", "image/png")
                ext = {"image/png": ".png", "image/jpeg": ".jpg",
                       "image/gif": ".gif", "image/webp": ".webp"}.get(media, ".png")
                img_path = tmpdir / f"img_{len(parts)}{ext}"
                try:
                    img_path.write_bytes(base64.b64decode(src.get("data", "")))
                    parts.append(f"[Image file: {img_path}]")
                except Exception as exc:
                    raise ClaudeCLIError(f"could not materialise image block: {exc}") from exc
            elif src.get("type") == "url":
                parts.append(f"[Image URL: {src.get('url', '')}]")
        else:
            # Unknown block type: include a readable form rather than dropping it.
            parts.append(str(block.get("text", block)))

    return "\n\n".join(p for p in parts if p)


class _Messages:
    def __init__(self, parent: "ClaudeCLIClient"):
        self._parent = parent

    def create(self, model: str = None, max_tokens: int = None,
               messages=None, system=None, **kwargs) -> _Response:
        messages = messages or []

        with tempfile.TemporaryDirectory(prefix="ks_claude_") as td:
            tmpdir = Path(td)

            segments: list[str] = []
            for m in messages:
                role = m.get("role", "user")
                body = _flatten_content(m.get("content", ""), tmpdir)
                # Multi-turn is rare here, but label turns so context survives.
                segments.append(body if len(messages) == 1 else f"[{role}]\n{body}")
            prompt = "\n\n".join(segments)

            cmd = [CLAUDE_BIN, "-p"]
            if model:
                cmd += ["--model", model]
            if system:
                sys_text = system if isinstance(system, str) else _flatten_content(system, tmpdir)
                if sys_text:
                    cmd += ["--append-system-prompt", sys_text]

            # CRITICAL: the pipeline loads ANTHROPIC_API_KEY from .env, and the
            # CLI refuses to use the subscription login when any API-key auth
            # source is present ("takes precedence over your claude.ai login").
            # Strip those vars for the child process only — the parent still has
            # them, so the KS_USE_API kill switch keeps working.
            child_env = {
                k: v for k, v in os.environ.items()
                if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
            }

            try:
                proc = subprocess.run(
                    cmd, input=prompt, capture_output=True, text=True,
                    timeout=self._parent.timeout, cwd=td, env=child_env,
                )
            except subprocess.TimeoutExpired as exc:
                raise ClaudeCLIError(
                    f"claude -p timed out after {self._parent.timeout}s") from exc

            if proc.returncode != 0:
                err = (proc.stderr or proc.stdout or "").strip()[:400]
                raise ClaudeCLIError(f"claude -p failed (exit {proc.returncode}): {err}")

            text = (proc.stdout or "").strip()
            if not text:
                raise ClaudeCLIError("claude -p returned empty output")

            return _Response(
                text,
                _Usage(_estimate_tokens(prompt), _estimate_tokens(text)),
                model or "claude-cli",
            )


class ClaudeCLIClient:
    """Stand-in for anthropic.Anthropic(). Only `.messages.create()` is used here."""

    def __init__(self, api_key: str = None, timeout: int = DEFAULT_TIMEOUT, **kwargs):
        # api_key accepted and ignored — call sites pass it; the CLI uses the
        # subscription, so there is nothing to authenticate with here.
        self.timeout = timeout
        self.messages = _Messages(self)


def make_client(api_key: str = None, **kwargs):
    """Factory used at every client-construction point in the pipeline.

    Honours the KS_USE_API kill switch, so reverting to metered billing is an
    environment variable and a restart — no code edit, no redeploy.
    """
    if os.environ.get("KS_USE_API") == "1":
        import anthropic
        return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    if not shutil.which(CLAUDE_BIN) and not Path(CLAUDE_BIN).exists():
        raise ClaudeCLIError(f"claude CLI not found at {CLAUDE_BIN}")
    return ClaudeCLIClient(api_key=api_key, **kwargs)

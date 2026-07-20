"""Pace oTree bots so stress tests do not stampede web workers.

Browser bots (``use_browser_bots=True``) normally auto-submit as soon as the
HTML arrives, which queues every participant on the same Session/DB workers.
We rewrite oTree's injected auto-submit script to ``setTimeout`` so the delay
happens in the browser (workers stay free).

CLI / ``SessionBotRunner`` bots sleep between HTTP submits via
``pace_before_bot_submit``.

Env / session config (ms):
  OTREE_BOT_SUBMIT_DELAY_MS   base delay (default 1500)
  OTREE_BOT_SUBMIT_JITTER_MS  extra 0..jitter spread (default 1000)
  session.config['bot_submit_delay_ms'] / ['bot_submit_jitter_ms'] override env
  Set base delay to 0 to disable.
"""

from __future__ import annotations

import os
import random
import re
import time
from typing import Any, Optional


_INSTALLED = False

# Marker oTree appends in Page.browser_bot_stuff (otree.views.abstract).
_BOT_SUBMIT_MARKER = b"browser-bot-auto-submit"
# Match the immediate submit oTree injects (whitespace-tolerant).
_IMMEDIATE_SUBMIT_RE = re.compile(
    br"(var form = document\.querySelector\('#form'\);\s*)form\.submit\(\);",
    re.MULTILINE,
)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return default


def bot_submit_delay_ms(session: Any = None, participant: Any = None) -> int:
    """Base delay + per-participant jitter so bots do not sync-submit."""
    cfg = getattr(session, "config", None) or {}
    if "bot_submit_delay_ms" in cfg and cfg.get("bot_submit_delay_ms") is not None:
        try:
            base = max(0, int(cfg.get("bot_submit_delay_ms")))
        except (TypeError, ValueError):
            base = _env_int("OTREE_BOT_SUBMIT_DELAY_MS", 1500)
    else:
        base = _env_int("OTREE_BOT_SUBMIT_DELAY_MS", 1500)
    if base <= 0:
        return 0

    if "bot_submit_jitter_ms" in cfg and cfg.get("bot_submit_jitter_ms") is not None:
        try:
            jitter = max(0, int(cfg.get("bot_submit_jitter_ms")))
        except (TypeError, ValueError):
            jitter = _env_int("OTREE_BOT_SUBMIT_JITTER_MS", 1000)
    else:
        jitter = _env_int("OTREE_BOT_SUBMIT_JITTER_MS", 1000)

    if jitter <= 0:
        return base

    pid = 0
    if participant is not None:
        try:
            pid = int(getattr(participant, "id_in_session", 0) or 0)
        except (TypeError, ValueError):
            pid = 0
    # Stable spread across bots in the same session; avoids thundering herd.
    spread = (pid * 137) % (jitter + 1) if pid > 0 else random.randint(0, jitter)
    return base + spread


def pace_before_bot_submit(*, session: Any = None, participant: Any = None) -> float:
    """Sleep before a CLI/SessionBotRunner submit. Returns seconds slept."""
    delay_ms = bot_submit_delay_ms(session, participant)
    if delay_ms <= 0:
        return 0.0
    seconds = delay_ms / 1000.0
    time.sleep(seconds)
    return seconds


def _rewrite_auto_submit_js(body: bytes, delay_ms: int) -> Optional[bytes]:
    if delay_ms <= 0 or _BOT_SUBMIT_MARKER not in body:
        return None
    if not _IMMEDIATE_SUBMIT_RE.search(body):
        return None

    def _repl(match: re.Match[bytes]) -> bytes:
        prefix = match.group(1)
        return (
            prefix
            + f"setTimeout(function () {{ form.submit(); }}, {int(delay_ms)});".encode(
                "utf-8"
            )
        )

    new_body, n = _IMMEDIATE_SUBMIT_RE.subn(_repl, body, count=1)
    return new_body if n else None


def install_browser_bot_submit_delay() -> bool:
    """Patch ``Page.browser_bot_stuff`` once at process start."""
    global _INSTALLED
    if _INSTALLED:
        return True
    try:
        from otree.views.abstract import Page
    except Exception:
        return False

    original = Page.browser_bot_stuff

    def browser_bot_stuff(self, response):
        original(self, response)
        try:
            delay_ms = bot_submit_delay_ms(self.session, self.participant)
            new_body = _rewrite_auto_submit_js(response.body, delay_ms)
            if new_body is None:
                return
            delta = len(new_body) - len(response.body)
            response.body = new_body
            if "Content-Length" in response.headers:
                response.headers["Content-Length"] = str(
                    int(response.headers["Content-Length"]) + delta
                )
        except Exception:
            # Never break page renders if pacing fails.
            return

    Page.browser_bot_stuff = browser_bot_stuff
    _INSTALLED = True
    return True

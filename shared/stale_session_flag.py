"""Timestamped session.vars flags that expire after a crash / hung request.

oTree session.vars are process-local until persisted; a hard kill mid-request can leave
boolean ``in_progress`` / claim flags forever. Storing ``time.time()`` and treating
stale values as free locks recovers automatically without lengthening the happy path.
"""

from __future__ import annotations

import time
from typing import Any, Optional


# Long enough for a healthy trio payoff on a slow DB; short enough that Clever Cloud
# restarts do not strand waiters for minutes. Happy path still clears the flag in finally.
DEFAULT_STALE_TTL_SECONDS = 90.0


def _as_timestamp(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    # Legacy bool True / other truthy: treat as unknown age → stale (recoverable).
    return None


def flag_is_fresh(value: Any, ttl_seconds: float = DEFAULT_STALE_TTL_SECONDS, *, now: Optional[float] = None) -> bool:
    """True if ``value`` is a timestamp still within ``ttl_seconds``."""
    ts = _as_timestamp(value)
    if ts is None:
        return False
    return ((now if now is not None else time.time()) - ts) < float(ttl_seconds)


def try_acquire_timed_flag(
    store: dict,
    key: str,
    ttl_seconds: float = DEFAULT_STALE_TTL_SECONDS,
    *,
    now: Optional[float] = None,
) -> bool:
    """
    Acquire ``store[key] = now`` if missing or stale.

    Returns True if this caller acquired (or stole a stale) flag.
    Returns False if another holder is still within TTL.
    """
    t = now if now is not None else time.time()
    existing = store.get(key)
    if existing is not None and flag_is_fresh(existing, ttl_seconds, now=t):
        return False
    store[key] = t
    return True


def clear_timed_flag(store: dict, key: str) -> None:
    store.pop(key, None)

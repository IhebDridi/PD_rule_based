"""Serialize per-session results-pool mutations across oTree workers."""

from __future__ import annotations

import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Tuple

from sqlalchemy import text

from otree.database import db, engine

# Fallback for SQLite / unknown backends (single-process only).
_fallback_locks: defaultdict[tuple[str, int], threading.Lock] = defaultdict(threading.Lock)


def advisory_lock_id(session: Any, part: int) -> int:
    """Stable 63-bit key for ``pg_advisory_xact_lock``."""
    sid = int(getattr(session, "id", 0) or 0)
    if sid <= 0:
        sid = abs(hash(str(getattr(session, "code", "")))) % (2**30)
    return (sid * 10 + int(part)) & ((1 << 63) - 1)


def normalize_pool_ids(pool: Any) -> List[int]:
    if not isinstance(pool, list):
        return []
    return sorted({int(pid) for pid in pool})


def pop_next_trio_ids(pool: List[int], group_size: int = 3) -> Tuple[Optional[List[int]], List[int]]:
    """
    Deterministic trio selection: lowest ``group_size`` IDs first.
    Returns ``(trio_ids, remaining_pool)`` or ``(None, pool)`` when too few waiters.
    """
    normalized = normalize_pool_ids(pool)
    if len(normalized) < group_size:
        return None, normalized
    trio = normalized[:group_size]
    remaining = [pid for pid in normalized if pid not in trio]
    return trio, remaining


def _refresh_session_state(session: Any) -> None:
    """Reload session.vars from DB after acquiring the lock."""
    try:
        db._db.refresh(session)
    except Exception:
        pass


@contextmanager
def session_part_lock(session: Any, part: int) -> Iterator[None]:
    """
    Hold an exclusive lock for results-pool / batch-formation work for one
    session and experiment part.

    PostgreSQL: transaction-scoped advisory lock (safe across workers).
    Other backends: in-process threading lock (dev / single-worker only).
    """
    dialect = engine.dialect.name
    if dialect == "postgresql":
        lock_id = advisory_lock_id(session, part)
        db._db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
        _refresh_session_state(session)
        yield
    else:
        code = str(getattr(session, "code", id(session)))
        with _fallback_locks[(code, int(part))]:
            _refresh_session_state(session)
            yield

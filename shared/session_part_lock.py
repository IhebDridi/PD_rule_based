"""Serialize per-session results-pool mutations across oTree workers.

IMPORTANT: callers must keep the critical section short (pool mutations only).
Never run payoff computation or whole-session scans while holding the lock —
that freezes unrelated pages via worker starvation and Session-row contention.

PostgreSQL uses *session-level* advisory locks (pg_try_advisory_lock) so the lock
can be released before payoffs run in the same request. Transaction-scoped
xact_lock would stay held until commit and defeat that separation.
"""

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
    """Stable 63-bit key for PostgreSQL advisory locks."""
    sid = int(getattr(session, "id", 0) or 0)
    if sid <= 0:
        sid = abs(hash(str(getattr(session, "code", "")))) % (2**30)
    return (sid * 10 + int(part)) & ((1 << 63) - 1)


def normalize_pool_ids(pool: Any) -> List[int]:
    """Dedupe pool IDs while preserving arrival order (no sort).

    Sorting by id made the same lowest-ID trio retry forever when payoffs soft-failed
    (incomplete choices), blocking later arrivals indefinitely.
    """
    if not isinstance(pool, list):
        return []
    seen = set()
    out: List[int] = []
    for raw in pool:
        pid = int(raw)
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def pop_next_trio_ids(pool: List[int], group_size: int = 3) -> Tuple[Optional[List[int]], List[int]]:
    """
    Trio selection: first ``group_size`` waiters in arrival order.
    Returns ``(trio_ids, remaining_pool)`` or ``(None, pool)`` when too few waiters.
    """
    normalized = normalize_pool_ids(pool)
    if len(normalized) < group_size:
        return None, normalized
    trio = normalized[:group_size]
    remaining = normalized[group_size:]
    return trio, remaining


def _refresh_session_state(session: Any) -> None:
    """Reload session.vars from DB after acquiring the lock."""
    try:
        db._db.refresh(session)
    except Exception:
        pass


def persist_session_state(session: Any = None) -> bool:
    """
    Mid-request commit so peer workers see claim / pool / heartbeat flags.

    Formation unlocks before payoffs; without this flush, Worker B can refresh a
    stale Session row and double-claim the same trio. Returns False if commit fails.
    """
    del session  # session rows are already dirty on the shared ORM session
    try:
        db.commit()
        return True
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return False


@contextmanager
def try_session_part_lock(session: Any, part: int) -> Iterator[bool]:
    """
    Non-blocking lock for results-pool mutations for one session+part.

    Yields ``True`` if this request owns the lock, ``False`` if another request
    already holds it. Releases before the context exits so payoffs / page
    rendering after the block do not hold the lock.
    """
    dialect = getattr(getattr(engine, "dialect", None), "name", "") or ""
    use_pg = dialect == "postgresql" and getattr(db, "_db", None) is not None

    if use_pg:
        lock_id = advisory_lock_id(session, part)
        row = db._db.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id},
        ).fetchone()
        acquired = bool(row[0]) if row is not None else False
        try:
            if acquired:
                _refresh_session_state(session)
            yield acquired
        finally:
            if acquired:
                db._db.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": lock_id},
                )
    else:
        code = str(getattr(session, "code", id(session)))
        lock = _fallback_locks[(code, int(part))]
        acquired = lock.acquire(blocking=False)
        try:
            if acquired:
                _refresh_session_state(session)
            yield acquired
        finally:
            if acquired:
                lock.release()


@contextmanager
def session_part_lock(session: Any, part: int) -> Iterator[None]:
    """
    Blocking exclusive lock for rare paths (e.g. explicit quit). Always unlocks
    before the context exits — do not run payoffs inside this lock.
    """
    dialect = getattr(getattr(engine, "dialect", None), "name", "") or ""
    use_pg = dialect == "postgresql" and getattr(db, "_db", None) is not None

    if use_pg:
        lock_id = advisory_lock_id(session, part)
        db._db.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": lock_id},
        )
        try:
            _refresh_session_state(session)
            yield
        finally:
            db._db.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": lock_id},
            )
    else:
        code = str(getattr(session, "code", id(session)))
        with _fallback_locks[(code, int(part))]:
            _refresh_session_state(session)
            yield

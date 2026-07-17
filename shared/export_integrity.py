"""Record and report grouping / payoff / results-cache failures (live + custom export)."""

from __future__ import annotations

from typing import Any, Callable, Iterable, List, Optional, Sequence, Set

from shared.tg_data_helpers import get_tg_results_display_from_cache


def record_data_error(participant: Any, code: str, detail: str = "") -> None:
    """Append a stable error code on the participant (shown again in custom export)."""
    msg = f"{code}:{detail}" if detail else code
    errors = participant.vars.get("data_integrity_errors")
    if not isinstance(errors, list):
        errors = []
    if msg not in errors:
        errors.append(msg)
    participant.vars["data_integrity_errors"] = errors


def record_data_errors_for_participants(participants: Iterable[Any], code: str, detail: str = "") -> None:
    for participant in participants:
        record_data_error(participant, code, detail)


def participant_batch_for_part(
    session: Any,
    participant_id: int,
    part: int,
    preferred_batch_id: Any = None,
) -> Optional[dict]:
    """
    Return {'batch_id': int, 'member_ids': list} if this participant is listed for the part,
    else None. Uses session.vars keys written by BatchWaitForGroup.

    When ``preferred_batch_id`` is set (successful GroupPartN), that list is preferred so a
    stale provisional key from a failed claim cannot win.
    """
    prefix = f"matching_group_members_part_{part}_"

    def _from_key(batch_id) -> Optional[dict]:
        key = f"{prefix}{batch_id}"
        value = session.vars.get(key)
        if not value or not isinstance(value, (list, tuple)):
            return None
        if participant_id not in value:
            return None
        try:
            bid = int(batch_id)
        except (TypeError, ValueError):
            bid = batch_id
        return {"batch_id": bid, "member_ids": list(value)}

    if preferred_batch_id is not None and preferred_batch_id != "" and preferred_batch_id != -1:
        hit = _from_key(preferred_batch_id)
        if hit is not None:
            return hit

    matches: List[dict] = []
    for key, value in session.vars.items():
        if not isinstance(key, str) or not key.startswith(prefix):
            continue
        if not value or not isinstance(value, (list, tuple)):
            continue
        if participant_id not in value:
            continue
        try:
            batch_id = int(key[len(prefix) :])
        except (TypeError, ValueError):
            batch_id = key[len(prefix) :]
        matches.append({"batch_id": batch_id, "member_ids": list(value)})
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # Multiple lists (should be rare after failed-claim cleanup): prefer highest batch_id.
    def _sort_key(m):
        bid = m["batch_id"]
        try:
            return (0, int(bid))
        except (TypeError, ValueError):
            return (1, str(bid))

    matches.sort(key=_sort_key)
    return matches[-1]

def _part_has_choices(rounds: Sequence[Any], part: int, rounds_per_part: int, get_choice) -> bool:
    start = (part - 1) * rounds_per_part + 1
    end = part * rounds_per_part
    for pr in rounds:
        if start <= pr.round_number <= end:
            ch = get_choice(pr)
            if ch in ("A", "B", "tg"):
                return True
    return False


def _results_cache_ok(participant: Any, part: int, rounds_per_part: int) -> bool:
    cache = participant.vars.get("results_display_cache")
    if not isinstance(cache, dict):
        return False
    part_data = cache.get(f"part_{part}")
    return isinstance(part_data, list) and len(part_data) == rounds_per_part


def collect_export_integrity_errors(
    participant: Any,
    rounds: Sequence[Any],
    C: Any,
    session: Any,
    resolve_opponent: Callable[[Any, int], Any],
    get_choice: Callable[[Any], Any],
    *,
    results_cache_required: bool = False,
) -> List[str]:
    """
    Build human-readable export error messages. Does not invent opponents or payoffs.
    """
    errors: List[str] = []
    stored = participant.vars.get("data_integrity_errors")
    if isinstance(stored, list):
        errors.extend(str(x) for x in stored if x)

    pid = participant.id_in_session
    rounds_per_part = C.rounds_per_part

    for part in (1, 2, 3):
        if not _part_has_choices(rounds, part, rounds_per_part, get_choice):
            continue
        batch = participant_batch_for_part(session, pid, part)
        if batch is None:
            errors.append(f"PART{part}_GROUPING_MISSING")
            continue
        members = batch["member_ids"]
        if len(members) != 3:
            errors.append(f"PART{part}_GROUP_SIZE_{len(members)}")
        if pid not in members:
            errors.append(f"PART{part}_NOT_IN_MEMBER_LIST")

        if results_cache_required and not _results_cache_ok(participant, part, rounds_per_part):
            errors.append(f"PART{part}_RESULTS_CACHE_MISSING")

        start = (part - 1) * rounds_per_part + 1
        end = part * rounds_per_part
        for pr in rounds:
            r = pr.round_number
            if r < start or r > end:
                continue
            choice = get_choice(pr)
            if not choice:
                errors.append(f"R{r}_CHOICE_MISSING")
                continue
            opp = resolve_opponent(pr, r)
            if opp is None:
                errors.append(f"R{r}_NO_BATCH_OPPONENT")
            elif opp.participant.id_in_session not in members:
                errors.append(f"R{r}_OPPONENT_OUTSIDE_BATCH")

    # De-duplicate while preserving order
    seen: Set[str] = set()
    out: List[str] = []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out

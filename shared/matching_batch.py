"""Resolve opponents within a released 3-player matching batch (not the whole oTree group)."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

from shared.export_integrity import participant_batch_for_part
from shared.tg_player_lookup import sorted_trio_at_round

# Cache only plain member-id dicts — never ORM Player instances (those go detached
# across requests and cause DetachedInstanceError on .in_round() / .participant).
# Key: (session_id, part, participant_id, live_gid, preferred_gid)
_BATCH_LOOKUP_CACHE: Dict[Tuple[int, int, int, int, int], Optional[dict]] = {}


def clear_matching_batch_cache() -> None:
    """Test helper."""
    _BATCH_LOOKUP_CACHE.clear()


def resolve_batch_for_participant(
    session: Any,
    participant_id: int,
    part: int,
    *,
    matching_group_id: Any = None,
    preferred_batch_id: Any = None,
) -> Optional[dict]:
    """
    Return {'batch_id', 'member_ids'} for this participant in ``part``.

    Prefers live ``matching_group_id`` + session member list when id >= 0.
    Else prefers durable ``preferred_batch_id`` (GroupPartN).
    After Results resets id to -1, recovers via ``participant_batch_for_part``.
    """
    sid = int(getattr(session, "id", 0) or 0)
    live_id = matching_group_id if matching_group_id is not None and matching_group_id >= 0 else None
    prefer = preferred_batch_id if preferred_batch_id not in (None, "", -1) else None
    try:
        live_k = int(live_id) if live_id is not None else -1
    except (TypeError, ValueError):
        live_k = -1
    try:
        prefer_k = int(prefer) if prefer is not None else -2
    except (TypeError, ValueError):
        prefer_k = -2
    cache_key = (sid, int(part), int(participant_id), live_k, prefer_k)
    if cache_key in _BATCH_LOOKUP_CACHE:
        return _BATCH_LOOKUP_CACHE[cache_key]

    result = None
    lookup_id = live_id if live_id is not None else prefer

    if lookup_id is not None:
        key_members = f"matching_group_members_part_{part}_{lookup_id}"
        member_ids = session.vars.get(key_members)
        if (
            member_ids
            and isinstance(member_ids, (list, tuple))
            and len(member_ids) >= 3
            and participant_id in member_ids
        ):
            result = {"batch_id": int(lookup_id), "member_ids": list(member_ids)}

    if result is None:
        result = participant_batch_for_part(
            session, participant_id, part, preferred_batch_id=prefer
        )

    # Never cache misses: under burst, members/GroupPart may appear moments later.
    # Caching None permanently emptied Results / opponent rows until worker restart.
    if result is not None:
        _BATCH_LOOKUP_CACHE[cache_key] = result
    return result


def opponent_in_matching_batch(
    pr: Any,
    round_number: int,
    C: Any,
    compute_rr: Callable[[int, int], Any],
    rr_cache: dict,
) -> Optional[Any]:
    """
    Return the opponent Player for ``pr`` in ``round_number`` using only
    batch member lists in session.vars (never Subsession/group.get_players()).

    Works even after Results sets ``matching_group_id = -1`` (Parts 1–2).

    Always loads fresh Player rows for ``round_number`` — never reuses cached ORM
    instances from a previous request.
    """
    part = C.get_part(round_number)
    part_start = (part - 1) * C.rounds_per_part + 1
    round_in_part = round_number - part_start
    if round_in_part < 0 or round_in_part >= C.rounds_per_part:
        return None

    my_id = pr.participant.id_in_session
    batch_gid = pr.participant.vars.get("matching_group_id", -1)
    preferred = pr.participant.vars.get(f"group_part_{part}")
    batch = resolve_batch_for_participant(
        pr.session,
        my_id,
        part,
        matching_group_id=batch_gid,
        preferred_batch_id=preferred,
    )
    if not batch:
        return None

    member_ids = batch["member_ids"]
    if my_id not in member_ids or len(member_ids) < 3:
        return None

    N = len(member_ids)
    if N not in rr_cache:
        rr_cache[N] = compute_rr(N, C.rounds_per_part)
    assignments = rr_cache[N]

    my_pos = pr.participant.vars.get(f"group_position_part_{part}")
    if not my_pos or my_pos < 1 or my_pos > N:
        my_pos = pr.participant.vars.get("matching_group_position", None)
    if not my_pos or my_pos < 1 or my_pos > N:
        # Recover position from member_ids order after id reset.
        try:
            my_pos = list(member_ids).index(my_id) + 1
        except ValueError:
            return None
    my_idx = my_pos - 1
    if round_in_part >= len(assignments[my_idx]):
        return None
    opp_idx, _ = assignments[my_idx][round_in_part]
    if opp_idx is None or opp_idx < 0 or opp_idx >= N:
        return None

    # Fresh trio at this round in durable part-seat order (not live rematch position).
    players_r = sorted_trio_at_round(
        pr.session.id, member_ids[:3], round_number, part=part
    )
    if players_r is None or opp_idx >= len(players_r):
        return None
    return players_r[opp_idx]

def get_opponent_from_batch(
    player: Any,
    round_number: int,
    Constants: Any,
    compute_rr: Callable[[int, int], Any],
    rr_cache: Optional[dict] = None,
) -> Optional[Any]:
    """TG/PD shared entry: opponent via batch lists only (no session-wide group scan)."""
    if rr_cache is None:
        rr_cache = {}
    me = player.in_round(round_number)
    return opponent_in_matching_batch(me, round_number, Constants, compute_rr, rr_cache)

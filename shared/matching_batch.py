"""Resolve opponents within a released 3-player matching batch (not the whole oTree group)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from shared.export_integrity import participant_batch_for_part
from shared.tg_player_lookup import sorted_trio_at_round

_BATCH_PLAYERS_CACHE: Dict[Tuple[str, int, int], List[Any]] = {}
_BATCH_LOOKUP_CACHE: Dict[Tuple[int, int, int], Optional[dict]] = {}


def clear_matching_batch_cache() -> None:
    """Test helper."""
    _BATCH_PLAYERS_CACHE.clear()
    _BATCH_LOOKUP_CACHE.clear()


def resolve_batch_for_participant(
    session: Any,
    participant_id: int,
    part: int,
    *,
    matching_group_id: Any = None,
) -> Optional[dict]:
    """
    Return {'batch_id', 'member_ids'} for this participant in ``part``.

    Prefers ``matching_group_id`` + session member list when id >= 0.
    After Results resets id to -1, recovers via ``participant_batch_for_part``.
    """
    sid = int(getattr(session, "id", 0) or 0)
    cache_key = (sid, int(part), int(participant_id))
    if cache_key in _BATCH_LOOKUP_CACHE:
        return _BATCH_LOOKUP_CACHE[cache_key]

    result = None
    if matching_group_id is not None and matching_group_id >= 0:
        key_members = f"matching_group_members_part_{part}_{matching_group_id}"
        member_ids = session.vars.get(key_members)
        if (
            member_ids
            and isinstance(member_ids, (list, tuple))
            and len(member_ids) >= 3
            and participant_id in member_ids
        ):
            result = {"batch_id": int(matching_group_id), "member_ids": list(member_ids)}

    if result is None:
        result = participant_batch_for_part(session, participant_id, part)

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
    """
    part = C.get_part(round_number)
    part_start = (part - 1) * C.rounds_per_part + 1
    round_in_part = round_number - part_start
    if round_in_part < 0 or round_in_part >= C.rounds_per_part:
        return None

    my_id = pr.participant.id_in_session
    batch_gid = pr.participant.vars.get("matching_group_id", -1)
    batch = resolve_batch_for_participant(
        pr.session, my_id, part, matching_group_id=batch_gid
    )
    if not batch:
        return None

    batch_gid = batch["batch_id"]
    member_ids = batch["member_ids"]
    if my_id not in member_ids or len(member_ids) < 3:
        return None

    session = pr.session
    try:
        cache_key = (session.code, part, int(batch_gid))
    except (TypeError, ValueError):
        cache_key = (session.code, part, str(batch_gid))

    players_start = _BATCH_PLAYERS_CACHE.get(cache_key)
    if not players_start:
        players_start = sorted_trio_at_round(session.id, member_ids[:3], part_start)
        if players_start is None:
            return None
        _BATCH_PLAYERS_CACHE[cache_key] = players_start

    N = len(member_ids)
    if N not in rr_cache:
        rr_cache[N] = compute_rr(N, C.rounds_per_part)
    assignments = rr_cache[N]

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
    # players_start is sorted by matching_group_position; index by opp_idx in that order
    if opp_idx >= len(players_start):
        return None
    opp_player_start = players_start[opp_idx]
    return opp_player_start.in_round(round_number)


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

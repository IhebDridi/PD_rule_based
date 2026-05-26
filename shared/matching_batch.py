"""Resolve opponents within a released 3-player matching batch (not the whole oTree group)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

_BATCH_PLAYERS_CACHE: Dict[Tuple[str, int, int], List[Any]] = {}


def opponent_in_matching_batch(
    pr: Any,
    round_number: int,
    C: Any,
    compute_rr: Callable[[int, int], Any],
    rr_cache: dict,
) -> Optional[Any]:
    """
    Return the opponent Player for ``pr`` in ``round_number`` using only
    ``matching_group_id`` + ``matching_group_members_part_{part}_{gid}``.

    Returns None if the participant is not in a released batch or the opponent
    cannot be resolved. Does not use the session-wide oTree group matrix.
    """
    part = C.get_part(round_number)
    part_start = (part - 1) * C.rounds_per_part + 1
    round_in_part = round_number - part_start
    if round_in_part < 0 or round_in_part >= C.rounds_per_part:
        return None

    batch_gid = pr.participant.vars.get("matching_group_id", -1)
    if batch_gid is None or batch_gid < 0:
        return None

    session = pr.session
    key_members = f"matching_group_members_part_{part}_{batch_gid}"
    member_ids = session.vars.get(key_members)
    if not member_ids or not isinstance(member_ids, (list, tuple)) or len(member_ids) < 3:
        return None

    my_id = pr.participant.id_in_session
    if my_id not in member_ids:
        return None

    cache_key = (session.code, part, batch_gid)
    players_start = _BATCH_PLAYERS_CACHE.get(cache_key)
    if not players_start:
        first_round_ss = pr.subsession.in_round(part_start)
        players_start = [
            p
            for p in first_round_ss.get_players()
            if p.participant.id_in_session in member_ids
        ]
        players_start = sorted(
            players_start,
            key=lambda p: p.participant.vars.get("matching_group_position", 0),
        )
        if len(players_start) != 3:
            return None
        _BATCH_PLAYERS_CACHE[cache_key] = players_start

    N = len(member_ids)
    if N not in rr_cache:
        rr_cache[N] = compute_rr(N, C.rounds_per_part)
    assignments = rr_cache[N]

    my_pos = pr.participant.vars.get("matching_group_position", None)
    if not my_pos or my_pos < 1 or my_pos > N:
        return None
    my_idx = my_pos - 1
    if round_in_part >= len(assignments[my_idx]):
        return None
    opp_idx, _ = assignments[my_idx][round_in_part]
    if opp_idx is None or opp_idx < 0 or opp_idx >= N:
        return None
    opp_player_start = players_start[opp_idx]
    return opp_player_start.in_round(round_number)

"""Resolve a few Player rows without scanning the whole subsession.

Used by matching, payoffs, Results, and BatchWait so large sessions (100–300)
never call Subsession.get_players() on the hot path. Data written to Player/
Participant fields is unchanged — only lookup cost changes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from otree.database import db
from otree.models import Participant


def participants_by_id_in_session(session_id: int, ids: Sequence[int]) -> Dict[int, Any]:
    wanted = [int(i) for i in ids]
    if not wanted:
        return {}
    rows = (
        db.query(Participant)
        .filter(
            Participant.session_id == session_id,
            Participant.id_in_session.in_(wanted),
        )
        .all()
    )
    return {p.id_in_session: p for p in rows}


def player_in_round_for_participant(participant, round_number: int):
    for pl in participant.get_players():
        if getattr(pl, "round_number", None) == round_number:
            return pl
    return None


def players_at_round_for_member_ids(
    session_id: int,
    member_ids: Sequence[int],
    round_number: int,
) -> Optional[List[Any]]:
    """
    Return Player rows for ``member_ids`` at ``round_number``, preserving order.
    Does not call Subsession.get_players() (which loads every participant).
    """
    pmap = participants_by_id_in_session(session_id, member_ids)
    out: List[Any] = []
    for mid in member_ids:
        part = pmap.get(int(mid))
        if part is None:
            return None
        pl = player_in_round_for_participant(part, round_number)
        if pl is None:
            return None
        out.append(pl)
    return out


def sorted_trio_at_round(
    session_id: int,
    member_ids: Sequence[int],
    round_number: int,
    *,
    part: Optional[int] = None,
) -> Optional[List[Any]]:
    """
    Trio in seat order for this matching batch.

    Prefer durable ``group_position_part_{part}``. Do **not** sort by live
    ``matching_group_position`` — that field is overwritten on every rematch, so
    using it after Part 2/3 scrambles Parts 1–2 opponent / Coplayer* export.

    Fallback: ``member_ids`` claim order (index 0 = seat 1 when the batch formed).
    """
    mids = [int(x) for x in list(member_ids)[:3]]
    players = players_at_round_for_member_ids(session_id, mids, round_number)
    if players is None or len(players) != 3:
        return None

    if part is not None:
        pos_key = f"group_position_part_{int(part)}"

        def _part_pos(p: Any) -> int:
            raw = p.participant.vars.get(pos_key)
            try:
                return int(raw) if raw is not None else 0
            except (TypeError, ValueError):
                return 0

        if all(_part_pos(p) >= 1 for p in players):
            return sorted(
                players,
                key=lambda p: (_part_pos(p), p.participant.id_in_session),
            )

    # Claim order is the durable seat map when part positions are missing.
    by_id = {int(p.participant.id_in_session): p for p in players}
    ordered = [by_id[mid] for mid in mids if mid in by_id]
    if len(ordered) == 3:
        return ordered
    return players

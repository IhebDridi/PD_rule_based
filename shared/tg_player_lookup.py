"""Resolve a few Player rows without scanning the whole subsession."""

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

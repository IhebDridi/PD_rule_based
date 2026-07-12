"""Build per-round Results diagrams for TG (group + roles + choices + payoffs)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from shared.tg_payoffs import compute_tg_payoffs, tg_results_row


def _sid(p) -> Optional[int]:
    if p is None:
        return None
    return p.participant.id_in_session


def _label(sid: Optional[int], my_sid: int) -> str:
    if sid is None:
        return "?"
    if sid == my_sid:
        return f"P{sid} (you)"
    return f"P{sid}"


def _role_short(assigned: Optional[str]) -> str:
    if assigned == "first":
        return "1st mover"
    if assigned == "second":
        return "2nd mover"
    return "—"


def _member_snapshot(me_round, opp, my_sid: int) -> Dict[str, Any]:
    row = tg_results_row(me_round, opp)
    assigned = me_round.field_maybe_none("role_assigned")
    first_c = me_round.field_maybe_none("choice_first_mover")
    second_c = me_round.field_maybe_none("choice_second_mover")
    return {
        "id": my_sid,
        "label": _label(my_sid, my_sid),  # overwritten by caller for non-you
        "role": row.get("role_assigned") or _role_short(assigned),
        "role_code": assigned,
        "my_choice": row.get("my_choice"),
        "other_choice": row.get("other_choice"),
        "payoff": row.get("payoff"),
        "choice_first": first_c,
        "choice_second": second_c,
        "opponent_id": _sid(opp),
    }


def build_tg_round_diagrams(
    player,
    part_start: int,
    part_end: int,
    current_part: int,
    get_opponent_in_round: Callable,
    rounds_per_part: int = 10,
) -> Dict[str, Any]:
    """
    Return group overview + one diagram dict per round in the part.

    Each round diagram lists all trio members (from the viewing player's DB)
    with role, opponent, choices that counted, and payoff.
    """
    my_sid = player.participant.id_in_session
    gid = player.participant.vars.get("matching_group_id", -1)
    member_ids: List[int] = []
    if gid is not None and gid >= 0:
        raw = player.session.vars.get(f"matching_group_members_part_{current_part}_{gid}")
        if raw and isinstance(raw, (list, tuple)):
            member_ids = list(raw)

    my_pos = player.participant.vars.get("matching_group_position")

    member_labels = [_label(i, my_sid) for i in member_ids]
    overview = {
        "matching_group_id": gid,
        "member_ids": member_ids,
        "my_id": my_sid,
        "my_position": my_pos,
        "member_labels": member_labels,
        "member_labels_text": " · ".join(member_labels) if member_labels else "",
    }

    rounds: List[Dict[str, Any]] = []
    for r in range(part_start, part_end + 1):
        round_in_part = r - (current_part - 1) * rounds_per_part
        round_ss = player.subsession.in_round(r)
        by_sid = {
            p.participant.id_in_session: p
            for p in round_ss.get_players()
            if not member_ids or p.participant.id_in_session in member_ids
        }

        members_out: List[Dict[str, Any]] = []
        ids_for_round = member_ids or [my_sid]
        for sid in ids_for_round:
            p = by_sid.get(sid)
            if p is None:
                continue
            opp = get_opponent_in_round(p, r)
            snap = _member_snapshot(p, opp, sid)
            snap["label"] = _label(sid, my_sid)
            snap["is_you"] = sid == my_sid
            snap["opponent_label"] = _label(_sid(opp), my_sid)
            members_out.append(snap)

        me = by_sid.get(my_sid) or player.in_round(r)
        my_opp = get_opponent_in_round(player, r)
        my_row = tg_results_row(me, my_opp)
        assigned = me.field_maybe_none("role_assigned")

        first_move = None
        second_move = None
        if assigned == "first":
            first_move = me.field_maybe_none("choice_first_mover")
            second_move = (
                my_opp.field_maybe_none("choice_second_mover") if my_opp else None
            )
        elif assigned == "second":
            first_move = (
                my_opp.field_maybe_none("choice_first_mover") if my_opp else None
            )
            second_move = me.field_maybe_none("choice_second_mover")

        outcome_note = ""
        if first_move == "B":
            outcome_note = "1st chose B → both earn 30 (2nd choice ignored for payoffs)."
        elif first_move == "A" and second_move == "A":
            outcome_note = "1st A + 2nd A → both earn 70."
        elif first_move == "A" and second_move == "B":
            outcome_note = "1st A + 2nd B → 1st earns 0, 2nd earns 100."

        # You vs opponent edge (primary visual)
        you_node = {
            "label": _label(my_sid, my_sid),
            "role": my_row.get("role_assigned") or _role_short(assigned),
            "choice": my_row.get("my_choice"),
            "payoff": my_row.get("payoff"),
            "is_first": assigned == "first",
        }
        opp_node = {
            "label": _label(_sid(my_opp), my_sid),
            "role": (
                "2nd mover"
                if assigned == "first"
                else ("1st mover" if assigned == "second" else "—")
            ),
            "choice": my_row.get("other_choice"),
            "payoff": None,
            "is_first": assigned == "second",
        }
        if my_opp is not None and first_move in ("A", "B") and second_move in ("A", "B"):
            pf, ps = compute_tg_payoffs(first_move, second_move)
            if assigned == "first":
                opp_node["payoff"] = ps
            elif assigned == "second":
                opp_node["payoff"] = pf

        third_ids = [
            i for i in ids_for_round if i not in (my_sid, _sid(my_opp))
        ]
        third_nodes = []
        for tid in third_ids:
            for m in members_out:
                if m["id"] == tid:
                    third_nodes.append(
                        {
                            "label": m["label"],
                            "role": m["role"],
                            "choice": m["my_choice"],
                            "payoff": m["payoff"],
                            "opponent_label": m["opponent_label"],
                        }
                    )
                    break

        rounds.append(
            {
                "round": round_in_part,
                "you": you_node,
                "opponent": opp_node,
                "third": third_nodes,
                "members": members_out,
                "first_move": first_move,
                "second_move": second_move,
                "outcome_note": outcome_note,
                "your_payoff": my_row.get("payoff"),
            }
        )

    return {"overview": overview, "rounds": rounds}

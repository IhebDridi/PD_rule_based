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


def _plain_label(label: str) -> str:
    return label.replace(" (you)", "").strip()


def _build_round_narrative(
    *,
    round_num: int,
    you_label: str,
    opp_label: str,
    assigned: Optional[str],
    first_move: Optional[str],
    second_move: Optional[str],
    your_payoff: Optional[int],
    opp_payoff: Optional[int],
    third_nodes: List[Dict[str, Any]],
) -> str:
    """Plain-language summary of what happened in this round for the viewing player."""
    you = _plain_label(you_label)
    opp = _plain_label(opp_label)
    parts: List[str] = [
        f"In round {round_num} you ({you}) were matched with {opp}."
    ]

    if assigned == "first":
        first_name, second_name = you, opp
    elif assigned == "second":
        first_name, second_name = opp, you
    else:
        parts.append("Roles were not recorded for this round.")
        if your_payoff is not None:
            parts.append(f"You earned {your_payoff} Ecoins.")
        return " ".join(parts)

    if first_move not in ("A", "B") or second_move not in ("A", "B"):
        parts.append(
            f"{first_name} was assigned 1st mover; {second_name} was assigned 2nd mover, "
            "but contingent choices are incomplete in the database."
        )
        if your_payoff is not None:
            parts.append(f"You earned {your_payoff} Ecoins.")
        return " ".join(parts)

    parts.append(
        f"Roles were assigned randomly: {first_name} was the 1st mover and chose {first_move}; "
        f"{second_name} was the 2nd mover and chose {second_move}."
    )

    if first_move == "B":
        parts.append(
            f"Because the 1st mover chose B, both players received 30 Ecoins "
            f"({second_name}'s choice of {second_move} is shown for transparency but did not change payoffs)."
        )
    elif first_move == "A" and second_move == "A":
        parts.append("Both players chose A, so each received 70 Ecoins.")
    elif first_move == "A" and second_move == "B":
        parts.append(
            f"The 1st mover chose A and the 2nd mover chose B, so {first_name} received 0 Ecoins "
            f"and {second_name} received 100 Ecoins."
        )

    if your_payoff is not None and opp_payoff is not None:
        parts.append(f"You earned {your_payoff} Ecoins; {opp} earned {opp_payoff} Ecoins.")
    elif your_payoff is not None:
        parts.append(f"You earned {your_payoff} Ecoins.")

    if third_nodes:
        third_bits = []
        for t in third_nodes:
            t_label = _plain_label(t.get("label", "?"))
            t_opp = _plain_label(t.get("opponent_label", "?"))
            t_pay = t.get("payoff")
            t_role = t.get("role", "—")
            pay_str = f"{t_pay} Ecoins" if t_pay is not None else "— Ecoins"
            third_bits.append(
                f"{t_label} (your other trio member) played against {t_opp} as {t_role} and earned {pay_str}"
            )
        parts.append("Meanwhile, " + "; ".join(third_bits) + ".")

    return " ".join(parts)


def annotate_diagrams_with_debug(
    round_diagrams: List[Dict[str, Any]],
    debug_rounds: Optional[List[Dict[str, Any]]],
) -> None:
    """Attach display-vs-DB mismatch flags to diagram rows (dev integrity UI)."""
    if not debug_rounds:
        for d in round_diagrams:
            d.setdefault("has_mismatch", False)
            d.setdefault("mismatch_flags", [])
            d.setdefault("mismatch_detail", "")
        return

    by_round = {row["round"]: row for row in debug_rounds}
    for d in round_diagrams:
        dbg = by_round.get(d["round"])
        d["has_mismatch"] = bool(dbg and dbg.get("warn"))
        d["mismatch_flags"] = list(dbg.get("flags") or []) if dbg else []
        mismatch = dbg.get("mismatch") if dbg else None
        d["mismatch_detail"] = (mismatch or {}).get("summary", "") if mismatch else ""


def build_all_rounds_tree(
    overview: Dict[str, Any],
    round_diagrams: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compact tree of all rounds for one participant — verify trio + per-round opponents
    and which contingent choices from others fed into this player's payoffs.
    """
    branches: List[Dict[str, Any]] = []
    for d in round_diagrams:
        opp_label = d.get("opponent", {}).get("label", "?")
        opp_member = None
        for m in d.get("members") or []:
            if m.get("label") == opp_label:
                opp_member = m
                break

        opp_affecting = d.get("opponent", {}).get("choice")
        assigned = d.get("you", {}).get("role", "")
        if assigned == "1st mover":
            opp_move_used = (
                f"2nd-mover contingency → {opp_affecting}"
                if opp_affecting is not None
                else "2nd-mover contingency → —"
            )
        elif assigned == "2nd mover":
            opp_move_used = (
                f"1st-mover contingency → {opp_affecting}"
                if opp_affecting is not None
                else "1st-mover contingency → —"
            )
        else:
            opp_move_used = "—"

        third = (d.get("third") or [None])[0]
        branches.append(
            {
                "round": d["round"],
                "opponent_label": opp_label,
                "your_role": d.get("you", {}).get("role", "—"),
                "your_choice": d.get("you", {}).get("choice"),
                "your_payoff": d.get("your_payoff"),
                "opp_choice_in_game": opp_affecting,
                "opp_contingent_first": (
                    opp_member.get("choice_first") if opp_member else None
                ),
                "opp_contingent_second": (
                    opp_member.get("choice_second") if opp_member else None
                ),
                "opp_move_used_label": opp_move_used,
                "first_move": d.get("first_move"),
                "second_move": d.get("second_move"),
                "third_label": third.get("label") if third else None,
                "third_opponent_label": third.get("opponent_label") if third else None,
                "third_role": third.get("role") if third else None,
                "third_payoff": third.get("payoff") if third else None,
                "has_mismatch": d.get("has_mismatch", False),
            }
        )

    return {
        "trio_text": overview.get("member_labels_text", ""),
        "my_position": overview.get("my_position"),
        "matching_group_id": overview.get("matching_group_id"),
        "show_batch_id": (
            overview.get("matching_group_id") is not None
            and overview.get("matching_group_id") >= 0
        ),
        "round_count": len(branches),
        "branches": branches,
    }


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

        opp_payoff: Optional[int] = None
        if my_opp is not None and first_move in ("A", "B") and second_move in ("A", "B"):
            pf, ps = compute_tg_payoffs(first_move, second_move)
            if assigned == "first":
                opp_payoff = ps
            elif assigned == "second":
                opp_payoff = pf

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
                            "node_status": "third",
                        }
                    )
                    break

        round_narrative = _build_round_narrative(
            round_num=round_in_part,
            you_label=_label(my_sid, my_sid),
            opp_label=_label(_sid(my_opp), my_sid),
            assigned=assigned,
            first_move=first_move,
            second_move=second_move,
            your_payoff=my_row.get("payoff"),
            opp_payoff=opp_payoff,
            third_nodes=third_nodes,
        )

        you_node = {
            "label": _label(my_sid, my_sid),
            "role": my_row.get("role_assigned") or _role_short(assigned),
            "choice": my_row.get("my_choice"),
            "payoff": my_row.get("payoff"),
            "is_first": assigned == "first",
            "node_status": "you",
        }
        opp_node = {
            "label": _label(_sid(my_opp), my_sid),
            "role": (
                "2nd mover"
                if assigned == "first"
                else ("1st mover" if assigned == "second" else "—")
            ),
            "choice": my_row.get("other_choice"),
            "payoff": opp_payoff,
            "is_first": assigned == "second",
            "node_status": "opponent",
        }

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
                "round_narrative": round_narrative,
                "your_payoff": my_row.get("payoff"),
                "has_mismatch": False,
                "mismatch_flags": [],
                "mismatch_detail": "",
            }
        )

    return {"overview": overview, "rounds": rounds}

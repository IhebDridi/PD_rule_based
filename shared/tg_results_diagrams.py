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
    Structural grouping graph for Results.

    Per round:
      players → R{n}_1st / R{n}_2nd contingency nodes
      → one group per directed edge (focal → opponent)
      → YOUR official match is the only group stored on the viewer's DB row
      → other groups are other players' directed matches (illustration only)
    """
    member_labels = overview.get("member_labels") or []
    stages: List[Dict[str, Any]] = []

    for d in round_diagrams:
        rn = d["round"]
        players: List[Dict[str, Any]] = []
        contingencies: List[Dict[str, Any]] = []

        for m in d.get("members") or []:
            role_code = m.get("role_code")
            c1 = m.get("choice_first")
            c2 = m.get("choice_second")
            pid = m.get("id")
            label = m.get("label")
            is_you = bool(m.get("is_you"))
            selected_first = role_code == "first"
            selected_second = role_code == "second"

            players.append(
                {
                    "id": pid,
                    "label": label,
                    "plain": _plain_label(label or "?"),
                    "is_you": is_you,
                    "role": m.get("role") or "—",
                    "role_code": role_code,
                    "opponent_label": m.get("opponent_label"),
                    "payoff": m.get("payoff"),
                }
            )
            contingencies.append(
                {
                    "node_id": f"r{rn}_p{pid}_1st",
                    "player_id": pid,
                    "player_label": label,
                    "plain": _plain_label(label or "?"),
                    "is_you": is_you,
                    "kind": "1st",
                    "kind_label": f"R{rn}_1st",
                    "choice": c1,
                    "selected": selected_first,
                    "title": f"R{rn} · {_plain_label(label or '?')} · if 1st",
                }
            )
            contingencies.append(
                {
                    "node_id": f"r{rn}_p{pid}_2nd",
                    "player_id": pid,
                    "player_label": label,
                    "plain": _plain_label(label or "?"),
                    "is_you": is_you,
                    "kind": "2nd",
                    "kind_label": f"R{rn}_2nd",
                    "choice": c2,
                    "selected": selected_second,
                    "title": f"R{rn} · {_plain_label(label or '?')} · if 2nd",
                }
            )

        by_id = {p["id"]: p for p in players if p.get("id") is not None}
        by_plain = {_plain_label(p["label"]): p for p in players}

        # One group per directed edge (focal → opponent). Only the viewer's
        # directed edge is their official Results/DB match.
        groups: List[Dict[str, Any]] = []
        for m in d.get("members") or []:
            me = by_id.get(m.get("id")) or by_plain.get(_plain_label(m.get("label") or ""))
            if me is None:
                continue
            opp_plain = _plain_label(m.get("opponent_label") or "")
            opp = by_plain.get(opp_plain)
            if opp is None:
                continue

            if me.get("role_code") == "first":
                first_p, second_p = me, opp
            elif me.get("role_code") == "second":
                first_p, second_p = opp, me
            else:
                continue

            first_choice = next(
                (
                    c["choice"]
                    for c in contingencies
                    if c["player_id"] == first_p["id"] and c["kind"] == "1st"
                ),
                None,
            )
            second_choice = next(
                (
                    c["choice"]
                    for c in contingencies
                    if c["player_id"] == second_p["id"] and c["kind"] == "2nd"
                ),
                None,
            )

            pay_first = pay_second = None
            if first_choice in ("A", "B") and second_choice in ("A", "B"):
                pay_first, pay_second = compute_tg_payoffs(first_choice, second_choice)

            # Official earnings for the focal player: prefer their stored DB payoff
            # when this is your match; otherwise illustrate with recomputed payoffs.
            if me.get("is_you") and me.get("payoff") is not None:
                focal_pay = me.get("payoff")
            elif me.get("role_code") == "first":
                focal_pay = pay_first if pay_first is not None else me.get("payoff")
            else:
                focal_pay = pay_second if pay_second is not None else me.get("payoff")

            groups.append(
                {
                    "id": f"r{rn}_focal_{me['plain']}_vs_{opp['plain']}",
                    "focal_label": me["label"],
                    "focal_plain": me["plain"],
                    "focal_is_you": me["is_you"],
                    "is_your_official_match": me["is_you"],
                    "involves_you": me["is_you"],
                    "opponent_label": opp["label"],
                    "first_label": first_p["label"],
                    "second_label": second_p["label"],
                    "first_choice": first_choice,
                    "second_choice": second_choice,
                    "first_plain": first_p["plain"],
                    "second_plain": second_p["plain"],
                    "pay_first": pay_first,
                    "pay_second": pay_second,
                    "focal_payoff": focal_pay,
                    "link_caption": (
                        f"{first_p['plain']}·R{rn}_1st({first_choice}) + "
                        f"{second_p['plain']}·R{rn}_2nd({second_choice})"
                    ),
                    "recipients": [
                        {
                            "label": me["label"],
                            "plain": me["plain"],
                            "is_you": me["is_you"],
                            "is_focal": True,
                            "role": me.get("role"),
                            "payoff": focal_pay,
                        }
                    ],
                    "note_other": (
                        None
                        if me["is_you"]
                        else (
                            f"This is {me['plain']}'s directed match (opponent {opp['plain']}). "
                            "Only that player's DB row is written for this edge — not yours."
                        )
                    ),
                }
            )

        columns = []
        for p in players:
            cols_c = [c for c in contingencies if c["player_id"] == p["id"]]
            columns.append({"player": p, "contingencies": cols_c})

        official = next((g for g in groups if g["is_your_official_match"]), None)
        your_outcome = None
        if official is not None:
            you_snap = d.get("you") or {}
            role_label = (you_snap.get("role") or "").lower()
            if "1st" in role_label or you_snap.get("is_first") is True:
                your_role, other_role = "1st mover", "2nd mover"
                your_choice = official["first_choice"]
                other_choice = official["second_choice"]
            elif "2nd" in role_label or you_snap.get("is_first") is False:
                your_role, other_role = "2nd mover", "1st mover"
                your_choice = official["second_choice"]
                other_choice = official["first_choice"]
            elif official.get("focal_plain") == official.get("first_plain"):
                your_role, other_role = "1st mover", "2nd mover"
                your_choice = official["first_choice"]
                other_choice = official["second_choice"]
            else:
                your_role, other_role = "2nd mover", "1st mover"
                your_choice = official["second_choice"]
                other_choice = official["first_choice"]

            pay = official.get("focal_payoff")
            if pay is None:
                pay = d.get("your_payoff")
            your_outcome = {
                "your_role": your_role,
                "your_choice": your_choice,
                "other_role": other_role,
                "other_choice": other_choice,
                "payoff": pay,
                "summary": (
                    f"Round {rn}: your choice as {your_role} {{{your_choice}}} + "
                    f"other choice as {other_role} {{{other_choice}}} = {{{pay}}}"
                ),
            }

        stages.append(
            {
                "round": rn,
                "columns": columns,
                "contingencies": contingencies,
                "groups": groups,
                "your_official_group": official,
                "your_outcome": your_outcome,
                "your_groups": [g for g in groups if g["is_your_official_match"]],
                "has_mismatch": d.get("has_mismatch", False),
                "mismatch_detail": d.get("mismatch_detail", ""),
                "your_payoff": d.get("your_payoff"),
            }
        )

    n_stages = len(stages)
    for i, stage in enumerate(stages):
        stage["is_first"] = i == 0
        stage["is_last"] = i == n_stages - 1

    return {
        "trio_text": overview.get("member_labels_text", ""),
        "member_labels": member_labels,
        "member_chips": overview.get("member_chips")
        or [{"label": lab, "is_you": False} for lab in member_labels],
        "my_position": overview.get("my_position"),
        "matching_group_id": overview.get("matching_group_id"),
        "show_batch_id": (
            overview.get("matching_group_id") is not None
            and overview.get("matching_group_id") >= 0
        ),
        "round_count": n_stages,
        "stages": stages,
        "branches": [
            {"round": s["round"], "has_mismatch": s["has_mismatch"], "your_payoff": s["your_payoff"]}
            for s in stages
        ],
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
        "member_chips": [
            {"label": _label(i, my_sid), "is_you": i == my_sid} for i in member_ids
        ],
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

"""Dev-only TG Results: compare on-screen rows vs raw Player DB fields."""

from __future__ import annotations

import os
from typing import Any, Callable, List, Optional

from shared.tg_payoffs import tg_results_row


def _otree_debug_mode() -> bool:
    """True when oTree runs in dev (same rule as otree.settings.DEBUG)."""
    return os.environ.get("OTREE_PRODUCTION") in (None, "", "0")


def _payoff_int(player) -> Optional[int]:
    if player.payoff is None:
        return None
    raw = getattr(player.payoff, "amount", player.payoff)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _opp_pos(opponent) -> str:
    if opponent is None:
        return ""
    pos = opponent.participant.vars.get("matching_group_position")
    if pos is not None and pos != "" and pos != -1:
        return str(pos)
    return str(getattr(opponent.participant, "id_in_session", "") or "")


def build_tg_results_debug(
    player,
    part_start: int,
    part_end: int,
    current_part: int,
    get_opponent_in_round: Callable[[Any, int], Any],
    *,
    rounds_per_part: int = 10,
) -> Optional[dict]:
    """
    Return display + DB row dicts for the oTree debug card (DEBUG mode only).

    Each compare row has parallel ``display`` and ``db`` sub-dicts plus ``flags``.
    """
    if not _otree_debug_mode():
        return None

    rows: List[dict] = []
    flags_by_round: dict = {}
    for r in range(part_start, part_end + 1):
        rr = player.in_round(r)
        opp = get_opponent_in_round(player, r)
        display = tg_results_row(rr, opp)
        display_round = r - (current_part - 1) * rounds_per_part

        db = {
            "otree_round": r,
            "role_assigned": rr.field_maybe_none("role_assigned"),
            "choice_first_mover": rr.field_maybe_none("choice_first_mover"),
            "choice_second_mover": rr.field_maybe_none("choice_second_mover"),
            "payoff": _payoff_int(rr),
            "opponent_pos": _opp_pos(opp),
            "opponent_role_assigned": opp.field_maybe_none("role_assigned") if opp else None,
            "opponent_choice_first_mover": (
                opp.field_maybe_none("choice_first_mover") if opp else None
            ),
            "opponent_choice_second_mover": (
                opp.field_maybe_none("choice_second_mover") if opp else None
            ),
            "opponent_payoff": _payoff_int(opp) if opp else None,
        }

        flags = []
        if display.get("payoff") != db.get("payoff"):
            flags.append("payoff_mismatch")
        role = db.get("role_assigned")
        if role == "first" and display.get("my_choice") != db.get("choice_first_mover"):
            flags.append("my_choice_mismatch")
        elif role == "second" and display.get("my_choice") != db.get("choice_second_mover"):
            flags.append("my_choice_mismatch")
        elif role not in ("first", "second") and display.get("my_choice"):
            flags.append("my_choice_without_role")

        flags_str = ", ".join(flags) if flags else "ok"

        rows.append(
            {
                "round": display_round,
                "display": {
                    "role_assigned": display.get("role_assigned"),
                    "my_choice": display.get("my_choice"),
                    "other_choice": display.get("other_choice"),
                    "payoff": display.get("payoff"),
                },
                "db": db,
                "warn": bool(flags),
            }
        )
        flags_by_round[display_round] = flags_str

    mismatch_count = sum(1 for row in rows if row["warn"])
    summary_vars: dict = {
        "tg_debug_part": current_part,
        "tg_debug_all_ok": mismatch_count == 0,
        "tg_debug_mismatch_count": mismatch_count,
    }
    for rnd, flag in flags_by_round.items():
        summary_vars[f"tg_debug_R{rnd}_flag"] = flag

    return {
        "part": current_part,
        "rounds": rows,
        "summary_vars": summary_vars,
    }

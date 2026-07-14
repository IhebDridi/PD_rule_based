"""Dev-only TG Results: compare on-screen rows vs raw Player DB fields."""

from __future__ import annotations

import os
from typing import Any, Callable, List, Optional, Tuple

from shared.tg_payoffs import compute_tg_payoffs, tg_results_row


def _otree_debug_mode() -> bool:
    """True when oTree runs in dev (same rule as otree.settings.DEBUG)."""
    return os.environ.get("OTREE_PRODUCTION") in (None, "", "0")


def is_otree_debug_mode() -> bool:
    """Public alias: True in oTree debug / non-production sessions."""
    return _otree_debug_mode()


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


def _role_label(role: Optional[str]) -> str:
    if role == "first":
        return "1st mover"
    if role == "second":
        return "2nd mover"
    return ""


def _db_effective_choice(db: dict) -> Optional[str]:
    """Contingent choice in DB that applies to the stored role for this round."""
    role = db.get("role_assigned")
    if role == "first":
        return db.get("choice_first_mover")
    if role == "second":
        return db.get("choice_second_mover")
    return None


def _db_expected_opponent_choice(db: dict) -> Optional[str]:
    """
    Opponent contingent that should appear on Results for the viewer's stored role.

    Viewer 1st → opponent's 2nd-mover contingent.
    Viewer 2nd → opponent's 1st-mover contingent.
    """
    role = db.get("role_assigned")
    if role == "first":
        return db.get("opponent_choice_second_mover")
    if role == "second":
        return db.get("opponent_choice_first_mover")
    return None


def _db_game_moves(db: dict) -> Tuple[Optional[str], Optional[str]]:
    """(1st-mover move, 2nd-mover move) implied by the viewer's directed match in DB."""
    role = db.get("role_assigned")
    if role == "first":
        return db.get("choice_first_mover"), db.get("opponent_choice_second_mover")
    if role == "second":
        return db.get("opponent_choice_first_mover"), db.get("choice_second_mover")
    return None, None


def _db_expected_payoff(db: dict) -> Optional[int]:
    first_move, second_move = _db_game_moves(db)
    role = db.get("role_assigned")
    if role not in ("first", "second"):
        return None
    if first_move not in ("A", "B") or second_move not in ("A", "B"):
        return None
    pay_first, pay_second = compute_tg_payoffs(first_move, second_move)
    return pay_first if role == "first" else pay_second


def _build_mismatch_detail(display: dict, db: dict, flags: List[str]) -> Optional[dict]:
    """Side-by-side screen vs DB values when this round has integrity flags."""
    if not flags:
        return None

    screen_choice = display.get("my_choice")
    db_choice = _db_effective_choice(db)
    screen_other = display.get("other_choice")
    db_other = _db_expected_opponent_choice(db)
    screen_payoff = display.get("payoff")
    db_payoff = db.get("payoff")
    expected_payoff = _db_expected_payoff(db)
    screen_role = display.get("role_assigned")
    db_role_label = _role_label(db.get("role_assigned"))

    messages: List[str] = []
    if "role_mismatch" in flags:
        messages.append(f"role — screen: {screen_role!r}, DB: {db_role_label!r} ({db.get('role_assigned')!r})")
    if "my_choice_mismatch" in flags:
        messages.append(
            f"your choice — screen: {screen_choice!r}, DB (role={db.get('role_assigned')!r}): {db_choice!r}"
        )
    if "my_choice_without_role" in flags:
        messages.append(
            f"your choice — screen: {screen_choice!r}, DB: no role "
            f"(c1={db.get('choice_first_mover')!r}, c2={db.get('choice_second_mover')!r})"
        )
    if "other_choice_mismatch" in flags:
        messages.append(
            f"opponent choice — screen: {screen_other!r}, "
            f"DB expected for your role: {db_other!r}"
        )
    if "other_choice_without_role" in flags:
        messages.append(
            f"opponent choice — screen: {screen_other!r}, DB: no role to select opponent contingent"
        )
    if "payoff_mismatch" in flags:
        messages.append(f"payoff — screen: {screen_payoff!r}, DB: {db_payoff!r}")
    if "db_payoff_inconsistent" in flags:
        messages.append(
            f"DB payoff inconsistent with directed match — "
            f"stored: {db_payoff!r}, recomputed from DB moves: {expected_payoff!r}"
        )

    return {
        "role_screen": screen_role,
        "role_db": db.get("role_assigned"),
        "choice_screen": screen_choice,
        "choice_db": db_choice,
        "other_choice_screen": screen_other,
        "other_choice_db": db_other,
        "choice_db_first": db.get("choice_first_mover"),
        "choice_db_second": db.get("choice_second_mover"),
        "payoff_screen": screen_payoff,
        "payoff_db": db_payoff,
        "payoff_db_expected": expected_payoff,
        "messages": messages,
        "summary": " | ".join(messages),
    }


def build_tg_results_debug(
    player,
    part_start: int,
    part_end: int,
    current_part: int,
    get_opponent_in_round: Callable[[Any, int], Any],
    *,
    rounds_per_part: int = 10,
    force: bool = False,
) -> Optional[dict]:
    """
    Full Results integrity check for the viewing participant (DEBUG mode only).

    For each round, compare what the Results table shows against what the DB
    implies for *this* player's directed match:

    - role
    - their active choice (contingent selected by role)
    - opponent choice (opponent contingent for the complementary role)
    - their payoff (screen vs stored, and stored vs recomputed from DB moves)

    Set ``force=True`` (e.g. TG session inspector) to run outside DEBUG mode.
    """
    if not force and not _otree_debug_mode():
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

        role = db.get("role_assigned")
        db_choice = _db_effective_choice(db)
        db_other = _db_expected_opponent_choice(db)
        expected_payoff = _db_expected_payoff(db)

        flags: List[str] = []

        # Role: screen label must match stored role
        if role in ("first", "second"):
            if display.get("role_assigned") != _role_label(role):
                flags.append("role_mismatch")
        elif display.get("role_assigned"):
            flags.append("role_mismatch")

        # Your choice for stored role
        if role == "first" and display.get("my_choice") != db.get("choice_first_mover"):
            flags.append("my_choice_mismatch")
        elif role == "second" and display.get("my_choice") != db.get("choice_second_mover"):
            flags.append("my_choice_mismatch")
        elif role not in ("first", "second") and display.get("my_choice"):
            flags.append("my_choice_without_role")

        # Opponent choice implied by your role (viewer-centric)
        if role in ("first", "second"):
            if display.get("other_choice") != db_other:
                flags.append("other_choice_mismatch")
        elif display.get("other_choice"):
            flags.append("other_choice_without_role")

        # Payoff: screen vs stored DB
        if display.get("payoff") != db.get("payoff"):
            flags.append("payoff_mismatch")

        # Payoff: stored DB vs recomputed directed-match payoffs
        if expected_payoff is not None and db.get("payoff") != expected_payoff:
            flags.append("db_payoff_inconsistent")

        flags_str = ", ".join(flags) if flags else "ok"
        mismatch = _build_mismatch_detail(display, db, flags)

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
                "db_effective_choice": db_choice,
                "db_expected_other_choice": db_other,
                "db_expected_payoff": expected_payoff,
                "warn": bool(flags),
                "flags": flags,
                "mismatch": mismatch,
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
        row = next((x for x in rows if x["round"] == rnd), None)
        if row and row.get("mismatch"):
            m = row["mismatch"]
            summary_vars[f"tg_debug_R{rnd}_choice_screen"] = m.get("choice_screen")
            summary_vars[f"tg_debug_R{rnd}_choice_db"] = m.get("choice_db")
            summary_vars[f"tg_debug_R{rnd}_other_choice_screen"] = m.get("other_choice_screen")
            summary_vars[f"tg_debug_R{rnd}_other_choice_db"] = m.get("other_choice_db")
            if m.get("payoff_screen") != m.get("payoff_db"):
                summary_vars[f"tg_debug_R{rnd}_payoff_screen"] = m.get("payoff_screen")
                summary_vars[f"tg_debug_R{rnd}_payoff_db"] = m.get("payoff_db")
            if m.get("payoff_db") != m.get("payoff_db_expected"):
                summary_vars[f"tg_debug_R{rnd}_payoff_db_expected"] = m.get("payoff_db_expected")
            summary_vars[f"tg_debug_R{rnd}_mismatch_detail"] = m.get("summary")

    return {
        "part": current_part,
        "rounds": rows,
        "summary_vars": summary_vars,
    }

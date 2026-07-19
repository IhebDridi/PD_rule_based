"""
Trust Game (TG) sequential payoff logic.

Each participant submits two contingent choices per round (1st-mover and 2nd-mover).
At payoff time roles are assigned randomly per round within each matched pair; payoffs
follow the sequential rules. Grouping / round-robin matching is unchanged from PD apps.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from otree.api import cu

from shared.stale_session_flag import (
    DEFAULT_STALE_TTL_SECONDS,
    clear_timed_flag,
    try_acquire_timed_flag,
)
from shared.tg_data_helpers import write_tg_results_display_cache

_ROUND_ROBIN_CACHE: Dict[int, Any] = {}

# BatchWait interprets these (True remains success for older callers).
PayoffRunStatus = Union[bool, None, str]  # True | False | None | "in_progress"


def stable_pair_seed_u32(session_code: str, round_number: int, id_a: int, id_b: int) -> int:
    """Stable across processes (unlike hash() of str under PYTHONHASHSEED)."""
    lo, hi = (id_a, id_b) if id_a <= id_b else (id_b, id_a)
    raw = f"{session_code}|{int(round_number)}|{lo}|{hi}".encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16)


def is_tg_module(module_name: str) -> bool:
    base = module_name.rsplit(".", 1)[0]
    return base.startswith("TG_")


def tg_choices_ready(player) -> bool:
    """True when both contingent TG choices are set for this round."""
    c1 = player.field_maybe_none("choice_first_mover")
    c2 = player.field_maybe_none("choice_second_mover")
    return c1 in ("A", "B") and c2 in ("A", "B")


def compute_tg_payoffs(first_move: str, second_move: str) -> Optional[Tuple[int, int]]:
    """
    Return (1st mover payoff, 2nd mover payoff) in Ecoins, or None if moves are invalid.
    If 1st chooses B, 2nd's choice is ignored and both get 30.
    """
    if first_move == "B":
        return 30, 30
    if first_move == "A":
        if second_move == "A":
            return 70, 70
        if second_move == "B":
            return 0, 100
    return None


def apply_tg_payoffs_for_pair(
    player_a,
    player_b,
    *,
    rng: random.Random,
    write_both: bool = False,
) -> bool:
    """
    Randomly assign roles for the (player_a, player_b) match and set payoffs.

    By default only ``player_a`` is written. Round-robin matching for N=3 is
    *directed* (P1→P3, P2→P1, P3→P2), so writing both players overwrote each
    row when the opponent’s own match ran later — causing Display≠DB
    (screen recomputes from directed opponent; DB held the last overwrite).

    Set ``write_both=True`` only for true mutual pairs / unit tests that apply once.
    Returns False if either player lacks both contingent choices.
    """
    a_first = player_a.field_maybe_none("choice_first_mover")
    a_second = player_a.field_maybe_none("choice_second_mover")
    b_first = player_b.field_maybe_none("choice_first_mover")
    b_second = player_b.field_maybe_none("choice_second_mover")
    if not all(x in ("A", "B") for x in (a_first, a_second, b_first, b_second)):
        return False

    if rng.random() < 0.5:
        a_is_first = True
        first_move, second_move = a_first, b_second
    else:
        a_is_first = False
        first_move, second_move = b_first, a_second

    payoffs = compute_tg_payoffs(first_move, second_move)
    if payoffs is None:
        return False
    pay_first, pay_second = payoffs

    if a_is_first:
        player_a.role_assigned = "first"
        player_a.payoff = cu(pay_first)
        if write_both:
            player_b.role_assigned = "second"
            player_b.payoff = cu(pay_second)
    else:
        player_a.role_assigned = "second"
        player_a.payoff = cu(pay_second)
        if write_both:
            player_b.role_assigned = "first"
            player_b.payoff = cu(pay_first)
    return True


def set_payoffs_tg_batch_group(group) -> None:
    """
    Legacy Group.set_payoffs entrypoint — intentionally a no-op.

    Live TG payoffs run only via ``run_payoffs_for_matching_group_tg`` from BatchWait.
    Calling ``group.get_players()`` here would freeze large sessions (one huge group).
    """
    return


def run_payoffs_for_matching_group_tg(
    subsession,
    matching_group_id: int,
    Constants: Any,
    compute_rr: Callable[[int, int], Any],
) -> PayoffRunStatus:
    """
    TG payoff runner: same pool / batch structure as PD, sequential TG payoffs per pair.

    Returns:
      True — payoffs written (or already ran)
      False — choices not ready yet (caller may soft-fail / rotate)
      "in_progress" — another request holds the payoff lock (do NOT tear down claim)
      None — hard failure (missing members / players)
    """
    rnd = subsession.round_number
    current_part = Constants.get_part(rnd)
    if current_part == 1:
        start, end = 1, 10
    elif current_part == 2:
        start, end = 11, 20
    elif current_part == 3:
        start, end = 21, 30
    else:
        return None

    run_key = f"payoffs_run_matching_group_{matching_group_id}_part_{current_part}"
    if subsession.session.vars.get(run_key):
        return True

    # Timestamped lock: if the worker dies mid-payoff, TTL lets the next waiter retry
    # without an admin clearing session.vars. Happy path still clears in finally.
    in_progress_key = f"{run_key}_in_progress"
    if not try_acquire_timed_flag(
        subsession.session.vars,
        in_progress_key,
        DEFAULT_STALE_TTL_SECONDS,
    ):
        return "in_progress"

    key = f"matching_group_members_part_{current_part}_{matching_group_id}"
    member_ids = subsession.session.vars.get(key)
    try:
        if not member_ids or not isinstance(member_ids, (list, tuple)) or len(member_ids) < 3:
            return None

        # Never call Subsession.get_players() here — with 300 participants that freezes the server.
        from shared.tg_player_lookup import players_at_round_for_member_ids

        players_start = players_at_round_for_member_ids(
            subsession.session.id,
            list(member_ids)[:3],
            start,
        )
        if players_start is None or len(players_start) != 3:
            return None
        players_start = sorted(
            players_start, key=lambda p: p.participant.vars.get("matching_group_position", 0)
        )

        def _all_ready() -> bool:
            for r in range(start, end + 1):
                for p0 in players_start:
                    if not tg_choices_ready(p0.in_round(r)):
                        return False
            return True

        if not _all_ready():
            return False

        N = len(member_ids)
        if N not in _ROUND_ROBIN_CACHE:
            _ROUND_ROBIN_CACHE[N] = compute_rr(N, Constants.rounds_per_part)
        assignments = _ROUND_ROBIN_CACHE[N]

        session_code = subsession.session.code
        for r in range(start, end + 1):
            part_start = (current_part - 1) * Constants.rounds_per_part + 1
            round_in_part = r - part_start
            players_r = [p0.in_round(r) for p0 in players_start]
            for i, p in enumerate(players_r):
                opp_idx, _ = assignments[i][round_in_part]
                if opp_idx is None:
                    continue
                opp = players_r[opp_idx]
                pair_seed = stable_pair_seed_u32(
                    session_code,
                    r,
                    p.participant.id_in_session,
                    opp.participant.id_in_session,
                )
                apply_tg_payoffs_for_pair(p, opp, rng=random.Random(pair_seed), write_both=False)

        write_tg_results_display_cache(
            players_start,
            assignments,
            current_part,
            start,
            end,
            Constants.rounds_per_part,
        )

        subsession.session.vars[run_key] = True
        return True
    finally:
        clear_timed_flag(subsession.session.vars, in_progress_key)


def _opponent_effective_choice(opponent, opp_role: Optional[str]) -> Optional[str]:
    if opponent is None or opp_role not in ("first", "second"):
        return None
    if opp_role == "first":
        return opponent.field_maybe_none("choice_first_mover")
    return opponent.field_maybe_none("choice_second_mover")


def _tg_opponent_display_choice(player, opponent) -> Optional[str]:
    """
    Opponent's contingent choice in the role the player did not play this round.

    Uses the player's assigned role (not the opponent's), so display stays correct even
    if opponent.role_assigned is missing or inconsistent on the opponent row.
    """
    my_role = player.field_maybe_none("role_assigned")
    if opponent is None or my_role not in ("first", "second"):
        return None
    if my_role == "first":
        return opponent.field_maybe_none("choice_second_mover")
    return opponent.field_maybe_none("choice_first_mover")


def _tg_game_moves(player, opponent) -> Tuple[Optional[str], Optional[str]]:
    """Return (1st-mover move, 2nd-mover move) actually played in the pair this round."""
    my_role = player.field_maybe_none("role_assigned")
    if my_role == "first":
        first_move = player.field_maybe_none("choice_first_mover")
        second_move = (
            opponent.field_maybe_none("choice_second_mover") if opponent else None
        )
    elif my_role == "second":
        first_move = (
            opponent.field_maybe_none("choice_first_mover") if opponent else None
        )
        second_move = player.field_maybe_none("choice_second_mover")
    else:
        return None, None
    return first_move, second_move


def _tg_payoff_from_db(player) -> Optional[int]:
    payoff = getattr(player, "payoff", None)
    if payoff is None and hasattr(player, "field_maybe_none"):
        payoff = player.field_maybe_none("payoff")
    if payoff is None:
        return None
    raw = getattr(payoff, "amount", payoff)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def tg_results_row(player, opponent, *, role: Optional[str] = None) -> dict:
    """Build one Results-table row for TG.

    Role and choices come from the player's directed match; ``payoff`` prefers the
    DB value (source of truth) so screen earnings match what was stored when this
    player was the focal participant on their directed edge.
    """
    assigned = role or player.field_maybe_none("role_assigned")
    role_label = ""
    if assigned == "first":
        role_label = "1st mover"
    elif assigned == "second":
        role_label = "2nd mover"

    first_move, second_move = _tg_game_moves(player, opponent)
    if assigned == "first":
        my_choice = first_move
    elif assigned == "second":
        my_choice = second_move
    else:
        my_choice = None

    other_choice = _tg_opponent_display_choice(player, opponent)

    payoff_val = _tg_payoff_from_db(player)
    # DB is source of truth. Do not invent display payoffs when unset / no role.
    if assigned not in ("first", "second"):
        payoff_val = None

    return {
        "role_assigned": role_label,
        "my_choice": my_choice,
        "other_choice": other_choice,
        "payoff": payoff_val,
        "is_payoff_round": True,
    }

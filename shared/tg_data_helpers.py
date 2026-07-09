"""TG data-flow helpers: block-field fallbacks, results cache, effective choices."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional


def read_block_map_from_player(player, field_prefix: str) -> Dict[int, str]:
    """Read round-indexed A/B map from block form fields on the block-round player row."""
    out: Dict[int, str] = {}
    for i in range(1, 11):
        val = player.field_maybe_none(f"{field_prefix}_{i}")
        if val in ("A", "B"):
            out[i] = val
    return out


def read_agent_first_map_from_player(player) -> Dict[int, str]:
    return read_block_map_from_player(player, "agent_decision_mandatory_delegation_round")


def read_agent_second_map_from_player(player) -> Dict[int, str]:
    return read_block_map_from_player(player, "agent_decision_mandatory_second_round")


def read_human_first_map_from_player(player) -> Dict[int, str]:
    return read_block_map_from_player(player, "human_decision_no_delegation_round")


def read_human_second_map_from_player(player) -> Dict[int, str]:
    return read_block_map_from_player(player, "human_second_no_delegation_round")


def merge_block_map(participant, vars_key: str, player, reader: Callable) -> Dict:
    """Prefer participant.vars block map; fall back to DB fields on the block-round player."""
    stored = participant.vars.get(vars_key)
    if isinstance(stored, dict) and stored:
        return dict(stored)
    return reader(player)


def tg_effective_choice(player) -> Optional[str]:
    """Role-based effective choice for display (after payoffs)."""
    role = player.field_maybe_none("role_assigned")
    if role == "first":
        return player.field_maybe_none("choice_first_mover")
    if role == "second":
        return player.field_maybe_none("choice_second_mover")
    return None


def tg_part_has_choices(rounds, part: int, rounds_per_part: int) -> bool:
    start = (part - 1) * rounds_per_part + 1
    end = part * rounds_per_part
    for pr in rounds:
        if start <= pr.round_number <= end:
            c1 = pr.field_maybe_none("choice_first_mover")
            c2 = pr.field_maybe_none("choice_second_mover")
            if c1 in ("A", "B") and c2 in ("A", "B"):
                return True
    return False


def build_tg_results_cache_for_part(
    players_start,
    assignments,
    current_part: int,
    start: int,
    end: int,
    rounds_per_part: int,
) -> List[List[dict]]:
    """Build per-player results_display_cache entries for one TG part (3 players)."""
    from shared.tg_payoffs import tg_results_row

    part_start = (current_part - 1) * rounds_per_part + 1
    cache_by_player: List[List[dict]] = [[] for _ in range(len(players_start))]
    for r in range(start, end + 1):
        round_in_part = r - part_start
        players_r = [p0.in_round(r) for p0 in players_start]
        for i, p in enumerate(players_r):
            opp_idx, _ = assignments[i][round_in_part]
            opp = players_r[opp_idx] if opp_idx is not None else None
            row = tg_results_row(p, opp)
            entry = {
                "round": round_in_part + 1,
                "my_choice": row.get("my_choice"),
                "other_choice": row.get("other_choice"),
                "payoff": row.get("payoff"),
                "role_assigned": row.get("role_assigned"),
            }
            if current_part == 3:
                entry["other_delegated"] = bool(
                    opp and opp.field_maybe_none("delegate_decision_optional")
                )
            cache_by_player[i].append(entry)
    return cache_by_player


def write_tg_results_display_cache(
    players_start,
    assignments,
    current_part: int,
    start: int,
    end: int,
    rounds_per_part: int,
) -> None:
    """Persist TG results rows into each participant's results_display_cache."""
    cache_by_player = build_tg_results_cache_for_part(
        players_start,
        assignments,
        current_part,
        start,
        end,
        rounds_per_part,
    )
    for p0, part_rows in zip(players_start, cache_by_player):
        existing = p0.participant.vars.get("results_display_cache") or {}
        if not isinstance(existing, dict):
            existing = {}
        existing[f"part_{current_part}"] = part_rows
        p0.participant.vars["results_display_cache"] = existing


def get_tg_results_display_from_cache(participant, part: int, rounds_per_part: int = 10):
    """Return cached TG results rows for a part, or None if missing/invalid."""
    cache = participant.vars.get("results_display_cache")
    if not isinstance(cache, dict):
        return None
    part_data = cache.get(f"part_{part}")
    if not isinstance(part_data, list) or len(part_data) != rounds_per_part:
        return None
    return part_data


def tg_export_choice_getter(pr) -> Optional[str]:
    """Export integrity: truthy when both contingent TG choices exist."""
    c1 = pr.field_maybe_none("choice_first_mover")
    c2 = pr.field_maybe_none("choice_second_mover")
    if c1 in ("A", "B") and c2 in ("A", "B"):
        return "tg"
    return None

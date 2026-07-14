"""Participant.vars storage for TG v2 human decision blocks."""

from __future__ import annotations

from typing import Any, Dict, Tuple


def human_first_vars_key(part: int) -> str:
    return f"human_v2_first_part{part}"


def human_second_vars_key(part: int) -> str:
    return f"human_v2_second_part{part}"


def human_first_step_key(part: int) -> str:
    return f"human_v2_first_step_part{part}"


def human_second_step_key(part: int) -> str:
    return f"human_v2_second_step_part{part}"


def normalize_human_block_map(raw: Any) -> Dict[int, str]:
    """Coerce keys to int; keep only A/B values."""
    if not isinstance(raw, dict):
        return {}
    out: Dict[int, str] = {}
    for key, value in raw.items():
        if value not in ("A", "B"):
            continue
        out[int(key)] = value
    return out


def record_human_first_choice(participant, part: int, round_i: int, choice: str) -> None:
    key = human_first_vars_key(part)
    decisions = normalize_human_block_map(participant.vars.get(key, {}))
    if choice in ("A", "B"):
        decisions[int(round_i)] = choice
    participant.vars[key] = decisions


def record_human_second_choice(participant, part: int, round_i: int, choice: str) -> None:
    key = human_second_vars_key(part)
    decisions = normalize_human_block_map(participant.vars.get(key, {}))
    if choice in ("A", "B"):
        decisions[int(round_i)] = choice
    participant.vars[key] = decisions


def human_block_maps_from_vars(participant, part: int) -> Tuple[Dict[int, str], Dict[int, str]]:
    first = normalize_human_block_map(participant.vars.get(human_first_vars_key(part), {}))
    second = normalize_human_block_map(participant.vars.get(human_second_vars_key(part), {}))
    return first, second


def backfill_human_block_fields_on_player(player, first_map: dict, second_map: dict) -> None:
    """Optional audit columns on the block-round player row."""
    for i in range(1, 11):
        first = first_map.get(i) or first_map.get(str(i))
        second = second_map.get(i) or second_map.get(str(i))
        if first in ("A", "B"):
            setattr(player, f"human_decision_no_delegation_round_{i}", first)
        if second in ("A", "B"):
            setattr(player, f"human_second_no_delegation_round_{i}", second)


def human_block_maps_complete(first_map: dict, second_map: dict) -> bool:
    for i in range(1, 11):
        if first_map.get(i) not in ("A", "B") or second_map.get(i) not in ("A", "B"):
            return False
    return True

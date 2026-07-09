"""Validation helpers for TG two-role block pages (human + agent)."""

from __future__ import annotations

from typing import Any, Dict, Optional


def validate_tg_block_maps(
    first_map: Dict[Any, Any],
    second_map: Dict[Any, Any],
    start_round: int,
) -> Optional[str]:
    """
    Return a user-visible error message when any round lacks both A/B choices.
    Used from page ``error_message`` so incomplete blocks cannot advance.
    """
    missing = []
    for i in range(1, 11):
        f = first_map.get(i) or first_map.get(str(i))
        s = second_map.get(i) or second_map.get(str(i))
        if f not in ("A", "B") or s not in ("A", "B"):
            missing.append(str(start_round + i - 1))
    if not missing:
        return None
    return (
        f"Missing choices for round(s): {', '.join(missing)}. "
        "Please complete all decisions before continuing."
    )

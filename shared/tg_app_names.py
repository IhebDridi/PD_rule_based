"""TG app_name identifiers written to the DB at session creation."""

from __future__ import annotations

import importlib
import re
from typing import Any


def tg_app_name_for_module(module_name: str) -> str:
    """Return treatment + order app_name slug for a TG_* models module."""
    base = module_name.rsplit(".", 1)[0]
    m = re.search(
        r"TG_(rule_based|goal_oriented|supervised_learning|llm)_delegation_(?:v2_)?(1st|2nd)",
        base,
    )
    if not m:
        return "rulebased_del1st"
    treatment, order = m.group(1), m.group(2)
    prefix = {
        "rule_based": "rulebased",
        "goal_oriented": "goaloriented",
        "supervised_learning": "supervised",
        "llm": "llm",
    }[treatment]
    return f"{prefix}_del{order}"


def tg_creating_session(subsession: Any) -> None:
    """Round 1: unmatched lobby flag + correct app_name on every Player row."""
    if subsession.round_number != 1:
        return
    module = importlib.import_module(type(subsession).__module__)
    constants = module.Constants
    app_name = tg_app_name_for_module(type(subsession).__module__)
    for p in subsession.get_players():
        p.participant.vars["matching_group_id"] = -1
        for r in range(1, constants.num_rounds + 1):
            p.in_round(r).app_name = app_name

"""Build ``DelegationExportSpec`` from an app module name (PD/SD/SH/TG delegation apps)."""

from __future__ import annotations

import re
from typing import Any, Callable

from shared.delegation_custom_export import DelegationExportSpec

_TREATMENT = {
    "rule_based": dict(
        condition_first="rule1st",
        condition_second="rule2nd",
        extension="empty",
        demographics="rule_based",
        per_round_agent_token="rule",
        summary_agent_fixed=None,
    ),
    "goal_oriented": dict(
        condition_first="goal1st",
        condition_second="goal2nd",
        extension="goal",
        demographics="standard",
        per_round_agent_token="goal",
        summary_agent_fixed="goal",
    ),
    "supervised_learning": dict(
        condition_first="super1st",
        condition_second="super2nd",
        extension="supervised",
        demographics="standard",
        per_round_agent_token="super",
        summary_agent_fixed="super",
    ),
    "llm": dict(
        condition_first="llm1st",
        condition_second="llm2nd",
        extension="llm",
        demographics="standard",
        per_round_agent_token="llm",
        summary_agent_fixed="llm",
    ),
}


def _treatment_key(module_name: str) -> str:
    base = module_name.rsplit(".", 1)[0]
    m = re.search(r"_(rule_based|goal_oriented|supervised_learning|llm)_delegation_", base)
    return m.group(1) if m else "rule_based"


def _game_used(module_name: str) -> str:
    base = module_name.rsplit(".", 1)[0]
    if base.startswith("TG_"):
        return "PD"
    return base.split("_", 1)[0].upper()


def make_delegation_export_spec(
    module_name: str,
    constants: Any,
    compute_rr: Callable[[int, int], Any],
) -> DelegationExportSpec:
    treatment = _treatment_key(module_name)
    meta = _TREATMENT[treatment]
    is_rule = treatment == "rule_based"
    is_tg = module_name.rsplit(".", 1)[0].startswith("TG_")

    return DelegationExportSpec(
        constants=constants,
        compute_rr=compute_rr,
        game_used=_game_used(module_name),
        condition_first=meta["condition_first"],
        condition_second=meta["condition_second"],
        layout="first_person_agents",
        demographics=meta["demographics"],
        round_data_style="rule_based_gid" if is_rule else "standard",
        per_round_agent_token=meta["per_round_agent_token"],
        summary_agent_fixed=meta["summary_agent_fixed"],
        extension=meta["extension"],
        access_mode="safe" if is_rule else "normal",
        opponent_mode="safe_wrap" if is_rule else "normal",
        payoff_mode="currency_amount" if is_rule else "simple",
        session_mode="safe" if is_rule else "direct",
        prolific_mode="or_empty" if is_rule else "strict",
        log_errors_to_stderr=is_rule and not is_tg,
        results_cache_required=is_rule and not is_tg,
    )

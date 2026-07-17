"""Form payloads for TG oTree bot tests (v2 block pages)."""

import json
import random


def tg_human_first_form(choice=None):
    c = choice or random.choice(["A", "B"])
    return {f"human_decision_no_delegation_round_{i}": c for i in range(1, 11)}


def tg_human_first_form_round(choice=None, round_i=1):
    c = choice or random.choice(["A", "B"])
    return {f"human_decision_no_delegation_round_{round_i}": c}


def tg_human_second_form(choice=None):
    c = choice or random.choice(["A", "B"])
    return {f"human_second_no_delegation_round_{i}": c for i in range(1, 11)}


def tg_human_second_form_round(choice=None, round_i=1):
    c = choice or random.choice(["A", "B"])
    return {f"human_second_no_delegation_round_{round_i}": c}


def tg_agent_first_form(choice=None):
    c = choice or random.choice(["A", "B"])
    return {f"agent_decision_mandatory_delegation_round_{i}": c for i in range(1, 11)}


def tg_agent_second_form(choice=None):
    c = choice or random.choice(["A", "B"])
    return {f"agent_decision_mandatory_second_round_{i}": c for i in range(1, 11)}


def tg_supervised_form(choice=None):
    c = choice or random.choice(["A", "B"])
    csv = ",".join([c] * 10)
    return {"supervised_last_generated_csv": csv}


def _ten_ab_map(choice=None):
    c = choice or random.choice(["A", "B"])
    return {i: c for i in range(1, 11)}


def seed_goal_agent_first(participant, *, part: int, choice=None):
    """Seed agent_v2_first_part{N} for TgGoalOrientedFirst (no form fields)."""
    decisions = _ten_ab_map(choice)
    participant.vars[f"agent_v2_first_part{part}"] = decisions
    return decisions


def seed_goal_agent_second(participant, *, part: int, choice=None):
    """Seed _tg_agent_second_pending_part_{N} for TgGoalOrientedSecond (no form fields)."""
    decisions = _ten_ab_map(choice)
    participant.vars[f"_tg_agent_second_pending_part_{part}"] = decisions
    return decisions


def tg_llm_conversation_payload(choice=None, *, second=False):
    """
    Return {conversation_history[_second]: JSON} with one assistant message
    containing a strict 10-item A/B line (see _parse_strict_ten_ab).
    """
    c = choice or random.choice(["A", "B"])
    content = ",".join([c] * 10)
    field = "conversation_history_second" if second else "conversation_history"
    return {field: json.dumps([{"role": "assistant", "content": content}])}

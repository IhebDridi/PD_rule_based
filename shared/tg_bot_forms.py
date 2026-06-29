"""Form payloads for TG oTree bot tests (v2 block pages)."""

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

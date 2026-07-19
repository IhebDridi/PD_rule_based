"""Reusable PlayerBot.play_round factory for TG treatment apps."""

from __future__ import annotations

import importlib
import random

from otree.bots.bot import Submission

from shared.tg_bot_forms import (
    seed_goal_agent_first,
    seed_goal_agent_second,
    tg_agent_first_form,
    tg_agent_second_form,
    tg_human_first_form_round,
    tg_human_second_form_round,
    tg_llm_conversation_payload,
    tg_supervised_form,
)
from shared.tg_v2_bot_stress import patch_tg_v2_bot_runner

TREATMENTS = frozenset({"rule_based", "goal", "supervised", "llm"})

# Session config key ``bot_stop_at`` (Create Session → Advanced).
# Bots halt on that page without submitting Next (inspect data mid-run).
BOT_STOP_AT_CHOICES = frozenset(
    {
        "finish",
        "results_part1",
        "results_part2",
        "results_part3",
        "guess",
        "debriefing",
    }
)

COMPREHENSION_ANSWERS = {
    "q1": "c",
    "q2": "b",
    "q6": "c",
    "q7": "a",
    "q8": "d",
    "q9": "c",
    "q5": "d",
    "q10": "b",
}


def normalize_bot_stop_at(raw) -> str:
    value = str(raw or "finish").strip().lower()
    if value not in BOT_STOP_AT_CHOICES:
        return "finish"
    return value


def _bot_stop_at(bot) -> str:
    try:
        cfg = bot.session.config or {}
    except Exception:
        cfg = {}
    return normalize_bot_stop_at(cfg.get("bot_stop_at"))


def _exit_form():
    return {
        "gender": "male",
        "age": 25,
        "occupation": "Bot",
        "ai_use": "monthly",
        "task_difficulty": "neutral",
        "part_3_feedback": "more_fun",
        "part_3_feedback_other": "",
        "part_4_feedback": "same_action",
        "part_4_feedback_other": "",
        "used_ai_or_bot": "no_focused",
        "feedback": "",
    }


def _agent_part_for_round(rnd: int) -> int:
    if rnd == 1:
        return 1
    if rnd == 11:
        return 2
    if rnd == 21:
        return 3
    raise ValueError(f"No agent block at round {rnd}")


def _yield_human_block(human_first_page, human_second_page):
    for i in range(1, 11):
        yield human_first_page, tg_human_first_form_round("A", i)
    for i in range(1, 11):
        yield human_second_page, tg_human_second_form_round("B", i)


def _yield_agent_block(bot, *, treatment: str, part: int, agent_first_page, agent_second_page):
    if treatment == "rule_based":
        yield agent_first_page, tg_agent_first_form("A")
        yield agent_second_page, tg_agent_second_form("B")
        return

    if treatment == "goal":
        seed_goal_agent_first(bot.participant, part=part, choice="A")
        yield agent_first_page
        seed_goal_agent_second(bot.participant, part=part, choice="B")
        yield agent_second_page
        return

    if treatment == "supervised":
        yield agent_first_page, tg_supervised_form("A")
        yield agent_second_page, tg_supervised_form("B")
        return

    if treatment == "llm":
        for field, value in tg_llm_conversation_payload("A").items():
            setattr(bot.player, field, value)
        yield agent_first_page
        for field, value in tg_llm_conversation_payload("B", second=True).items():
            setattr(bot.player, field, value)
        yield agent_second_page
        return

    raise ValueError(f"Unknown treatment: {treatment!r}")


def make_tg_player_bot_play_round(
    *,
    treatment: str,
    pages_module,
    human_first_page,
    human_second_page,
    agent_first_page,
    agent_second_page,
):
    """
    Return a play_round generator method for PlayerBot.

    treatment: rule_based | goal | supervised | llm
    pages_module: the app's .pages module (Constants loaded from sibling .models)

    Session config ``bot_stop_at`` (advanced create-session form):
      finish | results_part1 | results_part2 | results_part3 | guess | debriefing
    """
    if treatment not in TREATMENTS:
        raise ValueError(f"treatment must be one of {sorted(TREATMENTS)}, got {treatment!r}")

    app_name = pages_module.__name__.rsplit(".", 1)[0]
    Constants = importlib.import_module(f"{app_name}.models").Constants
    delegation_first = Constants.DELEGATION_FIRST

    InformedConsent = pages_module.InformedConsent
    MainInstructions = pages_module.MainInstructions
    ComprehensionTest = pages_module.ComprehensionTest
    InstructionsDelegation = pages_module.InstructionsDelegation
    InstructionsNoDelegation = pages_module.InstructionsNoDelegation
    InstructionsOptional = pages_module.InstructionsOptional
    DelegationDecision = pages_module.DelegationDecision
    Results = pages_module.Results
    InstructionsGuessingGame = pages_module.InstructionsGuessingGame
    GuessDelegation = pages_module.GuessDelegation
    ResultsGuess = pages_module.ResultsGuess
    Debriefing = pages_module.Debriefing
    ExitQuestionnaire = pages_module.ExitQuestionnaire
    Thankyou = pages_module.Thankyou

    patch_tg_v2_bot_runner(delegation_first=delegation_first)

    def play_round(self):
        rnd = self.round_number
        stop_at = _bot_stop_at(self)

        if rnd == 1:
            yield InformedConsent, {"prolific_id": f"TG_BOT_{self.participant.id_in_session:03d}"}
            yield MainInstructions
            yield ComprehensionTest, COMPREHENSION_ANSWERS
            if delegation_first:
                yield InstructionsDelegation
                yield from _yield_agent_block(
                    self,
                    treatment=treatment,
                    part=_agent_part_for_round(rnd),
                    agent_first_page=agent_first_page,
                    agent_second_page=agent_second_page,
                )
            else:
                yield InstructionsNoDelegation
                yield from _yield_human_block(human_first_page, human_second_page)

        if rnd == 10:
            # Halt on Results Part 1 (do not click Next).
            if stop_at == "results_part1":
                return
            yield Results

        if rnd == 11:
            if delegation_first:
                yield InstructionsNoDelegation
                yield from _yield_human_block(human_first_page, human_second_page)
            else:
                yield InstructionsDelegation
                yield from _yield_agent_block(
                    self,
                    treatment=treatment,
                    part=_agent_part_for_round(rnd),
                    agent_first_page=agent_first_page,
                    agent_second_page=agent_second_page,
                )

        if rnd == 20:
            if stop_at == "results_part2":
                return
            yield Results

        if rnd == 21:
            yield InstructionsOptional
            yield DelegationDecision, {"delegate_decision_optional": True}
            yield from _yield_agent_block(
                self,
                treatment=treatment,
                part=_agent_part_for_round(rnd),
                agent_first_page=agent_first_page,
                agent_second_page=agent_second_page,
            )

        if rnd == 30:
            if stop_at == "results_part3":
                return
            yield Results
            yield InstructionsGuessingGame
            if stop_at == "guess":
                return
            yield GuessDelegation, {
                f"guess_round_{i}": random.choice(["yes", "no"]) for i in range(1, 11)
            }
            yield ResultsGuess
            if stop_at == "debriefing":
                return
            yield Debriefing
            yield ExitQuestionnaire, _exit_form()
            yield Submission(Thankyou, {}, check_html=False)

    return play_round

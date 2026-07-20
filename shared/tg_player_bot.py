"""Reusable PlayerBot.play_round factory for TG treatment apps."""

from __future__ import annotations

import importlib
import random

from otree.bots.bot import Submission

from shared.bot_stop_at import normalize_bot_stop_at
from shared.tg_bot_forms import (
    seed_goal_agent_first,
    seed_goal_agent_second,
    tg_agent_first_form,
    tg_agent_second_form,
    tg_llm_conversation_payload,
    tg_supervised_form,
)
from shared.tg_human_block_vars import (
    human_first_step_key,
    human_second_step_key,
    record_human_first_choice,
    record_human_second_choice,
)
from shared.tg_v2_bot_stress import patch_tg_v2_bot_runner

TREATMENTS = frozenset({"rule_based", "goal", "supervised", "llm"})

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


def _bot_stop_at(bot) -> str:
    try:
        cfg = bot.session.config or {}
    except Exception:
        cfg = {}
    return normalize_bot_stop_at(cfg.get("bot_stop_at"))


def _stop_blocks_round(stop_at: str, rnd: int) -> bool:
    """
    True when this round must not submit anything because bots already stopped
    on an earlier Results / Guess / Debrief page.

    A bare ``return`` on round 10 alone is not enough for results_part1: oTree
    immediately starts round 11's play_round and tries to POST Part 2 while the
    participant is still on Results → AssertionError.
    """
    if stop_at == "results_part1" and rnd > 10:
        return True
    if stop_at == "results_part2" and rnd > 20:
        return True
    if stop_at == "results_part3" and rnd > 30:
        return True
    return False


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


def _seed_human_first_live_block(participant, part: int, choice: str = "A") -> None:
    """Pre-fill 10 first-mover choices for bots (same path as live_method; no invented blanks)."""
    if choice not in ("A", "B"):
        raise ValueError("bot human first choice must be A or B")
    for i in range(1, 11):
        record_human_first_choice(participant, part, i, choice)
    participant.vars[human_first_step_key(part)] = 10


def _seed_human_second_live_block(participant, part: int, choice: str = "B") -> None:
    if choice not in ("A", "B"):
        raise ValueError("bot human second choice must be A or B")
    for i in range(1, 11):
        record_human_second_choice(participant, part, i, choice)
    participant.vars[human_second_step_key(part)] = 10


def _human_part_for_round(rnd: int, delegation_first: bool) -> int:
    if rnd == 1 and not delegation_first:
        return 1
    if rnd == 11 and delegation_first:
        return 2
    raise ValueError(f"No human block at round {rnd} (delegation_first={delegation_first})")


def _yield_human_block(bot, human_first_page, human_second_page, *, part: int):
    # Live pages: seed vars then one empty submit each (before_next_page finalizes).
    # check_html=False: Confirm is type=button + liveSend (no classic submit input).
    _seed_human_first_live_block(bot.participant, part, "A")
    yield Submission(human_first_page, {}, check_html=False)
    _seed_human_second_live_block(bot.participant, part, "B")
    yield Submission(human_second_page, {}, check_html=False)


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

        if _stop_blocks_round(stop_at, rnd):
            return

        if rnd == 1:
            # Export flag — never leave bots looking like IsSimulated=0 humans.
            self.participant.vars["is_simulated"] = True
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
                yield from _yield_human_block(
                    self,
                    human_first_page,
                    human_second_page,
                    part=_human_part_for_round(rnd, delegation_first),
                )

        if rnd == 10:
            # Do not click Next on Results — later rounds are gated by _stop_blocks_round.
            if stop_at == "results_part1":
                return
            yield Results

        if rnd == 11:
            if delegation_first:
                yield InstructionsNoDelegation
                yield from _yield_human_block(
                    self,
                    human_first_page,
                    human_second_page,
                    part=_human_part_for_round(rnd, delegation_first),
                )
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

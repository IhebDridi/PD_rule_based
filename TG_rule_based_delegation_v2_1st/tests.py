"""Bot tests for TG_rule_based_delegation_v2_1st (delegation-first; human block in Part 2)."""

import os
import random

from otree.api import *
from otree.bots.bot import Submission

from shared.tg_bot_forms import (
    tg_agent_first_form,
    tg_agent_second_form,
    tg_human_first_form_round,
    tg_human_second_form_round,
)
from shared.tg_v2_bot_stress import patch_tg_v2_bot_runner

from .models import Constants
from pages_classes.tg_v2_pages import TgV2HumanDecisionsFirst, TgV2HumanDecisionsSecond
from .pages import (
    ComprehensionTest,
    Debriefing,
    DelegationDecision,
    ExitQuestionnaire,
    FailedTest,
    GuessDelegation,
    InformedConsent,
    InstructionsDelegation,
    InstructionsGuessingGame,
    InstructionsNoDelegation,
    InstructionsOptional,
    MainInstructions,
    Results,
    ResultsGuess,
    Thankyou,
    TgV2AgentProgrammingFirst,
    TgV2AgentProgrammingSecond,
)

os.environ.setdefault("OTREE_SKIP_CSRF", "1")

DELEGATION_FIRST = Constants.DELEGATION_FIRST

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


def _yield_human_block():
    for i in range(1, 11):
        yield TgV2HumanDecisionsFirst, tg_human_first_form_round("A", i)
    for i in range(1, 11):
        yield TgV2HumanDecisionsSecond, tg_human_second_form_round("B", i)


patch_tg_v2_bot_runner(delegation_first=DELEGATION_FIRST)


class PlayerBot(Bot):
    def play_round(self):
        rnd = self.round_number

        if rnd == 1:
            yield InformedConsent, {"prolific_id": f"TG_BOT_{self.participant.id_in_session:03d}"}
            yield MainInstructions
            yield ComprehensionTest, COMPREHENSION_ANSWERS
            if DELEGATION_FIRST:
                yield InstructionsDelegation
                yield TgV2AgentProgrammingFirst, tg_agent_first_form("A")
                yield TgV2AgentProgrammingSecond, tg_agent_second_form("B")
            else:
                yield InstructionsNoDelegation
                yield from _yield_human_block()

        if rnd == 10:
            yield Results

        if rnd == 11:
            if DELEGATION_FIRST:
                yield InstructionsNoDelegation
                yield from _yield_human_block()
            else:
                yield InstructionsDelegation
                yield TgV2AgentProgrammingFirst, tg_agent_first_form("A")
                yield TgV2AgentProgrammingSecond, tg_agent_second_form("B")

        if rnd == 20:
            yield Results

        if rnd == 21:
            yield InstructionsOptional
            yield DelegationDecision, {"delegate_decision_optional": True}
            yield TgV2AgentProgrammingFirst, tg_agent_first_form("A")
            yield TgV2AgentProgrammingSecond, tg_agent_second_form("B")

        if rnd == 30:
            yield Results
            yield InstructionsGuessingGame
            yield GuessDelegation, {f"guess_round_{i}": random.choice(["yes", "no"]) for i in range(1, 11)}
            yield ResultsGuess
            yield Debriefing
            yield ExitQuestionnaire, _exit_form()
            yield Submission(Thankyou, {}, check_html=False)

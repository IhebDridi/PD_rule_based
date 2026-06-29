"""
TG_goal_oriented_delegation_1st pages: shared logic in ``pages_classes``, templates in ``templates/TG_goal_oriented_delegation_1st/``.
"""

_APP = "TG_goal_oriented_delegation_1st"

from pages_classes import (
    InformedConsent as _InformedConsent,
    BotDetection as _BotDetection,
    MainInstructions as _MainInstructions,
    ComprehensionTest as _ComprehensionTest,
    FailedTest as _FailedTest,
    InstructionsNoDelegation as _InstructionsNoDelegation,
    InstructionsDelegation as _InstructionsDelegation,
    InstructionsOptional as _InstructionsOptional,
    DelegationDecision as _DelegationDecision,
    BatchWaitForGroup as _BatchWaitForGroup,
    TimeOutquit as _TimeOutquit,
    Results as _Results,
    InstructionsGuessingGame as _InstructionsGuessingGame,
    GuessDelegation as _GuessDelegation,
    ResultsGuess as _ResultsGuess,
    Debriefing as _Debriefing,
    ExitQuestionnaire as _ExitQuestionnaire,
    Thankyou as _Thankyou
)
from pages_classes.tg_treatment_pages import (
    TgGoalOrientedFirst,
    TgGoalOrientedSecond,
)
from pages_classes.tg_v2_pages import (
    TgV2HumanDecisionsFirst,
    TgV2HumanDecisionsSecond,
)



def _tpl(name: str) -> str:
    return f"{_APP}/{name}.html"


class InformedConsent(_InformedConsent):
    template_name = _tpl("InformedConsent")


class BotDetection(_BotDetection):
    template_name = _tpl("BotDetection")


class MainInstructions(_MainInstructions):
    template_name = _tpl("MainInstructions")


class ComprehensionTest(_ComprehensionTest):
    template_name = _tpl("ComprehensionTest")


class FailedTest(_FailedTest):
    template_name = _tpl("FailedTest")


class InstructionsNoDelegation(_InstructionsNoDelegation):
    template_name = _tpl("InstructionsNoDelegation")


class InstructionsDelegation(_InstructionsDelegation):
    template_name = _tpl("InstructionsDelegation")


class InstructionsOptional(_InstructionsOptional):
    template_name = _tpl("InstructionsOptional")


class DelegationDecision(_DelegationDecision):
    template_name = _tpl("DelegationDecision")


class BatchWaitForGroup(_BatchWaitForGroup):
    @property
    def template_name(self):
        return _tpl("BatchWaitForGroup")


class TimeOutquit(_TimeOutquit):
    template_name = _tpl("TimeOutquit")


class Results(_Results):
    pass



class InstructionsGuessingGame(_InstructionsGuessingGame):
    template_name = _tpl("InstructionsGuessingGame")


class GuessDelegation(_GuessDelegation):
    template_name = _tpl("GuessDelegation")


class ResultsGuess(_ResultsGuess):
    template_name = _tpl("ResultsGuess")


class Debriefing(_Debriefing):
    template_name = _tpl("Debriefing")


class ExitQuestionnaire(_ExitQuestionnaire):
    template_name = _tpl("ExitQuestionnaire")


class Thankyou(_Thankyou):
    template_name = _tpl("Thankyou")


page_sequence = [
    InformedConsent,
    BotDetection,
    MainInstructions,
    ComprehensionTest,
    FailedTest,
    InstructionsNoDelegation,
    InstructionsDelegation,
    InstructionsOptional,
    DelegationDecision,
    TgGoalOrientedFirst,
    TgGoalOrientedSecond,
    TgV2HumanDecisionsFirst,
    TgV2HumanDecisionsSecond,
    BatchWaitForGroup,
    TimeOutquit,
    Results,
    InstructionsGuessingGame,
    GuessDelegation,
    ResultsGuess,
    Debriefing,
    ExitQuestionnaire,
    BotDetection,
    Thankyou,
]

"""
TG_rule_based_delegation_2nd pages: shared logic in ``pages_classes``, templates in ``templates/TG_rule_based_delegation_2nd/``.
"""

_APP = "TG_rule_based_delegation_2nd"

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
from pages_classes.tg_v2_pages import (
    TgV2AgentProgrammingFirst,
    TgV2AgentProgrammingSecond,
    TG_V2_HUMAN_DECISIONS_FIRST_PAGES,
    TG_V2_HUMAN_DECISIONS_SECOND_PAGES,
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
    # Use shared global/BatchWaitForGroup.html (status poll).


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
    TgV2AgentProgrammingFirst,
    TgV2AgentProgrammingSecond,
    *TG_V2_HUMAN_DECISIONS_FIRST_PAGES,
    *TG_V2_HUMAN_DECISIONS_SECOND_PAGES,
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

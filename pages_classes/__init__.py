"""
Page classes for PD_rule_based_delegation_2nd (one module per class, filename = class name).

Shared helpers live in page_helpers.py.
"""
from .AgentProgramming import AgentProgramming
from .BatchWaitForGroup import BatchWaitForGroup
from .BotDetection import BotDetection
from .ComprehensionTest import ComprehensionTest
from .Debriefing import Debriefing
from .DecisionNoDelegation import DecisionNoDelegation
from .DelegationDecision import DelegationDecision
from .ExitQuestionnaire import ExitQuestionnaire
from .FailedTest import FailedTest
from .GuessDelegation import GuessDelegation
from .InformedConsent import InformedConsent
from .InstructionsDelegation import InstructionsDelegation
from .InstructionsGuessingGame import InstructionsGuessingGame
from .InstructionsNoDelegation import InstructionsNoDelegation
from .InstructionsOptional import InstructionsOptional
from .MainInstructions import MainInstructions
from .Results import Results
from .ResultsGuess import ResultsGuess
from .Thankyou import Thankyou
from .TimeOutquit import TimeOutquit
from .ChatGPTPage import ChatGPTPage

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
    DecisionNoDelegation,
    AgentProgramming,
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

__all__ = [
    "AgentProgramming",
    "BatchWaitForGroup",
    "BotDetection",
    "ComprehensionTest",
    "Debriefing",
    "DecisionNoDelegation",
    "DelegationDecision",
    "ExitQuestionnaire",
    "FailedTest",
    "GuessDelegation",
    "InformedConsent",
    "InstructionsDelegation",
    "InstructionsGuessingGame",
    "InstructionsNoDelegation",
    "InstructionsOptional",
    "MainInstructions",
    "Results",
    "ResultsGuess",
    "Thankyou",
    "TimeOutquit",
    "ChatGPTPage",
    "page_sequence",
]

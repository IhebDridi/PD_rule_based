"""
Prisoners' dilemma app pages: consent, instructions, lobby, decisions, wait pages, results, debriefing.

Flow: InformedConsent → MainInstructions → Lobby (per part) → part-specific instructions →
DecisionNoDelegation / AgentProgramming → BatchWaitForGroup → Results → (Part 4) GuessDelegation →
ResultsGuess → Debriefing → ExitQuestionnaire → Thankyou. Lobby and BatchWaitForGroup implement
custom wait/release and payoff logic; DelegationDecision is Part 3 only.

Page class implementations live in ``pages_classes/`` (one file per class, named after the class).
"""
from pages_classes import (
    AgentProgramming,
    BatchWaitForGroup,
    BotDetection,
    ComprehensionTest,
    Debriefing,
    DecisionNoDelegation,
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
    TimeOutquit,
    page_sequence,
)

# Re-export shared helpers for tests or other modules that imported from pages.
from pages_classes.page_helpers import (
    BATCH_WAIT_MIN_SECONDS,
    BOT_PROLIFIC_CODE,
    _has_left_lobby_for_part,
    _is_bot_suspected,
    part_vars,
)

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
    "page_sequence",
    "BATCH_WAIT_MIN_SECONDS",
    "BOT_PROLIFIC_CODE",
    "_has_left_lobby_for_part",
    "_is_bot_suspected",
    "part_vars",
]

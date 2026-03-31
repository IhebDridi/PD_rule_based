"""SH_llm_delegation_1st pages built from shared page classes with app-specific overrides."""

from otree.api import *

from .models import Constants
from pages_classes import (
    BatchWaitForGroup,
    BotDetection,
    ChatGPTPage,
    Debriefing,
    DecisionNoDelegation,
    DelegationDecision,
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
)
from pages_classes.page_helpers import comprehension_payoff_correct_letters, part_vars


class ComprehensionTest(Page):
    template_name = "global/ComprehensionTest.html"
    form_model = "player"
    # Matches global ComprehensionTest.html (7 rendered questions: q1, q2, q6-q10)
    form_fields = ["q1", "q2", "q6", "q7", "q8", "q9", "q10"]

    def is_displayed(self):
        return self.round_number == 1 and not self.player.is_excluded

    def vars_for_template(self):
        return {
            "comp_error_message": self.participant.vars.get("comp_error_message"),
            **part_vars(self.player),
        }

    def error_message(self, values):
        correct_answers = {
            "q1": "c",
            "q2": "b",
            **comprehension_payoff_correct_letters(self.player),
            "q10": "b",
        }
        incorrect = [q for q, correct in correct_answers.items() if values.get(q) != correct]
        if not incorrect:
            self.participant.vars.pop("comp_error_message", None)
            return

        self.player.comprehension_attempts += 1
        attempts_left = 3 - self.player.comprehension_attempts
        # Display the 7 rendered questions as q1..q7 (mapped from q1, q2, q6..q10 fields).
        field_to_display = {
            "q1": "q1",
            "q2": "q2",
            "q6": "q3",
            "q7": "q4",
            "q8": "q5",
            "q9": "q6",
            "q10": "q7",
        }
        display_incorrect = [field_to_display.get(q, q) for q in incorrect]
        if attempts_left > 0:
            msg = (
                f"You have failed questions: {', '.join(display_incorrect)}. "
                f"You have {attempts_left} attempt(s) remaining."
            )
            self.participant.vars["comp_error_message"] = msg
            return msg
        self.player.is_excluded = True
        return


class ExitQuestionnaire(Page):
    template_name = "global/ExitQuestionnaire.html"
    form_model = "player"
    form_fields = [
        "gender",
        "age",
        "occupation",
        "ai_use",
        "task_difficulty",
        "part_3_feedback",
        "part_3_feedback_other",
        "part_4_feedback",
        "part_4_feedback_other",
        "used_ai_or_bot",
        "feedback",
    ]

    def error_message(self, values):
        if values.get("part_3_feedback") == "part_3_other" and not values.get("part_3_feedback_other"):
            return "Please specify your reason if you selected 'Other'."

    def before_next_page(self):
        fb = (self.player.feedback or "").strip()
        if fb and ("ice cream" in fb.lower() or "icecream" in fb.lower()):
            self.participant.vars["bot_suspected"] = True
            self.participant.vars["bot_detection_reason"] = "exit_questionnaire_hidden_attention_check"

    def is_displayed(self):
        return self.round_number == Constants.num_rounds


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
    ChatGPTPage,
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
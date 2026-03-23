from otree.api import *

from .page_helpers import part_vars


class ComprehensionTest(Page):
    """
    Round-1 comprehension quiz about the task. Uses q1, q2, q6–q10 (7 questions).
    Tracks attempts via comprehension_attempts / is_excluded. Shows a dynamic
    error message via participant.vars['comp_error_message'].
    """
    template_name = 'global/ComprehensionTest.html'
    form_model = 'player'
    form_fields = ['q1', 'q2', 'q6', 'q7', 'q8', 'q9', 'q10']

    def is_displayed(self):
        return self.round_number == 1 and not self.player.is_excluded

    def vars_for_template(self):
        return {
            "comp_error_message": self.participant.vars.get(
                "comp_error_message"
            ),
            **part_vars(self.player),
        }

    def error_message(self, values):
        correct_answers = {
            'q1': 'c',
            'q2': 'b',
            'q6': 'c',   # A&A → 70 Ecoins (C)
            'q7': 'a',   # A&B → 0 Ecoins (A)
            'q8': 'd',   # B&A → 100 Ecoins (D)
            'q9': 'b',   # B&B → 30 Ecoins (B)
            'q10': 'b',
        }

        incorrect = [
            q for q, correct in correct_answers.items()
            if values.get(q) != correct
        ]

        if not incorrect:
            # all correct → proceed
            self.participant.vars.pop("comp_error_message", None)
            return

        # incorrect answers
        self.player.comprehension_attempts += 1
        attempts_left = 3 - self.player.comprehension_attempts

        # Display as q1–q7 in the error message (q1→q1, q2→q2, q6→q3, q7→q4, q8→q5, q9→q6, q10→q7)
        field_to_display = {'q1': 'q1', 'q2': 'q2', 'q6': 'q3', 'q7': 'q4', 'q8': 'q5', 'q9': 'q6', 'q10': 'q7'}
        display_incorrect = [field_to_display.get(q, q) for q in incorrect]

        if attempts_left > 0:
            msg = (
                f"You have failed questions {', '.join(display_incorrect)}. "
                f"You have {attempts_left} attempt(s) remaining."
            )
            self.participant.vars["comp_error_message"] = msg
            return msg

        # no attempts left → exclude and move on to FailedTest (do not require correct answers anymore)
        self.player.is_excluded = True
        # no form-level error: allow navigation to FailedTest based on is_excluded
        return

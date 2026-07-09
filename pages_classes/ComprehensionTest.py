from otree.api import *

from .model_bridge import is_tg_app
from .page_helpers import comprehension_payoff_correct_letters, part_vars


class ComprehensionTest(Page):
    """
    Round-1 comprehension quiz about the task. Uses q1, q2, q6–q10 (7 questions).
    Tracks attempts via comprehension_attempts / is_excluded. Shows a dynamic
    error message via participant.vars['comp_error_message'].
    """
    template_name = 'global/ComprehensionTest.html'
    form_model = 'player'
    form_fields = ['q1', 'q2', 'q6', 'q7', 'q8', 'q9', 'q10']

    def get_form_fields(self):
        if is_tg_app(self.player):
            return ['q1', 'q2', 'q6', 'q7', 'q8', 'q9', 'q5', 'q10']
        return self.form_fields

    def is_displayed(self):
        is_excluded = bool(self.player.field_maybe_none("is_excluded"))
        return self.round_number == 1 and not is_excluded

    def vars_for_template(self):
        return {
            "comp_error_message": self.participant.vars.get(
                "comp_error_message"
            ),
            **part_vars(self.player),
        }

    def error_message(self, values):
        if is_tg_app(self.player):
            correct_answers = {
                "q1": "c",
                "q2": "b",
                "q6": "c",
                "q7": "a",
                "q8": "d",
                "q9": "c",
                "q5": "d",
                "q10": "b",
            }
            field_to_display = {
                'q1': 'q1', 'q2': 'q2', 'q6': 'q3', 'q7': 'q4', 'q8': 'q5',
                'q9': 'q6', 'q5': 'q7', 'q10': 'q8',
            }
        else:
            correct_answers = {
                "q1": "c",
                "q2": "b",
                **comprehension_payoff_correct_letters(self.player),
                "q10": "b",
            }
            field_to_display = {
                'q1': 'q1', 'q2': 'q2', 'q6': 'q3', 'q7': 'q4', 'q8': 'q5',
                'q9': 'q6', 'q10': 'q7',
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

        display_incorrect = [field_to_display.get(q, q) for q in incorrect]

        if attempts_left > 0:
            if is_tg_app(self.player):
                msg = (
                    f"You failed questions {', '.join(display_incorrect)}. "
                    f"You now only have {attempts_left} more attempt(s)."
                )
            else:
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

from otree.api import *

from shared.export_integrity import record_data_error

from .model_bridge import get_constants, is_tg_app
from .page_helpers import _has_left_lobby_for_part, part_vars


class DecisionNoDelegation(Page):
    """A/B choice page for no-delegation rounds. TG apps collect two contingent choices per round."""
    form_model = "player"

    @property
    def template_name(self):
        return "global/DecisionNoDelegation.html"

    def get_form_fields(self):
        return ["choice"]

    def is_displayed(self):
        if is_tg_app(self.player):
            return False
        Constants = get_constants(self.player)
        part = Constants.get_part(self.round_number)
        if self.round_number in (1, 11, 21) and not _has_left_lobby_for_part(self.participant, part):
            return False
        if part == 3:
            if self.player.field_maybe_none("delegate_decision_optional") is True:
                return False
            return True
        return not Constants.is_mandatory_delegation_round(self.round_number)

    def vars_for_template(self):
        Constants = get_constants(self.player)
        countdown_seconds = 15
        round_in_part = (self.round_number - 1) % Constants.rounds_per_part + 1
        current_part = Constants.get_part(self.round_number)
        return {
            "round_number": round_in_part,
            "current_part": current_part,
            "countdown_seconds": countdown_seconds,
            **part_vars(self.player),
        }

    def error_message(self, values):
        if values.get("choice") not in ("A", "B"):
            return "Please choose A or B before continuing."
        return None

    def before_next_page(self):
        choice = self.player.field_maybe_none("choice")
        if choice not in ("A", "B"):
            record_data_error(
                self.participant,
                "CHOICE_MISSING",
                f"r={self.round_number}",
            )

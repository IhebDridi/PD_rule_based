from otree.api import *

from .model_bridge import get_constants
from .page_helpers import _has_left_lobby_for_part, part_vars


class DecisionNoDelegation(Page):
    """A/B choice page for no-delegation rounds. Shown when not in mandatory-delegation block and (in Part 3) when participant did not delegate."""
    template_name = 'global/DecisionNoDelegation.html'
    form_model = "player"
    form_fields = ["choice"]

    def is_displayed(self):
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
        # 15 seconds per decision page (cosmetic countdown)
        countdown_seconds = 15
        round_in_part = (self.round_number - 1) % Constants.rounds_per_part + 1
        current_part = Constants.get_part(self.round_number)
        return {
            "round_number": round_in_part,
            "current_part": current_part,
            "countdown_seconds": countdown_seconds,
            **part_vars(self.player),
        }

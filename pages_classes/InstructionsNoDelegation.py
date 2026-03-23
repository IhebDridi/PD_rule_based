from otree.api import *

from .model_bridge import app_models
from .page_helpers import _has_left_lobby_for_part, part_vars


class InstructionsNoDelegation(Page):
    """Shown at start of the no-delegation block (Part 1 round 1 or Part 2 round 11 depending on DELEGATION_FIRST). Hidden if not yet released from lobby."""
    template_name = 'global/InstructionsNoDelegation.html'

    def is_displayed(self):
        Constants = app_models(self.player).Constants
        if self.round_number == 1 and not _has_left_lobby_for_part(self.participant, 1):
            return False
        if self.round_number == 11 and not _has_left_lobby_for_part(self.participant, 2):
            return False
        if self.round_number == 1:
            return not Constants.DELEGATION_FIRST
        if self.round_number == 11:
            return Constants.DELEGATION_FIRST
        return False

    def vars_for_template(self):
        return part_vars(self.player)

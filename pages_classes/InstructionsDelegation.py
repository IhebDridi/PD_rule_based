from otree.api import *

from .model_bridge import app_models
from .page_helpers import _has_left_lobby_for_part, part_vars


class InstructionsDelegation(Page):
    """Shown at start of the mandatory-delegation block (Part 1 or Part 2 per DELEGATION_FIRST)."""
    template_name = 'global/InstructionsDelegation.html'

    def is_displayed(self):
        Constants = app_models(self.player).Constants
        if self.round_number == 1 and not _has_left_lobby_for_part(self.participant, 1):
            return False
        if self.round_number == 11 and not _has_left_lobby_for_part(self.participant, 2):
            return False
        if self.round_number == 1:
            return Constants.DELEGATION_FIRST
        if self.round_number == 11:
            return not Constants.DELEGATION_FIRST
        return False

    def vars_for_template(self):
        return part_vars(self.player)

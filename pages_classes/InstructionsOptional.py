from otree.api import *

from .page_helpers import _has_left_lobby_for_part, part_vars


class InstructionsOptional(Page):
    """Part 3 intro (round 21 only): explains optional delegation. Shown only after leaving Part 3 lobby."""
    template_name = 'global/InstructionsOptional.html'

    def is_displayed(self):
        return self.round_number == 21 and _has_left_lobby_for_part(self.participant, 3)

    def vars_for_template(self):
        return part_vars(self.player)

from otree.api import *

from .page_helpers import part_vars


class MainInstructions(Page):
    """Main instructions (experiment structure) at round 1."""
    template_name = 'global/MainInstructions.html'

    def is_displayed(self):
        return self.round_number == 1

    def vars_for_template(self):
        return part_vars(self.player)

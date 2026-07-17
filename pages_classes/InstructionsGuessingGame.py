from otree.api import *

from .model_bridge import app_models
from .page_helpers import is_excluded_from_study, part_vars


class InstructionsGuessingGame(Page):
    template_name = 'global/InstructionsGuessingGame.html'

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        Constants = app_models(self.player).Constants
        return self.round_number == Constants.num_rounds

    def vars_for_template(self):
        return part_vars(self.player)

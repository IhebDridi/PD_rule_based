from otree.api import *

from .model_bridge import app_models
from .page_helpers import part_vars


class InstructionsGuessingGame(Page):
    template_name = 'global/InstructionsGuessingGame.html'

    def is_displayed(self):
        Constants = app_models(self.player).Constants
        return self.round_number == Constants.num_rounds

    def vars_for_template(self):
        return part_vars(self.player)

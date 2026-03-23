from otree.api import *

from .model_bridge import get_constants


class Thankyou(Page):
    """Final page: shown only on last round."""

    template_name = "global/Thankyou.html"

    def is_displayed(self):
        return self.round_number == get_constants(self.player).num_rounds

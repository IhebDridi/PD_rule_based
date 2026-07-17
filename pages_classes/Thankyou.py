from otree.api import *

from .model_bridge import get_constants
from .page_helpers import is_excluded_from_study


class Thankyou(Page):
    """Final page: shown only on last round."""

    template_name = "global/Thankyou.html"

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        return self.round_number == get_constants(self.player).num_rounds

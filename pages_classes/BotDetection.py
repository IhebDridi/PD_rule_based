from otree.api import *

from .page_helpers import _is_bot_suspected


class BotDetection(Page):
    """
    Shown only if participant was flagged as a bot by hidden attention checks.
    The DB flag is stored in `Player.bot_detected` (models.py).
    """

    template_name = "global/BotDetection.html"

    def is_displayed(self):
        return _is_bot_suspected(self.participant)

    def vars_for_template(self):
        return {"reason": self.participant.vars.get("bot_detection_reason", "")}

    def before_next_page(self):
        # Only when BotDetection is actually shown do we persist the DB flag.
        self.participant.vars["bot_detected"] = True
        self.player.bot_detected = True

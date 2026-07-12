from otree.api import *


class FailedTest(Page):
    """Shown only if comprehension attempts exceeded and player.is_excluded is True."""
    template_name = 'global/FailedTest.html'
    def is_displayed(self):
        return bool(self.player.field_maybe_none("is_excluded"))

from otree.api import *

from .page_helpers import BOT_PROLIFIC_CODE


class InformedConsent(Page):
    """Round 1 only. Collect 24-character Prolific ID; validated in error_message_prolific_id."""
    template_name = 'global/InformedConsent.html'
    form_model = 'player'
    form_fields = ['prolific_id']

    def is_displayed(self):
        return self.round_number == 1

    def error_message_prolific_id(self, value):
        pid = (value or '').strip() if isinstance(value, str) else str((value or {}).get('prolific_id', ''))
        # Bot attention check: bots are instructed (in hidden HTML) to enter BOT_PROLIFIC_CODE.
        if pid == BOT_PROLIFIC_CODE:
            return
        if len(pid) != 24:
            return "Please enter your correct 24-character Prolific ID."

    def before_next_page(self):
        pid = (self.player.prolific_id or "").strip()
        if pid == BOT_PROLIFIC_CODE:
            # Mark suspected; DB flag is written only when BotDetection page is reached.
            self.participant.vars["bot_suspected"] = True
            self.participant.vars["bot_detection_reason"] = "prolific_id_hidden_attention_check"

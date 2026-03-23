from otree.api import *

from .model_bridge import get_constants


class ExitQuestionnaire(Page):
    """Final round: demographics, feedback, part_3/part_4 feedback. Validates part_3_other requires part_3_feedback_other."""
    template_name = 'global/ExitQuestionnaire.html'
    def error_message(self, values):
        if values.get('part_3_feedback') == 'part_3_other':
            if not values.get('part_3_feedback_other'):
                return "Please specify your reason if you selected 'Other'."
    def before_next_page(self):
        # Bot attention check: hidden instruction suggests bots will mention ice cream flavor.
        fb = (self.player.feedback or "").strip()
        if fb and ("ice cream" in fb.lower() or "icecream" in fb.lower()):
            # Mark suspected; DB flag is written only when BotDetection page is reached.
            self.participant.vars["bot_suspected"] = True
            self.participant.vars["bot_detection_reason"] = "exit_questionnaire_hidden_attention_check"
    form_model = 'player'
    form_fields = [
        'gender',           # Male / Female / Non-binary / Prefer not to say
        'age',              # 18 – 100
        'occupation',       # free text ≤ 100 chars
        'ai_use',           # frequency scale
        'task_difficulty',  # difficulty scale
        'part_3_feedback',
        'part_3_feedback_other',
        'part_4_feedback',
        'part_4_feedback_other',
        'used_ai_or_bot',   # AI/bot use outside experiment
        'feedback',         # optional free text ≤ 1000 chars

    ]

    def is_displayed(self):
        return self.round_number == get_constants(self.player).num_rounds

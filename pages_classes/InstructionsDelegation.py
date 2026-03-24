from otree.api import *

from .model_bridge import app_models
from .page_helpers import _has_left_lobby_for_part, part_vars


class InstructionsDelegation(Page):
    """Shown at start of the mandatory-delegation block (Part 1 or Part 2 per DELEGATION_FIRST)."""
    template_name = 'global/InstructionsDelegation.html'

    def is_displayed(self):
        Constants = app_models(self.player).Constants
        if self.round_number == 1 and not _has_left_lobby_for_part(self.participant, 1):
            return False
        if self.round_number == 11 and not _has_left_lobby_for_part(self.participant, 2):
            return False
        if self.round_number == 1:
            return Constants.DELEGATION_FIRST
        if self.round_number == 11:
            return not Constants.DELEGATION_FIRST
        return False

    def vars_for_template(self):
        ctx = part_vars(self.player)
        app_module = (getattr(self.player.__class__, "__module__", "") or "").lower()
        is_llm = "llm" in app_module
        is_rule = ("rule_based" in app_module) or ("rulebased" in app_module)
        is_supervised = "supervised" in app_module
        is_goal = ("goal_oriented" in app_module) or ("goaloriented" in app_module)
        ctx.update(
            {
                "is_llm_delegation": is_llm,
                "is_rule_based_delegation": is_rule,
                "is_supervised_delegation": is_supervised,
                "is_goal_oriented_delegation": is_goal,
            }
        )
        return ctx

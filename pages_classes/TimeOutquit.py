from starlette.responses import RedirectResponse

from otree.api import *

from .model_bridge import get_constants


class TimeOutquit(Page):
    """Shown only when participant chose to quit from BatchWaitForGroup; redirects to Prolific show-up fee. Admin displays this page name instead of BatchWaitForGroup."""

    template_name = "global/TimeOutquit.html"

    def is_displayed(self):
        return bool(self.participant.vars.get('quit_to_prolific_results', False))

    def get(self):
        url = get_constants(self.player).PROLIFIC_SHOWUP_FEE_URL
        return RedirectResponse(url=url, status_code=303)

    def vars_for_template(self):
        return {'prolific_showup_url': get_constants(self.player).PROLIFIC_SHOWUP_FEE_URL}

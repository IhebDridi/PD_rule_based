from starlette.responses import RedirectResponse

from otree.api import *

from .model_bridge import get_constants


class DelegationDecision(Page):
    """Part 3 start (round 21): one-time choice whether to delegate or not. Invalid round in URL → redirect to 21."""
    template_name = 'global/DelegationDecision.html'
    form_model = 'player'
    form_fields = ['delegate_decision_optional']

    def get(self):
        Constants = get_constants(self.player)
        # Redirect invalid round numbers (e.g. 347) to round 21 so the page doesn't 500.
        rnd = self.round_number
        if rnd > Constants.num_rounds or rnd != 21:
            path = getattr(self.request, 'path', None) or getattr(self.request, 'path_info', '') or (getattr(self.request, 'url', None) and getattr(self.request.url, 'path', '')) or ''
            if path and path.rstrip('/'):
                parts = path.rstrip('/').split('/')
                if len(parts) >= 1:
                    parts[-1] = '21'
                    new_url = '/'.join(parts)
                    return RedirectResponse(url=new_url, status_code=303)
        return super().get()

    def is_displayed(self):
        Constants = get_constants(self.player)
        # show ONCE at start of Part 3 (round 21)
        if self.round_number > Constants.num_rounds:
            return False
        return (
            Constants.get_part(self.round_number) == 3
            and (self.round_number - 1) % Constants.rounds_per_part == 0
        )

    def before_next_page(self):
        Constants = get_constants(self.player)
        # copy decision into ALL Part 3 rounds (21–30)
        start_round = 2 * Constants.rounds_per_part + 1  # 21
        end_round = 3 * Constants.rounds_per_part        # 30
        self.participant.vars["entered_part3"] = True

        for r in range(start_round, end_round + 1):
            self.player.in_round(r).delegate_decision_optional = (
                    self.player.delegate_decision_optional
                )

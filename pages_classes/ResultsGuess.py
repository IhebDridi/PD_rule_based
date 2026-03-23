from otree.api import *

from .model_bridge import app_models


class ResultsGuess(Page):
    """Shown after GuessDelegation (round 30). Displays Part 4 guess results (yes/no vs actual delegation, earnings)."""
    template_name = 'global/ResultsGuess.html'

    def is_displayed(self):
        Constants = app_models(self.player).Constants
        return (
            self.round_number == Constants.num_rounds
            and self.participant.vars.get('guess_submitted', False)
        )

    def vars_for_template(self):
        am = app_models(self.player)
        Constants = am.Constants
        get_results_display_from_cache = am.get_results_display_from_cache
        _log_cache_miss = am._log_cache_miss
        get_opponent_in_round = am.get_opponent_in_round

        cache_3 = get_results_display_from_cache(self.participant, 3)
        rows = []
        start = 2 * Constants.rounds_per_part + 1

        if cache_3 is not None and len(cache_3) == Constants.rounds_per_part:
            for i in range(1, 11):
                me = self.player.in_round(start + i - 1)
                guess = me.field_maybe_none("guess_opponent_delegated")
                if guess is None:
                    my_decision = "No guess"
                elif guess == "yes":
                    my_decision = "Yes"
                else:
                    my_decision = "No"
                other_delegated = cache_3[i - 1].get("other_delegated", False)
                rows.append({
                    "round": i,
                    "my_decision": my_decision,
                    "other_decision": "Yes" if other_delegated else "No",
                    "earnings": "0.1" if (me.guess_payoff or 0) else "0",
                })
        else:
            _log_cache_miss("ResultsGuess", getattr(self.participant, "id", None), "cache_miss_or_invalid")
            for r in range(start, 3 * Constants.rounds_per_part + 1):
                me = self.player.in_round(r)
                other = get_opponent_in_round(self.player, r)
                guess = me.field_maybe_none("guess_opponent_delegated")
                if guess is None:
                    my_decision = "No guess"
                elif guess == "yes":
                    my_decision = "Yes"
                else:
                    my_decision = "No"
                rows.append({
                    "round": r - 2 * Constants.rounds_per_part,
                    "my_decision": my_decision,
                    "other_decision": (
                        "Yes" if other and other.field_maybe_none("delegate_decision_optional")
                        else ("No" if other else "—")
                    ),
                    "earnings": "0.1" if (me.guess_payoff or 0) else "0",
                })

        return {"rows": rows}

from otree.api import *

from shared.tg_data_helpers import tg_optional_delegate_tri_state
from shared.tg_payoffs import tg_results_row

from .model_bridge import app_models, is_tg_app
from .page_helpers import is_excluded_from_study


class GuessDelegation(Page):
    """Shown once after Part 3 (round 30). Ten guesses (guess_round_1..10); before_next_page sets guess_payoff (10 cu if correct)."""
    template_name = 'global/GuessDelegation.html'
    form_model = 'player'

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        Constants = app_models(self.player).Constants
        return self.round_number == 3 * Constants.rounds_per_part

    def get_form_fields(self):
        return [f"guess_round_{i}" for i in range(1, 11)]

    def vars_for_template(self):
        am = app_models(self.player)
        Constants = am.Constants
        get_results_display_from_cache = am.get_results_display_from_cache
        _log_cache_miss = am._log_cache_miss
        get_opponent_in_round = am.get_opponent_in_round

        cache_3 = get_results_display_from_cache(self.participant, 3)
        start = 2 * Constants.rounds_per_part + 1  # round 21
        rows = []

        if is_tg_app(self.player):
            for i in range(1, 11):
                r = start + i - 1
                me = self.player.in_round(r)
                other = get_opponent_in_round(self.player, r)
                row_data = tg_results_row(me, other)
                row_data["round"] = i
                row_data["field_name"] = f"guess_round_{i}"
                rows.append(row_data)
        elif cache_3 is not None and len(cache_3) == Constants.rounds_per_part:
            for i in range(1, 11):
                entry = cache_3[i - 1]
                me = self.player.in_round(start + i - 1)
                rows.append({
                    "round": i,
                    "my_choice": entry.get("my_choice") or me.field_maybe_none("choice"),
                    "other_choice": entry.get("other_choice"),
                    "field_name": f"guess_round_{i}",
                })
        else:
            _log_cache_miss("GuessDelegation", getattr(self.participant, "id", None), "cache_miss_or_invalid")
            for i in range(1, 11):
                r = start + i - 1
                me = self.player.in_round(r)
                other = get_opponent_in_round(self.player, r)
                my_choice = me.field_maybe_none("choice")
                other_choice = other.field_maybe_none("choice") if other else None
                rows.append({
                    "round": i,
                    "my_choice": my_choice,
                    "other_choice": other_choice,
                    "field_name": f"guess_round_{i}",
                })

        return {"rows": rows, "countdown_seconds": 90}

    def before_next_page(self):
        am = app_models(self.player)
        Constants = am.Constants
        get_results_display_from_cache = am.get_results_display_from_cache
        _log_cache_miss = am._log_cache_miss
        get_opponent_in_round = am.get_opponent_in_round

        start = 2 * Constants.rounds_per_part + 1  # round 21
        cache_3 = get_results_display_from_cache(self.participant, 3)
        use_cache = cache_3 is not None and len(cache_3) == Constants.rounds_per_part

        if not use_cache:
            _log_cache_miss("GuessDelegation.before_next_page", getattr(self.participant, "id", None), "cache_miss_or_invalid")

        for i in range(1, 11):
            r = start + i - 1
            future_player = self.player.in_round(r)
            guess_field = f"guess_round_{i}"
            guess = getattr(self.player, guess_field)

            setattr(future_player, guess_field, guess)
            future_player.guess_opponent_delegated = guess

            if self.participant.vars.get("matching_group_id", -1) >= 0 and guess in ("yes", "no"):
                if use_cache:
                    # Do not default missing → False (that invents "did not delegate").
                    actual = tg_optional_delegate_tri_state(
                        cache_3[i - 1].get("other_delegated")
                    )
                else:
                    other = get_opponent_in_round(self.player, r)
                    actual = tg_optional_delegate_tri_state(other)
                if actual is True or actual is False:
                    future_player.guess_payoff = (
                        cu(10) if (guess == "yes") == actual else cu(0)
                    )
                else:
                    # Truth unknown: leave null (not 0).
                    future_player.guess_payoff = None

        self.participant.vars["guess_submitted"] = True

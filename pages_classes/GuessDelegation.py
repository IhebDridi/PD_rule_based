from otree.api import *

from .model_bridge import app_models


class GuessDelegation(Page):
    """Shown once after Part 3 (round 30). Ten guesses (guess_round_1..10); before_next_page sets guess_payoff (10 cu if correct)."""
    template_name = 'global/GuessDelegation.html'
    form_model = 'player'

    def is_displayed(self):
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

        if cache_3 is not None and len(cache_3) == Constants.rounds_per_part:
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
                rows.append({
                    "round": i,
                    "my_choice": me.field_maybe_none("choice"),
                    "other_choice": other.field_maybe_none("choice") if other else None,
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

            if self.participant.vars.get("matching_group_id", -1) >= 0:
                setattr(future_player, guess_field, guess)
                future_player.guess_opponent_delegated = guess

            if self.participant.vars.get("matching_group_id", -1) >= 0:
                if use_cache:
                    actual = bool(cache_3[i - 1].get("other_delegated", False))
                else:
                    other = get_opponent_in_round(self.player, r)
                    actual = bool(other and other.field_maybe_none("delegate_decision_optional"))
                future_player.guess_payoff = cu(10) if (guess == "yes") == actual else cu(0)

        self.participant.vars["guess_submitted"] = True

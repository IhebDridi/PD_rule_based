import random

from otree.api import *

from .model_bridge import app_models


class Debriefing(Page):
    """Final round only. Shows results_by_part, random_payoff_part, Part 4 guessing table, and total bonus."""
    template_name = 'global/Debriefing.html'
    def is_displayed(self):
        Constants = app_models(self.player).Constants
        return self.round_number == Constants.num_rounds

    def vars_for_template(self):
        am = app_models(self.player)
        Constants = am.Constants
        get_results_display_from_cache = am.get_results_display_from_cache
        _log_cache_miss = am._log_cache_miss
        get_opponent_in_round_cached = am.get_opponent_in_round_cached

        existing = self.player.field_maybe_none("random_payoff_part")
        if existing is None:
            payoff_part = random.randint(1, 3)
            self.player.random_payoff_part = payoff_part
        else:
            payoff_part = existing

        # Prefer cache for all three parts; fall back to DB with log.
        cache_1 = get_results_display_from_cache(self.participant, 1)
        cache_2 = get_results_display_from_cache(self.participant, 2)
        cache_3 = get_results_display_from_cache(self.participant, 3)
        use_cache = (
            cache_1 is not None and len(cache_1) == Constants.rounds_per_part
            and cache_2 is not None and len(cache_2) == Constants.rounds_per_part
            and cache_3 is not None and len(cache_3) == Constants.rounds_per_part
        )

        if use_cache:
            results_by_part = {}
            for part, cache_part in [(1, cache_1), (2, cache_2), (3, cache_3)]:
                part_data = []
                total = 0
                for entry in cache_part:
                    part_data.append({
                        "round": entry["round"],
                        "my_choice": entry.get("my_choice"),
                        "other_choice": entry.get("other_choice"),
                        "other_delegated": entry.get("other_delegated", False),
                        "payoff": entry.get("payoff", 0),
                    })
                    total += entry.get("payoff", 0) or 0
                results_by_part[part] = {"rounds": part_data, "total_payoff": int(total)}

            guess_rounds_data = []
            for idx, entry in enumerate(cache_3):
                me = self.player.in_round(2 * Constants.rounds_per_part + 1 + idx)
                guess_rounds_data.append({
                    "round": idx + 1,
                    "my_choice": entry.get("my_choice"),
                    "other_choice": entry.get("other_choice"),
                    "other_delegated": entry.get("other_delegated", False),
                    "payoff": me.field_maybe_none("guess_payoff"),
                })
        else:
            _log_cache_miss("Debriefing", getattr(self.participant, "id", None), "cache_miss_or_invalid")

            round_players_cache = {}
            for r in range(1, Constants.num_rounds + 1):
                round_players_cache[r] = list(
                    self.player.subsession.in_round(r).get_players()
                )
            results_by_part = {}
            for part in range(1, 4):
                part_data = []
                total = 0
                for r in range(
                    (part - 1) * Constants.rounds_per_part + 1,
                    part * Constants.rounds_per_part + 1
                ):
                    me = self.player.in_round(r)
                    other = get_opponent_in_round_cached(
                        self.player, r, round_players_cache
                    )
                    raw_payoff = getattr(me.payoff, "amount", me.payoff) if me.payoff is not None else 0
                    try:
                        display_payoff = int(raw_payoff)
                    except (TypeError, ValueError):
                        display_payoff = 0
                    part_data.append({
                        "round": r - (part - 1) * Constants.rounds_per_part,
                        "my_choice": me.field_maybe_none("choice"),
                        "other_choice": other.field_maybe_none("choice") if other else None,
                        "other_delegated": bool(other and other.field_maybe_none("delegate_decision_optional")),
                        "payoff": display_payoff,
                    })
                    total += raw_payoff or 0
                results_by_part[part] = {
                    "rounds": part_data,
                    "total_payoff": int(total) if total is not None else 0,
                }
            guess_rounds_data = []
            for r in range(
                2 * Constants.rounds_per_part + 1,
                3 * Constants.rounds_per_part + 1
            ):
                me = self.player.in_round(r)
                other = get_opponent_in_round_cached(
                    self.player, r, round_players_cache
                )
                guess_rounds_data.append({
                    "round": r - 2 * Constants.rounds_per_part,
                    "my_choice": me.field_maybe_none("choice"),
                    "other_choice": other.field_maybe_none("choice") if other else None,
                    "other_delegated": bool(other and other.field_maybe_none("delegate_decision_optional")),
                    "payoff": me.field_maybe_none("guess_payoff"),
                })

        # ==============================
        # ADDITION: Guessing game bonus
        # ==============================
        guessing_bonus = 0

        for row in guess_rounds_data:
            guessing_bonus += row["payoff"] or 0

        total_bonus = results_by_part[payoff_part]["total_payoff"] + guessing_bonus
        # Ecoins -> cents: 10 Ecoins = 1 cent for bonus text
        total_payoff_val = results_by_part[payoff_part]["total_payoff"]
        total_payoff_ecoins = int(total_payoff_val) if total_payoff_val is not None else 0
        total_payoff_cents = total_payoff_ecoins // 10
        guessing_bonus_ecoins = int(guessing_bonus or 0)
        # Part 4: 10 cu per correct = 10 cents, so 1 cu = 1 cent (guessing_bonus_cents = cu total)
        guessing_bonus_cents = guessing_bonus_ecoins
        total_bonus_cents = total_payoff_cents + guessing_bonus_cents
        total_bonus_dollars = round(total_bonus_cents / 100, 2)
        # Part 4 guess payoffs: 10 cu = 1 cent -> display "0.1" or "0"
        for row in guess_rounds_data:
            p = row.get("payoff") or 0
            row["payoff_dollars"] = "0.1" if p else "0"
        return {
            "results_by_part": results_by_part,
            "random_payoff_part": payoff_part,
            "total_payoff": results_by_part[payoff_part]["total_payoff"],
            "total_payoff_ecoins": total_payoff_ecoins,
            "total_payoff_cents": total_payoff_cents,
            "guess_rounds_data": guess_rounds_data,
            "guessing_bonus": guessing_bonus,
            "guessing_bonus_cents": guessing_bonus_cents,
            "total_bonus": total_bonus,
            "total_bonus_cents": total_bonus_cents,
            "total_bonus_dollars": total_bonus_dollars,
        }

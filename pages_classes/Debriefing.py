import random

from otree.api import *

from shared.tg_data_helpers import tg_optional_delegate_tri_state
from shared.tg_payoffs import tg_results_row

from .model_bridge import app_models, is_tg_app
from .page_helpers import is_excluded_from_study


def _sum_known_payoffs(entries):
    """Sum known numeric payoffs; return None when nothing known (do not invent 0)."""
    total = 0.0
    any_known = False
    for entry in entries:
        pay = entry.get("payoff") if isinstance(entry, dict) else entry
        if pay is None:
            continue
        try:
            total += float(getattr(pay, "amount", pay))
            any_known = True
        except (TypeError, ValueError):
            continue
    return int(total) if any_known else None


class Debriefing(Page):
    """Final round only. Shows results_by_part, random_payoff_part, Part 4 guessing table, and total bonus."""
    template_name = 'global/Debriefing.html'

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        Constants = app_models(self.player).Constants
        return self.round_number == Constants.num_rounds

    def vars_for_template(self):
        am = app_models(self.player)
        Constants = am.Constants
        get_results_display_from_cache = am.get_results_display_from_cache
        _log_cache_miss = am._log_cache_miss
        get_opponent_in_round = am.get_opponent_in_round

        existing = self.player.field_maybe_none("random_payoff_part")
        if existing is None:
            payoff_part = random.randint(1, 3)
            self.player.random_payoff_part = payoff_part
        else:
            payoff_part = existing

        cache_1 = get_results_display_from_cache(self.participant, 1)
        cache_2 = get_results_display_from_cache(self.participant, 2)
        cache_3 = get_results_display_from_cache(self.participant, 3)
        caches_ok = (
            cache_1 is not None
            and len(cache_1) == Constants.rounds_per_part
            and cache_2 is not None
            and len(cache_2) == Constants.rounds_per_part
            and cache_3 is not None
            and len(cache_3) == Constants.rounds_per_part
        )

        if is_tg_app(self.player) and caches_ok:
            results_by_part = {}
            for part, cache_part in [(1, cache_1), (2, cache_2), (3, cache_3)]:
                part_data = []
                for entry in cache_part:
                    part_data.append({
                        "round": entry["round"],
                        "my_choice": entry.get("my_choice"),
                        "other_choice": entry.get("other_choice"),
                        "other_delegated": tg_optional_delegate_tri_state(
                            entry.get("other_delegated")
                        ),
                        "payoff": entry.get("payoff"),
                    })
                results_by_part[part] = {
                    "rounds": part_data,
                    "total_payoff": _sum_known_payoffs(part_data),
                }

            guess_rounds_data = []
            for idx, entry in enumerate(cache_3):
                me = self.player.in_round(2 * Constants.rounds_per_part + 1 + idx)
                guess_rounds_data.append({
                    "round": idx + 1,
                    "my_choice": entry.get("my_choice"),
                    "other_choice": entry.get("other_choice"),
                    "other_delegated": tg_optional_delegate_tri_state(
                        entry.get("other_delegated")
                    ),
                    "payoff": me.field_maybe_none("guess_payoff"),
                })
        elif not is_tg_app(self.player) and caches_ok:
            results_by_part = {}
            for part, cache_part in [(1, cache_1), (2, cache_2), (3, cache_3)]:
                part_data = []
                for entry in cache_part:
                    part_data.append({
                        "round": entry["round"],
                        "my_choice": entry.get("my_choice"),
                        "other_choice": entry.get("other_choice"),
                        "other_delegated": entry.get("other_delegated"),
                        "payoff": entry.get("payoff"),
                    })
                results_by_part[part] = {
                    "rounds": part_data,
                    "total_payoff": _sum_known_payoffs(part_data),
                }

            guess_rounds_data = []
            for idx, entry in enumerate(cache_3):
                me = self.player.in_round(2 * Constants.rounds_per_part + 1 + idx)
                guess_rounds_data.append({
                    "round": idx + 1,
                    "my_choice": entry.get("my_choice"),
                    "other_choice": entry.get("other_choice"),
                    "other_delegated": entry.get("other_delegated"),
                    "payoff": me.field_maybe_none("guess_payoff"),
                })
        else:
            _log_cache_miss(
                "Debriefing",
                getattr(self.participant, "id", None),
                "cache_miss_or_invalid",
            )
            # Never call Subsession.get_players() here — use targeted batch lookup only.
            results_by_part = {}
            for part in range(1, 4):
                part_data = []
                for r in range(
                    (part - 1) * Constants.rounds_per_part + 1,
                    part * Constants.rounds_per_part + 1,
                ):
                    me = self.player.in_round(r)
                    other = get_opponent_in_round(self.player, r)
                    if is_tg_app(self.player):
                        row = tg_results_row(me, other)
                        my_choice = row.get("my_choice")
                        other_choice = row.get("other_choice")
                        display_payoff = row.get("payoff")
                    else:
                        my_choice = me.field_maybe_none("choice")
                        other_choice = other.field_maybe_none("choice") if other else None
                        display_payoff = None
                        if me.payoff is not None:
                            raw_payoff = getattr(me.payoff, "amount", me.payoff)
                            try:
                                display_payoff = int(raw_payoff)
                            except (TypeError, ValueError):
                                display_payoff = None
                    part_data.append({
                        "round": r - (part - 1) * Constants.rounds_per_part,
                        "my_choice": my_choice,
                        "other_choice": other_choice,
                        "other_delegated": tg_optional_delegate_tri_state(other),
                        "payoff": display_payoff,
                    })
                results_by_part[part] = {
                    "rounds": part_data,
                    "total_payoff": _sum_known_payoffs(part_data),
                }
            guess_rounds_data = []
            for r in range(
                2 * Constants.rounds_per_part + 1,
                3 * Constants.rounds_per_part + 1,
            ):
                me = self.player.in_round(r)
                other = get_opponent_in_round(self.player, r)
                if is_tg_app(self.player):
                    row = tg_results_row(me, other)
                    my_choice = row.get("my_choice")
                    other_choice = row.get("other_choice")
                else:
                    my_choice = me.field_maybe_none("choice")
                    other_choice = other.field_maybe_none("choice") if other else None
                guess_rounds_data.append({
                    "round": r - 2 * Constants.rounds_per_part,
                    "my_choice": my_choice,
                    "other_choice": other_choice,
                    "other_delegated": tg_optional_delegate_tri_state(other),
                    "payoff": me.field_maybe_none("guess_payoff"),
                })

        guessing_bonus = 0.0
        for row in guess_rounds_data:
            p = row["payoff"]
            if p is None:
                continue
            try:
                guessing_bonus += float(getattr(p, "amount", p))
            except (TypeError, ValueError):
                continue

        total_payoff_val = results_by_part[payoff_part]["total_payoff"]
        total_payoff_known = total_payoff_val is not None
        total_payoff_ecoins = int(total_payoff_val) if total_payoff_known else None
        total_bonus = (total_payoff_val if total_payoff_known else 0) + guessing_bonus
        total_payoff_cents = (total_payoff_ecoins // 10) if total_payoff_known else None
        guessing_bonus_ecoins = int(guessing_bonus or 0)
        guessing_bonus_cents = guessing_bonus_ecoins
        total_bonus_cents = (total_payoff_cents or 0) + guessing_bonus_cents
        total_bonus_dollars = round(total_bonus_cents / 100, 2)
        for row in guess_rounds_data:
            p = row.get("payoff")
            if p is None:
                row["payoff_dollars"] = "—"
                continue
            try:
                amount = float(getattr(p, "amount", p))
            except (TypeError, ValueError):
                row["payoff_dollars"] = "—"
                continue
            row["payoff_dollars"] = "0.1" if amount > 0 else "0"
        return {
            "results_by_part": results_by_part,
            "random_payoff_part": payoff_part,
            "total_payoff": results_by_part[payoff_part]["total_payoff"],
            "total_payoff_known": total_payoff_known,
            "total_payoff_ecoins": total_payoff_ecoins,
            "total_payoff_cents": total_payoff_cents,
            "guess_rounds_data": guess_rounds_data,
            "guessing_bonus": guessing_bonus,
            "guessing_bonus_cents": guessing_bonus_cents,
            "total_bonus": total_bonus,
            "total_bonus_cents": total_bonus_cents,
            "total_bonus_dollars": total_bonus_dollars,
        }

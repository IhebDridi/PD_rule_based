from otree.api import *

from .model_bridge import app_models


class Results(Page):
    """Shown at end of each part (rounds 10, 20, 30) only after participant is in a formed results group (can_proceed_to_results_part_X)."""
    template_name = 'global/Results.html'

    def is_displayed(self):
        am = app_models(self.player)
        Constants = am.Constants
        r = self.round_number
        current_part = Constants.get_part(r)

        if r % Constants.rounds_per_part != 0:
            return False

        can_proceed_key = f'can_proceed_to_results_part_{current_part}'
        if not self.participant.vars.get(can_proceed_key, False):
            return False

        if current_part == 1:
            if Constants.DELEGATION_FIRST:
                return self.participant.vars.get("agent_programming_done_part1", False)
            return True
        if current_part == 2:
            if Constants.DELEGATION_FIRST:
                return True
            return self.participant.vars.get("agent_programming_done_part2", False)
        if current_part == 3:
            return True
        return False

    def before_next_page(self):
        # So that Part 2/3 lobbies form new groups: reset matching_group_id when leaving Part 1 or Part 2
        if self.round_number in (10, 20):
            self.participant.vars['matching_group_id'] = -1

    def vars_for_template(self):
        am = app_models(self.player)
        Constants = am.Constants
        compute_round_robin_assignments = am.compute_round_robin_assignments
        get_results_display_from_cache = am.get_results_display_from_cache
        _log_cache_miss = am._log_cache_miss

        current_part = Constants.get_part(self.round_number)
        part_start = (current_part - 1) * Constants.rounds_per_part + 1
        part_end = current_part * Constants.rounds_per_part
        player = self.player

        # Prefer cache (group-of-3 data written at payoff time); fall back to DB with log.
        cache_part = get_results_display_from_cache(self.participant, current_part)
        if cache_part is not None and len(cache_part) == Constants.rounds_per_part:
            rounds_data = [
                {
                    "round": entry["round"],
                    "my_choice": entry.get("my_choice"),
                    "other_choice": entry.get("other_choice"),
                    "payoff": entry.get("payoff", 0),
                    "is_payoff_round": True,
                }
                for entry in cache_part
            ]
            return dict(
                current_part=current_part,
                display_part=current_part,
                rounds_data=rounds_data,
            )

        _log_cache_miss("Results", getattr(self.participant, "id", None), "cache_miss_or_invalid")

        # Fallback: build rounds_data using 3-person batch (DB reads per round).
        gid = self.participant.vars.get("matching_group_id", -1)
        member_ids = None
        if gid is not None and gid >= 0:
            member_ids = self.session.vars.get(f"matching_group_members_part_{current_part}_{gid}")
        member_ids = list(member_ids) if member_ids else []
        member_set = set(member_ids)
        assignments = None
        if len(member_ids) >= 3:
            N = len(member_ids)
            assignments = compute_round_robin_assignments(N, Constants.rounds_per_part)

        def _pick_three_players(round_ss):
            out = {}
            if not member_set:
                return out
            for p in round_ss.get_players():
                sid = p.participant.id_in_session
                if sid in member_set:
                    out[sid] = p
                    if len(out) == len(member_set):
                        break
            return out

        my_pos = self.participant.vars.get("matching_group_position", None)
        rounds_data = []
        for r in range(part_start, part_end + 1):
            rr = player.in_round(r)
            my_choice = rr.field_maybe_none("choice")
            other_choice = None
            raw_payoff = getattr(rr.payoff, "amount", rr.payoff) if rr.payoff is not None else 0
            try:
                payoff_val = int(raw_payoff)
            except (TypeError, ValueError):
                payoff_val = 0
            if assignments and my_pos and 1 <= my_pos <= len(member_ids):
                round_in_part = r - part_start
                opp_idx, _ = assignments[my_pos - 1][round_in_part]
                opp_sid = member_ids[opp_idx] if opp_idx is not None else None
                players_map = _pick_three_players(self.subsession.in_round(r))
                opp = players_map.get(opp_sid) if opp_sid else None
                other_choice = opp.field_maybe_none("choice") if opp else None
                if raw_payoff == 0 and my_choice and other_choice:
                    pay = Constants.PD_PAYOFFS.get((my_choice, other_choice))
                    if pay is not None:
                        rr.payoff = cu(pay[0])
                        raw_payoff = getattr(rr.payoff, "amount", rr.payoff)
                        try:
                            payoff_val = int(raw_payoff)
                        except (TypeError, ValueError):
                            payoff_val = 0
            rounds_data.append({
                "round": r - (current_part - 1) * Constants.rounds_per_part,
                "my_choice": my_choice,
                "other_choice": other_choice,
                "payoff": payoff_val,
                "is_payoff_round": True,
            })

        return dict(
            current_part=current_part,
            display_part=current_part,
            rounds_data=rounds_data,
        )

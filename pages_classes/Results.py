from otree.api import *

from shared.tg_payoffs import tg_results_row
from shared.tg_results_debug import build_tg_results_debug, is_otree_debug_mode
from shared.tg_results_diagrams import (
    annotate_diagrams_with_debug,
    build_all_rounds_tree,
    build_tg_round_diagrams,
)

from .model_bridge import app_models, is_tg_app
from .page_helpers import is_excluded_from_study


class Results(Page):
    """Shown at end of each part (rounds 10, 20, 30) only after participant is in a formed results group (can_proceed_to_results_part_X)."""

    @property
    def template_name(self):
        if is_tg_app(self.player):
            return "global/ResultsTG.html"
        return "global/Results.html"

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        am = app_models(self.player)
        Constants = am.Constants
        r = self.round_number
        current_part = Constants.get_part(r)

        if r % Constants.rounds_per_part != 0:
            return False

        can_proceed_key = f'can_proceed_to_results_part_{current_part}'
        if not self.participant.vars.get(can_proceed_key, False):
            return False

        if is_tg_app(self.player):
            if current_part == 1:
                if Constants.DELEGATION_FIRST:
                    return self.participant.vars.get("agent_programming_done_part1", False)
                return self.participant.vars.get("human_v2_done_part1", False)
            if current_part == 2:
                if Constants.DELEGATION_FIRST:
                    return self.participant.vars.get("human_v2_done_part2", False)
                return self.participant.vars.get("agent_programming_done_part2", False)
            if current_part == 3:
                if self.player.field_maybe_none("delegate_decision_optional") is True:
                    return self.participant.vars.get("agent_programming_done_part3", False)
                return self.participant.vars.get("human_v2_done_part3", False)
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
        # So that Part 2/3 lobbies form new groups: reset matching_group_id when leaving Part 1 or Part 2.
        # Persist group_part_N only when this part actually completed matching (can_proceed).
        if self.round_number in (10, 20):
            Constants = app_models(self.player).Constants
            part = Constants.get_part(self.round_number)
            can_proceed = bool(
                self.participant.vars.get(f"can_proceed_to_results_part_{part}", False)
            )
            gid = self.participant.vars.get("matching_group_id", -1)
            if can_proceed and gid is not None and gid >= 0:
                self.participant.vars.setdefault(f"group_part_{part}", gid)
                pos = self.participant.vars.get("matching_group_position")
                if pos is not None:
                    self.participant.vars.setdefault(f"group_position_part_{part}", pos)
            self.participant.vars["matching_group_id"] = -1

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

        if is_tg_app(player):
            return self._vars_for_template_tg(
                Constants,
                compute_round_robin_assignments,
                current_part,
                part_start,
                part_end,
                player,
            )

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
        assignments = None
        if len(member_ids) >= 3:
            N = len(member_ids)
            assignments = compute_round_robin_assignments(N, Constants.rounds_per_part)

        def _pick_three_players(round_number):
            from shared.tg_player_lookup import players_at_round_for_member_ids

            out = {}
            if not member_ids:
                return out
            trio = players_at_round_for_member_ids(
                self.session.id, list(member_ids), round_number
            )
            if not trio:
                return out
            for p in trio:
                out[p.participant.id_in_session] = p
            return out

        my_pos = self.participant.vars.get("matching_group_position", None)
        rounds_data = []
        for r in range(part_start, part_end + 1):
            rr = player.in_round(r)
            my_choice = rr.field_maybe_none("choice")
            other_choice = None
            payoff_val = None
            if rr.payoff is not None:
                raw_payoff = getattr(rr.payoff, "amount", rr.payoff)
                try:
                    payoff_val = int(raw_payoff)
                except (TypeError, ValueError):
                    payoff_val = None
            raw_payoff = payoff_val if payoff_val is not None else 0
            if assignments and my_pos and 1 <= my_pos <= len(member_ids):
                round_in_part = r - part_start
                opp_idx, _ = assignments[my_pos - 1][round_in_part]
                opp_sid = member_ids[opp_idx] if opp_idx is not None else None
                players_map = _pick_three_players(r)
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
                            payoff_val = None
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

    def _vars_for_template_tg(
        self,
        Constants,
        compute_round_robin_assignments,
        current_part,
        part_start,
        part_end,
        player,
    ):
        """
        Prefer results_display_cache written at payoff time (cheap for navigators).
        Rebuild from DB only on cache miss; heavy diagram/debug work only in debug mode
        or when the cache is missing. Payoff DB fields remain the source of truth.
        """
        from shared.tg_data_helpers import get_tg_results_display_from_cache

        am = app_models(self.player)
        get_opponent_in_round = am.get_opponent_in_round
        debug = is_otree_debug_mode()

        cache_part = get_tg_results_display_from_cache(
            self.participant, current_part, Constants.rounds_per_part
        )
        if cache_part is not None:
            rounds_data = [
                {
                    "round": entry.get("round"),
                    "my_choice": entry.get("my_choice"),
                    "other_choice": entry.get("other_choice"),
                    "payoff": entry.get("payoff"),
                    "role_assigned": entry.get("role_assigned"),
                    "is_payoff_round": True,
                }
                for entry in cache_part
            ]
            out = dict(
                current_part=current_part,
                display_part=current_part,
                rounds_data=rounds_data,
                group_overview={},
                round_diagrams=[],
                all_rounds_tree={},
                show_round_diagrams=False,
            )
            if not debug:
                return out
            # Debug: still attach diagrams/checks without blocking production users.
        else:
            rounds_data = []
            for r in range(part_start, part_end + 1):
                rr = player.in_round(r)
                opp = get_opponent_in_round(player, r)
                row = tg_results_row(rr, opp)
                row["round"] = r - (current_part - 1) * Constants.rounds_per_part
                rounds_data.append(row)
            out = dict(
                current_part=current_part,
                display_part=current_part,
                rounds_data=rounds_data,
                show_round_diagrams=debug,
            )
            if not debug:
                # Production cache-miss: show table from DB, skip diagram rebuild.
                out.update(
                    group_overview={},
                    round_diagrams=[],
                    all_rounds_tree={},
                )
                return out

        diagrams = build_tg_round_diagrams(
            player,
            part_start,
            part_end,
            current_part,
            get_opponent_in_round,
            rounds_per_part=Constants.rounds_per_part,
        )
        tg_debug = build_tg_results_debug(
            player,
            part_start,
            part_end,
            current_part,
            get_opponent_in_round,
            rounds_per_part=Constants.rounds_per_part,
        )
        debug_rounds = tg_debug["rounds"] if tg_debug else None
        annotate_diagrams_with_debug(diagrams["rounds"], debug_rounds)
        all_rounds_tree = build_all_rounds_tree(diagrams["overview"], diagrams["rounds"])
        out.update(
            group_overview=diagrams["overview"],
            round_diagrams=diagrams["rounds"],
            all_rounds_tree=all_rounds_tree,
            show_round_diagrams=True,
        )
        if tg_debug is not None:
            out["tg_results_debug"] = {
                "part": tg_debug["part"],
                "rounds": tg_debug["rounds"],
            }
            out.update(tg_debug["summary_vars"])
        return out

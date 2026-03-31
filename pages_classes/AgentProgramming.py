import json

from otree.api import *

from .model_bridge import get_constants
from .page_helpers import _has_left_lobby_for_part, part_vars


class AgentProgramming(Page):
    """
    Page where participants set agent decisions (A or B) for each round of the delegation block.
    live_method receives JSON from the front end and stores in participant.vars; before_next_page
    copies those (or form fields for mandatory blocks) into player.in_round(r).choice.

    Intentionally **no** ``template_name`` here: each app supplies its own HTML (e.g.
    ``AgentProgramming.html`` or ``MistralPage.html``) under ``<app>/templates/<AppName>/``.
    """

    form_model = 'player'

    @staticmethod
    def live_method(player, data):
        """Receive allocations from liveSend (table A/B choices) and store in participant.vars (agent_programming_part1/2/3)."""
        if not data or 'allocations' not in data:
            return
        raw = json.loads(data['allocations'])
        # raw keys may be "agent_decision_mandatory_delegation_round_1" or "1"
        decisions = {}
        for k, v in raw.items():
            if v not in ('A', 'B'):
                continue
            if isinstance(k, int):
                decisions[k] = v
            elif isinstance(k, str) and k.isdigit():
                decisions[int(k)] = v
            elif '_round_' in str(k):
                try:
                    rn = int(str(k).split('_')[-1])
                    if 1 <= rn <= 10:
                        decisions[rn] = v
                except (ValueError, IndexError):
                    pass
        if not decisions:
            return
        r = player.round_number
        if r == 1:
            player.participant.vars['agent_programming_part1'] = decisions
        elif r == 11:
            player.participant.vars['agent_programming_part2'] = decisions
        elif r == 21:
            player.participant.vars['agent_programming_part3'] = decisions

    def is_displayed(self):
        Constants = get_constants(self.player)
        r = self.round_number
        current_part = Constants.get_part(r)
        if r in (1, 11, 21) and not _has_left_lobby_for_part(self.participant, current_part):
            return False

        # Mandatory delegation: Part 1 (round 1) or Part 2 (round 11) depending on DELEGATION_FIRST
        if r == 1 and Constants.DELEGATION_FIRST:
            return not self.participant.vars.get("agent_programming_done_part1", False)
        if r == 11 and not Constants.DELEGATION_FIRST:
            return not self.participant.vars.get("agent_programming_done_part2", False)

        if current_part == 3:
            return (
                self.player.field_maybe_none("delegate_decision_optional") is True
                and not self.participant.vars.get("agent_programming_done_part3", False)
            )

        return False

    def get_form_fields(self):
        Constants = get_constants(self.player)
        r = self.round_number
        current_part = Constants.get_part(r)
        # Mandatory delegation block (round 1 or 11): form saves to player
        if r in (1, 11):
            return [
                f"agent_decision_mandatory_delegation_round_{i}"
                for i in range(1, 11)
            ]
        # Part 3 uses participant.vars from live
        if current_part == 3:
            return []
        return []

    def vars_for_template(self):
        Constants = get_constants(self.player)
        current_part = Constants.get_part(self.round_number)
        return {
            "current_part": current_part,
            "delegate_decision": self.player.field_maybe_none(
                "delegate_decision_optional"
            ),
            "countdown_seconds": 90,
            **part_vars(self.player),
        }

    def before_next_page(self):
        Constants = get_constants(self.player)
        r = self.round_number
        current_part = Constants.get_part(r)

        # ==========================================
        # Mandatory delegation Part 1 (rounds 1–10) — when DELEGATION_FIRST
        # ==========================================
        if r == 1 and Constants.DELEGATION_FIRST:
            decisions = self.participant.vars.get('agent_programming_part1', {})
            if not decisions:
                for i in range(1, 11):
                    decision = self.player.field_maybe_none(
                        f"agent_decision_mandatory_delegation_round_{i}"
                    )
                    if decision:
                        decisions[i] = decision
            for i in range(1, 11):
                decision = decisions.get(i) or decisions.get(str(i))
                if decision in ('A', 'B'):
                    self.player.in_round(i).choice = decision
            self.participant.vars["agent_programming_done_part1"] = True

        # ==========================================
        # Mandatory delegation Part 2 (rounds 11–20) — when not DELEGATION_FIRST
        # ==========================================
        elif r == 11 and not Constants.DELEGATION_FIRST:
            decisions = self.participant.vars.get('agent_programming_part2', {})
            if not decisions:
                for i in range(1, 11):
                    decision = self.player.field_maybe_none(
                        f"agent_decision_mandatory_delegation_round_{i}"
                    )
                    if decision:
                        decisions[i] = decision
            for i in range(1, 11):
                decision = decisions.get(i) or decisions.get(str(i))
                if decision in ('A', 'B'):
                    self.player.in_round(10 + i).choice = decision
            self.participant.vars["agent_programming_done_part2"] = True

        # ==========================================
        # PART 3 — Optional delegation (rounds 21–30)
        # ==========================================
        elif current_part == 3:
            decisions = self.participant.vars.get(
                'agent_programming_part3', {}
            )
            start_round = 2 * Constants.rounds_per_part + 1  # 21

            for i in range(1, 11):
                round_number = start_round + i - 1
                decision = decisions.get(i) or decisions.get(str(i))
                if decision in ('A', 'B'):
                    self.player.in_round(round_number).choice = decision
            self.participant.vars["agent_programming_done_part3"] = True

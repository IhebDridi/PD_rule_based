import json

from otree.api import *

from shared.export_integrity import record_data_error

from .model_bridge import get_constants, is_tg_app
from .page_helpers import _has_left_lobby_for_part, part_vars


def _tg_agent_form_fields():
    fields = []
    for i in range(1, 11):
        fields.append(f"agent_decision_mandatory_delegation_round_{i}")
        fields.append(f"agent_decision_mandatory_second_round_{i}")
    return fields


def _tg_agent_decisions_complete(values):
    for i in range(1, 11):
        if values.get(f"agent_decision_mandatory_delegation_round_{i}") not in ("A", "B"):
            return False
        if values.get(f"agent_decision_mandatory_second_round_{i}") not in ("A", "B"):
            return False
    return True


def _copy_tg_choices_to_rounds(player, start_round, first_by_round, second_by_round):
    for i in range(1, 11):
        rn = start_round + i - 1
        pr = player.in_round(rn)
        first = first_by_round.get(i) or first_by_round.get(str(i))
        second = second_by_round.get(i) or second_by_round.get(str(i))
        if first in ("A", "B"):
            pr.choice_first_mover = first
        if second in ("A", "B"):
            pr.choice_second_mover = second


class AgentProgramming(Page):
    """
    Page where participants set agent decisions (A or B) for each round of the delegation block.
    live_method receives JSON from the front end and stores in participant.vars; before_next_page
    copies those (or form fields for mandatory blocks) into player.in_round(r).choice.

    Confirm button uses oTree live pattern (see templates/global/AgentProgrammingContent.html):
    type=button → liveSend → liveRecv → form.submit(). Form fields are the primary DB save path.
    """

    form_model = 'player'
    preserve_unsubmitted_inputs = True

    @property
    def template_name(self):
        if is_tg_app(self.player):
            return "global/AgentProgrammingTG.html"
        return "global/AgentProgramming.html"

    @staticmethod
    def live_method(player, data):
        """Receive allocations from liveSend; ack so the client can submit the form safely."""
        pid = player.id_in_group

        def respond(payload):
            return {pid: payload}

        if not data or 'allocations' not in data:
            return respond(
                dict(type='allocations_error', message='No data received. Please try again.')
            )
        try:
            raw = json.loads(data['allocations'])
        except (TypeError, json.JSONDecodeError):
            return respond(
                dict(type='allocations_error', message='Invalid data. Please try again.')
            )
        if is_tg_app(player):
            if not _tg_agent_decisions_complete(raw):
                return respond(
                    dict(
                        type='allocations_error',
                        message='Please choose A or B for every 1st-mover and 2nd-mover cell.',
                    )
                )
            decisions_first = {
                i: raw.get(f"agent_decision_mandatory_delegation_round_{i}")
                for i in range(1, 11)
            }
            decisions_second = {
                i: raw.get(f"agent_decision_mandatory_second_round_{i}")
                for i in range(1, 11)
            }
            payload = {"first": decisions_first, "second": decisions_second}
            r = player.round_number
            if r == 1:
                player.participant.vars['agent_programming_part1'] = payload
            elif r == 11:
                player.participant.vars['agent_programming_part2'] = payload
            elif r == 21:
                player.participant.vars['agent_programming_part3'] = payload
            return respond(dict(type='allocations_saved'))
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
        if len(decisions) < 10:
            return respond(
                dict(
                    type='allocations_error',
                    message='Please choose A or B for every round before continuing.',
                )
            )
        r = player.round_number
        if r == 1:
            player.participant.vars['agent_programming_part1'] = decisions
        elif r == 11:
            player.participant.vars['agent_programming_part2'] = decisions
        elif r == 21:
            player.participant.vars['agent_programming_part3'] = decisions
        return respond(dict(type='allocations_saved'))

    def is_displayed(self):
        if is_tg_app(self.player):
            return False
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
        if is_tg_app(self.player) and (r in (1, 11) or (current_part == 3 and r == 21)):
            return _tg_agent_form_fields()
        # Mandatory delegation block (round 1 or 11): form saves to player
        if r in (1, 11):
            return [
                f"agent_decision_mandatory_delegation_round_{i}"
                for i in range(1, 11)
            ]
        # Part 3 (round 21): persist via form_fields so oTree writes to DB on submit
        # (live_method vars are a backup only; see oTree live pages docs on liveSend + next).
        if current_part == 3 and r == 21:
            return [
                f"agent_decision_mandatory_delegation_round_{i}"
                for i in range(1, 11)
            ]
        return []

    def error_message(self, values):
        Constants = get_constants(self.player)
        r = self.round_number
        if r in (1, 11) or (Constants.get_part(r) == 3 and r == 21):
            if is_tg_app(self.player):
                if not _tg_agent_decisions_complete(values):
                    return "Please choose A or B for every 1st-mover and 2nd-mover cell."
                return None
            for i in range(1, 11):
                key = f"agent_decision_mandatory_delegation_round_{i}"
                if values.get(key) not in ("A", "B"):
                    return "Please choose A or B for every round before continuing."
        return None

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
            if is_tg_app(self.player):
                payload = self.participant.vars.get('agent_programming_part1', {})
                first = payload.get('first', {}) if isinstance(payload, dict) else {}
                second = payload.get('second', {}) if isinstance(payload, dict) else {}
                if not first:
                    first = {
                        i: self.player.field_maybe_none(f"agent_decision_mandatory_delegation_round_{i}")
                        for i in range(1, 11)
                    }
                if not second:
                    second = {
                        i: self.player.field_maybe_none(f"agent_decision_mandatory_second_round_{i}")
                        for i in range(1, 11)
                    }
                _copy_tg_choices_to_rounds(self.player, 1, first, second)
            else:
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
            if is_tg_app(self.player):
                payload = self.participant.vars.get('agent_programming_part2', {})
                first = payload.get('first', {}) if isinstance(payload, dict) else {}
                second = payload.get('second', {}) if isinstance(payload, dict) else {}
                if not first:
                    first = {
                        i: self.player.field_maybe_none(f"agent_decision_mandatory_delegation_round_{i}")
                        for i in range(1, 11)
                    }
                if not second:
                    second = {
                        i: self.player.field_maybe_none(f"agent_decision_mandatory_second_round_{i}")
                        for i in range(1, 11)
                    }
                _copy_tg_choices_to_rounds(self.player, 11, first, second)
            else:
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
            start_round = 2 * Constants.rounds_per_part + 1  # 21
            missing_rounds = []
            if is_tg_app(self.player):
                payload = dict(self.participant.vars.get("agent_programming_part3", {}))
                first = payload.get('first', {}) if isinstance(payload, dict) else {}
                second = payload.get('second', {}) if isinstance(payload, dict) else {}
                if not first:
                    first = {
                        i: self.player.field_maybe_none(f"agent_decision_mandatory_delegation_round_{i}")
                        for i in range(1, 11)
                    }
                if not second:
                    second = {
                        i: self.player.field_maybe_none(f"agent_decision_mandatory_second_round_{i}")
                        for i in range(1, 11)
                    }
                for i in range(1, 11):
                    rn = start_round + i - 1
                    f = first.get(i) or first.get(str(i))
                    s = second.get(i) or second.get(str(i))
                    if f in ("A", "B") and s in ("A", "B"):
                        pr = self.player.in_round(rn)
                        pr.choice_first_mover = f
                        pr.choice_second_mover = s
                    else:
                        missing_rounds.append(str(rn))
            else:
                decisions = dict(self.participant.vars.get("agent_programming_part3", {}))
                if not decisions:
                    for i in range(1, 11):
                        decision = self.player.field_maybe_none(
                            f"agent_decision_mandatory_delegation_round_{i}"
                        )
                        if decision in ("A", "B"):
                            decisions[i] = decision

                for i in range(1, 11):
                    round_number = start_round + i - 1
                    decision = decisions.get(i) or decisions.get(str(i))
                    if decision in ("A", "B"):
                        self.player.in_round(round_number).choice = decision
                    else:
                        missing_rounds.append(str(round_number))

            if missing_rounds:
                record_data_error(
                    self.participant,
                    "PART3_AGENT_CHOICES_INCOMPLETE",
                    ",".join(missing_rounds),
                )
            else:
                self.participant.vars["agent_programming_done_part3"] = True

from otree.api import *
from .models import (
    Constants,
    get_payoff_round,
    apply_wait_timeout_after_part,
    mark_dropped_per_participant_timeout,
    repurpose_dropouts_as_simulated,
    release_batch_from_lobby,
    run_payoffs_for_matching_group,
    run_payoffs_for_matching_group_with_dropouts,
    ensure_round_groups_initialized,
)
import json
import time
import pandas as pd
import settings

# Minimum seconds before the group can proceed from BatchWaitForGroup (gives everyone time to load).
BATCH_WAIT_MIN_SECONDS = 2


def part_vars():
    """Part numbers for templates: Part X (no delegation) and Part Y (delegation). Change order via Constants.DELEGATION_FIRST."""
    return {
        "part_no_delegation": Constants.part_no_delegation(),
        "part_delegation": Constants.part_delegation(),
    }


# -----------------------------
#  General Introduction & Setup
# -----------------------------

class InformedConsent(Page):
    form_model = 'player'
    form_fields = ['prolific_id']
    def is_displayed(self):
        return self.round_number == 1  # Show only once at the beginning
    def error_message_prolific_id(self, value):
        print('error check informed consesnte')
        pid = value.get('prolific_id', '')
        if len(value.strip()) != 24:
            return "Please make sure that your Prolific ID is correct. You will not be able to proceed in the experiment without providing your Prolific ID."


""" class Introduction(Page):
    def is_displayed(self):
        return self.round_number == 1  # Show only once at the beginning """


class ComprehensionTest(Page):
    form_model = 'player'
    form_fields = ['q1', 'q2', 'q3', 'q4', 'q5',
                   'q6', 'q7', 'q8', 'q9', 'q10']

    def is_displayed(self):
        return self.round_number == 1 and not self.player.is_excluded

    def vars_for_template(self):
        return {
            "comp_error_message": self.participant.vars.get(
                "comp_error_message"
            ),
            **part_vars(),
        }

    def error_message(self, values):
        correct_answers = {
            'q1': 'c',
            'q2': 'b',
            'q3': 'c',
            'q4': 'c',
            'q5': 'a',
            'q6': 'c',
            'q7': 'a',
            'q8': 'b',
            'q9': 'b',
            'q10': 'b',
        }

        incorrect = [
            q for q, correct in correct_answers.items()
            if values.get(q) != correct
        ]

        if not incorrect:
            #  all correct → proceed
            self.participant.vars.pop("comp_error_message", None)
            return

        #  incorrect answers
        self.player.comprehension_attempts += 1
        attempts_left = 3 - self.player.comprehension_attempts

        if attempts_left > 0:
            msg = (
                f"You have failed questions: {', '.join(incorrect)}. "
                f"You have {attempts_left} attempt(s) remaining."
            )
            self.participant.vars["comp_error_message"] = msg
            return msg

        #  no attempts left → exclude
        self.player.is_excluded = True
        return (
            "You have failed the comprehension test too many times "
            "and cannot continue with the experiment."
        )


class FailedTest(Page):
    def is_displayed(self):
        return self.player.is_excluded

# -------------------------
#  Per-Part Instructions
# -------------------------

""" class Instructions(Page):
    def is_displayed(self):
        current_part = Constants.get_part(self.round_number)
        return not self.player.is_excluded and (self.round_number - 1) % Constants.rounds_per_part == 0

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        return {
            'current_part': current_part,
            'incorrect_answers': self.player.incorrect_answers,

        } """


# -------------------------
#  Agent Programming
# -------------------------
#from here

class AgentProgramming(Page):
    form_model = 'player'

    @staticmethod
    def live_method(player, data):
        """Receive allocations from liveSend (table A/B choices) and store in participant.vars."""
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

    def is_displayed(self):
        r = self.round_number
        # Batch start: only show after release from lobby for this part
        if Constants.USE_BATCH_START and r in (1, 11, 21):
            if self.participant.vars.get('matching_group_id', -1) < 0:
                return False
        current_part = Constants.get_part(r)

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
        # Cosmetic 90s countdown shared within a part: reuse per-part start time.
        current_part = Constants.get_part(self.round_number)
        start_key = f'part_{current_part}_start_time'
        if start_key not in self.participant.vars:
            self.participant.vars[start_key] = time.time()
        start_time = self.participant.vars.get(start_key, time.time())
        elapsed = time.time() - start_time
        countdown_seconds = max(0, 90 - int(elapsed))
        return {
            "current_part": current_part,
            "delegate_decision": self.player.field_maybe_none(
                "delegate_decision_optional"
            ),
            "countdown_seconds": countdown_seconds,
            **part_vars(),
        }
    def before_next_page(self):
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
                decision = decisions.get(i)
                if decision:
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
                decision = decisions.get(i)
                if decision:
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
                decision = decisions.get(i)

                print(f"Saving decision for round {round_number}: {decision}")

                self.player.in_round(round_number).choice = decision

            self.participant.vars["agent_programming_done_part3"] = True

        # ==========================================
        # Other parts: do nothing
        # ==========================================
        else:
            return 
# -------------------------
#  waiting page: no one proceeds until ALL participants have finished
#  their 10 rounds for this part; then comparison/payoffs run (no None values).
# -------------------------
class WaitForGroup(WaitPage):
    wait_for_all_groups = True  # wait until everyone in session has finished the part

    def is_displayed(self):
        return self.round_number % Constants.rounds_per_part == 0

    @staticmethod
    def after_all_players_arrive(subsession):
        rnd = subsession.round_number
        if rnd % Constants.rounds_per_part != 0:
            return
        current_part = Constants.get_part(rnd)
        if current_part == 1:
            start, end = 1, 10
        elif current_part == 2:
            start, end = 11, 20
        elif current_part == 3:
            start, end = 21, 30
        else:
            return

        # All participants have arrived at this wait page → all have submitted their 10 rounds.
        # Use round-specific groups so Part 3 (and any part with reshuffled pairs per round) uses the correct pairing for each round.
        for r in range(start, end + 1):
            round_subsession = subsession.in_round(r)
            for group in round_subsession.get_groups():
                for p in group.get_players():
                    if p.in_round(r).field_maybe_none("choice") is None:
                        return  # should not happen if everyone arrived
                group.set_payoffs()


class BatchWaitForGroup(WaitPage):
    """
    Wait page at end of each part when USE_BATCH_START is True.
    Waits only for the 10 participants in your matching group (matching_group_id >= 0).
    No form; advance is automatic when all have arrived and BATCH_WAIT_MIN_SECONDS have passed.
    When USE_WAIT_TIMEOUT is True: per-participant 90s timer; non-arrivers can be marked dropped.
    """
    template_name = 'prisoners_dilemma/BatchWaitForGroup.html'

    def is_displayed(self):
        return (
            Constants.USE_BATCH_START
            and self.round_number % Constants.rounds_per_part == 0
            # Only participants who have been released from a lobby batch (matching_group_id >= 0)
            # should ever see this wait page. Leftover/inactive participants (gid == -1) skip it.
            and self.participant.vars.get('matching_group_id', -1) >= 0
        )

    def get(self):
        context = self.get_context_data()
        current_part = Constants.get_part(self.round_number)
        arrived_key = f'wait_arrived_part_{current_part}'
        arrived_at_key = f'wait_arrived_part_{current_part}_at'
        gid = self.participant.vars.get('matching_group_id', -1)
        participants = self.session.get_participants()
        in_my_group = [p for p in participants if p.vars.get('matching_group_id') == gid]
        arrived_in_group = [p for p in in_my_group if p.vars.get(arrived_key)]
        dropped_in_group = [p for p in in_my_group if p.vars.get('dropped_out')]
        n_arrived = len(arrived_in_group)
        n_dropped = len(dropped_in_group)
        matching_group_size_actual = len(in_my_group)
        applied_key = f'payoffs_run_matching_group_{gid}_part_{current_part}'
        print(
            f"[BATCH WAIT] part={current_part}, gid={gid}, "
            f"n_arrived={n_arrived}, n_dropped={n_dropped}, "
            f"group_size={matching_group_size_actual}"
        )
        can_proceed = (n_arrived + n_dropped) >= matching_group_size_actual
        if can_proceed and BATCH_WAIT_MIN_SECONDS > 0:
            first_arrived_at = self.participant.vars.get(arrived_at_key) or time.time()
            if (time.time() - first_arrived_at) < BATCH_WAIT_MIN_SECONDS:
                can_proceed = False
        if can_proceed:
            if not self.session.vars.get(applied_key):
                if n_dropped > 0:
                    repurpose_dropouts_as_simulated(self.session)
                    if n_arrived > 0:
                        arrived_ids = [p.id_in_session for p in arrived_in_group]
                        run_payoffs_for_matching_group_with_dropouts(
                            self.subsession, gid, arrived_ids
                        )
                    else:
                        run_payoffs_for_matching_group(self.subsession, gid)
                else:
                    run_payoffs_for_matching_group(self.subsession, gid)
                self.session.vars[applied_key] = True
            return self._response_when_ready()
        return self._get_wait_page()

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        arrived_key = f'wait_arrived_part_{current_part}'
        arrived_at_key = f'wait_arrived_part_{current_part}_at'
        start_key = f'part_{current_part}_start_time'
        if start_key not in self.participant.vars:
            self.participant.vars[start_key] = time.time()
        self.participant.vars[arrived_key] = True
        if arrived_at_key not in self.participant.vars:
            self.participant.vars[arrived_at_key] = time.time()
        gid = self.participant.vars.get('matching_group_id', -1)
        if Constants.USE_WAIT_TIMEOUT:
            mark_dropped_per_participant_timeout(self.session, current_part)
        participants = self.session.get_participants()
        in_my_group = [p for p in participants if p.vars.get('matching_group_id') == gid]
        matching_group_size_actual = len(in_my_group)
        n_arrived = sum(1 for p in in_my_group if p.vars.get(arrived_key))
        n_dropped = sum(1 for p in in_my_group if p.vars.get('dropped_out'))
        my_start = self.participant.vars.get(start_key) or time.time()
        return {
            'n_arrived': n_arrived,
            'batch_size': matching_group_size_actual,
            'use_timeout': Constants.USE_WAIT_TIMEOUT,
            'timeout_seconds': Constants.WAIT_PAGE_TIMEOUT_SECONDS,
            'first_arrival_timestamp': my_start,
        }


class WaitForGroupWithTimeout(Page):
    """
    Shown when USE_WAIT_TIMEOUT is True instead of WaitForGroup.
    Records first arrival when the first participant loads the page (gradual entry).
    Auto-submits after 90s, then runs timeout payoff logic (or normal payoff if all arrived).
    Works for any session size (50, 76, 100, etc.).
    """
    def is_displayed(self):
        return self.round_number % Constants.rounds_per_part == 0

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        key_first = f'wait_part_{current_part}_first_arrival'
        arrived_key = f'wait_arrived_part_{current_part}'
        # First player to load this wait page sets the timer (gradual entry supported)
        self.session.vars.setdefault(key_first, time.time())
        # Count as "arrived" when they load the page (so x/N finished updates as people enter)
        self.participant.vars[arrived_key] = True
        first_arrival = self.session.vars[key_first]
        participants = self.session.get_participants()
        n_arrived = sum(1 for p in participants if p.vars.get(arrived_key))
        return {
            'timeout_seconds': Constants.WAIT_PAGE_TIMEOUT_SECONDS,
            'first_arrival_timestamp': first_arrival,
            'n_arrived': n_arrived,
            'n_total': len(participants),
        }

    @staticmethod
    def live_method(player, data):
        """Return current count of participants who have reached this wait page (for x/N display)."""
        if not data or data.get('type') != 'get_count':
            return
        current_part = Constants.get_part(player.round_number)
        arrived_key = f'wait_arrived_part_{current_part}'
        participants = player.session.get_participants()
        n_arrived = sum(1 for p in participants if p.vars.get(arrived_key))
        payload = {'n_arrived': n_arrived, 'n_total': len(participants)}
        return {player.id_in_group: payload}

    def before_next_page(self):
        current_part = Constants.get_part(self.round_number)
        arrived_key = f'wait_arrived_part_{current_part}'
        first_key = f'wait_part_{current_part}_first_arrival'
        applied_key = f'wait_part_{current_part}_timeout_applied'

        self.participant.vars[arrived_key] = True

        first_arrival = self.session.vars.get(first_key) or time.time()
        elapsed = time.time() - first_arrival
        timeout_triggered = elapsed >= Constants.WAIT_PAGE_TIMEOUT_SECONDS

        if timeout_triggered and not self.session.vars.get(applied_key):
            apply_wait_timeout_after_part(self.subsession)
            self.session.vars[applied_key] = True
        elif not timeout_triggered:
            # Check if everyone arrived (normal path)
            participants = self.session.get_participants()
            n_arrived = sum(1 for p in participants if p.vars.get(arrived_key))
            if n_arrived < len(participants):
                raise Exception("Please wait for other participants.")
            if not self.session.vars.get(applied_key):
                # Run same payoff logic as WaitForGroup.after_all_players_arrive
                rnd = self.round_number
                if rnd == 10:
                    start, end = 1, 10
                elif rnd == 20:
                    start, end = 11, 20
                elif rnd == 30:
                    start, end = 21, 30
                else:
                    start = end = rnd
                for r in range(start, end + 1):
                    round_subsession = self.subsession.in_round(r)
                    for group in round_subsession.get_groups():
                        for p in group.get_players():
                            if p.in_round(r).field_maybe_none("choice") is None:
                                return
                        group.set_payoffs()
                self.session.vars[applied_key] = True


# -------------------------
#  Decision Making
# -------------------------

""" class Decision(Page):
    form_model = 'player'
    form_fields = ['choice']
    #timeout_seconds = 20


    def is_displayed(self):
        current_part = Constants.get_part(self.round_number)
        return current_part == 2 or (current_part == 3 and not self.player.delegate_decision_optional)

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        display_round = (self.round_number - 1) % Constants.rounds_per_part + 1
        allocation = None
        if current_part == 1:
            allocation = self.player.get_agent_decision_mandatory(display_round)
        elif current_part == 3 and self.player.delegate_decision_optional:
            allocation = self.player.get_agent_decision_optional(display_round)
        #add logic to add allocation for part 1:

        return {
            'round_number': display_round,
            'current_part': current_part,
            'decision_mode': (
                "agent" if (current_part == 1 or (current_part == 3 and self.player.delegate_decision_optional)) else "manual"
            ),
            'player_allocation': allocation,
            'alert_message': self.participant.vars.get('alert_message', ""),
        }

    def before_next_page(self):
        import json
        import random

        #decisions = json.loads(self.player.random_decisions)
        #print(f"[DEBUG] Existing random_decisions: {decisions}")

        # Get current part and display round
        current_part = Constants.get_part(self.round_number)
        display_round = (self.round_number - 1) % Constants.rounds_per_part + 1

        if current_part == 2 or (current_part == 3 and not self.player.delegate_decision_optional)  :  # Part 1 logic or Part 3 with manual with manual decisions and timer
  
                self.participant.vars['alert_message'] = None
                self.player.random_decisions = False
                

            # Update decisions for the current round



        elif current_part == 1:  # Mandatory delegation
            self.player.allocation = self.player.get_agent_decision_mandatory(display_round)
            self.participant.vars['alert_message'] = ""
            self.player.random_decisions = True
            self.player.delegate_decision_optional = False 

        elif current_part == 3 and self.player.delegate_decision_optional:  # Optional delegation
            self.player.allocation = self.player.get_agent_decision_optional(display_round)
            self.participant.vars['alert_message'] = ""
            self.player.random_decisions = False
            self.player.delegate_decision_optional = True
        




        # elif current_part == 3 and not self.player.delegate_decision_optional:  # Manual decision

        #     #self.player.allocation = self.player.get_agent_decision_optional(display_round)
        #     self.player.random_decisions = False
        #     self.player.delegate_decision_optional = False
        #     self.player.allocation = self.player.get_agent_decision_optional(display_round)



        #print(f"round:{self.round_number}  self.player.allocation: {self.player.allocation}")
 """


# -------------------------
#  Delegation Decision
# -------------------------

class DelegationDecision(Page):
    form_model = 'player'
    form_fields = ['delegate_decision_optional']

    def is_displayed(self):
        # show ONCE at start of Part 3 (round 21)
        return (
            Constants.get_part(self.round_number) == 3
            and (self.round_number - 1) % Constants.rounds_per_part == 0
        )

    def before_next_page(self):
        # copy decision into ALL Part 3 rounds (21–30)
        start_round = 2 * Constants.rounds_per_part + 1  # 21
        end_round = 3 * Constants.rounds_per_part        # 30

        for r in range(start_round, end_round + 1):
            self.player.in_round(r).delegate_decision_optional = (
                self.player.delegate_decision_optional
            )

        print(
            "DELEGATION DECISION:",
            self.player.id_in_group,
            self.player.delegate_decision_optional
        )

        # =================================================
        # ✅ DEBUG: show agent decision for round 2 (Part 3) — only when they delegated
        # =================================================
        if self.player.delegate_decision_optional:
            decisions = self.participant.vars.get('agent_programming_part3')
            if decisions is None:
                print("⚠ agent_programming_part3 is MISSING")
            else:
                print("Saving decision for round 2:", decisions.get(2))


# -------------------------
#  Results
# -------------------------

class Results(Page):
    def is_displayed(self):
        r = self.round_number
        current_part = Constants.get_part(r)

        # End of each part only (round 10, 20, 30)
        if r % Constants.rounds_per_part != 0:
            return False

        # Part 1 (rounds 1-10): delegation block when DELEGATION_FIRST else no-del block
        if current_part == 1:
            if Constants.DELEGATION_FIRST:
                return self.participant.vars.get("agent_programming_done_part1", False)
            return True  # no-del block, no agent programming

        # Part 2 (rounds 11-20): no-del block when DELEGATION_FIRST else delegation block
        if current_part == 2:
            if Constants.DELEGATION_FIRST:
                return True  # no-del block
            return self.participant.vars.get("agent_programming_done_part2", False)

        # Part 3 (round 30): show Results for everyone (delegation and no-delegation) after they finish their 10 rounds
        if current_part == 3:
            return True

        return False

    def before_next_page(self):
        # So that Part 2/3 lobbies form new groups: reset matching_group_id when leaving Part 1 or Part 2
        if Constants.USE_BATCH_START and self.round_number in (10, 20):
            self.participant.vars['matching_group_id'] = -1

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)

        payoff_round = None

        player = self.player
        rounds_data = []

        for r in range(
            (current_part - 1) * Constants.rounds_per_part + 1,
            current_part * Constants.rounds_per_part + 1
        ):
            rr = player.in_round(r)
            other = rr.get_others_in_group()[0]

            rounds_data.append({
                'round': r - (current_part - 1) * Constants.rounds_per_part,
                'my_choice': rr.field_maybe_none('choice'),
                'other_choice': other.field_maybe_none('choice'),
                'payoff': rr.payoff,
                'is_payoff_round': (r == payoff_round),
            })

        # Part 1 then Part 2 always: first block = Part 1, second = Part 2, third = Part 3
        display_part = current_part

        return dict(
            current_part=current_part,
            display_part=display_part,
            rounds_data=rounds_data,
        )

# -------------------------
#  Delegation guessing
# -------------------------

class GuessDelegation(Page):
    form_model = 'player'

    def is_displayed(self):
        #  show ONCE, at end of Part 3; simulated participants skip (guesses set in creating_session)
        if self.round_number != 3 * Constants.rounds_per_part:
            return False
        return not self.participant.vars.get('is_simulated', False)

    def get_form_fields(self):
        return [f"guess_round_{i}" for i in range(1, 11)]

    def vars_for_template(self):
        rows = []
        start = 2 * Constants.rounds_per_part + 1  # round 21

        for i in range(1, 11):
            r = start + i - 1
            me = self.player.in_round(r)
            other = me.get_others_in_group()[0]

            rows.append({
                "round": i,
                "my_choice": me.field_maybe_none("choice"),
                "other_choice": other.field_maybe_none("choice"),
                "field_name": f"guess_round_{i}",
            })

        # Cosmetic 90s countdown for guessing page; reuse Part 3 start time.
        current_part = Constants.get_part(self.round_number)
        start_key = f'part_{current_part}_start_time'
        if start_key not in self.participant.vars:
            self.participant.vars[start_key] = time.time()
        start_time = self.participant.vars.get(start_key, time.time())
        elapsed = time.time() - start_time
        countdown_seconds = max(0, 90 - int(elapsed))

        return {
            "rows": rows,
            "countdown_seconds": countdown_seconds,
        }

    def before_next_page(self):
        start = 2 * Constants.rounds_per_part + 1  # round 21

        for i in range(1, 11):
            r = start + i - 1
            future_player = self.player.in_round(r)

            guess_field = f"guess_round_{i}"
            guess = getattr(self.player, guess_field)

            #  1. store the per‑round guess explicitly
            setattr(future_player, guess_field, guess)

            #  2. store unified guess field (used elsewhere)
            future_player.guess_opponent_delegated = guess

            #  3. compute and ALWAYS store payoff
            other = future_player.get_others_in_group()[0]
            actual = bool(other.field_maybe_none("delegate_decision_optional"))

            # 10 cents per correct answer (1 point = 1 cent)
            future_player.guess_payoff = (
                cu(10) if (guess == 'yes') == actual else cu(0)
            )

        self.participant.vars['guess_submitted'] = True


# -------------------------
#  Debriefing
# -------------------------

class Debriefing(Page):
    def is_displayed(self):
        return  self.round_number == Constants.num_rounds


    def vars_for_template(self):
        import random

        results_by_part = {}

        existing = self.player.field_maybe_none("random_payoff_part")
        if existing is None:
            payoff_part = random.randint(1, 3)
            self.player.random_payoff_part = payoff_part
        else:
            payoff_part = existing

        for part in range(1, 4):
            part_data = []
            total = 0

            for r in range(
                (part - 1) * Constants.rounds_per_part + 1,
                part * Constants.rounds_per_part + 1
            ):
                me = self.player.in_round(r)
                other = me.get_others_in_group()[0]

                part_data.append({
                    "round": r - (part - 1) * Constants.rounds_per_part,
                    "my_choice": me.field_maybe_none("choice"),
                    "other_choice": other.field_maybe_none("choice"),
                    "other_delegated": bool(other.field_maybe_none("delegate_decision_optional")),
                    "payoff": me.payoff,
                })

                total += me.payoff or 0



            results_by_part[part] = {
                "rounds": part_data,
                "total_payoff": total,
            }
        # ==============================
        # ADDITION: Part 4 results table
        # ==============================
        guess_rounds_data = []

        for r in range(
            2 * Constants.rounds_per_part + 1,
            3 * Constants.rounds_per_part + 1
        ):
            me = self.player.in_round(r)
            other = me.get_others_in_group()[0]

            guess_rounds_data.append({
                "round": r - 2 * Constants.rounds_per_part,
                "my_choice": me.field_maybe_none("choice"),
                "other_choice": other.field_maybe_none("choice"),
                "other_delegated": bool(other.field_maybe_none("delegate_decision_optional")),
                "payoff": me.field_maybe_none("payoff"),
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
        # Part 4 guess payoffs in cents -> display strings: \"0.1\" or \"0\"
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
            "total_bonus": total_bonus,
        }



class ExitQuestionnaire(Page):
    def error_message(self, values):
        if values.get('part_3_feedback') == 'part_3_other':
            if not values.get('part_3_feedback_other'):
                return "Please specify your reason if you selected 'Other'."
    form_model = 'player'
    form_fields = [
        'gender',           # Male / Female / Non-binary / Prefer not to say
        'age',              # 18 – 100
        'occupation',       # free text ≤ 100 chars
        'ai_use',           # frequency scale
        'task_difficulty',  # difficulty scale
        'part_3_feedback',
        'part_3_feedback_other',
        'part_4_feedback',
        'part_4_feedback_other',
        'feedback',         # optional free text ≤ 1000 chars

    ]

    def is_displayed(self):
        return  self.round_number == Constants.num_rounds


class Thankyou(Page):

    # the Prolific completion link

    def vars_for_template(self):
        prolific_url = 'https://bsky.app/profile/iterrucha.bsky.social'

        return dict(url=prolific_url)
    
    def is_displayed(self): 
        return self.round_number == Constants.num_rounds

""" class SaveData(Page):
    def is_displayed(self):
        return self.round_number == Constants.num_rounds or self.player.is_excluded

    def save_player_data(self):
        import pandas as pd

        rows = []

        for pl in self.player.in_all_rounds():
            other = pl.get_others_in_group()[0]

            part = Constants.get_part(pl.round_number)
            round_in_part = (pl.round_number - 1) % Constants.rounds_per_part + 1

            rows.append({
                # --- Identifiers ---
                "participant_code": pl.participant.code,
                "session_code": pl.session.code,
                "experiment": pl.session.config.get("display_name", ""),
                "prolific_id": pl.field_maybe_none("prolific_id"),

                # --- Structure ---
                "part": part,
                "round_in_part": round_in_part,
                "absolute_round": pl.round_number,

                # --- Decisions ---
                "my_choice": pl.field_maybe_none("choice"),
                "my_delegated": bool(pl.field_maybe_none("delegate_decision_optional")),
                "opponent_choice": other.field_maybe_none("choice"),
                "opponent_delegated": bool(other.field_maybe_none("delegate_decision_optional")),
                "guess_opponent_delegated": pl.field_maybe_none("guess_opponent_delegated"),
                
                # --- Outcome ---
                "payoff": pl.payoff,

                # --- Payment logic ---
                "payoff_part_selected": pl.field_maybe_none("random_payoff_part"),

                # --- Demographics ---
                "gender": pl.field_maybe_none("gender"),
                "age": pl.field_maybe_none("age"),
                "occupation": pl.field_maybe_none("occupation"),
                "ai_use": pl.field_maybe_none("ai_use"),
                "task_difficulty": pl.field_maybe_none("task_difficulty"),
                "feedback": pl.field_maybe_none("feedback"),

                # --- Quality control ---
                "comprehension_attempts": pl.field_maybe_none("comprehension_attempts"),
                "is_excluded": pl.field_maybe_none("is_excluded"),
                
            })

        df = pd.DataFrame(rows)

        #  Forward-fill demographics & static fields
        static_cols = [
            "prolific_id", "gender", "age", "occupation",
            "ai_use", "task_difficulty", "feedback",
            "payoff_part_selected", "comprehension_attempts", "is_excluded"
        ]
        df[static_cols] = df[static_cols].ffill().bfill()

        prolific_id = df["prolific_id"].iloc[0]

        path = settings.data_path
        df.to_csv(path + f"{prolific_id}.csv", index=False)


            
    def before_next_page(self):AgentProgramming
        # Save player data before moving to the next page
        print("S Round number:  ,",self.round_number)

        if self.round_number == Constants.num_rounds:
            #print("Round number: ,",self.round_number)
            self.save_player_data()

 """
#new pages
class BotDetection(Page):
    template_name = "prisoners_dilemma/templates/prisoners_dilemma/BotDetection.html"

    def is_displayed(self):
        if self.round_number != 1:
            return False
        pid = self.player.field_maybe_none("prolific_id")
        return pid == "1234567890GenerativeAI4U"
    
class MainInstructions(Page):
    template_name = "prisoners_dilemma/templates/prisoners_dilemma/MainInstructions.html"

    def is_displayed(self):
        return self.round_number == 1

    def vars_for_template(self):
        return part_vars()

class InstructionsNoDelegation(Page):
    template_name = "prisoners_dilemma/templates/prisoners_dilemma/InstructionsNoDelegation.html"

    def is_displayed(self):
        # Part 1 first: show at round 1 when Part 1 = No delegation (not DELEGATION_FIRST)
        # Part 2 second: show at round 11 when Part 2 = No delegation (DELEGATION_FIRST)
        r = self.round_number
        return (r == 1 and not Constants.DELEGATION_FIRST) or (r == 11 and Constants.DELEGATION_FIRST)

    def vars_for_template(self):
        if Constants.USE_BATCH_START and self.round_number in (11, 21):
            ensure_round_groups_initialized(self.subsession, self.participant)
        return part_vars()

class InstructionsDelegation(Page):
    def is_displayed(self):
        # Part 1 first: show at round 1 when Part 1 = Delegation (DELEGATION_FIRST)
        # Part 2 second: show at round 11 when Part 2 = Delegation (not DELEGATION_FIRST)
        r = self.round_number
        return (r == 1 and Constants.DELEGATION_FIRST) or (r == 11 and not Constants.DELEGATION_FIRST)

    def vars_for_template(self):
        if Constants.USE_BATCH_START and self.round_number in (11, 21):
            ensure_round_groups_initialized(self.subsession, self.participant)
        return part_vars()


class Lobby(WaitPage):
    """
    Wait-page style lobby when USE_BATCH_START: participants wait until 10 are ready (or stale timeout).
    No form, no Next button; advance happens automatically when the batch is released (same as default oTree wait page).
    Bots do not submit this page; they are advanced when the batch is formed.
    """
    template_name = 'prisoners_dilemma/Lobby.html'

    def is_displayed(self):
        if not Constants.USE_BATCH_START:
            return False
        rnd = self.round_number
        if rnd == 1:
            return not self.participant.vars.get('has_left_lobby', False)
        if rnd == 11:
            return not self.participant.vars.get('has_left_lobby_part_2', False)
        if rnd == 21:
            return not self.participant.vars.get('has_left_lobby_part_3', False)
        return False

    def _lobby_part(self):
        """Return 1, 2, or 3 for current lobby part."""
        if self.round_number == 1:
            return 1
        if self.round_number == 11:
            return 2
        if self.round_number == 21:
            return 3
        return 1

    def get(self):
        # Run lobby logic (add self to lobby, maybe release batch); then redirect if released or show wait page.
        context = self.get_context_data()
        if context.get('can_leave_lobby'):
            part = self._lobby_part()
            if part == 1:
                self.participant.vars['has_left_lobby'] = True
            elif part == 2:
                self.participant.vars['has_left_lobby_part_2'] = True
            else:
                self.participant.vars['has_left_lobby_part_3'] = True
            return self._response_when_ready()
        return self._get_wait_page()

    def vars_for_template(self):
        part = self._lobby_part()
        if part == 1:
            lobby_key = 'lobby_ids'
            next_batch_key = 'next_batch_id'
            can_leave_key = 'can_leave_lobby'
        else:
            lobby_key = f'lobby_ids_part_{part}'
            next_batch_key = f'next_batch_id_part_{part}'
            can_leave_key = f'can_leave_lobby_part_{part}'

        lobby = list(self.session.vars.get(lobby_key, []))
        last_join_key = 'lobby_last_join_time' if part == 1 else f'lobby_last_join_time_part_{part}'
        start_key = f'part_{part}_start_time'
        if start_key not in self.participant.vars:
            self.participant.vars[start_key] = time.time()
        # Only clear matching_group_id when first entering this part's lobby (not yet released).
        # Otherwise a refresh after release would wipe gid and split the batch (9 with gid=-1, 1 with gid=0).
        if (
            part >= 2
            and self.participant.vars.get('matching_group_id', -1) >= 0
            and not self.participant.vars.get(can_leave_key, False)
        ):
            self.participant.vars['matching_group_id'] = -1
        if (
            self.participant.id_in_session not in lobby
            and self.participant.vars.get('matching_group_id', -1) < 0
            and not self.participant.vars.get(can_leave_key, False)
        ):
            lobby.append(self.participant.id_in_session)
            self.session.vars[lobby_key] = lobby
            self.session.vars[last_join_key] = time.time()
        n_waiting = len(lobby)
        batch_size = Constants.matching_group_size
        next_batch_id = self.session.vars.get(next_batch_key, 0)
        now = time.time()
        last_join = self.session.vars.get(last_join_key)
        stale_timeout = getattr(Constants, 'STALE_LOBBY_TIMEOUT_SECONDS', 300)
        release_stale = (
            n_waiting >= 2
            and n_waiting % 2 == 0
            and n_waiting < batch_size
            and last_join is not None
            and (now - last_join) >= stale_timeout
        )
        if n_waiting >= batch_size:
            batch_ids = sorted(lobby)[:batch_size]
            self.session.vars[lobby_key] = [x for x in lobby if x not in batch_ids]
            self.session.vars[next_batch_key] = next_batch_id + 1
            subsession = self.subsession
            batch_players = [p for p in subsession.get_players() if p.participant.id_in_session in batch_ids]
            print(
                f"[LOBBY] Releasing full batch from part={part} with "
                f"{len(batch_players)} participants (expected {batch_size}); "
                f"batch_id={next_batch_id}, lobby_key={lobby_key}"
            )
            release_batch_from_lobby(subsession, batch_players, batch_id=next_batch_id, part=part)
        elif release_stale:
            batch_ids = list(lobby)
            self.session.vars[lobby_key] = []
            self.session.vars[next_batch_key] = next_batch_id + 1
            subsession = self.subsession
            batch_players = [p for p in subsession.get_players() if p.participant.id_in_session in batch_ids]
            print(
                f"[LOBBY] Stale release from part={part}: {len(batch_players)} participants after "
                f"{stale_timeout}s with no new joins; batch_id={next_batch_id}"
            )
            release_batch_from_lobby(subsession, batch_players, batch_id=next_batch_id, part=part)
        can_leave = self.participant.vars.get(can_leave_key, False)
        stale_release_available = (
            n_waiting >= 2 and n_waiting % 2 == 0 and n_waiting < batch_size
            and getattr(Constants, 'STALE_LOBBY_TIMEOUT_SECONDS', 300) > 0
        )
        stale_timeout_seconds = getattr(Constants, 'STALE_LOBBY_TIMEOUT_SECONDS', 300)
        refresh_seconds = 1 if n_waiting >= 9 else 2
        return {
            'n_waiting': n_waiting,
            'batch_size': batch_size,
            'can_leave_lobby': can_leave,
            'lobby_part': part,
            'stale_release_available': stale_release_available,
            'stale_timeout_minutes': stale_timeout_seconds // 60,
            'stale_timeout_seconds': stale_timeout_seconds,
            'refresh_seconds': refresh_seconds,
        }

    @staticmethod
    def live_method(player, data):
        if not data or data.get('type') != 'get_lobby_count':
            return
        rnd = player.round_number
        if rnd == 1:
            lobby_key = 'lobby_ids'
        elif rnd == 11:
            lobby_key = 'lobby_ids_part_2'
        elif rnd == 21:
            lobby_key = 'lobby_ids_part_3'
        else:
            lobby_key = 'lobby_ids'
        lobby = player.session.vars.get(lobby_key, [])
        n = len(lobby)
        return {player.id_in_group: {'n_waiting': n, 'batch_size': Constants.matching_group_size}}


#changes are made
class DecisionNoDelegation(Page):
    template_name = "prisoners_dilemma/DecisionNoDelegation.html"
    form_model = "player"
    form_fields = ["choice"]

    def is_displayed(self):
        # Batch start: only show after release from lobby for this part (matching_group_id >= 0)
        if Constants.USE_BATCH_START and self.round_number in (1, 11, 21):
            if self.participant.vars.get('matching_group_id', -1) < 0:
                return False
        part = Constants.get_part(self.round_number)
        # Part 3: show when they chose not to delegate, in rounds 21–30. (InstructionsOptional and DelegationDecision come before this in page_sequence, so round 21 shows instructions → delegation choice → then this page.)
        if part == 3:
            if self.player.field_maybe_none("delegate_decision_optional") is True:
                return False
            return True  # rounds 21–30, no delegation (10 choice rounds so Part 3 results have no None)
        # Part 1 or 2: show in no-delegation block only
        return not Constants.is_mandatory_delegation_round(self.round_number)

    def vars_for_template(self):
        # Per-participant 90s timer (cosmetic countdown): record part start when they first see a decision page of this part.
        part = Constants.get_part(self.round_number)
        start_key = f'part_{part}_start_time'
        if self.round_number in (1, 11, 21):
            if start_key not in self.participant.vars:
                self.participant.vars[start_key] = time.time()
        start_time = self.participant.vars.get(start_key, time.time())
        elapsed = time.time() - start_time
        countdown_seconds = max(0, 90 - int(elapsed))
        if Constants.USE_BATCH_START and self.round_number in (11, 21):
            ensure_round_groups_initialized(self.subsession, self.participant)
        round_in_part = (self.round_number - 1) % Constants.rounds_per_part + 1
        current_part = Constants.get_part(self.round_number)
        return {
            "round_number": round_in_part,
            "current_part": current_part,
            "countdown_seconds": countdown_seconds,
            **part_vars(),
        }

        
class InstructionsOptional(Page):
    template_name = "prisoners_dilemma/templates/prisoners_dilemma/InstructionsOptional.html"

    def is_displayed(self):
        return (
            Constants.get_part(self.round_number) == 3
            and (self.round_number - 1) % Constants.rounds_per_part == 0
        )

    def vars_for_template(self):
        if Constants.USE_BATCH_START and self.round_number == 21:
            ensure_round_groups_initialized(self.subsession, self.participant)
        return part_vars()

class InstructionsGuessingGame(Page):
    template_name = "prisoners_dilemma/templates/prisoners_dilemma/InstructionsGuessingGame.html"

    def is_displayed(self):
        return self.round_number == 30
    
class DecisionsGuessingGame(Page):
    template_name = "prisoners_dilemma/templates/prisoners_dilemma/DecisionsGuessingGame.html"
    form_model = "player"
    form_fields = ["guess_opponent_delegated"]

    def is_displayed(self):
        return self.round_number == Constants.num_rounds
    
class ResultsGuess(Page):
    def is_displayed(self):
        return (
            self.round_number == Constants.num_rounds
            and self.participant.vars.get('guess_submitted', False)
        )

    def vars_for_template(self):
        rows = []

        for r in range(
            2 * Constants.rounds_per_part + 1,
            3 * Constants.rounds_per_part + 1
        ):
            me = self.player.in_round(r)
            other = me.get_others_in_group()[0]

            guess = me.field_maybe_none("guess_opponent_delegated")

            if guess is None:
                my_decision = "No guess"
            elif guess == 'yes':
                my_decision = "Yes"
            else:
                my_decision = "No"

            earnings_str = "0.1" if (me.guess_payoff or 0) else "0"

            rows.append({
                "round": r - 2 * Constants.rounds_per_part,
                "my_decision": my_decision,
                "other_decision": (
                    "Yes"
                    if other.field_maybe_none("delegate_decision_optional")
                    else "No"
                ),
                # 0.1 dollars for correct, 0 for incorrect
                "earnings": earnings_str,
            })

        return {"rows": rows}
# -------------------------
#  Page Sequence
# -------------------------

def _wait_page_class():
    """Batch start: wait only for your group of 10. Else timeout wait page or standard wait for all."""
    if Constants.USE_BATCH_START:
        return BatchWaitForGroup
    return WaitForGroupWithTimeout if Constants.USE_WAIT_TIMEOUT else WaitForGroup


page_sequence = [
    InformedConsent,
    BotDetection,
    MainInstructions,
    ComprehensionTest,
    FailedTest,
    *([Lobby] if Constants.USE_BATCH_START else []),  # Lobby first at round 1/11/21 so participants land on Lobby before Instructions
    InstructionsDelegation,
    InstructionsNoDelegation,

    # Part 3: instructions then delegation decision then decision pages (InstructionsOptional, DelegationDecision before DecisionNoDelegation)
    InstructionsOptional,
    DelegationDecision,
    DecisionNoDelegation,
    AgentProgramming,
    _wait_page_class(),
    Results,

    InstructionsGuessingGame,
    GuessDelegation,
    ResultsGuess,
    Debriefing,
    ExitQuestionnaire,
    Thankyou,
]
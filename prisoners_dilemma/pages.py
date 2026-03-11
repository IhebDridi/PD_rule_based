"""
Prisoners' dilemma app pages: consent, instructions, lobby, decisions, wait pages, results, debriefing.

Flow: InformedConsent → MainInstructions → Lobby (per part) → part-specific instructions →
DecisionNoDelegation / AgentProgramming → BatchWaitForGroup → Results → (Part 4) GuessDelegation →
ResultsGuess → Debriefing → ExitQuestionnaire → Thankyou. Lobby and BatchWaitForGroup implement
custom wait/release and payoff logic; DelegationDecision is Part 3 only.
"""
from starlette.responses import RedirectResponse
from otree.api import *
from .models import Constants, release_lobby_batch, run_payoffs_for_matching_group, get_opponent_in_round
import json
import time

# Minimum seconds all batch members must have been on BatchWaitForGroup before payoffs run (avoids races).
BATCH_WAIT_MIN_SECONDS = 2


def _has_left_lobby_for_part(participant, part):
    """
    Return True for all participants.

    Original version checked lobby flags (has_left_lobby / has_left_lobby_part_X), but with the
    current design there is no Lobby in the flow, so everyone should be allowed to proceed to
    instructions and decision pages without a prior lobby gate.
    """
    return True


def part_vars():
    """Template vars for part labels (part_no_delegation, part_delegation) used across instruction pages."""
    return {
        "part_no_delegation": Constants.part_no_delegation(),
        "part_delegation": Constants.part_delegation(),
    }


# =============================================================================
# Consent and instructions
# =============================================================================

class InformedConsent(Page):
    """Round 1 only. Collect 24-character Prolific ID; validated in error_message_prolific_id."""
    form_model = 'player'
    form_fields = ['prolific_id']

    def is_displayed(self):
        return self.round_number == 1

    def error_message_prolific_id(self, value):
        pid = (value or '').strip() if isinstance(value, str) else str((value or {}).get('prolific_id', ''))
        if len(pid) != 24:
            return "Please enter your correct 24-character Prolific ID."


class MainInstructions(Page):
    """Main instructions (experiment structure) at round 1."""
    template_name = 'prisoners_dilemma/MainInstructions.html'

    def is_displayed(self):
        return self.round_number == 1

    def vars_for_template(self):
        return part_vars()


class ComprehensionTest(Page):
    """
    Round-1 comprehension quiz about the task. Uses q1–q10 fields on Player and
    tracks attempts via comprehension_attempts / is_excluded. Shows a dynamic
    error message via participant.vars['comp_error_message'].
    """
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
            # all correct → proceed
            self.participant.vars.pop("comp_error_message", None)
            return

        # incorrect answers
        self.player.comprehension_attempts += 1
        attempts_left = 3 - self.player.comprehension_attempts

        if attempts_left > 0:
            msg = (
                f"You have failed questions: {', '.join(incorrect)}. "
                f"You have {attempts_left} attempt(s) remaining."
            )
            self.participant.vars["comp_error_message"] = msg
            return msg

        # no attempts left → exclude and move on to FailedTest (do not require correct answers anymore)
        self.player.is_excluded = True
        # no form-level error: allow navigation to FailedTest based on is_excluded
        return


class FailedTest(Page):
    """Shown only if comprehension attempts exceeded and player.is_excluded is True."""
    def is_displayed(self):
        return self.player.is_excluded


class InstructionsNoDelegation(Page):
    """Shown at start of the no-delegation block (Part 1 round 1 or Part 2 round 11 depending on DELEGATION_FIRST). Hidden if not yet released from lobby."""
    template_name = 'prisoners_dilemma/InstructionsNoDelegation.html'

    def is_displayed(self):
        if self.round_number == 1 and not _has_left_lobby_for_part(self.participant, 1):
            return False
        if self.round_number == 11 and not _has_left_lobby_for_part(self.participant, 2):
            return False
        if self.round_number == 1:
            return not Constants.DELEGATION_FIRST
        if self.round_number == 11:
            return Constants.DELEGATION_FIRST
        return False

    def vars_for_template(self):
        return part_vars()


class InstructionsDelegation(Page):
    """Shown at start of the mandatory-delegation block (Part 1 or Part 2 per DELEGATION_FIRST)."""
    template_name = 'prisoners_dilemma/InstructionsDelegation.html'

    def is_displayed(self):
        if self.round_number == 1 and not _has_left_lobby_for_part(self.participant, 1):
            return False
        if self.round_number == 11 and not _has_left_lobby_for_part(self.participant, 2):
            return False
        if self.round_number == 1:
            return Constants.DELEGATION_FIRST
        if self.round_number == 11:
            return not Constants.DELEGATION_FIRST
        return False

    def vars_for_template(self):
        return part_vars()


class InstructionsOptional(Page):
    """Part 3 intro (round 21 only): explains optional delegation. Shown only after leaving Part 3 lobby."""
    template_name = 'prisoners_dilemma/InstructionsOptional.html'

    def is_displayed(self):
        return self.round_number == 21 and _has_left_lobby_for_part(self.participant, 3)

    def vars_for_template(self):
        return part_vars()


class InstructionsGuessingGame(Page):
    template_name = 'prisoners_dilemma/InstructionsGuessingGame.html'

    def is_displayed(self):
        return self.round_number == Constants.num_rounds

    def vars_for_template(self):
        return part_vars()


# =============================================================================
# Agent programming (delegation: set A/B per round via table; live_method + before_next_page sync to choice)
# =============================================================================

class AgentProgramming(Page):
    """
    Page where participants set agent decisions (A or B) for each round of the delegation block.
    live_method receives JSON from the front end and stores in participant.vars; before_next_page
    copies those (or form fields for mandatory blocks) into player.in_round(r).choice.
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
        current_part = Constants.get_part(self.round_number)
        return {
            "current_part": current_part,
            "delegate_decision": self.player.field_maybe_none(
                "delegate_decision_optional"
            ),
            "countdown_seconds": 90,
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


class BatchWaitForGroup(WaitPage):
    """
    Shown at end of each part (rounds 10, 20, 30). Waits until every participant in the same
    matching_group_id has arrived; then one request runs run_payoffs_for_matching_group and all
    proceed. Uses session key payoffs_run_matching_group_{gid}_part_{part} so payoffs run only once.
    """
    template_name = 'prisoners_dilemma/BatchWaitForGroup.html'

    def is_displayed(self):
        """At part boundaries (round 10, 20, 30): show if left lobby for this part and not yet in a formed results group."""
        r = self.round_number
        if r % Constants.rounds_per_part != 0:
            return False
        current_part = Constants.get_part(r)
        if not _has_left_lobby_for_part(self.participant, current_part):
            return False
        can_proceed_key = f'can_proceed_to_results_part_{current_part}'
        return not self.participant.vars.get(can_proceed_key, False)

    def get(self):
        """
        Wait after decisions, just before Results. Participants stay here until:

        - A group of exactly FIXED_GROUP_SIZE (3) is formed from the pool → payoffs run → proceed to Results, or
        - Fewer than 3 are available for RESULTS_WAIT_TIMEOUT_SECONDS → show a choice:
          * wait 5 more minutes, or
          * return to Prolific with the show-up fee.
        """
        _params = getattr(self.request, "GET", None) or getattr(self.request, "query_params", None)
        current_part = Constants.get_part(self.round_number)
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        pool_key = f"results_pool_part_{current_part}"
        joined_at_key = f"results_wait_joined_at_part_{current_part}"

        # Handle actions from the timeout choice UI.
        if _params:
            if _params.get("quit"):
                # Participant chooses to leave → remove from pool, mark quit, advance to TimeOutquit (admin shows that name), which then redirects to Prolific.
                pool = [sid for sid in self.session.vars.get(pool_key, []) if sid != self.participant.id_in_session]
                self.session.vars[pool_key] = pool
                self.participant.vars['quit_to_prolific_results'] = True
                return self._response_when_ready()
            if _params.get("wait_more"):
                # This participant chooses to wait 5 more minutes → reset their personal join time (new 5‑min window).
                self.participant.vars[joined_at_key] = time.time()

        # If already assigned to a results group, go to Results.
        if self.participant.vars.get(can_proceed_key):
            return self._response_when_ready()
        return self._get_wait_page()

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        pool_key = f'results_pool_part_{current_part}'
        group_size = getattr(Constants, 'FIXED_GROUP_SIZE', 3)
        participants = self.session.get_participants()
        lock_key = f'_results_pool_lock_part_{current_part}'
        first_join_key = f'results_first_join_part_{current_part}'
        joined_at_key = f'results_wait_joined_at_part_{current_part}'
        timeout_seconds = 300  # 5 minutes: show wait-or-quit only after this participant has waited this long
        if pool_key not in self.session.vars:
            self.session.vars[pool_key] = []
        now = time.time()
        if first_join_key not in self.session.vars:
            self.session.vars[first_join_key] = now
        pid = self.participant.id_in_session
        # Under one lock: add self to pool (and set this participant's joined-at time), maybe form a group of 3.
        if not self.session.vars.get(lock_key):
            self.session.vars[lock_key] = True
            try:
                pool = list(self.session.vars.get(pool_key, []))
                if pid not in pool:
                    pool.append(pid)
                    self.session.vars[pool_key] = pool
                    self.participant.vars[joined_at_key] = now  # per-participant: when they joined the wait
                pool = list(self.session.vars.get(pool_key, []))
                if len(pool) >= group_size:
                    first_ids = pool[:group_size]
                    self.session.vars[pool_key] = pool[group_size:]
                    next_batch_key = f'results_next_batch_id_part_{current_part}'
                    batch_id = self.session.vars.get(next_batch_key, 0)
                    self.session.vars[next_batch_key] = batch_id + 1
                    part_start_round = (current_part - 1) * Constants.rounds_per_part + 1
                    round_ss = self.subsession.in_round(part_start_round)
                    batch_players = [pl for pl in round_ss.get_players() if pl.participant.id_in_session in first_ids]
                    batch_players = sorted(batch_players, key=lambda pl: first_ids.index(pl.participant.id_in_session))
                    if len(batch_players) == group_size:
                        # Lightweight grouping: do NOT call set_group_matrix (too slow for big sessions).
                        # Store the 3 participant IDs for opponent lookup/payoffs, and set matching_group vars.
                        self.session.vars[f'matching_group_members_part_{current_part}_{batch_id}'] = list(first_ids)
                        for i, pl in enumerate(batch_players):
                            pl.participant.vars['matching_group_id'] = batch_id
                            pl.participant.vars['matching_group_position'] = i + 1
                        time.sleep(0.5)
                        run_payoffs_for_matching_group(self.subsession, batch_id)
                        for p in participants:
                            if p.id_in_session in first_ids:
                                p.vars[f'can_proceed_to_results_part_{current_part}'] = True
            finally:
                self.session.vars[lock_key] = False
        n_in_pool = len(self.session.vars.get(pool_key, []))
        # Show wait-or-quit only if pool still has < 3 AND this participant has personally waited >= 5 minutes.
        joined_at = self.participant.vars.get(joined_at_key, now)
        show_wait_or_quit_results = (n_in_pool < group_size) and ((now - joined_at) >= timeout_seconds)
        path = getattr(self.request, 'path', None) or getattr(self.request, 'path_info', '') or ''
        build_uri = getattr(self.request, 'build_absolute_uri', None)
        base_url = (build_uri(path) if build_uri and path else path) or ''
        wait_more_url = base_url + ('&' if '?' in base_url else '?') + 'wait_more=1'
        quit_url = base_url + ('&' if '?' in base_url else '?') + 'quit=1'
        return {
            'n_arrived': n_in_pool,
            'batch_size': group_size,
            'show_wait_or_quit_results': show_wait_or_quit_results,
            'wait_more_url': wait_more_url,
            'quit_to_prolific_url': quit_url,
        }

    @staticmethod
    def live_method(player, data):
        """Return current results-pool size (pair-only-before-Results: pool of 3 forms a group)."""
        if not data or data.get('type') != 'get_count':
            return
        current_part = Constants.get_part(player.round_number)
        pool_key = f'results_pool_part_{current_part}'
        pool = player.session.vars.get(pool_key, [])
        group_size = getattr(Constants, 'FIXED_GROUP_SIZE', 3)
        payload = {'n_arrived': len(pool), 'n_total': group_size}
        return {player.id_in_group: payload}


# =============================================================================
# TimeOutquit: shown only to participants who chose to leave from results wait; redirects to Prolific (admin shows this page name)
# =============================================================================

class TimeOutquit(Page):
    """Shown only when participant chose to quit from BatchWaitForGroup; redirects to Prolific show-up fee. Admin displays this page name instead of BatchWaitForGroup."""
    template_name = 'prisoners_dilemma/TimeOutquit.html'

    def is_displayed(self):
        return bool(self.participant.vars.get('quit_to_prolific_results', False))

    def get(self):
        return RedirectResponse(url=Constants.PROLIFIC_SHOWUP_FEE_URL, status_code=303)

    def vars_for_template(self):
        return {'prolific_showup_url': Constants.PROLIFIC_SHOWUP_FEE_URL}


# =============================================================================
# Delegation decision (Part 3 only: delegate or play yourself)
# =============================================================================

class DelegationDecision(Page):
    """Part 3 start (round 21): one-time choice whether to delegate or not. Invalid round in URL → redirect to 21."""
    form_model = 'player'
    form_fields = ['delegate_decision_optional']

    def get(self):
        # Redirect invalid round numbers (e.g. 347) to round 21 so the page doesn't 500.
        rnd = self.round_number
        if rnd > Constants.num_rounds or rnd != 21:
            path = getattr(self.request, 'path', None) or getattr(self.request, 'path_info', '') or (getattr(self.request, 'url', None) and getattr(self.request.url, 'path', '')) or ''
            if path and path.rstrip('/'):
                parts = path.rstrip('/').split('/')
                if len(parts) >= 1:
                    parts[-1] = '21'
                    new_url = '/'.join(parts)
                    return RedirectResponse(url=new_url, status_code=303)
        return super().get()

    def is_displayed(self):
        # show ONCE at start of Part 3 (round 21)
        if self.round_number > Constants.num_rounds:
            return False
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


# =============================================================================
# Results (end of Parts 1–3: show round-by-round choices, opponent, payoff)
# =============================================================================

class Results(Page):
    """Shown at end of each part (rounds 10, 20, 30) only after participant is in a formed results group (can_proceed_to_results_part_X)."""
    def is_displayed(self):
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
        current_part = Constants.get_part(self.round_number)
        part_start = (current_part - 1) * Constants.rounds_per_part + 1
        part_end = current_part * Constants.rounds_per_part

        player = self.player
        # Repair: when payoffs ran before all choices were committed (e.g. 30 bots at once), recompute for any round where both choices exist but payoff is 0.
        for r in range(part_start, part_end + 1):
            rr = player.in_round(r)
            other = get_opponent_in_round(player, r)
            payoff_val = getattr(rr.payoff, 'amount', rr.payoff) if rr.payoff is not None else 0
            if payoff_val == 0 and rr.field_maybe_none('choice') and other and other.field_maybe_none('choice'):
                try:
                    rr.group.set_payoffs()
                except Exception:
                    pass

        rounds_data = []
        for r in range(part_start, part_end + 1):
            rr = player.in_round(r)
            other = get_opponent_in_round(player, r)
            rounds_data.append({
                'round': r - (current_part - 1) * Constants.rounds_per_part,
                'my_choice': rr.field_maybe_none('choice'),
                'other_choice': other.field_maybe_none('choice') if other else None,
                'payoff': rr.payoff,
                'is_payoff_round': True,
            })

        # Part 1 then Part 2 always: first block = Part 1, second = Part 2, third = Part 3
        display_part = current_part

        return dict(
            current_part=current_part,
            display_part=display_part,
            rounds_data=rounds_data,
        )

# =============================================================================
# Part 4: guessing whether opponent delegated (per Part 3 round)
# =============================================================================

class GuessDelegation(Page):
    """Shown once after Part 3 (round 30). Ten guesses (guess_round_1..10); before_next_page sets guess_payoff (10 cu if correct)."""
    form_model = 'player'

    def is_displayed(self):
        return self.round_number == 3 * Constants.rounds_per_part

    def get_form_fields(self):
        return [f"guess_round_{i}" for i in range(1, 11)]

    def vars_for_template(self):
        rows = []
        start = 2 * Constants.rounds_per_part + 1  # round 21

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

        return {
            "rows": rows,
            "countdown_seconds": 90,
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

            #  3. compute and ALWAYS store payoff (10 cents per correct → 10 correct = $1 total)
            other = get_opponent_in_round(self.player, r)
            actual = bool(other and other.field_maybe_none("delegate_decision_optional"))

            future_player.guess_payoff = (
                cu(10) if (guess == 'yes') == actual else cu(0)
            )

        self.participant.vars['guess_submitted'] = True


# =============================================================================
# Debriefing and exit questionnaire
# =============================================================================

class Debriefing(Page):
    """Final round only. Shows results_by_part, random_payoff_part, Part 4 guessing table, and total bonus."""
    def is_displayed(self):
        return self.round_number == Constants.num_rounds


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
                other = get_opponent_in_round(self.player, r)
                part_data.append({
                    "round": r - (part - 1) * Constants.rounds_per_part,
                    "my_choice": me.field_maybe_none("choice"),
                    "other_choice": other.field_maybe_none("choice") if other else None,
                    "other_delegated": bool(other and other.field_maybe_none("delegate_decision_optional")),
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
            other = get_opponent_in_round(self.player, r)
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



class ExitQuestionnaire(Page):
    """Final round: demographics, feedback, part_3/part_4 feedback. Validates part_3_other requires part_3_feedback_other."""
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
    """Final page: shown only on last round."""
    def is_displayed(self):
        return self.round_number == Constants.num_rounds


# =============================================================================
# Lobby: wait for 3+ participants, release batch (first-in first-out), wait-or-quit on timeout
# =============================================================================

class Lobby(WaitPage):
    """
    Lobby: wait 5 min (part 1) or 2 min (parts 2–3). When >= MIN_PLAYERS_TO_START and timeout, release batch
    with round-robin matching. If timeout and < 3, show wait-or-quit (wait 5 more or return to Prolific for $1).
    """
    template_name = 'prisoners_dilemma/Lobby.html'

    def is_displayed(self):
        rnd = self.round_number
        if rnd == 1:
            return not self.participant.vars.get('has_left_lobby', False) and not self.participant.vars.get('quit_to_prolific', False)
        if rnd == 11:
            return not self.participant.vars.get('has_left_lobby_part_2', False) and not self.participant.vars.get('quit_to_prolific', False)
        if rnd == 21:
            return not self.participant.vars.get('has_left_lobby_part_3', False) and not self.participant.vars.get('quit_to_prolific', False)
        return False

    def _lobby_part(self):
        """Return 1, 2, or 3 for the part this Lobby instance belongs to (round 1 → part 1, 11 → 2, 21 → 3)."""
        if self.round_number == 1:
            return 1
        if self.round_number == 11:
            return 2
        if self.round_number == 21:
            return 3
        return 1

    def get(self):
        _params = getattr(self.request, 'GET', None) or getattr(self.request, 'query_params', None)
        if _params and _params.get('quit'):
            self.participant.vars['quit_to_prolific'] = True
            return RedirectResponse(url=Constants.PROLIFIC_RETURN_URL, status_code=303)
        part = self._lobby_part()
        wait_quit_key = f'show_wait_or_quit_part_{part}'
        first_join_key = f'lobby_first_join_part_{part}'
        restart = _params.get('restart') if _params else None
        if restart and self.session.vars.get(wait_quit_key):
            self.session.vars[wait_quit_key] = False
            self.session.vars[first_join_key] = time.time()
        context = self.get_context_data()
        if context.get('can_leave_lobby'):
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
            timeout_sec = Constants.LOBBY_WAIT_SECONDS_PART1
        else:
            lobby_key = f'lobby_ids_part_{part}'
            next_batch_key = f'next_batch_id_part_{part}'
            can_leave_key = f'can_leave_lobby_part_{part}'
            timeout_sec = Constants.LOBBY_WAIT_SECONDS_PART2_3
        first_join_key = f'lobby_first_join_part_{part}'
        wait_quit_key = f'show_wait_or_quit_part_{part}'

        lobby = list(self.session.vars.get(lobby_key, []))
        can_leave = self.participant.vars.get(can_leave_key, False)
        if self.participant.id_in_session not in lobby and not can_leave:
            if len(lobby) == 0:
                self.session.vars[first_join_key] = time.time()
            lobby.append(self.participant.id_in_session)
            self.session.vars[lobby_key] = lobby
        if part >= 2 and self.participant.vars.get('matching_group_id', -1) >= 0 and not can_leave:
            self.participant.vars['matching_group_id'] = -1
        n_waiting = len(lobby)
        next_batch_id = self.session.vars.get(next_batch_key, 0)
        now = time.time()
        first_join = self.session.vars.get(first_join_key)
        if first_join is None:
            first_join = now
            self.session.vars[first_join_key] = now
        elapsed = now - first_join
        min_players = Constants.MIN_PLAYERS_TO_START
        min_wait = getattr(Constants, 'LOBBY_MIN_WAIT_SECONDS', 2)
        # First in first out: when N>=3 are in the lobby and min_wait passed, release those N as one group.
        # (oTree alternative: WaitPage with group_by_arrival_time_method returning waiting_players when len >= 3.)
        # Use a session lock so only one request runs release (avoids IntegrityError from concurrent set_group_matrix).
        # Pair only before Results: release from lobby without forming groups (no release_lobby_batch here).
        if n_waiting >= min_players and elapsed >= min_wait:
            lock_key = f'_lobby_release_lock_part_{part}'
            if not self.session.vars.get(lock_key):
                self.session.vars[lock_key] = True
                try:
                    batch_ids = list(self.session.vars.get(lobby_key, []))
                    if len(batch_ids) < min_players:
                        batch_ids = []
                    self.session.vars[lobby_key] = []
                    self.session.vars[first_join_key] = None
                    self.session.vars[next_batch_key] = next_batch_id + 1
                    for p in self.session.get_participants():
                        if p.id_in_session in batch_ids:
                            p.vars[can_leave_key] = True
                finally:
                    self.session.vars[lock_key] = False
        elif elapsed >= timeout_sec and n_waiting < min_players:
            self.session.vars[wait_quit_key] = True
        can_leave = self.participant.vars.get(can_leave_key, False)
        show_wait_or_quit = self.session.vars.get(wait_quit_key, False)
        path = getattr(self.request, 'path', None) or getattr(self.request, 'path_info', '') or ''
        build_uri = getattr(self.request, 'build_absolute_uri', None)
        base_url = (build_uri(path) if build_uri and path else path) or ''
        restart_url = base_url + ('&' if '?' in base_url else '?') + 'restart=1'
        quit_to_prolific_url = base_url + ('&' if '?' in base_url else '?') + 'quit=1'
        return {
            'can_leave_lobby': can_leave,
            'lobby_part': part,
            'show_wait_or_quit': show_wait_or_quit,
            'prolific_return_url': Constants.PROLIFIC_RETURN_URL,
            'quit_to_prolific_url': quit_to_prolific_url,
            'restart_url': restart_url,
            'refresh_seconds': 2,
        }

    @staticmethod
    def live_method(player, data):
        if not data or data.get('type') != 'get_lobby_count':
            return
        rnd = player.round_number
        lobby_key = 'lobby_ids' if rnd == 1 else f'lobby_ids_part_{2 if rnd == 11 else 3}'
        lobby = player.session.vars.get(lobby_key, [])
        return {player.id_in_group: {'n_waiting': len(lobby)}}



# =============================================================================
# Decision page (no delegation: human chooses A or B)
# =============================================================================

class DecisionNoDelegation(Page):
    """A/B choice page for no-delegation rounds. Shown when not in mandatory-delegation block and (in Part 3) when participant did not delegate."""
    template_name = "prisoners_dilemma/DecisionNoDelegation.html"
    form_model = "player"
    form_fields = ["choice"]

    def is_displayed(self):
        part = Constants.get_part(self.round_number)
        if self.round_number in (1, 11, 21) and not _has_left_lobby_for_part(self.participant, part):
            return False
        if part == 3:
            if self.player.field_maybe_none("delegate_decision_optional") is True:
                return False
            return True
        return not Constants.is_mandatory_delegation_round(self.round_number)

    def vars_for_template(self):
        # 15 seconds per decision page (cosmetic countdown)
        countdown_seconds = 15
        round_in_part = (self.round_number - 1) % Constants.rounds_per_part + 1
        current_part = Constants.get_part(self.round_number)
        return {
            "round_number": round_in_part,
            "current_part": current_part,
            "countdown_seconds": countdown_seconds,
            **part_vars(),
        }


class ResultsGuess(Page):
    """Shown after GuessDelegation (round 30). Displays Part 4 guess results (yes/no vs actual delegation, earnings)."""
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
            other = get_opponent_in_round(self.player, r)

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
                    "Yes" if other and other.field_maybe_none("delegate_decision_optional")
                    else ("No" if other else "—")
                ),
                # 0.1 dollars for correct, 0 for incorrect
                "earnings": earnings_str,
            })

        return {"rows": rows}
# -------------------------
#  Page Sequence
# -------------------------

page_sequence = [
    InformedConsent,
    MainInstructions,
    ComprehensionTest,
    FailedTest,
    # Lobby,  # temporarily disabled: pairing happens only on BatchWaitForGroup before Results
    InstructionsNoDelegation,
    InstructionsDelegation,
    InstructionsOptional,
    DelegationDecision,
    DecisionNoDelegation,
    AgentProgramming,
    BatchWaitForGroup,
    TimeOutquit,
    Results,
    InstructionsGuessingGame,
    GuessDelegation,
    ResultsGuess,
    Debriefing,
    ExitQuestionnaire,
    Thankyou,
]
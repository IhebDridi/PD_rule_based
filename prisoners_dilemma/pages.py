from starlette.responses import RedirectResponse
from otree.api import *
from .models import Constants, release_lobby_batch, run_payoffs_for_matching_group, get_opponent_in_round
import json
import time


BATCH_WAIT_MIN_SECONDS = 2


def part_vars():
    return {
        "part_no_delegation": Constants.part_no_delegation(),
        "part_delegation": Constants.part_delegation(),
    }


# --- Consent & instructions ---

class InformedConsent(Page):
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


class InstructionsNoDelegation(Page):
    template_name = 'prisoners_dilemma/InstructionsNoDelegation.html'

    def is_displayed(self):
        if self.round_number in (1, 11) and self.participant.vars.get('matching_group_id', -1) < 0:
            return False
        if self.round_number == 1:
            return not Constants.DELEGATION_FIRST
        if self.round_number == 11:
            return Constants.DELEGATION_FIRST
        return False

    def vars_for_template(self):
        return part_vars()


class InstructionsDelegation(Page):
    template_name = 'prisoners_dilemma/InstructionsDelegation.html'

    def is_displayed(self):
        if self.round_number in (1, 11) and self.participant.vars.get('matching_group_id', -1) < 0:
            return False
        if self.round_number == 1:
            return Constants.DELEGATION_FIRST
        if self.round_number == 11:
            return not Constants.DELEGATION_FIRST
        return False

    def vars_for_template(self):
        return part_vars()


class InstructionsOptional(Page):
    template_name = 'prisoners_dilemma/InstructionsOptional.html'

    def is_displayed(self):
        return (
            self.round_number == 21
            and self.participant.vars.get('matching_group_id', -1) >= 0
        )

    def vars_for_template(self):
        return part_vars()


class InstructionsGuessingGame(Page):
    template_name = 'prisoners_dilemma/InstructionsGuessingGame.html'

    def is_displayed(self):
        return self.round_number == Constants.num_rounds

    def vars_for_template(self):
        return part_vars()


# --- Agent Programming (delegation rounds) ---

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
        elif r == 21:
            player.participant.vars['agent_programming_part3'] = decisions

    def is_displayed(self):
        r = self.round_number
        if r in (1, 11, 21) and self.participant.vars.get('matching_group_id', -1) < 0:
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
        current_part = Constants.get_part(self.round_number)
        return {
            "current_part": current_part,
            "delegate_decision": self.player.field_maybe_none(
                "delegate_decision_optional"
            ),
            "countdown_seconds": 15,
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
    Wait page at end of each part. Waits for all in your round-robin batch (matching_group_id >= 0);
    then runs payoffs. No dropout/simulated logic.
    """
    template_name = 'prisoners_dilemma/BatchWaitForGroup.html'

    def is_displayed(self):
        return (
            self.round_number % Constants.rounds_per_part == 0
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
        n_arrived = sum(1 for p in in_my_group if p.vars.get(arrived_key))
        group_size = len(in_my_group)
        applied_key = f'payoffs_run_matching_group_{gid}_part_{current_part}'
        can_proceed = n_arrived >= group_size
        if can_proceed and BATCH_WAIT_MIN_SECONDS > 0:
            first_arrived_at = self.participant.vars.get(arrived_at_key) or time.time()
            if (time.time() - first_arrived_at) < BATCH_WAIT_MIN_SECONDS:
                can_proceed = False
        if can_proceed:
            if not self.session.vars.get(applied_key):
                # Claim immediately so only one request runs payoffs (avoid race with concurrent arrivals).
                self.session.vars[applied_key] = True
                # Brief delay so in-flight choice writes from other participants can commit.
                time.sleep(0.5)
                run_payoffs_for_matching_group(self.subsession, gid)
            return self._response_when_ready()
        return self._get_wait_page()

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        arrived_key = f'wait_arrived_part_{current_part}'
        arrived_at_key = f'wait_arrived_part_{current_part}_at'
        if arrived_at_key not in self.participant.vars:
            self.participant.vars[arrived_at_key] = time.time()
        self.participant.vars[arrived_key] = True
        gid = self.participant.vars.get('matching_group_id', -1)
        participants = self.session.get_participants()
        in_my_group = [p for p in participants if p.vars.get('matching_group_id') == gid]
        n_arrived = sum(1 for p in in_my_group if p.vars.get(arrived_key))
        return {
            'n_arrived': n_arrived,
            'batch_size': len(in_my_group),
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


# --- Delegation Decision (Part 3 only) ---

class DelegationDecision(Page):
    form_model = 'player'
    form_fields = ['delegate_decision_optional']

    def get(self):
        # If URL has an invalid round (e.g. 347 when only 30 rounds exist), redirect to the valid round for this page (21).
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


# --- Results (end of each part) ---


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
        if self.round_number in (10, 20):
            self.participant.vars['matching_group_id'] = -1

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        part_start = (current_part - 1) * Constants.rounds_per_part + 1
        part_end = current_part * Constants.rounds_per_part

        player = self.player
        # Repair: when a late-arriving batch has choices but payoffs were never run (or ran too early), recompute.
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

# -------------------------
#  Delegation guessing
# -------------------------

class GuessDelegation(Page):
    form_model = 'player'

    def is_displayed(self):
        #  show ONCE, at end of Part 3; simulated participants skip (guesses set in creating_session)
        if self.round_number != 3 * Constants.rounds_per_part:
            return False
        return True

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
            "countdown_seconds": 15,
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
            other = get_opponent_in_round(self.player, r)
            actual = bool(other and other.field_maybe_none("delegate_decision_optional"))

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
        guessing_bonus_cents = guessing_bonus_ecoins // 10
        total_bonus_cents = total_payoff_cents + guessing_bonus_cents
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
    def is_displayed(self):
        return self.round_number == Constants.num_rounds


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
        if (
            self.participant.id_in_session not in lobby
            and self.participant.vars.get('matching_group_id', -1) < 0
            and not self.participant.vars.get(can_leave_key, False)
        ):
            if len(lobby) == 0:
                self.session.vars[first_join_key] = time.time()
            lobby.append(self.participant.id_in_session)
            self.session.vars[lobby_key] = lobby
        if part >= 2 and self.participant.vars.get('matching_group_id', -1) >= 0 and not self.participant.vars.get(can_leave_key, False):
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
        if n_waiting >= min_players and elapsed >= min_wait:
            lock_key = f'_lobby_release_lock_part_{part}'
            if not self.session.vars.get(lock_key):
                self.session.vars[lock_key] = True
                try:
                    # Snapshot lobby inside lock so we release exactly who is in it now (avoids batch growing as more join in parallel).
                    batch_ids = list(self.session.vars.get(lobby_key, []))
                    if len(batch_ids) < min_players:
                        batch_ids = []
                    self.session.vars[lobby_key] = []
                    self.session.vars[first_join_key] = None
                    self.session.vars[next_batch_key] = next_batch_id + 1
                    if batch_ids:
                        subsession = self.subsession
                        batch_players = [p for p in subsession.get_players() if p.participant.id_in_session in batch_ids]
                        release_lobby_batch(subsession, batch_players, batch_id=next_batch_id, part=part)
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



#changes are made
class DecisionNoDelegation(Page):
    template_name = "prisoners_dilemma/DecisionNoDelegation.html"
    form_model = "player"
    form_fields = ["choice"]

    def is_displayed(self):
        if self.round_number in (1, 11, 21) and self.participant.vars.get('matching_group_id', -1) < 0:
            return False
        part = Constants.get_part(self.round_number)
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
    Lobby,
    InstructionsNoDelegation,
    InstructionsDelegation,
    InstructionsOptional,
    DelegationDecision,
    DecisionNoDelegation,
    AgentProgramming,
    BatchWaitForGroup,
    Results,
    InstructionsGuessingGame,
    GuessDelegation,
    ResultsGuess,
    Debriefing,
    ExitQuestionnaire,
    Thankyou,
]
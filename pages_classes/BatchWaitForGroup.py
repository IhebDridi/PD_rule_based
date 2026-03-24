import time

from otree.api import *

from .model_bridge import app_models
from .page_helpers import BATCH_WAIT_MIN_SECONDS, _has_left_lobby_for_part


class BatchWaitForGroup(WaitPage):
    """
    Shown at end of each part (rounds 10, 20, 30). Waits until every participant in the same
    matching_group_id has arrived; then one request runs run_payoffs_for_matching_group and all
    proceed. Uses session key payoffs_run_matching_group_{gid}_part_{part} so payoffs run only once.

    Template path is ``global/BatchWaitForGroup.html``.
    """

    @property
    def template_name(self):
        return "global/BatchWaitForGroup.html"

    # Performance/safety knobs for large sessions.
    POOL_CLEANUP_EVERY_UPDATES = 75
    FIXED_RESULTS_GROUP_SIZE = 3

    def is_displayed(self):
        """At part boundaries (round 10, 20, 30): show if left lobby for this part and not yet in a formed results group."""
        Constants = app_models(self.player).Constants
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
        am = app_models(self.player)
        Constants = am.Constants
        _params = getattr(self.request, "GET", None) or getattr(self.request, "query_params", None)
        current_part = Constants.get_part(self.round_number)
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        ready_at_key = f"results_ready_at_part_{current_part}"
        pool_key = f"results_pool_part_{current_part}"
        pool_version_key = f"results_pool_version_part_{current_part}"
        joined_at_key = f"results_wait_joined_at_part_{current_part}"
        wait_more_token_key = f"results_wait_more_token_part_{current_part}"

        # Handle actions from the timeout choice UI.
        if _params:
            if _params.get("quit"):
                # Participant chooses to leave → remove from pool, mark quit, advance to TimeOutquit (admin shows that name), which then redirects to Prolific.
                pool = [sid for sid in self.session.vars.get(pool_key, []) if sid != self.participant.id_in_session]
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = int(self.session.vars.get(pool_version_key, 0)) + 1
                self.participant.vars['quit_to_prolific_results'] = True
                self.participant.vars[f"results_waiting_part_{current_part}"] = False
                return self._response_when_ready()
            if _params.get("wait_more"):
                # Consume "wait more" only once per click token.
                # Without this, auto-refresh on a URL containing wait_more=1 can keep resetting the timer.
                wait_more_token = _params.get("wait_more_token") or _params.get("t") or ""
                if wait_more_token:
                    if self.participant.vars.get(wait_more_token_key) != wait_more_token:
                        self.participant.vars[joined_at_key] = time.time()
                        self.participant.vars[wait_more_token_key] = wait_more_token
                else:
                    # Backward-compatible fallback if token is missing.
                    # Reset once and mark consumed to avoid repeated resets on refresh.
                    if self.participant.vars.get(wait_more_token_key) != "__legacy__":
                        self.participant.vars[joined_at_key] = time.time()
                        self.participant.vars[wait_more_token_key] = "__legacy__"

        # If already assigned to a results group, go to Results.
        # Update the shared results pool and maybe form a group for this part
        self._update_results_pool_and_maybe_group()
        # If already assigned to a results group, wait a minimum time before redirecting.
        if self.participant.vars.get(can_proceed_key):
            now = time.time()
            ready_at = self.participant.vars.get(ready_at_key)
            if ready_at is None:
                self.participant.vars[ready_at_key] = now
                return self._get_wait_page()
            if now - float(ready_at) < BATCH_WAIT_MIN_SECONDS:
                return self._get_wait_page()
            return self._response_when_ready()
        return self._get_wait_page()

    def post(self):
        """
        Handle auto-refresh POSTs from oTree's wait page JS.
        We mirror the GET logic so that participants who already have
        can_proceed_to_results_part_X set are redirected without needing
        a full manual refresh.
        """
        Constants = app_models(self.player).Constants
        current_part = Constants.get_part(self.round_number)
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        ready_at_key = f"results_ready_at_part_{current_part}"
        # Pool/group update is idempotent when a group is already formed.
        self._update_results_pool_and_maybe_group()
        if self.participant.vars.get(can_proceed_key):
            now = time.time()
            ready_at = self.participant.vars.get(ready_at_key)
            if ready_at is None:
                self.participant.vars[ready_at_key] = now
                return self._get_wait_page()
            if now - float(ready_at) < BATCH_WAIT_MIN_SECONDS:
                return self._get_wait_page()
            return self._response_when_ready()
        return self._get_wait_page()

    def _update_results_pool_and_maybe_group(self):
        """Side-effect helper: incrementally maintain pool and, if possible, form one group of 3."""
        am = app_models(self.player)
        Constants = am.Constants
        current_part = Constants.get_part(self.round_number)
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        pool_key = f'results_pool_part_{current_part}'
        group_size = self.FIXED_RESULTS_GROUP_SIZE
        first_join_key = f'results_first_join_part_{current_part}'
        joined_at_key = f'results_wait_joined_at_part_{current_part}'
        waiting_key = f'results_waiting_part_{current_part}'
        ready_at_key = f"results_ready_at_part_{current_part}"
        pool_version_key = f"results_pool_version_part_{current_part}"
        claim_prefix = f"results_group_claim_part_{current_part}_"
        pool = self.session.vars.get(pool_key, [])
        if not isinstance(pool, list):
            pool = []
        # Keep pool normalized (unique + sorted) without scanning all participants.
        pool = sorted({int(pid) for pid in pool})
        self.session.vars[pool_key] = pool
        now = time.time()
        if first_join_key not in self.session.vars:
            self.session.vars[first_join_key] = now
        pid = self.participant.id_in_session

        # Keep own status/pool entry consistent first.
        if self.participant.vars.get(can_proceed_key) or self.participant.vars.get('quit_to_prolific_results', False):
            self.participant.vars[waiting_key] = False
            if pid in pool:
                pool = [x for x in pool if x != pid]
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = int(self.session.vars.get(pool_version_key, 0)) + 1
            return

        if not self.participant.vars.get(waiting_key):
            self.participant.vars[waiting_key] = True
            self.participant.vars[joined_at_key] = now
        if pid not in pool:
            pool.append(pid)
            pool.sort()
            self.session.vars[pool_key] = pool
            self.session.vars[pool_version_key] = int(self.session.vars.get(pool_version_key, 0)) + 1

        # Periodic stale-entry cleanup (infrequent, for long high-traffic sessions).
        pool_version = int(self.session.vars.get(pool_version_key, 0))
        if pool and (pool_version % self.POOL_CLEANUP_EVERY_UPDATES == 0):
            participants = self.session.get_participants()
            pmap = {p.id_in_session: p for p in participants}
            cleaned = []
            for sid in pool:
                pp = pmap.get(sid)
                if not pp:
                    continue
                if pp.vars.get(can_proceed_key) or pp.vars.get('quit_to_prolific_results', False):
                    continue
                if not pp.vars.get(waiting_key):
                    continue
                cleaned.append(sid)
            cleaned = sorted(set(cleaned))
            if cleaned != pool:
                pool = cleaned
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = pool_version + 1

            # Keep session vars compact: remove obsolete claim keys for this part.
            active_trio_claim = None
            if len(pool) >= group_size:
                active_ids = pool[:group_size]
                active_trio_claim = f"{claim_prefix}{'_'.join(map(str, active_ids))}"
            stale_claim_keys = [
                k for k in list(self.session.vars.keys())
                if isinstance(k, str) and k.startswith(claim_prefix) and k != active_trio_claim
            ]
            for k in stale_claim_keys:
                self.session.vars.pop(k, None)

        if len(pool) < group_size:
            return

        # Deterministic trio claim: smallest IDs first.
        first_ids = pool[:group_size]
        claim_key = f"results_group_claim_part_{current_part}_{'_'.join(map(str, first_ids))}"
        if self.session.vars.get(claim_key):
            return
        self.session.vars[claim_key] = True

        payoffs_ready = False
        try:
            participants = self.session.get_participants()
            pmap = {p.id_in_session: p for p in participants}
            trio = [pmap.get(i) for i in first_ids]
            if any(p is None for p in trio):
                # Drop stale IDs only when encountered.
                pool = [x for x in pool if x in pmap]
                self.session.vars[pool_key] = pool
                return
            if any(p.vars.get(can_proceed_key) or p.vars.get('quit_to_prolific_results', False) for p in trio):
                pool = [x for x in pool if x not in first_ids]
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = int(self.session.vars.get(pool_version_key, 0)) + 1
                return

            batch_id = first_ids[0]
            part_start_round = (current_part - 1) * Constants.rounds_per_part + 1
            round_ss = self.subsession.in_round(part_start_round)
            batch_players = [pl for pl in round_ss.get_players() if pl.participant.id_in_session in first_ids]
            batch_players = sorted(batch_players, key=lambda pl: first_ids.index(pl.participant.id_in_session))
            if len(batch_players) != group_size:
                return

            self.session.vars[f'matching_group_members_part_{current_part}_{batch_id}'] = list(first_ids)
            for i, pl in enumerate(batch_players):
                pl.participant.vars['matching_group_id'] = batch_id
                pl.participant.vars['matching_group_position'] = i + 1

            payoffs_ready = bool(am.run_payoffs_for_matching_group(self.subsession, batch_id))
            if not payoffs_ready:
                return

            for p in trio:
                p.vars[f'can_proceed_to_results_part_{current_part}'] = True
                p.vars[ready_at_key] = now
                p.vars[waiting_key] = False
            self.session.vars[pool_key] = [x for x in pool if x not in first_ids]
            self.session.vars[pool_version_key] = int(self.session.vars.get(pool_version_key, 0)) + 1
            # Claim no longer needed after success.
            self.session.vars.pop(claim_key, None)
        finally:
            # If payoffs not ready yet, allow a future refresh to retry this trio claim.
            if not payoffs_ready:
                self.session.vars.pop(claim_key, None)

    def vars_for_template(self):
        Constants = app_models(self.player).Constants
        current_part = Constants.get_part(self.round_number)
        pool_key = f'results_pool_part_{current_part}'
        group_size = self.FIXED_RESULTS_GROUP_SIZE
        first_join_key = f'results_first_join_part_{current_part}'
        joined_at_key = f'results_wait_joined_at_part_{current_part}'
        timeout_seconds = 300  # 5 minutes: show wait-or-quit only after this participant has waited this long
        now = time.time()
        if pool_key not in self.session.vars:
            self.session.vars[pool_key] = []
        if first_join_key not in self.session.vars:
            self.session.vars[first_join_key] = now
        n_in_pool = len(self.session.vars.get(pool_key, []))
        # Show wait-or-quit only if pool still has < 3 AND this participant has personally waited >= 5 minutes.
        joined_at = self.participant.vars.get(joined_at_key, now)
        show_wait_or_quit_results = (n_in_pool < group_size) and ((now - joined_at) >= timeout_seconds)
        path = getattr(self.request, 'path', None) or getattr(self.request, 'path_info', '') or ''
        build_uri = getattr(self.request, 'build_absolute_uri', None)
        base_url = (build_uri(path) if build_uri and path else path) or ''
        wait_more_token = str(int(now * 1000))
        wait_more_url = (
            base_url
            + ('&' if '?' in base_url else '?')
            + f'wait_more=1&wait_more_token={wait_more_token}'
        )
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
        Constants = app_models(player).Constants
        current_part = Constants.get_part(player.round_number)
        pool_key = f'results_pool_part_{current_part}'
        pool = player.session.vars.get(pool_key, [])
        group_size = BatchWaitForGroup.FIXED_RESULTS_GROUP_SIZE
        payload = {'n_arrived': len(pool), 'n_total': group_size}
        return {player.id_in_group: payload}

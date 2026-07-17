import time

from otree.api import *

from shared.export_integrity import record_data_errors_for_participants
from shared.session_part_lock import normalize_pool_ids, session_part_lock, try_session_part_lock
from shared.tg_player_lookup import participants_by_id_in_session, players_at_round_for_member_ids

from .model_bridge import app_models
from .page_helpers import BATCH_WAIT_MIN_SECONDS, _has_left_lobby_for_part, is_excluded_from_study


class BatchWaitForGroup(WaitPage):
    """
    End of each part (rounds 10, 20, 30): join a shared pool, form trios of 3,
    run payoffs, then proceed to Results.

    Large-session freeze rule: most wait-page polls must NOT touch session.vars
    (oTree marks Session dirty on every vars access and rewrites the pickle).
    Already-waiting participants only retry formation every few seconds.
    """

    @property
    def template_name(self):
        return "global/BatchWaitForGroup.html"

    FIXED_RESULTS_GROUP_SIZE = 3
    # How often an already-waiting participant may try lock / formation again.
    FORMATION_RETRY_SECONDS = 8.0

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        Constants = app_models(self.player).Constants
        r = self.round_number
        if r % Constants.rounds_per_part != 0:
            return False
        current_part = Constants.get_part(r)
        if not _has_left_lobby_for_part(self.participant, current_part):
            return False
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        return not self.participant.vars.get(can_proceed_key, False)

    def get(self):
        Constants = app_models(self.player).Constants
        _params = getattr(self.request, "GET", None) or getattr(self.request, "query_params", None)
        current_part = Constants.get_part(self.round_number)
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        ready_at_key = f"results_ready_at_part_{current_part}"
        pool_key = f"results_pool_part_{current_part}"
        pool_version_key = f"results_pool_version_part_{current_part}"
        joined_at_key = f"results_wait_joined_at_part_{current_part}"
        wait_more_token_key = f"results_wait_more_token_part_{current_part}"

        if _params:
            if _params.get("quit"):
                with session_part_lock(self.session, current_part):
                    pool = normalize_pool_ids(self.session.vars.get(pool_key, []))
                    pool = [sid for sid in pool if sid != self.participant.id_in_session]
                    self.session.vars[pool_key] = pool
                    self.session.vars[pool_version_key] = int(self.session.vars.get(pool_version_key, 0)) + 1
                self.participant.vars["quit_to_prolific_results"] = True
                self.participant.vars[f"results_waiting_part_{current_part}"] = False
                return self._response_when_ready()
            if _params.get("wait_more"):
                wait_more_token = _params.get("wait_more_token") or _params.get("t") or ""
                if wait_more_token:
                    if self.participant.vars.get(wait_more_token_key) != wait_more_token:
                        self.participant.vars[joined_at_key] = time.time()
                        self.participant.vars[wait_more_token_key] = wait_more_token
                else:
                    if self.participant.vars.get(wait_more_token_key) != "__legacy__":
                        self.participant.vars[joined_at_key] = time.time()
                        self.participant.vars[wait_more_token_key] = "__legacy__"

        if self.participant.vars.get(can_proceed_key):
            return self._maybe_redirect_when_ready(can_proceed_key, ready_at_key)

        self._update_results_pool_and_maybe_group()
        if self.participant.vars.get(can_proceed_key):
            return self._maybe_redirect_when_ready(can_proceed_key, ready_at_key)
        return self._get_wait_page()

    def post(self):
        Constants = app_models(self.player).Constants
        current_part = Constants.get_part(self.round_number)
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        ready_at_key = f"results_ready_at_part_{current_part}"

        if self.participant.vars.get(can_proceed_key):
            return self._maybe_redirect_when_ready(can_proceed_key, ready_at_key)

        self._update_results_pool_and_maybe_group()
        if self.participant.vars.get(can_proceed_key):
            return self._maybe_redirect_when_ready(can_proceed_key, ready_at_key)
        return self._get_wait_page()

    def _maybe_redirect_when_ready(self, can_proceed_key, ready_at_key):
        now = time.time()
        ready_at = self.participant.vars.get(ready_at_key)
        if ready_at is None:
            self.participant.vars[ready_at_key] = now
            return self._get_wait_page()
        if now - float(ready_at) < BATCH_WAIT_MIN_SECONDS:
            return self._get_wait_page()
        return self._response_when_ready()

    def _update_results_pool_and_maybe_group(self):
        """Join once; later polls are cheap unless formation is due."""
        am = app_models(self.player)
        Constants = am.Constants
        current_part = Constants.get_part(self.round_number)
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        waiting_key = f"results_waiting_part_{current_part}"
        ready_at_key = f"results_ready_at_part_{current_part}"
        pool_key = f"results_pool_part_{current_part}"
        pool_version_key = f"results_pool_version_part_{current_part}"
        first_join_key = f"results_first_join_part_{current_part}"
        joined_at_key = f"results_wait_joined_at_part_{current_part}"
        attempt_key = f"results_form_attempt_at_part_{current_part}"
        claim_prefix = f"results_group_claim_part_{current_part}_"
        group_size = self.FIXED_RESULTS_GROUP_SIZE
        pid = self.participant.id_in_session
        now = time.time()

        # Cheap idle path: already in the pool — do not touch session.vars.
        if self.participant.vars.get(waiting_key) and not self.participant.vars.get(can_proceed_key):
            last_attempt = float(self.participant.vars.get(attempt_key, 0) or 0)
            if now - last_attempt < self.FORMATION_RETRY_SECONDS:
                return
            self.participant.vars[attempt_key] = now
            # Fall through: occasional formation attempt only.

        claimed = None

        with try_session_part_lock(self.session, current_part) as acquired:
            if not acquired:
                if not self.participant.vars.get(waiting_key):
                    self.participant.vars[waiting_key] = True
                    self.participant.vars[joined_at_key] = now
                return

            pool = normalize_pool_ids(self.session.vars.get(pool_key, []))
            if first_join_key not in self.session.vars:
                self.session.vars[first_join_key] = now

            if self.participant.vars.get(can_proceed_key) or self.participant.vars.get(
                "quit_to_prolific_results", False
            ):
                self.participant.vars[waiting_key] = False
                if pid in pool:
                    pool = [x for x in pool if x != pid]
                    self.session.vars[pool_key] = pool
                    self.session.vars[pool_version_key] = int(
                        self.session.vars.get(pool_version_key, 0)
                    ) + 1
                return

            if not self.participant.vars.get(waiting_key):
                self.participant.vars[waiting_key] = True
                self.participant.vars[joined_at_key] = now
            if pid not in pool:
                pool = normalize_pool_ids(pool + [pid])
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = int(
                    self.session.vars.get(pool_version_key, 0)
                ) + 1
            else:
                # Already listed — do not rewrite session.vars unless forming.
                pass

            # Cache displayed pool size on participant (avoids session.vars in template).
            self.participant.vars[f"results_pool_seen_n_part_{current_part}"] = len(pool)

            if len(pool) < group_size:
                return

            first_ids = pool[:group_size]
            claim_key = f"{claim_prefix}{'_'.join(map(str, first_ids))}"
            if self.session.vars.get(claim_key):
                return

            pmap = participants_by_id_in_session(self.session.id, first_ids)
            trio = [pmap.get(i) for i in first_ids]
            if any(p is None for p in trio):
                pool = [x for x in pool if x in pmap]
                self.session.vars[pool_key] = pool
                return
            if any(
                p.vars.get(can_proceed_key) or p.vars.get("quit_to_prolific_results", False)
                for p in trio
            ):
                pool = [x for x in pool if x not in first_ids]
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = int(
                    self.session.vars.get(pool_version_key, 0)
                ) + 1
                return

            batch_id = first_ids[0]
            part_start_round = (current_part - 1) * Constants.rounds_per_part + 1
            batch_players = players_at_round_for_member_ids(
                self.session.id, first_ids, part_start_round
            )
            if batch_players is None or len(batch_players) != group_size:
                record_data_errors_for_participants(
                    trio,
                    "GROUP_FORMATION_FAILED",
                    f"part={current_part} expected={group_size}",
                )
                return

            self.session.vars[claim_key] = True
            self.session.vars[f"matching_group_members_part_{current_part}_{batch_id}"] = list(
                first_ids
            )
            for i, pl in enumerate(batch_players):
                pl.participant.vars["matching_group_id"] = batch_id
                pl.participant.vars["matching_group_position"] = i + 1
            claimed = (first_ids, batch_id, claim_key, trio)

        if not claimed:
            return

        first_ids, batch_id, claim_key, trio = claimed
        payoffs_ready = False
        try:
            payoffs_ready = bool(am.run_payoffs_for_matching_group(self.subsession, batch_id))
            if not payoffs_ready:
                # Log once per batch — retries are expected until choices are complete.
                log_key = f"payoffs_not_ready_logged_part_{current_part}_{batch_id}"
                if not self.session.vars.get(log_key):
                    record_data_errors_for_participants(
                        trio,
                        "PAYOFFS_OR_RESULTS_NOT_READY",
                        f"part={current_part} batch_id={batch_id}",
                    )
                    self.session.vars[log_key] = True
                return

            # Durable export ids only after payoffs succeed (avoid polluting failed claims).
            for p in trio:
                p.vars[can_proceed_key] = True
                p.vars[ready_at_key] = now
                p.vars[waiting_key] = False
                p.vars[f"group_part_{current_part}"] = batch_id
                pos = p.vars.get("matching_group_position")
                if pos is not None:
                    p.vars[f"group_position_part_{current_part}"] = pos

            with session_part_lock(self.session, current_part):
                pool = normalize_pool_ids(self.session.vars.get(pool_key, []))
                pool = [x for x in pool if x not in first_ids]
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = int(
                    self.session.vars.get(pool_version_key, 0)
                ) + 1
                self.session.vars.pop(claim_key, None)
                self.session.vars.pop(
                    f"payoffs_not_ready_logged_part_{current_part}_{batch_id}", None
                )
        finally:
            if not payoffs_ready:
                with try_session_part_lock(self.session, current_part) as acquired:
                    if acquired:
                        self.session.vars.pop(claim_key, None)

    def vars_for_template(self):
        """Avoid session.vars here — every access dirties the Session row in oTree."""
        Constants = app_models(self.player).Constants
        current_part = Constants.get_part(self.round_number)
        group_size = self.FIXED_RESULTS_GROUP_SIZE
        joined_at_key = f"results_wait_joined_at_part_{current_part}"
        timeout_seconds = 300
        now = time.time()
        n_in_pool = int(self.participant.vars.get(f"results_pool_seen_n_part_{current_part}", 0) or 0)
        joined_at = self.participant.vars.get(joined_at_key, now)
        show_wait_or_quit_results = (now - joined_at) >= timeout_seconds
        path = getattr(self.request, "path", None) or getattr(self.request, "path_info", "") or ""
        build_uri = getattr(self.request, "build_absolute_uri", None)
        base_url = (build_uri(path) if build_uri and path else path) or ""
        wait_more_token = str(int(now * 1000))
        wait_more_url = (
            base_url
            + ("&" if "?" in base_url else "?")
            + f"wait_more=1&wait_more_token={wait_more_token}"
        )
        quit_url = base_url + ("&" if "?" in base_url else "?") + "quit=1"
        return {
            "n_arrived": n_in_pool,
            "batch_size": group_size,
            "show_wait_or_quit_results": show_wait_or_quit_results,
            "wait_more_url": wait_more_url,
            "quit_to_prolific_url": quit_url,
        }

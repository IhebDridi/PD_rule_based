import time

from otree.api import *
from otree.models import Participant

from shared.export_integrity import record_data_errors_for_participants
from shared.session_part_lock import normalize_pool_ids, session_part_lock, try_session_part_lock

from .model_bridge import app_models
from .page_helpers import BATCH_WAIT_MIN_SECONDS, _has_left_lobby_for_part


class BatchWaitForGroup(WaitPage):
    """
    End of each part (rounds 10, 20, 30): join a shared pool, form trios of 3,
    run payoffs, then proceed to Results.

    Critical for large sessions: pool mutations use a *non-blocking* try-lock and
    payoff computation runs *outside* that lock. Otherwise a busy Results wait
    freezes unrelated pages (InformedConsent → MainInstructions, etc.) via
    worker starvation and Session-row contention.
    """

    @property
    def template_name(self):
        return "global/BatchWaitForGroup.html"

    POOL_CLEANUP_EVERY_UPDATES = 75
    FIXED_RESULTS_GROUP_SIZE = 3

    def is_displayed(self):
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

        if _params:
            if _params.get("quit"):
                # Short blocking lock ok: rare user action, no payoffs.
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

        # Ready participants must not re-enter formation / session locks.
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

    def _participants_by_ids(self, ids):
        """Load only the needed participants (never scan the whole 300-person session)."""
        if not ids:
            return {}
        from otree.database import db

        wanted = [int(i) for i in ids]
        rows = (
            db.query(Participant)
            .filter(
                Participant.session_id == self.session.id,
                Participant.id_in_session.in_(wanted),
            )
            .all()
        )
        return {p.id_in_session: p for p in rows}

    def _players_at_round_for_ids(self, part_start_round, first_ids):
        """Resolve Player rows for the trio without scanning every session player."""
        pmap = self._participants_by_ids(first_ids)
        out = []
        for pid in first_ids:
            part = pmap.get(pid)
            if part is None:
                return None
            players = [
                pl for pl in part.get_players() if getattr(pl, "round_number", None) == part_start_round
            ]
            if len(players) != 1:
                return None
            out.append(players[0])
        return out

    def _update_results_pool_and_maybe_group(self):
        """Join pool under try-lock; run at most one trio's payoffs outside the lock."""
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
        claim_prefix = f"results_group_claim_part_{current_part}_"
        group_size = self.FIXED_RESULTS_GROUP_SIZE
        pid = self.participant.id_in_session
        now = time.time()

        claimed = None  # (first_ids, batch_id, claim_key)

        with try_session_part_lock(self.session, current_part) as acquired:
            if not acquired:
                # Another request is mutating the pool / claiming a trio.
                # Return immediately so this worker stays free for other pages.
                if not self.participant.vars.get(waiting_key):
                    self.participant.vars[waiting_key] = True
                    self.participant.vars[joined_at_key] = now
                return

            pool = normalize_pool_ids(self.session.vars.get(pool_key, []))
            self.session.vars[pool_key] = pool
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
                pool.append(pid)
                pool.sort()
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = int(
                    self.session.vars.get(pool_version_key, 0)
                ) + 1

            pool_version = int(self.session.vars.get(pool_version_key, 0))
            if pool and (pool_version % self.POOL_CLEANUP_EVERY_UPDATES == 0):
                pool = self._cleanup_results_pool_light(
                    pool, pool_key, pool_version_key, pool_version, claim_prefix, group_size
                )

            if len(pool) < group_size:
                return

            first_ids = pool[:group_size]
            claim_key = f"{claim_prefix}{'_'.join(map(str, first_ids))}"
            if self.session.vars.get(claim_key):
                return

            # Claim under lock only — no payoffs here.
            pmap = self._participants_by_ids(first_ids)
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
            batch_players = self._players_at_round_for_ids(part_start_round, first_ids)
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

        # ---- Payoffs OUTSIDE the lock (must not block other participants) ----
        if not claimed:
            return

        first_ids, batch_id, claim_key, trio = claimed
        payoffs_ready = False
        try:
            payoffs_ready = bool(am.run_payoffs_for_matching_group(self.subsession, batch_id))
            if not payoffs_ready:
                record_data_errors_for_participants(
                    trio,
                    "PAYOFFS_OR_RESULTS_NOT_READY",
                    f"part={current_part} batch_id={batch_id}",
                )
                return

            for p in trio:
                p.vars[can_proceed_key] = True
                p.vars[ready_at_key] = now
                p.vars[waiting_key] = False

            # Short blocking cleanup after success — must clear claim so later trios can form.
            with session_part_lock(self.session, current_part):
                pool = normalize_pool_ids(self.session.vars.get(pool_key, []))
                pool = [x for x in pool if x not in first_ids]
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = int(
                    self.session.vars.get(pool_version_key, 0)
                ) + 1
                self.session.vars.pop(claim_key, None)
        finally:
            if not payoffs_ready:
                with try_session_part_lock(self.session, current_part) as acquired:
                    if acquired:
                        self.session.vars.pop(claim_key, None)

    def _cleanup_results_pool_light(
        self, pool, pool_key, pool_version_key, pool_version, claim_prefix, group_size
    ):
        """Drop claim keys only — avoid scanning 300 participants on the hot path."""
        active_trio_claim = None
        if len(pool) >= group_size:
            active_ids = pool[:group_size]
            active_trio_claim = f"{claim_prefix}{'_'.join(map(str, active_ids))}"
        stale_claim_keys = [
            k
            for k in list(self.session.vars.keys())
            if isinstance(k, str) and k.startswith(claim_prefix) and k != active_trio_claim
        ]
        for k in stale_claim_keys:
            self.session.vars.pop(k, None)
        self.session.vars[pool_key] = pool
        self.session.vars[pool_version_key] = pool_version
        return pool

    def vars_for_template(self):
        Constants = app_models(self.player).Constants
        current_part = Constants.get_part(self.round_number)
        pool_key = f"results_pool_part_{current_part}"
        group_size = self.FIXED_RESULTS_GROUP_SIZE
        joined_at_key = f"results_wait_joined_at_part_{current_part}"
        timeout_seconds = 300
        now = time.time()
        # Read-only: do not create session.vars keys here (avoids dirty Session row).
        pool = self.session.vars.get(pool_key, [])
        n_in_pool = len(pool) if isinstance(pool, list) else 0
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

    @staticmethod
    def live_method(player, data):
        if not data or data.get("type") != "get_count":
            return
        Constants = app_models(player).Constants
        current_part = Constants.get_part(player.round_number)
        pool_key = f"results_pool_part_{current_part}"
        pool = player.session.vars.get(pool_key, [])
        group_size = BatchWaitForGroup.FIXED_RESULTS_GROUP_SIZE
        payload = {"n_arrived": len(pool) if isinstance(pool, list) else 0, "n_total": group_size}
        return {player.id_in_group: payload}

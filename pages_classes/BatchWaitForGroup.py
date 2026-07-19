import time

from otree.api import *
from starlette.responses import JSONResponse

from shared.export_integrity import record_data_errors_for_participants
from shared.matching_batch import clear_matching_batch_cache
from shared.session_part_lock import (
    normalize_pool_ids,
    persist_session_state,
    refresh_session_state,
    session_part_lock,
    try_session_part_lock,
)
from shared.stale_session_flag import DEFAULT_STALE_TTL_SECONDS, flag_is_fresh, touch_timed_flag
from shared.tg_player_lookup import participants_by_id_in_session, players_at_round_for_member_ids

from .model_bridge import app_models, is_tg_app
from .page_helpers import BATCH_WAIT_MIN_SECONDS, _has_left_lobby_for_part, is_excluded_from_study


class BatchWaitForGroup(WaitPage):
    """
    End of each part (rounds 10, 20, 30): join a shared pool, form trios of 3,
    run payoffs, then proceed to Results.

    Large-session freeze rule: most wait-page polls must NOT touch session.vars
    (oTree marks Session dirty on every vars access and rewrites the pickle).
    Already-waiting participants only retry formation every few seconds.

    Browser wakeup uses ?status=1 (read-only participant.vars JSON). Formation and
    session.vars writes happen only on full page loads / rare form_due reloads.
    """

    @property
    def template_name(self):
        return "global/BatchWaitForGroup.html"

    FIXED_RESULTS_GROUP_SIZE = 3
    # How often an already-waiting participant may try lock / formation again.
    FORMATION_RETRY_SECONDS = 8.0
    QUIT_PROMPT_SECONDS = 300

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

    def _batch_wait_status_payload(self):
        """
        Read-only wakeup payload. Must not write participant.vars or session.vars.
        Formation stays on full GET (3rd joiner / form_due reload).
        """
        # Multi-worker: peer finalize may have written can_proceed on another worker.
        # Reload this Participant row so status sees the fresh vars without a full page load.
        try:
            from otree.database import db

            db._db.refresh(self.participant)
        except Exception:
            pass

        Constants = app_models(self.player).Constants
        current_part = Constants.get_part(self.round_number)
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        waiting_key = f"results_waiting_part_{current_part}"
        ready_at_key = f"results_ready_at_part_{current_part}"
        attempt_key = f"results_form_attempt_at_part_{current_part}"
        joined_at_key = f"results_wait_joined_at_part_{current_part}"
        seen_n_key = f"results_pool_seen_n_part_{current_part}"

        pvars = self.participant.vars
        ready = bool(pvars.get(can_proceed_key)) or bool(pvars.get("quit_to_prolific_results"))
        waiting = bool(pvars.get(waiting_key))
        last_attempt = pvars.get(attempt_key)
        now = time.time()
        # Only nudge a full reload after a real attempt timestamp exists (set on join).
        form_due = False
        if waiting and not ready and last_attempt is not None:
            form_due = (now - float(last_attempt)) >= self.FORMATION_RETRY_SECONDS

        joined_at = pvars.get(joined_at_key)
        show_quit = False
        if joined_at is not None:
            show_quit = (now - float(joined_at)) >= self.QUIT_PROMPT_SECONDS

        # Respect BATCH_WAIT_MIN_SECONDS before telling the client to advance.
        advance = ready
        if ready and not pvars.get("quit_to_prolific_results"):
            ready_at = pvars.get(ready_at_key)
            if ready_at is None or (now - float(ready_at)) < BATCH_WAIT_MIN_SECONDS:
                advance = False
                # Matched but not yet allowed to leave: force a full GET so ready_at
                # is planted / min-wait is evaluated server-side (status is read-only).
                # Without this, a fresh form_attempt timestamp can leave the client
                # polling forever with ready=false and form_due=false until manual refresh.
                form_due = True

        return {
            "ready": bool(advance),
            "matched": bool(pvars.get(can_proceed_key)),
            "form_due": bool(form_due),
            "show_quit": bool(show_quit),
            "n_arrived": int(pvars.get(seen_n_key, 0) or 0),
            "batch_size": self.FIXED_RESULTS_GROUP_SIZE,
        }

    def _batch_wait_status_response(self):
        return JSONResponse(
            self._batch_wait_status_payload(),
            headers={"Cache-Control": "no-store"},
        )

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

        # Lightweight browser poll: no formation, no session.vars.
        if _params and _params.get("status"):
            return self._batch_wait_status_response()

        if _params:
            if _params.get("quit"):
                self._quit_from_results_pool(current_part, pool_key, pool_version_key)
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

    def _quit_from_results_pool(self, current_part, pool_key, pool_version_key):
        """
        Remove this participant from the wait pool.

        If they are inside a *fresh* claim, do NOT abort the claim or requeue
        peers — payoffs may still be writing. Rematching peers mid-payoff polluted
        GroupPart. Claim finishes normally; the quitter simply leaves.
        """
        pid = self.participant.id_in_session
        can_proceed_key = f"can_proceed_to_results_part_{current_part}"
        now = time.time()
        claim_prefix = f"results_group_claim_part_{current_part}_"

        with session_part_lock(self.session, current_part):
            pool = normalize_pool_ids(self.session.vars.get(pool_key, []))
            live_gid = self.participant.vars.get("matching_group_id")
            in_fresh_claim = False
            if (
                live_gid is not None
                and int(live_gid) >= 0
                and not self.participant.vars.get(can_proceed_key)
            ):
                members_key = f"matching_group_members_part_{current_part}_{int(live_gid)}"
                member_ids = self.session.vars.get(members_key)
                if (
                    isinstance(member_ids, (list, tuple))
                    and len(member_ids) >= 3
                    and pid in member_ids
                ):
                    claim_key = f"{claim_prefix}{'_'.join(map(str, list(member_ids)[:3]))}"
                    claim_val = self.session.vars.get(claim_key)
                    if claim_val is not None and flag_is_fresh(
                        claim_val, DEFAULT_STALE_TTL_SECONDS, now=now
                    ):
                        in_fresh_claim = True

            # Always keep quitter out of the pool. Never touch an active claim.
            pool = [sid for sid in pool if sid != pid]
            self.session.vars[pool_key] = pool
            self.session.vars[pool_version_key] = int(
                self.session.vars.get(pool_version_key, 0)
            ) + 1
            if in_fresh_claim:
                clear_matching_batch_cache()
            # Durable pool update before unlock (same rationale as claim flush).
            persist_session_state(self.session)

    def _clear_provisional_claim_ids(self, trio, batch_id, current_part, can_proceed_key):
        """Clear live provisional ids only — never durable ids from a finished part."""
        for p in trio:
            if p is None:
                continue
            if p.vars.get(can_proceed_key):
                continue
            if p.vars.get("matching_group_id") == batch_id:
                p.vars["matching_group_id"] = -1
            p.vars.pop("matching_group_position", None)
            if p.vars.get(f"group_part_{current_part}") == batch_id:
                p.vars.pop(f"group_part_{current_part}", None)
                p.vars.pop(f"group_position_part_{current_part}", None)

    def _rotate_failed_trio_under_lock(
        self,
        *,
        current_part,
        can_proceed_key,
        pool_key,
        pool_version_key,
        claim_key,
        members_key,
        first_ids,
    ):
        """Soft-fail: drop claim/members; requeue only still-waiting non-quitters."""
        self.session.vars.pop(claim_key, None)
        self.session.vars.pop(members_key, None)
        pool = normalize_pool_ids(self.session.vars.get(pool_key, []))
        pmap = participants_by_id_in_session(self.session.id, first_ids)
        requeue = []
        for sid in first_ids:
            p = pmap.get(sid)
            if p is None:
                continue
            if p.vars.get("quit_to_prolific_results"):
                continue
            if p.vars.get(can_proceed_key):
                continue
            requeue.append(sid)
        rest = [x for x in pool if x not in first_ids]
        rotated = normalize_pool_ids(rest + requeue)
        if rotated != pool:
            self.session.vars[pool_key] = rotated
            self.session.vars[pool_version_key] = int(
                self.session.vars.get(pool_version_key, 0)
            ) + 1
        clear_matching_batch_cache()

    def _trio_has_part_payoff_progress(self, first_ids, current_part, Constants) -> bool:
        """True if any trio member already has roles written for this part (TTL reclaim)."""
        part_start = (current_part - 1) * Constants.rounds_per_part + 1
        part_end = current_part * Constants.rounds_per_part
        batch_players = players_at_round_for_member_ids(
            self.session.id, first_ids, part_start
        )
        if not batch_players:
            return False
        for p0 in batch_players:
            for r in range(part_start, part_end + 1):
                role = p0.in_round(r).field_maybe_none("role_assigned")
                if role in ("first", "second"):
                    return True
        return False

    def _finalize_successful_claim(
        self,
        *,
        am,
        current_part,
        can_proceed_key,
        waiting_key,
        ready_at_key,
        pool_key,
        pool_version_key,
        claim_key,
        first_ids,
        batch_id,
        trio,
        now,
    ):
        """Durable GroupPart only after payoffs succeeded — then release claim/pool."""
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
            clear_matching_batch_cache()
            persist_session_state(self.session)

    def _run_claimed_payoffs(
        self,
        *,
        am,
        current_part,
        can_proceed_key,
        waiting_key,
        ready_at_key,
        pool_key,
        pool_version_key,
        first_ids,
        batch_id,
        claim_key,
        trio,
        now,
    ):
        """
        Run payoffs outside the formation lock.

        Status handling (no pollution):
          True — durable GroupPart + release claim
          "in_progress" — leave claim+provisional alone (peer is writing)
          False / None — under lock: finalize if peer finished, leave if peer
            writing, else clear provisional + soft-fail rotate
        """
        members_key = f"matching_group_members_part_{current_part}_{batch_id}"
        # Heartbeat the claim so a long payoff run is not treated as abandoned.
        touch_timed_flag(self.session.vars, claim_key)
        status = am.run_payoffs_for_matching_group(self.subsession, batch_id)
        touch_timed_flag(self.session.vars, claim_key)

        if status is True:
            self._finalize_successful_claim(
                am=am,
                current_part=current_part,
                can_proceed_key=can_proceed_key,
                waiting_key=waiting_key,
                ready_at_key=ready_at_key,
                pool_key=pool_key,
                pool_version_key=pool_version_key,
                claim_key=claim_key,
                first_ids=first_ids,
                batch_id=batch_id,
                trio=trio,
                now=now,
            )
            return

        if status == "in_progress":
            # Peer still computing — do NOT rotate or clear provisional.
            return

        # False / None: revalidate under lock so we never tear down a live or finished writer.
        run_key = f"payoffs_run_matching_group_{batch_id}_part_{current_part}"
        in_progress_key = f"{run_key}_in_progress"
        with session_part_lock(self.session, current_part):
            now_locked = time.time()
            peer_done = bool(self.session.vars.get(run_key)) or any(
                p is not None and p.vars.get(can_proceed_key) for p in trio
            )
            peer_writing = flag_is_fresh(
                self.session.vars.get(in_progress_key),
                DEFAULT_STALE_TTL_SECONDS,
                now=now_locked,
            )
            if peer_done:
                self._finalize_successful_claim(
                    am=am,
                    current_part=current_part,
                    can_proceed_key=can_proceed_key,
                    waiting_key=waiting_key,
                    ready_at_key=ready_at_key,
                    pool_key=pool_key,
                    pool_version_key=pool_version_key,
                    claim_key=claim_key,
                    first_ids=first_ids,
                    batch_id=batch_id,
                    trio=trio,
                    now=now_locked,
                )
                return
            if peer_writing:
                # Another request holds the payoff lease — leave claim alone.
                return

            if status is False:
                # Dedupe on a participant row (under part lock) — avoid Session.vars
                # dirtying for a log-only flag.
                log_key = f"payoffs_not_ready_logged_part_{current_part}_{batch_id}"
                anchor = next((p for p in trio if p is not None), None)
                if anchor is not None and not anchor.vars.get(log_key):
                    record_data_errors_for_participants(
                        trio,
                        "PAYOFFS_OR_RESULTS_NOT_READY",
                        f"part={current_part} batch_id={batch_id}",
                    )
                    anchor.vars[log_key] = True

            self._clear_provisional_claim_ids(trio, batch_id, current_part, can_proceed_key)
            self._rotate_failed_trio_under_lock(
                current_part=current_part,
                can_proceed_key=can_proceed_key,
                pool_key=pool_key,
                pool_version_key=pool_version_key,
                claim_key=claim_key,
                members_key=members_key,
                first_ids=first_ids,
            )
            persist_session_state(self.session)

    def _try_continue_mid_claim_payoffs(
        self,
        *,
        am,
        current_part,
        can_proceed_key,
        waiting_key,
        ready_at_key,
        pool_key,
        pool_version_key,
        claim_prefix,
        now,
    ):
        """
        If this participant is already in a fresh claim, retry payoffs without
        forming a new trio (prevents rejoin-while-claimed races).

        TG only: PD/SD/SH payoff runners lack an in_progress gate, so mid-claim
        retries there can double-write under concurrent GETs.
        """
        if not is_tg_app(self.player):
            return False
        if self.participant.vars.get(can_proceed_key):
            return False
        live_gid = self.participant.vars.get("matching_group_id")
        if live_gid is None or int(live_gid) < 0:
            return False
        # Cheap Session reload only (no part lock): mid-claim is rare vs status polls.
        # Avoids acting on a stale claim/members snapshot without slowing the wait path.
        refresh_session_state(self.session)
        batch_id = int(live_gid)
        members_key = f"matching_group_members_part_{current_part}_{batch_id}"
        member_ids = self.session.vars.get(members_key)
        if not isinstance(member_ids, (list, tuple)) or len(member_ids) < 3:
            return False
        first_ids = [int(x) for x in list(member_ids)[:3]]
        if self.participant.id_in_session not in first_ids:
            return False
        claim_key = f"{claim_prefix}{'_'.join(map(str, first_ids))}"
        claim_val = self.session.vars.get(claim_key)
        if claim_val is None or not flag_is_fresh(claim_val, DEFAULT_STALE_TTL_SECONDS, now=now):
            return False

        pmap = participants_by_id_in_session(self.session.id, first_ids)
        trio = [pmap.get(i) for i in first_ids]
        if any(p is None for p in trio):
            return False

        self._run_claimed_payoffs(
            am=am,
            current_part=current_part,
            can_proceed_key=can_proceed_key,
            waiting_key=waiting_key,
            ready_at_key=ready_at_key,
            pool_key=pool_key,
            pool_version_key=pool_version_key,
            first_ids=first_ids,
            batch_id=batch_id,
            claim_key=claim_key,
            trio=trio,
            now=now,
        )
        return True

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

        # Mid-claim: retry payoffs without touching the pool front.
        if self._try_continue_mid_claim_payoffs(
            am=am,
            current_part=current_part,
            can_proceed_key=can_proceed_key,
            waiting_key=waiting_key,
            ready_at_key=ready_at_key,
            pool_key=pool_key,
            pool_version_key=pool_version_key,
            claim_prefix=claim_prefix,
            now=now,
        ):
            return

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
                    self.participant.vars[attempt_key] = now
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
                self.participant.vars[attempt_key] = now
            if pid not in pool:
                pool = normalize_pool_ids(pool + [pid])
                self.session.vars[pool_key] = pool
                self.session.vars[pool_version_key] = int(
                    self.session.vars.get(pool_version_key, 0)
                ) + 1

            self.participant.vars[f"results_pool_seen_n_part_{current_part}"] = len(pool)

            if len(pool) < group_size:
                return

            first_ids = pool[:group_size]
            claim_key = f"{claim_prefix}{'_'.join(map(str, first_ids))}"
            claim_val = self.session.vars.get(claim_key)
            if claim_val is not None and flag_is_fresh(claim_val, DEFAULT_STALE_TTL_SECONDS, now=now):
                return
            if claim_val is not None:
                # Stale claim after a crash — never rematch while a writer lease is live.
                stale_batch_id = first_ids[0]
                run_key = f"payoffs_run_matching_group_{stale_batch_id}_part_{current_part}"
                in_progress_key = f"{run_key}_in_progress"
                if flag_is_fresh(
                    self.session.vars.get(in_progress_key),
                    DEFAULT_STALE_TTL_SECONDS,
                    now=now,
                ):
                    # Writer still heartbeating; claim age alone must not steal the trio.
                    return
                pmap_stale = participants_by_id_in_session(self.session.id, first_ids)
                any_done = bool(self.session.vars.get(run_key)) or any(
                    (pmap_stale.get(sid) is not None)
                    and pmap_stale[sid].vars.get(can_proceed_key)
                    for sid in first_ids
                )
                if not any_done and self._trio_has_part_payoff_progress(
                    first_ids, current_part, Constants
                ):
                    # Partial payoffs already landed (writer died mid-part) — never rematch.
                    any_done = True
                self.session.vars.pop(claim_key, None)
                if any_done:
                    # Payoffs already ran (or peers already durable) — finish
                    # can_proceed/GroupPart if the finalizer crashed; never rematch.
                    ready_at_key = f"results_ready_at_part_{current_part}"
                    waiting_key = f"results_waiting_part_{current_part}"
                    for sid in first_ids:
                        p = pmap_stale.get(sid)
                        if p is None:
                            continue
                        if not p.vars.get(can_proceed_key):
                            p.vars[can_proceed_key] = True
                            p.vars[ready_at_key] = now
                            p.vars[waiting_key] = False
                        if p.vars.get(f"group_part_{current_part}") is None:
                            p.vars[f"group_part_{current_part}"] = stale_batch_id
                            pos = p.vars.get("matching_group_position")
                            if pos is not None:
                                p.vars[f"group_position_part_{current_part}"] = pos
                    pool = [x for x in pool if x not in first_ids]
                    self.session.vars[pool_key] = pool
                    self.session.vars[pool_version_key] = int(
                        self.session.vars.get(pool_version_key, 0)
                    ) + 1
                    # Drop orphaned in_progress if the writer died after run_key.
                    self.session.vars.pop(f"{run_key}_in_progress", None)
                    clear_matching_batch_cache()
                    persist_session_state(self.session)
                    return

                self.session.vars.pop(
                    f"matching_group_members_part_{current_part}_{stale_batch_id}", None
                )
                self.session.vars.pop(f"{run_key}_in_progress", None)
                for sid in first_ids:
                    p = pmap_stale.get(sid)
                    if p is None:
                        continue
                    if p.vars.get(can_proceed_key):
                        continue
                    if p.vars.get("matching_group_id") == stale_batch_id:
                        p.vars["matching_group_id"] = -1
                    p.vars.pop("matching_group_position", None)
                    if p.vars.get(f"group_part_{current_part}") == stale_batch_id:
                        p.vars.pop(f"group_part_{current_part}", None)
                        p.vars.pop(f"group_position_part_{current_part}", None)
                clear_matching_batch_cache()
                persist_session_state(self.session)

            pmap = participants_by_id_in_session(self.session.id, first_ids)
            trio = [pmap.get(i) for i in first_ids]
            if any(p is None for p in trio):
                pool = [x for x in pool if x in pmap]
                self.session.vars[pool_key] = pool
                return
            drop_ids = [
                sid
                for sid, p in zip(first_ids, trio)
                if p.vars.get(can_proceed_key) or p.vars.get("quit_to_prolific_results", False)
            ]
            if drop_ids:
                # Only remove quitters / already-matched; leave healthy waiters in pool.
                pool = [x for x in pool if x not in drop_ids]
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

            # Claim + provisional members. Remove trio from pool under lock so quit /
            # other workers cannot re-form a overlapping front while payoffs run.
            self.session.vars[claim_key] = now
            self.session.vars[f"matching_group_members_part_{current_part}_{batch_id}"] = list(
                first_ids
            )
            for i, pl in enumerate(batch_players):
                pl.participant.vars["matching_group_id"] = batch_id
                pl.participant.vars["matching_group_position"] = i + 1
            pool = [x for x in pool if x not in first_ids]
            self.session.vars[pool_key] = pool
            self.session.vars[pool_version_key] = int(
                self.session.vars.get(pool_version_key, 0)
            ) + 1
            # Flush before unlock so peer workers refresh a durable claim, not a
            # process-local phantom (multi-worker double-claim).
            if not persist_session_state(self.session):
                # Commit failed — roll claim back in memory; do not run payoffs.
                self.session.vars.pop(claim_key, None)
                self.session.vars.pop(
                    f"matching_group_members_part_{current_part}_{batch_id}", None
                )
                for pl in batch_players:
                    if pl.participant.vars.get("matching_group_id") == batch_id:
                        pl.participant.vars["matching_group_id"] = -1
                    pl.participant.vars.pop("matching_group_position", None)
                pool = normalize_pool_ids(
                    list(self.session.vars.get(pool_key, [])) + list(first_ids)
                )
                self.session.vars[pool_key] = pool
                clear_matching_batch_cache()
                return
            claimed = (first_ids, batch_id, claim_key, trio)

        if not claimed:
            return

        first_ids, batch_id, claim_key, trio = claimed
        self._run_claimed_payoffs(
            am=am,
            current_part=current_part,
            can_proceed_key=can_proceed_key,
            waiting_key=waiting_key,
            ready_at_key=ready_at_key,
            pool_key=pool_key,
            pool_version_key=pool_version_key,
            first_ids=first_ids,
            batch_id=batch_id,
            claim_key=claim_key,
            trio=trio,
            now=now,
        )

    def vars_for_template(self):
        """Avoid session.vars here — every access dirties the Session row in oTree."""
        Constants = app_models(self.player).Constants
        current_part = Constants.get_part(self.round_number)
        group_size = self.FIXED_RESULTS_GROUP_SIZE
        joined_at_key = f"results_wait_joined_at_part_{current_part}"
        now = time.time()
        n_in_pool = int(self.participant.vars.get(f"results_pool_seen_n_part_{current_part}", 0) or 0)
        joined_at = self.participant.vars.get(joined_at_key, now)
        show_wait_or_quit_results = (now - float(joined_at)) >= self.QUIT_PROMPT_SECONDS
        path = getattr(self.request, "path", None) or getattr(self.request, "path_info", "") or ""
        build_uri = getattr(self.request, "build_absolute_uri", None)
        base_url = (build_uri(path) if build_uri and path else path) or ""
        # Strip prior query so status/quit/wait_more links stay clean.
        base_path = base_url.split("?", 1)[0]
        wait_more_token = str(int(now * 1000))
        wait_more_url = f"{base_path}?wait_more=1&wait_more_token={wait_more_token}"
        quit_url = f"{base_path}?quit=1"
        status_url = f"{base_path}?status=1"
        return {
            "n_arrived": n_in_pool,
            "batch_size": group_size,
            "show_wait_or_quit_results": show_wait_or_quit_results,
            "wait_more_url": wait_more_url,
            "quit_to_prolific_url": quit_url,
            "batch_wait_status_url": status_url,
            "batch_wait_advance_url": base_path,
        }

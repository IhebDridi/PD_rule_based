"""10-bot concurrent runner, timing, and integrity checks for TG v2 apps."""

from __future__ import annotations

import importlib
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from otree.database import db
from otree.models import Participant, Session

from pages_classes.page_helpers import BATCH_WAIT_MIN_SECONDS
from shared.tg_human_block_vars import (
    human_block_maps_complete,
    human_block_maps_from_vars,
)
from shared.tg_data_helpers import tg_round_has_partial_contingents

BOT_STRESS_NUM_PARTICIPANTS = 10
BOT_STRESS_MAX_IDLE_LOOPS = 120
BOT_STRESS_BATCH_WAIT_QUIT_LOOPS = 40


def record_bot_submit_timing(participant, page_name: str, elapsed_ms: float) -> None:
    timings = participant.vars.get("bot_stress_submit_ms")
    if not isinstance(timings, list):
        timings = []
    timings.append({"page": page_name, "ms": round(elapsed_ms, 2)})
    participant.vars["bot_stress_submit_ms"] = timings


def _batch_wait_url_with_query(url: str, query: Dict[str, str]) -> str:
    parsed = urlparse(url)
    merged = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    merged.update(query)
    return urlunparse(parsed._replace(query=urlencode(merged)))


def _participant_from_bot(bot) -> Optional[Participant]:
    code = getattr(bot, "participant_code", None)
    if not code:
        return None
    try:
        return Participant.objects_get(code=code)
    except Exception:
        return None


def _refresh_batch_wait(bot) -> None:
    url = getattr(bot, "url", None) or getattr(bot, "path", None) or ""
    if not url:
        return
    bot.response = bot.client.get(url, allow_redirects=True)
    bot.url = getattr(bot.response, "url", url)


def _quit_batch_wait(bot) -> None:
    url = getattr(bot, "url", None) or getattr(bot, "path", None) or ""
    if not url:
        return
    quit_url = _batch_wait_url_with_query(url, {"quit": "1"})
    bot.response = bot.client.get(quit_url, allow_redirects=True)
    bot.url = getattr(bot.response, "url", quit_url)


def _can_proceed_any_part(participant: Participant) -> bool:
    for part in (1, 2, 3):
        if participant.vars.get(f"can_proceed_to_results_part_{part}"):
            return True
    return bool(participant.vars.get("quit_to_prolific_results"))


def patch_tg_v2_bot_runner(*, delegation_first: bool) -> None:
    """Concurrent round-robin runner with BatchWait polling and submit timing."""
    from otree.bots.runner import SessionBotRunner

    def _play(self):
        self.open_start_urls()
        session_code = None
        if self.bots:
            first_bot = next(iter(self.bots.values()))
            session_code = getattr(first_bot, "session_code", None)

        loops_without_progress = 0
        batch_wait_loops: Dict[str, int] = {}

        while self.bots:
            if loops_without_progress > BOT_STRESS_MAX_IDLE_LOOPS:
                stuck = {pid: getattr(b, "url", "") for pid, b in self.bots.items()}
                raise AssertionError(f"Bots stuck after idle loops: {stuck}")

            playable_ids = list(self.bots.keys())
            progress_made = False

            for pid in playable_ids:
                bot = self.bots.get(pid)
                if not bot:
                    continue

                url = getattr(bot, "url", None) or ""
                participant = _participant_from_bot(bot)
                if participant and participant.vars.get("quit_to_prolific_results"):
                    self.bots.pop(pid, None)
                    progress_made = True
                    continue
                if "complete" in url.lower() or "prolific.com" in url.lower():
                    self.bots.pop(pid, None)
                    progress_made = True
                    continue

                if "BatchWaitForGroup" in url or bot.on_wait_page():
                    loops = batch_wait_loops.get(pid, 0) + 1
                    batch_wait_loops[pid] = loops
                    participant = _participant_from_bot(bot)
                    if participant and _can_proceed_any_part(participant):
                        time.sleep(max(0.0, BATCH_WAIT_MIN_SECONDS - 0.1))
                    if loops >= BOT_STRESS_BATCH_WAIT_QUIT_LOOPS and participant and not _can_proceed_any_part(participant):
                        _quit_batch_wait(bot)
                    else:
                        _refresh_batch_wait(bot)
                    progress_made = True
                    continue

                try:
                    submission = bot.get_next_submit()
                except StopIteration:
                    self.bots.pop(pid, None)
                    progress_made = True
                    continue
                except AssertionError as exc:
                    if _try_bot_catchup(bot, exc):
                        progress_made = True
                        continue
                    raise

                page_name = getattr(getattr(submission, "page_class", None), "__name__", "Unknown")
                t0 = time.perf_counter()
                bot.submit(submission)
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                participant = _participant_from_bot(bot)
                if participant is not None:
                    record_bot_submit_timing(participant, page_name, elapsed_ms)
                progress_made = True

            if progress_made:
                loops_without_progress = 0
            else:
                loops_without_progress += 1
                time.sleep(0.05)

        if session_code:
            session = Session.objects_get(code=session_code)
            stop_at = str((session.config or {}).get("bot_stop_at") or "finish").strip().lower()
            if stop_at and stop_at not in ("finish", "none", ""):
                summary = {
                    "skipped_full_verify": True,
                    "bot_stop_at": stop_at,
                    "note": "Partial bot run — integrity verify skipped",
                }
            else:
                summary = verify_tg_v2_bot_stress_session(
                    session,
                    delegation_first=delegation_first,
                )
            Session.objects_get(code=session_code).vars["bot_stress_last_summary"] = summary
            db.commit()
            print(format_bot_stress_summary(summary))

    SessionBotRunner.play = _play


def _try_bot_catchup(bot, exc: AssertionError) -> bool:
    """Best-effort sync when bot code and participant page disagree."""
    msg = str(exc)
    if "participant is actually here" not in msg and "Discrepancy between bot code and app code" not in msg:
        return False
    pages = re.findall(r"'page':\s*'(\w+)'", msg)
    actual_page = pages[1] if len(pages) > 1 else (pages[0] if pages else "")
    if actual_page == "BatchWaitForGroup":
        _refresh_batch_wait(bot)
        return True
    return False


def _human_parts_for_app(delegation_first: bool) -> List[int]:
    """oTree parts that run the 10+10 human decision block."""
    return [2] if delegation_first else [1]


def verify_tg_v2_bot_stress_session(
    session: Session,
    *,
    delegation_first: bool,
    expected_first_choice: str = "A",
    expected_second_choice: str = "B",
) -> Dict[str, Any]:
    """
    Assert human vars + per-round contingent fields for participants that finished
    a human block. Returns timing summary from participant.vars.
    """
    errors: List[str] = []
    timing_rows: List[dict] = []
    checked_players = 0

    for participant in session.get_participants():
        timings = participant.vars.get("bot_stress_submit_ms") or []
        if isinstance(timings, list):
            timing_rows.extend(timings)

        if participant.vars.get("quit_to_prolific_results"):
            continue

        for part in _human_parts_for_app(delegation_first):
            if not participant.vars.get(f"human_v2_done_part{part}"):
                continue

            first_map, second_map = human_block_maps_from_vars(participant, part)
            if not human_block_maps_complete(first_map, second_map):
                errors.append(
                    f"P{participant.id_in_session} part{part}: incomplete vars "
                    f"first={first_map!r} second={second_map!r}"
                )
                continue

            for i in range(1, 11):
                if first_map.get(i) != expected_first_choice:
                    errors.append(
                        f"P{participant.id_in_session} part{part} r{i} first "
                        f"expected {expected_first_choice!r} got {first_map.get(i)!r}"
                    )
                if second_map.get(i) != expected_second_choice:
                    errors.append(
                        f"P{participant.id_in_session} part{part} r{i} second "
                        f"expected {expected_second_choice!r} got {second_map.get(i)!r}"
                    )

            player = participant.get_players()[0]
            start_round = (part - 1) * 10 + 1
            for i in range(1, 11):
                pr = player.in_round(start_round + i - 1)
                exp_first = first_map[i]
                exp_second = second_map[i]
                db_first = pr.field_maybe_none("choice_first_mover")
                db_second = pr.field_maybe_none("choice_second_mover")
                if db_first != exp_first or db_second != exp_second:
                    errors.append(
                        f"P{participant.id_in_session} oTree r{start_round + i - 1}: "
                        f"DB c1={db_first!r} c2={db_second!r} "
                        f"expected {exp_first!r}/{exp_second!r}"
                    )
                if tg_round_has_partial_contingents(pr):
                    errors.append(
                        f"P{participant.id_in_session} oTree r{start_round + i - 1}: partial contingents"
                    )
            checked_players += 1

    human_submit_ms = [
        row["ms"]
        for row in timing_rows
        if row.get("page") in ("TgV2HumanDecisionsFirst", "TgV2HumanDecisionsSecond")
    ]
    summary = {
        "participants": len(session.get_participants()),
        "human_blocks_checked": checked_players,
        "human_submit_count": len(human_submit_ms),
        "human_submit_ms_avg": round(sum(human_submit_ms) / len(human_submit_ms), 2) if human_submit_ms else None,
        "human_submit_ms_max": round(max(human_submit_ms), 2) if human_submit_ms else None,
        "human_submit_ms_p95": _percentile(human_submit_ms, 95),
        "errors": errors,
    }
    if errors:
        raise AssertionError("TG v2 bot stress integrity failed:\n" + "\n".join(errors))
    return summary


def verify_tg_v2_bot_stress_session_by_code(session_code: Optional[str], *, skip_if_no_session: bool = False) -> None:
    if not session_code:
        if skip_if_no_session:
            return
        raise AssertionError("Missing session code for bot stress verification")
    session = Session.objects_get(code=session_code)
    delegation_first = session.config.get("delegation_first", None)
    if delegation_first is None:
        # Infer from first app in session app_sequence (avoids hardcoding a v2 app).
        app_sequence = session.config.get("app_sequence") or []
        if not app_sequence:
            raise AssertionError("Cannot infer DELEGATION_FIRST: empty app_sequence")
        Constants = importlib.import_module(f"{app_sequence[0]}.models").Constants
        delegation_first = Constants.DELEGATION_FIRST
    summary = verify_tg_v2_bot_stress_session(session, delegation_first=delegation_first)
    session.vars["bot_stress_last_summary"] = summary
    db.commit()


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return round(ordered[idx], 2)


def format_bot_stress_summary(summary: Dict[str, Any]) -> str:
    if summary.get("skipped_full_verify"):
        return (
            "TG v2 bot stress summary\n"
            f"  skipped full verify (bot_stop_at={summary.get('bot_stop_at')})\n"
            f"  note: {summary.get('note')}"
        )
    lines = [
        "TG v2 bot stress summary",
        f"  participants: {summary.get('participants')}",
        f"  human blocks checked: {summary.get('human_blocks_checked')}",
        f"  human submits: {summary.get('human_submit_count')}",
        f"  human submit ms avg: {summary.get('human_submit_ms_avg')}",
        f"  human submit ms p95: {summary.get('human_submit_ms_p95')}",
        f"  human submit ms max: {summary.get('human_submit_ms_max')}",
    ]
    return "\n".join(lines)

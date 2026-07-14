"""Scan existing TG sessions in the DB for Results / export integrity issues."""

from __future__ import annotations

import importlib
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared.export_integrity import collect_export_integrity_errors, participant_batch_for_part
from shared.tg_data_helpers import tg_export_choice_getter, tg_part_has_round_data
from shared.tg_results_debug import build_tg_results_debug


def _session_config_name(session: Any) -> str:
    cfg = getattr(session, "config", None) or {}
    return str(cfg.get("name") or cfg.get("display_name") or "")


def is_tg_session_config(name: str) -> bool:
    return name.startswith("TG_") and name != "TG_session_inspector"


def _parse_ymd(value: Optional[str]) -> Optional[date]:
    text = (value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _day_bounds(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Tuple[Optional[float], Optional[float]]:
    """Inclusive YYYY-MM-DD → unix [start, end) timestamps (local calendar days)."""
    d_from = _parse_ymd(date_from)
    d_to = _parse_ymd(date_to)
    start_ts = end_ts = None
    if d_from is not None:
        start_ts = datetime.combine(d_from, datetime.min.time()).timestamp()
    if d_to is not None:
        end_ts = datetime.combine(d_to + timedelta(days=1), datetime.min.time()).timestamp()
    return start_ts, end_ts


def _created_meta(session: Any) -> Dict[str, Any]:
    created = getattr(session, "_created", None)
    if created is None:
        return {
            "created_ts": None,
            "created_date": "",
            "created_readable": "unknown",
            "created_label": "unknown",
        }
    try:
        ts = float(created)
        dt = datetime.fromtimestamp(ts)
        readable = (
            session._created_readable()
            if hasattr(session, "_created_readable")
            else dt.strftime("%Y-%m-%d %H:%M")
        )
        return {
            "created_ts": ts,
            "created_date": dt.strftime("%Y-%m-%d"),
            "created_readable": readable,
            "created_label": dt.strftime("%Y-%m-%d %H:%M"),
        }
    except (TypeError, ValueError, OSError):
        return {
            "created_ts": None,
            "created_date": "",
            "created_readable": "unknown",
            "created_label": "unknown",
        }


def list_tg_sessions(
    *,
    limit: int = 100,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return recent TG experiment sessions (newest first), optionally filtered by create date."""
    from otree.models import Session

    start_ts, end_ts = _day_bounds(date_from, date_to)
    rows: List[Dict[str, Any]] = []
    # Scan more rows when filtering so date windows still return enough matches.
    scan_cap = max(limit * 8, 200)
    for session in Session.objects_filter().order_by(Session.id.desc()).limit(scan_cap):
        name = _session_config_name(session)
        if not is_tg_session_config(name):
            continue
        meta = _created_meta(session)
        ts = meta.get("created_ts")
        if start_ts is not None and (ts is None or ts < start_ts):
            continue
        if end_ts is not None and (ts is None or ts >= end_ts):
            continue
        rows.append(
            {
                "id": session.id,
                "code": session.code,
                "config_name": name,
                "num_participants": session.num_participants,
                "label": session.label or "",
                "is_demo": bool(getattr(session, "is_demo", False)),
                **meta,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def _participant_prolific_id(participant: Any) -> str:
    players = participant.get_players()
    if not players:
        return ""
    val = players[0].field_maybe_none("prolific_id")
    return (val or "").strip()


def filter_session_participants(
    participants: List[Any],
    *,
    participant_limit: Optional[int] = None,
    prolific_id: Optional[str] = None,
) -> List[Any]:
    """Return participants to scan, ordered by id_in_session."""
    ordered = sorted(participants, key=lambda p: p.id_in_session)
    prolific_q = (prolific_id or "").strip()
    if prolific_q:
        ordered = [
            p
            for p in ordered
            if _participant_prolific_id(p).lower() == prolific_q.lower()
        ]
    if participant_limit is not None and participant_limit > 0:
        ordered = ordered[:participant_limit]
    return ordered


def _normalize_participant_limit(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _load_target_app(session: Any):
    app_name = (session.config or {}).get("app_sequence", [None])[0]
    if not app_name or not str(app_name).startswith("TG_"):
        raise ValueError(f"Session {session.code!r} is not a TG app ({app_name!r}).")
    models = importlib.import_module(f"{app_name}.models")
    return app_name, models


def _scan_participant(
    participant: Any,
    session: Any,
    Constants: Any,
    get_opponent_in_round: Callable[[Any, int], Any],
) -> Dict[str, Any]:
    players = participant.get_players()
    if not players:
        return {
            "id_in_session": participant.id_in_session,
            "code": participant.code,
            "label": participant.label or "",
            "prolific_id": "",
            "error": "NO_PLAYER_ROWS",
            "parts": [],
            "export_errors": [],
            "stored_errors": [],
            "flag_counts": {},
            "total_flags": 0,
            "rounds": [],
            "has_issues": True,
        }

    player_r1 = players[0]
    rounds_per_part = Constants.rounds_per_part
    export_errors = collect_export_integrity_errors(
        participant,
        players,
        Constants,
        session,
        get_opponent_in_round,
        tg_export_choice_getter,
        results_cache_required=False,
    )

    stored = participant.vars.get("data_integrity_errors")
    stored_errors = [str(x) for x in stored] if isinstance(stored, list) else []

    parts_out: List[Dict[str, Any]] = []
    all_rounds: List[Dict[str, Any]] = []
    flag_counts: Dict[str, int] = {}

    for part in (1, 2, 3):
        part_start = (part - 1) * rounds_per_part + 1
        part_end = part * rounds_per_part
        if not tg_part_has_round_data(players, part, rounds_per_part):
            continue

        dbg = build_tg_results_debug(
            player_r1,
            part_start,
            part_end,
            part,
            get_opponent_in_round,
            rounds_per_part=rounds_per_part,
            force=True,
        )
        part_flags: List[str] = []
        part_rounds: List[Dict[str, Any]] = []
        if dbg:
            for row in dbg.get("rounds") or []:
                flags = row.get("flags") or []
                part_flags.extend(flags)
                for f in flags:
                    flag_counts[f] = flag_counts.get(f, 0) + 1
                part_rounds.append(
                    {
                        "round": row.get("round"),
                        "flags": flags,
                        "flags_text": ", ".join(flags) if flags else "",
                        "is_partial_contingent": "partial_contingent_choices" in flags,
                        "has_flags": bool(flags),
                        "display": row.get("display") or {},
                        "db": row.get("db") or {},
                        "mismatch_summary": (row.get("mismatch") or {}).get("summary", ""),
                    }
                )
                all_rounds.append(
                    {
                        "part": part,
                        "round": row.get("round"),
                        "otree_round": (row.get("db") or {}).get("otree_round"),
                        "flags": flags,
                        "mismatch_summary": (row.get("mismatch") or {}).get("summary", ""),
                    }
                )

        batch = participant_batch_for_part(session, participant.id_in_session, part)
        batch_id = batch.get("batch_id") if batch else None
        parts_out.append(
            {
                "part": part,
                "batch_id": batch_id,
                "has_batch_id": batch_id is not None,
                "member_ids": batch.get("member_ids") if batch else [],
                "member_ids_text": (
                    ", ".join(str(x) for x in batch.get("member_ids", [])) if batch else ""
                ),
                "debug_ok": bool(dbg and dbg.get("summary_vars", {}).get("tg_debug_all_ok")),
                "mismatch_count": dbg.get("summary_vars", {}).get("tg_debug_mismatch_count", 0)
                if dbg
                else 0,
                "flags": sorted(set(part_flags)),
                "rounds": part_rounds,
            }
        )

    total_flags = sum(flag_counts.values()) + len(export_errors) + len(stored_errors)

    return {
        "id_in_session": participant.id_in_session,
        "code": participant.code,
        "label": participant.label or "",
        "prolific_id": _participant_prolific_id(participant),
        "matching_group_id": participant.vars.get("matching_group_id"),
        "parts": parts_out,
        "export_errors": export_errors,
        "stored_errors": stored_errors,
        "flag_counts": flag_counts,
        "total_flags": total_flags,
        "rounds": all_rounds,
        "has_issues": total_flags > 0,
    }


def _batch_overview(session: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for key, value in (session.vars or {}).items():
        if not isinstance(key, str) or not key.startswith("matching_group_members_part_"):
            continue
        if not isinstance(value, (list, tuple)):
            continue
        suffix = key.replace("matching_group_members_part_", "", 1)
        if "_" not in suffix:
            continue
        part_str, batch_str = suffix.rsplit("_", 1)
        try:
            part = int(part_str)
            batch_id = int(batch_str)
        except ValueError:
            continue
        out.append(
            {
                "part": part,
                "batch_id": batch_id,
                "member_ids": list(value),
                "member_ids_text": ", ".join(str(x) for x in value),
                "size": len(value),
            }
        )
    out.sort(key=lambda x: (x["part"], x["batch_id"]))
    return out


def inspect_tg_session_by_code(
    session_code: str,
    *,
    participant_limit: Optional[int] = None,
    prolific_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Full integrity report for one TG session code."""
    from otree.models import Session

    code = (session_code or "").strip()
    if not code:
        return {"ok": False, "error": "No session code provided."}

    limit = _normalize_participant_limit(participant_limit)
    prolific_q = (prolific_id or "").strip() or None

    try:
        session = Session.objects_get(code=code)
    except Exception:
        return {"ok": False, "error": f"Session not found: {code!r}"}

    config_name = _session_config_name(session)
    if not is_tg_session_config(config_name):
        return {
            "ok": False,
            "error": f"Session {code!r} is not a TG experiment ({config_name!r}).",
        }

    try:
        app_name, models = _load_target_app(session)
    except ValueError as e:
        return {"ok": False, "error": str(e)}

    Constants = models.Constants
    get_opponent = models.get_opponent_in_round

    all_participants = list(session.get_participants())
    selected_participants = filter_session_participants(
        all_participants,
        participant_limit=limit,
        prolific_id=prolific_q,
    )
    participant_reports = [
        _scan_participant(p, session, Constants, get_opponent) for p in selected_participants
    ]

    flag_totals: Dict[str, int] = {}
    for rep in participant_reports:
        for k, v in (rep.get("flag_counts") or {}).items():
            flag_totals[k] = flag_totals.get(k, 0) + v

    export_issue_count = sum(len(r.get("export_errors") or []) for r in participant_reports)
    stored_issue_count = sum(len(r.get("stored_errors") or []) for r in participant_reports)
    participants_with_issues = sum(1 for r in participant_reports if r.get("has_issues"))
    partial_contingent_count = flag_totals.get("partial_contingent_choices", 0)
    scanned_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filter_active = bool(limit or prolific_q)

    return {
        "ok": True,
        "session": {
            "id": session.id,
            "code": session.code,
            "config_name": config_name,
            "app_name": app_name,
            "num_participants": session.num_participants,
            "label": session.label or "",
            **_created_meta(session),
        },
        "batches": _batch_overview(session),
        "summary": {
            "participant_count": len(participant_reports),
            "session_participant_count": len(all_participants),
            "participants_with_issues": participants_with_issues,
            "flag_totals": flag_totals,
            "flag_totals_list": sorted(flag_totals.items(), key=lambda x: (-x[1], x[0])),
            "export_issue_count": export_issue_count,
            "stored_issue_count": stored_issue_count,
            "partial_contingent_count": partial_contingent_count,
            "all_clear": participants_with_issues == 0 and bool(participant_reports),
            "scanned_at": scanned_at,
            "filter_active": filter_active,
            "participant_limit": limit,
            "filter_prolific_id": prolific_q or "",
            "prolific_not_found": bool(prolific_q and not participant_reports),
        },
        "participants": participant_reports,
    }


def session_choice_label(session_row: Dict[str, Any]) -> str:
    demo = " demo" if session_row.get("is_demo") else ""
    label = session_row.get("label") or ""
    label_bit = f" · {label}" if label else ""
    created = session_row.get("created_label") or session_row.get("created_date") or "?"
    return (
        f"{session_row['code']} · {created} · {session_row['config_name']} · "
        f"n={session_row['num_participants']}{demo}{label_bit}"
    )


def inspector_step(participant) -> str:
    return participant.vars.get("inspector_step") or "select"


def set_inspector_step(participant, step: str) -> None:
    participant.vars["inspector_step"] = step


def stash_session_date_filters(participant, player) -> None:
    """Preserve SessionSelect date filters while inspect page reuses the same fields."""
    participant.vars["inspector_select_date_from"] = player.field_maybe_none("filter_date_from") or ""
    participant.vars["inspector_select_date_to"] = player.field_maybe_none("filter_date_to") or ""
    player.filter_date_from = ""
    player.filter_date_to = ""


def restore_session_date_filters(participant, player) -> None:
    player.filter_date_from = participant.vars.get("inspector_select_date_from") or ""
    player.filter_date_to = participant.vars.get("inspector_select_date_to") or ""


def read_inspect_participant_limit(player) -> Optional[int]:
    return _normalize_participant_limit(player.field_maybe_none("filter_date_from"))


def read_inspect_prolific_id(player) -> Optional[str]:
    val = (player.field_maybe_none("filter_date_to") or "").strip()
    return val or None

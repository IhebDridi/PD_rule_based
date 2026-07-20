"""
Background / CLI custom CSV export for one session (avoids Clever ~180s HTTP timeout).

Usage (CLI, on Clever SSH or local with DATABASE_URL):
  python -m shared.background_export --session xh3fj087 --out out.csv
  python -m shared.background_export --session xh3fj087 --app TG_goal_oriented_delegation_1st

In-process job API (TG_session_inspector):
  job_id = start_export_job(session_code, skip_integrity=True)
  get_export_job(job_id) -> {status, path, error, progress, ...}
"""
from __future__ import annotations

import argparse
import csv
import importlib
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared.delegation_custom_export import _export_log, delegation_custom_export
from shared.export_spec_factory import make_delegation_export_spec

_JOBS: Dict[str, Dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def export_dir() -> Path:
    raw = (os.environ.get("OTREE_EXPORT_DIR") or "").strip()
    if raw:
        path = Path(raw)
    else:
        path = Path(os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp") / "otree_exports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_app_name(session: Any, app_name: Optional[str] = None) -> str:
    if app_name:
        return app_name
    seq = (session.config or {}).get("app_sequence") or []
    if not seq:
        raise ValueError(f"Session {session.code!r} has empty app_sequence.")
    name = str(seq[0])
    if name == "TG_session_inspector":
        raise ValueError("Cannot export TG_session_inspector itself.")
    return name


def load_players_for_session(session_code: str, app_name: Optional[str] = None) -> tuple:
    """Return (app_name, models_module, players_list) for one session."""
    from otree.models import Session

    _export_log(f"load_players begin session={session_code!r}")
    t0 = time.time()
    session = Session.objects_get(code=session_code)
    resolved = resolve_app_name(session, app_name)
    models = importlib.import_module(f"{resolved}.models")
    players: List[Any] = []
    participants = list(session.get_participants())
    _export_log(
        f"load_players session={session_code!r} app={resolved} "
        f"participants={len(participants)}"
    )
    for i, participant in enumerate(participants, start=1):
        players.extend(participant.get_players())
        if i == 1 or i % 25 == 0 or i == len(participants):
            _export_log(
                f"load_players progress {i}/{len(participants)} "
                f"player_rows={len(players)} elapsed={time.time() - t0:.1f}s"
            )
    _export_log(
        f"load_players done session={session_code!r} player_rows={len(players)} "
        f"elapsed={time.time() - t0:.1f}s"
    )
    return resolved, models, players


def export_session_to_csv(
    session_code: str,
    out_path: Path,
    *,
    app_name: Optional[str] = None,
    skip_integrity: bool = True,
    progress_callback=None,
) -> Dict[str, Any]:
    """Synchronously write custom-export CSV for one session. Returns summary dict."""
    resolved, models, players = load_players_for_session(session_code, app_name)
    Constants = models.Constants
    compute_rr = models.compute_round_robin_assignments
    spec = make_delegation_export_spec(
        f"{resolved}.models", Constants, compute_rr
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    n_rows = 0
    _export_log(f"write begin path={out_path}")
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for row in delegation_custom_export(
            players,
            spec,
            session_code=session_code,
            skip_integrity=skip_integrity,
            progress_callback=progress_callback,
        ):
            writer.writerow(row)
            n_rows += 1
            if n_rows == 1 or n_rows % 25 == 0:
                f.flush()
    _export_log(
        f"write done path={out_path} rows={n_rows} "
        f"bytes={out_path.stat().st_size if out_path.exists() else 0} "
        f"elapsed={time.time() - t0:.1f}s"
    )
    return {
        "session_code": session_code,
        "app_name": resolved,
        "path": str(out_path.resolve()),
        "rows_including_header": n_rows,
        "data_rows": max(0, n_rows - 1),
        "skip_integrity": skip_integrity,
        "elapsed_s": round(time.time() - t0, 2),
        "bytes": out_path.stat().st_size if out_path.exists() else 0,
    }


def start_export_job(
    session_code: str,
    *,
    app_name: Optional[str] = None,
    skip_integrity: bool = True,
) -> str:
    """Start a daemon thread that writes CSV under export_dir(). Returns job_id."""
    job_id = uuid.uuid4().hex[:12]
    out_path = export_dir() / f"{session_code}_{job_id}_custom.csv"
    job = {
        "id": job_id,
        "status": "running",
        "session_code": session_code,
        "app_name": app_name or "",
        "skip_integrity": skip_integrity,
        "path": str(out_path),
        "error": "",
        "started_at": time.time(),
        "finished_at": None,
        "summary": None,
        "progress": {"phase": "queued", "message": "queued"},
    }
    with _JOBS_LOCK:
        _JOBS[job_id] = job

    def _on_progress(payload: dict):
        with _JOBS_LOCK:
            job["progress"] = dict(payload)
            phase = payload.get("phase", "")
            done = payload.get("done")
            total = payload.get("total")
            if done is not None and total:
                job["progress"]["message"] = f"{phase} {done}/{total}"
            else:
                job["progress"]["message"] = str(phase)

    def _run():
        try:
            _export_log(f"job {job_id} start session={session_code!r}")
            summary = export_session_to_csv(
                session_code,
                out_path,
                app_name=app_name,
                skip_integrity=skip_integrity,
                progress_callback=_on_progress,
            )
            with _JOBS_LOCK:
                job["status"] = "done"
                job["summary"] = summary
                job["app_name"] = summary.get("app_name") or job["app_name"]
                job["finished_at"] = time.time()
                job["progress"] = {
                    "phase": "done",
                    "message": f"done {summary.get('data_rows', 0)} rows",
                    "written": summary.get("data_rows", 0),
                }
            _export_log(f"job {job_id} done {summary}")
        except Exception as e:
            with _JOBS_LOCK:
                job["status"] = "error"
                job["error"] = f"{type(e).__name__}: {e}"
                job["finished_at"] = time.time()
                job["progress"] = {"phase": "error", "message": job["error"]}
            _export_log(f"job {job_id} ERROR {type(e).__name__}: {e}")

    threading.Thread(target=_run, name=f"export-{job_id}", daemon=True).start()
    return job_id


def get_export_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def read_export_csv_text(job_id: str, *, max_bytes: int = 8_000_000) -> Optional[str]:
    """Return CSV text for a finished job, or None if missing/too large."""
    job = get_export_job(job_id)
    if not job or job.get("status") != "done":
        return None
    path = Path(job["path"])
    if not path.is_file():
        return None
    if path.stat().st_size > max_bytes:
        return None
    return path.read_text(encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="oTree session code")
    parser.add_argument("--app", default=None, help="App name (default: session app_sequence[0])")
    parser.add_argument(
        "--out",
        default=None,
        help="Output CSV path (default: ./<session>_custom_export.csv)",
    )
    parser.add_argument(
        "--integrity",
        action="store_true",
        help="Run integrity checks (slower). Default skips them.",
    )
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else Path(f"{args.session}_custom_export.csv")
    summary = export_session_to_csv(
        args.session,
        out,
        app_name=args.app,
        skip_integrity=not args.integrity,
    )
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

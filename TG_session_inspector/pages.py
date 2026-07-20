"""Pages for the TG session inspector (internal QA tool)."""

from otree.api import *
from urllib.parse import quote

from shared.background_export import (
    get_export_job,
    read_export_csv_text,
    start_export_job,
)
from shared.tg_session_inspector import (
    _normalize_participant_pos,
    inspect_tg_session_by_code,
    inspector_step,
    list_tg_sessions,
    read_inspect_participant_from,
    read_inspect_participant_to,
    read_inspect_prolific_id,
    restore_session_date_filters,
    set_inspector_step,
    stash_session_date_filters,
)


class SessionSelect(Page):
    """Pick an existing TG session from the database (optionally filter by date)."""

    template_name = "TG_session_inspector/SessionSelect.html"
    form_model = "player"
    form_fields = [
        "filter_date_from",
        "filter_date_to",
        "selected_session_code",
        "select_action",
    ]

    def is_displayed(self):
        return inspector_step(self.participant) == "select"

    def vars_for_template(self):
        date_from = self.player.field_maybe_none("filter_date_from") or ""
        date_to = self.player.field_maybe_none("filter_date_to") or ""
        if not date_from and not date_to:
            date_from = self.participant.vars.get("inspector_select_date_from") or ""
            date_to = self.participant.vars.get("inspector_select_date_to") or ""
        sessions = list_tg_sessions(
            limit=100,
            date_from=date_from or None,
            date_to=date_to or None,
        )
        return {
            "sessions": sessions,
            "filter_date_from": date_from,
            "filter_date_to": date_to,
            "filter_active": bool(date_from or date_to),
        }

    def error_message(self, values):
        action = (values.get("select_action") or "scan").strip()
        if action == "filter":
            d_from = (values.get("filter_date_from") or "").strip()
            d_to = (values.get("filter_date_to") or "").strip()
            if d_from:
                try:
                    __import__("datetime").date.fromisoformat(d_from)
                except ValueError:
                    return "From date must be YYYY-MM-DD."
            if d_to:
                try:
                    __import__("datetime").date.fromisoformat(d_to)
                except ValueError:
                    return "To date must be YYYY-MM-DD."
            if d_from and d_to and d_from > d_to:
                return "From date must be on or before To date."
            return None

        code = (values.get("selected_session_code") or "").strip()
        if not code:
            return "Please select a session, or click Apply filter."
        report = inspect_tg_session_by_code(code)
        if not report.get("ok"):
            return report.get("error") or "Could not load that session."

    def before_next_page(self):
        action = (self.player.field_maybe_none("select_action") or "scan").strip()
        if action == "filter":
            self.player.selected_session_code = ""
            set_inspector_step(self.participant, "select")
        else:
            stash_session_date_filters(self.participant, self.player)
            set_inspector_step(self.participant, "inspect")


class InspectSession(Page):
    """Show DB rows, integrity flags, and export-style errors."""

    template_name = "TG_session_inspector/InspectSession.html"
    form_model = "player"
    form_fields = [
        "inspect_action",
        "filter_date_from",
        "filter_date_to",
        "select_action",
    ]

    def is_displayed(self):
        return inspector_step(self.participant) == "inspect"

    def _inspect_report(self):
        return inspect_tg_session_by_code(
            self.player.selected_session_code,
            participant_from=read_inspect_participant_from(self.player),
            participant_to=read_inspect_participant_to(self.player),
            prolific_id=read_inspect_prolific_id(self.player),
        )

    def _export_panel(self):
        job_id = self.participant.vars.get("bg_export_job_id") or ""
        job = get_export_job(job_id) if job_id else None
        panel = {
            "job_id": job_id,
            "job": job,
            "download_href": "",
            "download_name": "",
            "download_too_large": False,
            "hint": (
                "Background export writes a session-filtered custom CSV on this "
                "server (skips integrity by default). Use when the Data-page "
                "custom export times out on Clever (~180s)."
            ),
        }
        if job and job.get("status") == "done":
            text = read_export_csv_text(job_id)
            code = job.get("session_code") or "session"
            panel["download_name"] = f"{code}_custom_export.csv"
            if text is None:
                panel["download_too_large"] = True
                panel["hint"] = (
                    f"Export finished at {job.get('path')} but the file is too "
                    "large to embed. Download via Clever SSH or: "
                    f"python -m shared.background_export --session {code}"
                )
            else:
                panel["download_href"] = (
                    "data:text/csv;charset=utf-8," + quote(text)
                )
        return panel

    def vars_for_template(self):
        return {
            "report": self._inspect_report(),
            "participant_from": self.player.field_maybe_none("filter_date_from") or "",
            "participant_to": self.player.field_maybe_none("filter_date_to") or "",
            "filter_prolific_id": self.player.field_maybe_none("select_action") or "",
            "export_panel": self._export_panel(),
        }

    def error_message(self, values):
        action = (values.get("inspect_action") or "done").strip()
        if action in ("export_start", "export_refresh"):
            return None
        p_from = _normalize_participant_pos(values.get("filter_date_from"))
        p_to = _normalize_participant_pos(values.get("filter_date_to"))
        raw_from = values.get("filter_date_from")
        raw_to = values.get("filter_date_to")
        if raw_from not in (None, "") and p_from is None:
            return "P from must be a positive number (e.g. 1 for P1)."
        if raw_to not in (None, "") and p_to is None:
            return "P to must be a positive number (e.g. 20 for P20)."
        if p_from is not None and p_to is not None and p_from > p_to:
            return "P from must be less than or equal to P to."
        return None

    def before_next_page(self):
        action = (self.player.field_maybe_none("inspect_action") or "done").strip()
        if action == "export_start":
            code = (self.player.selected_session_code or "").strip()
            if code:
                job_id = start_export_job(code, skip_integrity=True)
                self.participant.vars["bg_export_job_id"] = job_id
            set_inspector_step(self.participant, "inspect")
        elif action == "export_refresh":
            set_inspector_step(self.participant, "inspect")
        elif action in ("rescan", "apply_filters"):
            set_inspector_step(self.participant, "inspect")
        elif action == "back":
            self.player.selected_session_code = ""
            self.participant.vars.pop("bg_export_job_id", None)
            restore_session_date_filters(self.participant, self.player)
            set_inspector_step(self.participant, "select")
        else:
            set_inspector_step(self.participant, "done")


page_sequence = [SessionSelect, InspectSession]

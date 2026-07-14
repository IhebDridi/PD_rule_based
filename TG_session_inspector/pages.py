"""Pages for the TG session inspector (internal QA tool)."""

from otree.api import *

from shared.tg_session_inspector import (
    _normalize_participant_limit,
    inspect_tg_session_by_code,
    inspector_step,
    list_tg_sessions,
    set_inspector_step,
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
            self.player.participant_limit = None
            self.player.filter_prolific_id = ""
            set_inspector_step(self.participant, "inspect")


class InspectSession(Page):
    """Show DB rows, integrity flags, and export-style errors."""

    template_name = "TG_session_inspector/InspectSession.html"
    form_model = "player"
    form_fields = [
        "inspect_action",
        "participant_limit",
        "filter_prolific_id",
    ]

    def is_displayed(self):
        return inspector_step(self.participant) == "inspect"

    def _inspect_report(self):
        limit = _normalize_participant_limit(self.player.field_maybe_none("participant_limit"))
        prolific = (self.player.field_maybe_none("filter_prolific_id") or "").strip() or None
        return inspect_tg_session_by_code(
            self.player.selected_session_code,
            participant_limit=limit,
            prolific_id=prolific,
        )

    def vars_for_template(self):
        return {
            "report": self._inspect_report(),
            "participant_limit": self.player.field_maybe_none("participant_limit") or "",
            "filter_prolific_id": self.player.field_maybe_none("filter_prolific_id") or "",
        }

    def error_message(self, values):
        raw_limit = values.get("participant_limit")
        if raw_limit not in (None, ""):
            try:
                n = int(raw_limit)
            except (TypeError, ValueError):
                return "Participant limit must be a positive number."
            if n < 1:
                return "Participant limit must be at least 1."
        return None

    def before_next_page(self):
        action = (self.player.field_maybe_none("inspect_action") or "done").strip()
        if action in ("rescan", "apply_filters"):
            set_inspector_step(self.participant, "inspect")
        elif action == "back":
            self.player.selected_session_code = ""
            set_inspector_step(self.participant, "select")
        else:
            set_inspector_step(self.participant, "done")


page_sequence = [SessionSelect, InspectSession]

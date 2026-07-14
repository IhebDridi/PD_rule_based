"""Pages for the TG session inspector (internal QA tool)."""

from otree.api import *

from shared.tg_session_inspector import (
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

    @staticmethod
    def is_displayed(player):
        return inspector_step(player.participant) == "select"

    @staticmethod
    def vars_for_template(player):
        date_from = player.field_maybe_none("filter_date_from") or ""
        date_to = player.field_maybe_none("filter_date_to") or ""
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

    @staticmethod
    def error_message(player, values):
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

    @staticmethod
    def before_next_page(player, timeout_happened):
        action = (player.field_maybe_none("select_action") or "scan").strip()
        if action == "filter":
            player.selected_session_code = ""
            set_inspector_step(player.participant, "select")
        else:
            set_inspector_step(player.participant, "inspect")


class InspectSession(Page):
    """Show DB rows, integrity flags, and export-style errors."""

    template_name = "TG_session_inspector/InspectSession.html"
    form_model = "player"
    form_fields = ["inspect_action"]

    @staticmethod
    def is_displayed(player):
        return inspector_step(player.participant) == "inspect"

    @staticmethod
    def vars_for_template(player):
        report = inspect_tg_session_by_code(player.selected_session_code)
        return {"report": report}

    @staticmethod
    def before_next_page(player, timeout_happened):
        action = (player.field_maybe_none("inspect_action") or "done").strip()
        if action == "rescan":
            set_inspector_step(player.participant, "inspect")
        elif action == "back":
            player.selected_session_code = ""
            set_inspector_step(player.participant, "select")
        else:
            set_inspector_step(player.participant, "done")


page_sequence = [SessionSelect, InspectSession]

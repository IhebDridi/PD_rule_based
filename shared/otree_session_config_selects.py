"""
Render selected SESSION_CONFIG fields as <select> dropdowns in Create Session.

oTree 5 only natively supports bool / int / float / str widgets (checkbox / number / text).
We keep values as strings so form parsing stays unchanged, and override the HTML for
fields registered in SESSION_CONFIG_SELECT_FIELDS.
"""

from __future__ import annotations

from html import escape

from shared.bot_stop_at import BOT_STOP_AT_OPTIONS

# field_name -> ordered (value, label) options
SESSION_CONFIG_SELECT_FIELDS: dict[str, list[tuple[str, str]]] = {
    "bot_stop_at": BOT_STOP_AT_OPTIONS,
}


def apply_session_config_select_patch() -> None:
    from otree.session import SessionConfig

    if getattr(SessionConfig, "_pd_select_fields_patched", False):
        return

    _orig = SessionConfig.editable_field_html

    def editable_field_html(self, field_name: str) -> str:
        choices = SESSION_CONFIG_SELECT_FIELDS.get(field_name)
        if not choices:
            return _orig(self, field_name)

        existing = str(self[field_name])
        html_name = escape(self.html_field_name(field_name), quote=True)
        options_html = []
        for value, label in choices:
            selected = " selected" if existing == value else ""
            options_html.append(
                "<option value='{}'{}>{}</option>".format(
                    escape(value, quote=True),
                    selected,
                    escape(label),
                )
            )
        return (
            "<tr><td><b>{}</b></td><td>"
            "<select name='{}' class='form-control'>{}</select>"
            "</td></tr>"
        ).format(escape(field_name), html_name, "".join(options_html))

    SessionConfig.editable_field_html = editable_field_html  # type: ignore[method-assign]
    SessionConfig._pd_select_fields_patched = True


apply_session_config_select_patch()

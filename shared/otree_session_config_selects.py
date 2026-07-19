"""
Render selected SESSION_CONFIG fields as <select> dropdowns in Create Session.

oTree 5 only natively supports bool / int / float / str widgets (checkbox / number / text).
We keep values as strings so form parsing stays unchanged, and override the HTML for
fields registered in SESSION_CONFIG_SELECT_FIELDS.

The patch cannot be applied from the middle of settings.py (importing otree.session
while settings are still loading raises NameError). Instead we install a lightweight
import hook that patches SessionConfig right after otree.session finishes loading.
"""

from __future__ import annotations

import sys
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


class _OtreeSessionPatchFinder:
    """Wrap loading of otree.session so we can patch SessionConfig immediately after."""

    def find_spec(self, fullname, path, target=None):  # noqa: ANN001
        if fullname != "otree.session":
            return None
        # Remove ourselves so we don't recurse; then ask the remaining finders.
        try:
            sys.meta_path.remove(self)
        except ValueError:
            pass
        for finder in list(sys.meta_path):
            find_spec = getattr(finder, "find_spec", None)
            if find_spec is None:
                continue
            spec = find_spec(fullname, path, target)
            if spec is None or spec.loader is None:
                continue
            loader = spec.loader
            if not hasattr(loader, "exec_module"):
                return spec
            orig_exec = loader.exec_module

            def exec_module(module, _orig=orig_exec):
                _orig(module)
                apply_session_config_select_patch()

            loader.exec_module = exec_module  # type: ignore[method-assign]
            return spec
        return None


def install_session_config_select_import_hook() -> None:
    """
    Call from settings.py (safe: does not import otree).

    If otree.session is already imported, patch immediately.
    """
    if "otree.session" in sys.modules:
        apply_session_config_select_patch()
        return
    if any(isinstance(f, _OtreeSessionPatchFinder) for f in sys.meta_path):
        return
    sys.meta_path.insert(0, _OtreeSessionPatchFinder())

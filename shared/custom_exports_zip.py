"""Build a ZIP of every installed app's ``custom_export`` CSV (same as oTree admin per app)."""
from __future__ import annotations

import io
import zipfile
from typing import Iterable, Optional


def build_custom_exports_zip_bytes(
    session_code: Optional[str] = None,
    app_names: Optional[Iterable[str]] = None,
) -> bytes:
    from otree.export import custom_export_app, get_installed_apps_with_data

    if app_names is None:
        names = sorted(get_installed_apps_with_data())
    else:
        names = sorted(app_names)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for app_name in names:
            try:
                sio = io.StringIO()
                custom_export_app(
                    app_name,
                    sio,
                    session_code=session_code,
                    function_name="custom_export",
                )
                zf.writestr(f"{app_name}.csv", sio.getvalue().encode("utf-8-sig"))
            except Exception as e:
                zf.writestr(
                    f"{app_name}_EXPORT_ERROR.txt",
                    f"{type(e).__name__}: {e}\n".encode("utf-8", errors="replace"),
                )
    return buf.getvalue()

"""
Register an admin Data-page download: all apps' ``custom_export`` in one ZIP.

oTree only offers "All apps (wide format)" for the combined normal export; this adds a
second combined option that runs each app's ``custom_export`` (like the per-app custom links).

Loaded from ``settings.py`` after ``SESSION_CONFIGS`` so ``otree.urls`` can build routes.
"""
from __future__ import annotations

import datetime

_registered = False


def register_once() -> None:
    global _registered
    if _registered:
        return
    _registered = True

    from starlette.responses import Response
    from starlette.routing import Route

    from otree import settings as otree_settings
    from otree.urls import ALWAYS_UNRESTRICTED, UNRESTRICTED_IN_DEMO_MODE
    from otree.views import cbv

    import otree.urls as otree_urls_module
    from shared.custom_exports_zip import build_custom_exports_zip_bytes

    view_name = "ExportAllAppsCustomBundle"

    class ExportAllAppsCustomBundle(cbv.AdminView):
        url_pattern = "/ExportAllAppsCustomBundle"

        def get(self, request, **kwargs):
            # Login is enforced in AdminView.inner_dispatch before get() runs.
            session_code = request.query_params.get("session_code")
            data = build_custom_exports_zip_bytes(session_code=session_code)
            today = datetime.date.today().isoformat()
            filename = f"all_apps_custom_exports-{today}.zip"
            return Response(
                content=data,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )

    V = ExportAllAppsCustomBundle
    V._requires_login = {
        "STUDY": view_name not in ALWAYS_UNRESTRICTED,
        "DEMO": view_name not in UNRESTRICTED_IN_DEMO_MODE,
        "": False,
        None: False,
    }[otree_settings.AUTH_LEVEL]

    otree_urls_module.routes.append(Route(V.url_pattern, V, name=view_name))
    otree_urls_module.VIEWS_WITHOUT_LOCK.add(view_name)

    import otree.views.export as export_views

    _orig = export_views.ExportIndex.vars_for_template

    def _vars_with_bundle(self):
        from otree.asgi import reverse

        d = dict(_orig(self))
        u = reverse(view_name)
        bundle_row = dict(
            name="All apps — custom exports (ZIP, one CSV per app)",
            csv_url=u,
            excel_url=u,
            api_csv_url=u,
            api_excel_url=u,
            example_session_url=u + "?session_code={SESSION_CODE}",
        )
        d["other_exports"] = list(d.get("other_exports", [])) + [bundle_row]
        return d

    export_views.ExportIndex.vars_for_template = _vars_with_bundle

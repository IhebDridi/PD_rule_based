#!/usr/bin/env python3
"""
Run every app’s ``custom_export`` and pack the CSVs into one ZIP (same logic as oTree admin).

From the project directory (where ``settings.py`` lives), with the same Python env as ``otree``:

    python scripts/bundle_custom_exports.py
    python scripts/bundle_custom_exports.py --session-code abc12
    python scripts/bundle_custom_exports.py --apps PD_llm_delegation_1st,SD_llm_delegation_1st
    python scripts/bundle_custom_exports.py --output exports.zip
"""
from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="ZIP all custom_export CSVs (one file per app).")
    parser.add_argument(
        "--session-code",
        default=None,
        help="Only include players from this session (same as admin session filter).",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="custom_exports_bundle.zip",
        help="Output ZIP path (default: custom_exports_bundle.zip in cwd).",
    )
    parser.add_argument(
        "--apps",
        default=None,
        help="Comma-separated app names. Default: all apps that have data (oTree discovery).",
    )
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    if "DJANGO_SETTINGS_MODULE" not in os.environ:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")

    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    import django

    django.setup()

    from otree.export import get_installed_apps_with_data

    from shared.custom_exports_zip import build_custom_exports_zip_bytes

    if args.apps:
        app_names = [a.strip() for a in args.apps.split(",") if a.strip()]
    else:
        app_names = list(get_installed_apps_with_data())

    out_path = os.path.abspath(args.output)
    data = build_custom_exports_zip_bytes(
        session_code=args.session_code,
        app_names=app_names,
    )
    with open(out_path, "wb") as f:
        f.write(data)

    print(f"Wrote {out_path} ({len(app_names)} app(s) attempted).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

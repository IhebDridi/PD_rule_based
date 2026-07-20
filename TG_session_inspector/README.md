# TG_session_inspector

Internal **QA tool** for inspecting existing Trust Game (TG) sessions. Not a participant-facing experiment.

## Purpose

Browse TG sessions in the database, filter by date, and inspect Results / export integrity issues (missing parts, matching anomalies, etc.).

Logic lives mainly in `shared/tg_session_inspector.py`.

## Session config

| Config | Notes |
|--------|--------|
| `TG_session_inspector` | `num_demo_participants=1`, no bots variant |

```bash
otree create_session TG_session_inspector 1
```

## Flow

1. **SessionSelect** — list / filter TG sessions; pick a `session_code`
2. **InspectSession** — show integrity / data diagnostics for that session
3. **Background custom export** — start a session-filtered CSV job (skips integrity by default), refresh status, download when ready

URL slug: `tg_session_inspector`.

## Background export (Clever timeout workaround)

Stock **Data → Custom export** is one HTTP request and can hit Clever’s ~180s proxy limit on large sessions.

| Path | How |
|------|-----|
| Inspector UI | Inspect a session → **Start export (fast, this session)** → **Refresh** → **Download CSV** |
| CLI (SSH / local + `DATABASE_URL`) | `python -m shared.background_export --session SESSION_CODE` |
| Faster stock Data export | Default skips integrity (`OTREE_CUSTOM_EXPORT_SKIP_INTEGRITY=1`). Optionally set `OTREE_CUSTOM_EXPORT_SESSION=code` on Clever to filter to one session. Set integrity env to `0` to restore full checks. |

Job files are written under `$OTREE_EXPORT_DIR` or `%TEMP%/otree_exports` / `/tmp/otree_exports`.

## Layout in this folder

| Path | Role |
|------|------|
| `models.py` | Minimal Player fields for filters / selection |
| `pages.py` | `SessionSelect`, `InspectSession` (+ export start/refresh) |
| `templates/TG_session_inspector/` | Inspector UI |
| `shared/background_export.py` | Job runner + CLI |
| `shared/delegation_custom_export.py` | `session_code` / `skip_integrity` kwargs |

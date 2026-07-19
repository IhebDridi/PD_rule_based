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

URL slug: `tg_session_inspector`.

## Layout in this folder

| Path | Role |
|------|------|
| `models.py` | Minimal Player fields for filters / selection |
| `pages.py` | `SessionSelect`, `InspectSession` |
| `templates/TG_session_inspector/` | Inspector UI |

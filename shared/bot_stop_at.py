"""bot_stop_at session-config choices (shared by admin select + PlayerBot)."""

from __future__ import annotations

# (value, label) — value is stored in session.config['bot_stop_at']
BOT_STOP_AT_OPTIONS: list[tuple[str, str]] = [
    ("finish", "finish — run through Thank you"),
    ("results_part1", "results_part1 — stop on Results after Part 1"),
    ("results_part2", "results_part2 — stop on Results after Part 2"),
    ("results_part3", "results_part3 — stop on Results after Part 3"),
    ("guess", "guess — stop on GuessDelegation"),
    ("debriefing", "debriefing — stop on Debriefing"),
]

BOT_STOP_AT_CHOICES = frozenset(value for value, _ in BOT_STOP_AT_OPTIONS)
BOT_STOP_AT_DEFAULT = "finish"


def normalize_bot_stop_at(raw) -> str:
    value = str(raw or BOT_STOP_AT_DEFAULT).strip().lower()
    if value not in BOT_STOP_AT_CHOICES:
        return BOT_STOP_AT_DEFAULT
    return value

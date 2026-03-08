# Prisoners' Dilemma — Rule-based delegation experiment

oTree experiment for a repeated prisoners' dilemma with delegation and a guessing game. Participants are matched in groups of 3 or more via a lobby; within each group, opponents are assigned by round-robin over 10 rounds per part.

## Requirements

- Python 3.10+
- [oTree](https://www.otree.org/) (install via `pip install otree` or your project’s virtualenv)

## Setup

1. Clone or download the project.
2. Create and activate a virtual environment (recommended).
3. Install dependencies (e.g. `pip install otree` if not already installed).
4. Set `OTREE_ADMIN_PASSWORD` in the environment if you use the admin interface.

## Running locally

- **Development server:**  
  `otree devserver`  
  Then open the URL shown (e.g. http://localhost:8000).

- **Create a session:**  
  Use the oTree admin (e.g. http://localhost:8000/demo) or the command line, e.g.:  
  `otree create_session prisoners_dilemma_bots 10`  
  (session config name and number of participants as needed).

## Session configs (in `settings.py`)

| Config name               | Description                          | Use case              |
|---------------------------|--------------------------------------|------------------------|
| `prisoners_dilemma_bots`  | Rule-based, 10 demo participants, bots | Automated/demo testing |
| `prisoners_dilemma_manual`| Rule-based, 10 participants, no bots | Manual testing         |
| `prisoners_dilemma_100`   | Rule-based, 100 participants, no bots| Larger manual test     |
| `manual_tests`            | Separate manual-tests app            | Other manual tests     |

## Experiment structure

- **Informed consent** → **Main instructions** → **Lobby** (Part 1).
- **Part 1 (rounds 1–10):** No delegation — participants choose A or B each round.
- **Lobby** (Part 2) → **Part 2 (rounds 11–20):** Mandatory delegation — decisions made by an AI agent according to instructions.
- **Lobby** (Part 3) → **Part 3 (rounds 21–30):** Optional delegation — each participant chooses whether to delegate or play themselves.
- **Part 4 (guessing game):** 10 rounds guessing whether the opponent delegated (bonus for correct guesses).
- **Debriefing** → **Exit questionnaire** → **Thank you**.

Payoffs (in points) per round: (A,A)=70,70; (A,B)=0,100; (B,A)=100,0; (B,B)=30,30. One of Parts 1–3 is randomly selected for bonus payment; Part 4 bonus is separate. Conversion: 1 point = $0.01 (configurable in `settings.py`).

## Lobby and grouping

- **Minimum to start a part:** 3 participants (`MIN_PLAYERS_TO_START` in `prisoners_dilemma/models.py`).
- Participants wait in the lobby until at least 3 are present and a short minimum wait has passed; then that set is released as one group (first-in first-out). No bots; only human participants are matched.
- If after the timeout (2 min for Part 1, 1 min for Parts 2–3) there are still fewer than 3, participants see a **wait or quit** screen: wait again or return to Prolific for a $1 compensation (link in constants).
- At session creation everyone is in a single group; real playing groups are formed only when a batch is released from the lobby, so session creation stays fast even with many participants.

## Round-robin matching

Within each released group of N (N ≥ 3), opponents are determined by a round-robin rule over 10 rounds so that each participant faces a defined sequence of opponents and total matches = N × 10. Payoffs use the standard PD matrix above.

## Data export

- **Standard oTree export:** from the admin or export URLs.
- **Custom export:** implemented in `prisoners_dilemma/models.py` (`custom_export`). Use the custom export from the oTree admin to download the app-specific CSV (round-level decisions, payoffs, guessing outcomes, bonus totals, etc.).

## Production / deployment

- `run.sh` is set up for production (e.g. Clever Cloud): it uses `DATABASE_URL` (e.g. `POSTGRESQL_ADDON_URI`) and runs `otree prodserver 9000`.
- For a local DB reset: `otree resetdb` (or `echo y | otree resetdb` non-interactively). With PostgreSQL + PostGIS, if `resetdb` fails on extension-owned tables, you may need to reset only the app schema and then run `otree migrate`.

## Project layout (main files)

- `settings.py` — Session configs, rooms, currency, admin.
- `prisoners_dilemma/` — Main app: `models.py` (constants, grouping, payoffs, custom export), `pages.py` (flow, lobby, decisions, results), `tests.py` (bot tests).
- `prisoners_dilemma/templates/prisoners_dilemma/` — HTML templates for each page.

## License

Use and adapt as required by your institution or oTree’s license terms.

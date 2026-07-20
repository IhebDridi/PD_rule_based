# PD_rule_based — oTree delegation experiments

oTree project for **delegation** experiments across several simultaneous-choice and sequential games. Each game family has four agent interfaces (rule-based, LLM, goal-oriented, supervised learning) and a **1st / 2nd** order variant (whether mandatory delegation comes before or after the human block).

This README is the project overview. **Per-app docs** live in each app folder as `README.md` — GitHub shows them when you open that directory.

## Trust Game apps (documented)

| App | Delegation UI | Order | README |
|-----|---------------|-------|--------|
| `TG_rule_based_delegation_1st` | Manual A/B plan | Agent first | [README](TG_rule_based_delegation_1st/README.md) |
| `TG_rule_based_delegation_2nd` | Manual A/B plan | Human first | [README](TG_rule_based_delegation_2nd/README.md) |
| `TG_llm_delegation_1st` | LLM chatbot | Agent first | [README](TG_llm_delegation_1st/README.md) |
| `TG_llm_delegation_2nd` | LLM chatbot | Human first | [README](TG_llm_delegation_2nd/README.md) |
| `TG_goal_oriented_delegation_1st` | Goal slider | Agent first | [README](TG_goal_oriented_delegation_1st/README.md) |
| `TG_goal_oriented_delegation_2nd` | Goal slider | Human first | [README](TG_goal_oriented_delegation_2nd/README.md) |
| `TG_supervised_learning_delegation_1st` | Dataset generate | Agent first | [README](TG_supervised_learning_delegation_1st/README.md) |
| `TG_supervised_learning_delegation_2nd` | Dataset generate | Human first | [README](TG_supervised_learning_delegation_2nd/README.md) |
| `TG_session_inspector` | — (QA tool) | — | [README](TG_session_inspector/README.md) |

Each treatment also has a `*_with_bots` session config in `settings.py` for browser-bot testing.

### Other game families in this repo

Same naming pattern under `PD_*`, `SD_*`, and `SH_*` (session configs listed in `settings.py`). Those folders do not yet have dedicated README files.

## Shared design (TG)

**Game:** Sequential Trust Game. Each round, a participant submits contingent A/B choices as 1st and 2nd mover; roles are assigned when payoffs are computed (`shared/tg_payoffs.py`).

| 1st | 2nd | Payoffs (Ecoins) |
|-----|-----|------------------|
| B | (ignored) | 30, 30 |
| A | A | 70, 70 |
| A | B | 0, 100 |

**Parts:** 30 rounds (10 per part). `_1st` apps put **mandatory delegation in Part 1**; `_2nd` apps put it in **Part 2**. Part 3 is always optional delegation. Then: guessing game → debriefing → exit questionnaire → thank you.

**Matching (important):**

- Participants decide freely (`players_per_group = None`).
- Only at **BatchWaitForGroup** (end of each part) we form **logical groups of exactly 3** (FIFO).
- Opponents within a trio use **round-robin** over that part’s 10 rounds.
- Payoffs use **only those three** participants’ stored choices.
- Admin export may still show a single oTree `group_id`; matching uses `participant.vars["matching_group_id"]` (and related session vars), not oTree’s matrix.

## Requirements

- Python 3.10+
- [oTree](https://www.otree.org/) (`pip install otree` or the project virtualenv)
- For LLM treatments: provider credentials as required by `pages_classes/MistralPage.py` / app helpers

## Setup

1. Clone the project.
2. Create and activate a virtual environment.
3. Install dependencies (`pip install otree`, plus any LLM SDK your env needs).
4. Set `OTREE_ADMIN_PASSWORD` if you use the admin UI.

## Running locally

```bash
otree devserver
```

Open the URL shown (e.g. http://localhost:8000). Create a session from Demo/Admin, or:

```bash
otree create_session TG_rule_based_delegation_1st 10
```

### Useful session defaults (`SESSION_CONFIG_DEFAULTS`)

| Key | Meaning |
|-----|---------|
| `bot_stop_at` | Dropdown in Create Session → Configure: `finish` \| `results_part1` \| `results_part2` \| `results_part3` \| `guess` \| `debriefing` |
| `use_midnight_teal` | UI theme (`OTREE_THEME=midnight-teal` / `classic`) |
| `real_world_currency_per_point` | Default `0.01` |
| `participation_fee` | Default `6` |

## Project layout

| Path | Role |
|------|------|
| `settings.py` | Session configs, rooms, currency, defaults |
| `TG_*` / `PD_*` / `SD_*` / `SH_*` | One oTree app per treatment × order |
| `pages_classes/` | Shared page class implementations |
| `shared/` | Matching, TG payoffs, export, bots, inspector helpers |
| `templates/global/` | Shared HTML templates |
| `run.sh` | Production entry (e.g. Clever Cloud → `otree prodserver`) |

App folders are thin: `models.py`, `pages.py` (wrappers + sequence), `tests.py`, and `templates/<app_name>/`.

## Waiting on BatchWaitForGroup

If fewer than 3 participants are available, players wait. After ~5 minutes they can wait again or quit (Prolific show-up path). Quitters are removed from the pool so they are not paired later.

## Data export

Use oTree’s standard export, or each app’s **custom export** (via `shared/delegation_custom_export.py` / `export_spec_factory.py`) for treatment-specific fields (e.g. conversation logs, supervised attempt history, agent programming history).

## Production

`run.sh` is set up for production (e.g. Clever Cloud): uses `DATABASE_URL` and runs `otree prodserver 9000`. For a local DB reset: `otree resetdb` (use care on PostgreSQL / PostGIS setups).

**Clever scaling:** use **one** app instance + Redis, not multiple web instances for the same session. Details: [docs/CLEVER_OTREE_SCALING.md](docs/CLEVER_OTREE_SCALING.md).

**Bot pacing:** browser bots wait ~1.5s (+ jitter) before auto-submit so workers stay free (`OTREE_BOT_SUBMIT_DELAY_MS` / session config `bot_submit_delay_ms`). Set to `0` to disable.

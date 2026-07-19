# TG_rule_based_delegation_2nd

Trust Game (sequential) with **rule-based agent programming**, and **mandatory delegation in Part 2**.

## Treatment

| Item | Value |
|------|--------|
| Game | Sequential Trust Game (contingent 1st/2nd mover A/B) |
| Delegation UI | Manual A/B plan for 10 rounds × both roles |
| Order (`DELEGATION_FIRST`) | `False` — Part 1 = human, Part 2 = mandatory agent |
| Part 3 | Optional: delegate (same agent UI) or play yourself |
| URL slug (`name_in_url`) | `exp_game421` |

Sibling app with reversed part order: [`TG_rule_based_delegation_1st`](../TG_rule_based_delegation_1st/).

## Payoffs (Ecoins)

| 1st mover | 2nd mover | Payoffs |
|-----------|-----------|---------|
| B | (ignored) | 30, 30 |
| A | A | 70, 70 |
| A | B | 0, 100 |

Roles are assigned at payoff time. Implemented in `shared/tg_payoffs.py`.

## Session configs

| Config | Bots |
|--------|------|
| `TG_rule_based_delegation_2nd` | No |
| `TG_rule_based_delegation_2nd_with_bots` | Yes (`use_browser_bots=True`) |

```bash
otree create_session TG_rule_based_delegation_2nd 10
```

Optional: set `bot_stop_at` in Create Session → Advanced (`finish`, `results_part1`, `results_part2`, `results_part3`, `guess`, `debriefing`).

## Flow (high level)

Consent → bot check → instructions / comprehension →  
**Part 1** (human contingent decisions) → BatchWait → Results →  
**Part 2** (mandatory rule-based agent) → BatchWait → Results →  
**Part 3** (optional delegate) → BatchWait → Results →  
Guessing game → Debriefing → Exit Q → Thank you.

At the end of each part, `BatchWaitForGroup` forms **groups of 3** (FIFO) and computes payoffs from those three players only.

## Agent programming

Pages: `TgV2AgentProgrammingFirst` / `TgV2AgentProgrammingSecond` — participant fills A/B for all 10 rounds for each role.

Notable saved field: `agent_prog_allocation` (JSON history of programming attempts).

## Layout in this folder

| Path | Role |
|------|------|
| `models.py` | Constants, Player fields, export hooks |
| `pages.py` | Thin wrappers + `page_sequence` |
| `tests.py` | Browser-bot tests (`shared/tg_player_bot.py`) |
| `templates/TG_rule_based_delegation_2nd/` | App-specific HTML |

Shared page logic lives under `pages_classes/` and `shared/` at the repo root.

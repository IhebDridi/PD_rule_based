# TG_goal_oriented_delegation_1st

Trust Game (sequential) with **goal-slider agent programming**, and **mandatory delegation in Part 1**.

## Treatment

| Item | Value |
|------|--------|
| Game | Sequential Trust Game (contingent 1st/2nd mover A/B) |
| Delegation UI | Slider sets P(A); system samples 10 A/B decisions per role |
| Order (`DELEGATION_FIRST`) | `True` — Part 1 = mandatory agent, Part 2 = human |
| Part 3 | Optional: delegate (same slider UI) or play yourself |
| URL slug (`name_in_url`) | `exp_game414` |

Sibling app with reversed part order: [`TG_goal_oriented_delegation_2nd`](../TG_goal_oriented_delegation_2nd/).

## Payoffs (Ecoins)

| 1st mover | 2nd mover | Payoffs |
|-----------|-----------|---------|
| B | (ignored) | 30, 30 |
| A | A | 70, 70 |
| A | B | 0, 100 |

Implemented in `shared/tg_payoffs.py`.

## Session configs

| Config | Bots |
|--------|------|
| `TG_goal_oriented_delegation_1st` | No |
| `TG_goal_oriented_delegation_1st_with_bots` | Yes |

```bash
otree create_session TG_goal_oriented_delegation_1st 10
```

Optional: `bot_stop_at` in Create Session → Advanced.

## Flow (high level)

Consent → bot check → instructions / comprehension →  
**Part 1** (mandatory goal-oriented agent) → BatchWait → Results →  
**Part 2** (human) → BatchWait → Results →  
**Part 3** (optional delegate) → BatchWait → Results →  
Guess → Debrief → Exit Q → Thank you.

Matching: end-of-part `BatchWaitForGroup` forms **trios of 3** (FIFO).

## Agent programming

Pages: `TgGoalOrientedFirst` / `TgGoalOrientedSecond`.

Slider maps to approximately `p_A = 0.05 + 0.90 * slider`, then 10 random A/B draws.

Notable saved field: `agent_prog_allocation` — JSON events with `slider_value`, allocations, and sampled decisions (full attempt history).

## Layout in this folder

| Path | Role |
|------|------|
| `models.py` | Constants, Player fields, export hooks |
| `pages.py` | Thin wrappers + `page_sequence` |
| `tests.py` | Browser-bot tests |
| `templates/TG_goal_oriented_delegation_1st/` | App-specific HTML |

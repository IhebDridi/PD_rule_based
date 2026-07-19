# TG_goal_oriented_delegation_2nd

Trust Game (sequential) with **goal-slider agent programming**, and **mandatory delegation in Part 2**.

## Treatment

| Item | Value |
|------|--------|
| Game | Sequential Trust Game (contingent 1st/2nd mover A/B) |
| Delegation UI | Slider sets P(A); system samples 10 A/B decisions per role |
| Order (`DELEGATION_FIRST`) | `False` — Part 1 = human, Part 2 = mandatory agent |
| Part 3 | Optional: delegate (same slider UI) or play yourself |
| URL slug (`name_in_url`) | `exp_game424` |

Sibling app with reversed part order: [`TG_goal_oriented_delegation_1st`](../TG_goal_oriented_delegation_1st/).

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
| `TG_goal_oriented_delegation_2nd` | No |
| `TG_goal_oriented_delegation_2nd_with_bots` | Yes |

```bash
otree create_session TG_goal_oriented_delegation_2nd 10
```

Optional: `bot_stop_at` in Create Session → Advanced.

## Flow (high level)

Consent → bot check → instructions / comprehension →  
**Part 1** (human) → BatchWait → Results →  
**Part 2** (mandatory goal-oriented agent) → BatchWait → Results →  
**Part 3** (optional delegate) → BatchWait → Results →  
Guess → Debrief → Exit Q → Thank you.

Matching: end-of-part `BatchWaitForGroup` forms **trios of 3** (FIFO).

## Agent programming

Pages: `TgGoalOrientedFirst` / `TgGoalOrientedSecond`.

Notable saved field: `agent_prog_allocation` (slider value + sampled decisions, full attempt history).

## Layout in this folder

| Path | Role |
|------|------|
| `models.py` | Constants, Player fields, export hooks |
| `pages.py` | Thin wrappers + `page_sequence` |
| `tests.py` | Browser-bot tests |
| `templates/TG_goal_oriented_delegation_2nd/` | App-specific HTML |

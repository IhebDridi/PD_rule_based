# TG_supervised_learning_delegation_1st

Trust Game (sequential) with **supervised-learning-style agent programming**, and **mandatory delegation in Part 1**.

## Treatment

| Item | Value |
|------|--------|
| Game | Sequential Trust Game (contingent 1st/2nd mover A/B) |
| Delegation UI | Choose among datasets with different P(A); Generate samples a 10-round plan; confirm |
| Order (`DELEGATION_FIRST`) | `True` — Part 1 = mandatory agent, Part 2 = human |
| Part 3 | Optional: delegate (same UI) or play yourself |
| URL slug (`name_in_url`) | `exp_game413` |

Sibling app with reversed part order: [`TG_supervised_learning_delegation_2nd`](../TG_supervised_learning_delegation_2nd/).

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
| `TG_supervised_learning_delegation_1st` | No |
| `TG_supervised_learning_delegation_1st_with_bots` | Yes |

```bash
otree create_session TG_supervised_learning_delegation_1st 10
```

Optional: `bot_stop_at` in Create Session → Advanced.

## Flow (high level)

Consent → bot check → instructions / comprehension →  
**Part 1** (mandatory supervised agent) → BatchWait → Results →  
**Part 2** (human) → BatchWait → Results →  
**Part 3** (optional delegate) → BatchWait → Results →  
Guess → Debrief → Exit Q → Thank you.

Matching: end-of-part `BatchWaitForGroup` forms **trios of 3** (FIFO).

## Agent programming

Pages: `TgSupervisedAgentFirst` / `TgSupervisedAgentSecond`.

Typically five datasets with P(A) ∈ {0.05, 0.25, 0.5, 0.75, 0.95}. Each Generate samples 10 A/B choices; participant may regenerate before confirming.

Notable saved fields:

- `supervised_history` — datasets shown + `attempts[]` for every Generate
- `supervised_dataset`, `supervised_mean`, `supervised_last_generated_csv`
- `agent_prog_allocation` (also present for consistency with other treatments)

## Layout in this folder

| Path | Role |
|------|------|
| `models.py` | Constants, Player fields, export hooks |
| `pages.py` | Thin wrappers + `page_sequence` |
| `tests.py` | Browser-bot tests |
| `templates/TG_supervised_learning_delegation_1st/` | App-specific HTML |

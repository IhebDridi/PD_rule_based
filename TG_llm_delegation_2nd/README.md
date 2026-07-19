# TG_llm_delegation_2nd

Trust Game (sequential) with **LLM chatbot agent programming**, and **mandatory delegation in Part 2**.

## Treatment

| Item | Value |
|------|--------|
| Game | Sequential Trust Game (contingent 1st/2nd mover A/B) |
| Delegation UI | Chat with an LLM until it returns a strict 10× A/B plan per role |
| Order (`DELEGATION_FIRST`) | `False` — Part 1 = human, Part 2 = mandatory agent |
| Part 3 | Optional: delegate (same chat UI) or play yourself |
| URL slug (`name_in_url`) | `exp_game422` |

Sibling app with reversed part order: [`TG_llm_delegation_1st`](../TG_llm_delegation_1st/).

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
| `TG_llm_delegation_2nd` | No |
| `TG_llm_delegation_2nd_with_bots` | Yes |

```bash
otree create_session TG_llm_delegation_2nd 10
```

Optional: `bot_stop_at` in Create Session → Advanced.

## Flow (high level)

Consent → bot check → instructions / comprehension →  
**Part 1** (human) → BatchWait → Results →  
**Part 2** (mandatory LLM agent) → BatchWait → Results →  
**Part 3** (optional delegate) → BatchWait → Results →  
Guess → Debrief → Exit Q → Thank you.

Matching: end-of-part `BatchWaitForGroup` forms **trios of 3** (FIFO).

## Agent programming

Pages: `TgLlmAgentFirst` / `TgLlmAgentSecond` (see also `pages_classes/MistralPage.py`).

Notable saved fields: `conversation_history` / `conversation_history_second` (full chat logs).

## Layout in this folder

| Path | Role |
|------|------|
| `models.py` | Constants, Player fields, export hooks |
| `pages.py` | Thin wrappers + `page_sequence` |
| `mistralassistant.py` | LLM helper used by this treatment |
| `tests.py` | Browser-bot tests |
| `templates/TG_llm_delegation_2nd/` | App-specific HTML |

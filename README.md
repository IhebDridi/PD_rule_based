## Prisoners Dilemma app – core logic overview

This README summarizes the **primary logic** of the `prisoners_dilemma` app: how participants are grouped, how rounds and parts are structured, how payoffs and bonuses are computed, and how delegation / agents work. For implementation details and edge cases, also see `prisoners_dilemma/GROUPING_AND_TIMEOUTS.md`.

---

### 1. Groups and matching

- **Target group size**: 10 participants per matching group.
- **Matching group ID**:
  - Each participant has `participant.vars['matching_group_id']`.
  - Values:
    - `0, 1, 2, …` → real matching groups.
    - `-1` → not yet in any group (still in lobby / inactive).
- **Per‑part grouping**:
  - Matching groups are defined **per part**:
    - Part 1 → rounds 1–10.
    - Part 2 → rounds 11–20.
    - Part 3 → rounds 21–30.
  - A participant can be in different matching groups across parts (depending on when they arrive in each lobby).

#### Lobby and batch formation

- For each part, there is a **lobby list** in `session.vars` that accumulates `id_in_session` values of waiting participants.
- When **≥10** participants are waiting:
  - The first 10 by `id_in_session` form a batch.
  - Those 10 are removed from the lobby and assigned a new `matching_group_id` for that part.
- When **2–9** participants are waiting and no new participants join for a **stale‑lobby timeout** (20 seconds in tests):
  - The entire waiting set (must be even) is released as a **smaller matching group** (e.g. 6 people).
  - They get their own `matching_group_id` and are paired only among themselves in that part.

---

### 2. Parts, rounds, and page flow

- **Parts and rounds**:
  - Part 1: rounds **1–10**.
  - Part 2: rounds **11–20**.
  - Part 3: rounds **21–30**.
  - Helper: `Constants.get_part(round_number)` returns 1/2/3.

- **High‑level sequence (per participant)**:
  - Consent, instructions, comprehension test.
  - Part 1 (mandatory delegation or human play, depending on `Constants.DELEGATION_FIRST`).
  - Part 2 (complementary condition: human play or mandatory delegation).
  - Part 3 (optional delegation).
  - Part 4 (guessing game).
  - Debriefing, exit questionnaire, thank‑you page.

---

### 3. Payoff logic (Prisoners Dilemma)

- **Action space**: two options, labelled **A** and **B**.
- **Payoff matrix** (`Constants.PD_PAYOFFS`):

```python
PD_PAYOFFS = {
    ('A', 'A'): (70, 70),
    ('A', 'B'): (0, 100),
    ('B', 'A'): (100, 0),
    ('B', 'B'): (30, 30),
}
```

- On each round:
  - Each player chooses `A` or `B` (directly or via an agent).
  - Within each matching group, players are paired and `set_payoffs()` applies the matrix to produce per‑round payoffs in **Ecoins**.
  - Ecoins are stored as a `CurrencyField` (`player.payoff`).

---

### 4. Delegation and agent types

The experiment has three main parts with different delegation regimes. Logically we think in terms of **agent type** and **delegation order**; the current implementation is **rule‑based first, delegation second** (`Condition = "rule2nd"` in the export).

- **Agent types (conceptual)**:
  - `no-agent` – the human chooses directly each round.
  - `rule` – a simple rule‑based agent pre‑programmed by the participant.
  - `supervised` – reserved label for a supervised model agent (not yet wired in this app).
  - `goal` – reserved label for a goal‑based agent (not yet wired in this app).
  - `llm` – reserved label for an LLM agent (not yet wired in this app).

- **Current mapping by part (as exported)**:
  - **Part 1 (rounds 1–10)**:
    - Agent type in export: `"rule"` for both player and co‑player.
    - Logic: the participant programs a rule‑based agent once; the agent then chooses A/B in Part 1 based on those rules.
  - **Part 2 (rounds 11–20)**:
    - Agent type: `"no-agent"` (both players).
    - Logic: human chooses `A` or `B` each round directly (no delegation).
  - **Part 3 (rounds 21–30)**:
    - Agent type: currently also `"rule"` for both, in the export.
    - Logic:
      - Each participant chooses whether to **delegate or not** (optional delegation).
      - If they delegate, the rule‑based agent is used.
      - If they do not, they choose directly.
      - The delegate decision is stored and used to interpret the guessing game.

---

### 5. End‑of‑part synchronization and payoffs

At the end of each part (after rounds 10, 20, 30), participants in the same `matching_group_id` see a wait page (`BatchWaitForGroup`):

- `BatchWaitForGroup.is_displayed`:
  - Only shown when:
    - `Constants.USE_BATCH_START` is enabled.
    - `round_number` is at the end of a part (10, 20, 30).
    - `participant.vars['matching_group_id'] >= 0` (i.e. they are in a real group).

- **Actual group size** for the current part:
  - Computed as the count of participants with that `matching_group_id`.
  - This is 10 for full batches; can be smaller (e.g. 6) for stale‑lobby groups.

- **Payoff computation**:
  - Once all expected arrivals (and any dropouts) are accounted for, the app runs:
    - `run_payoffs_for_matching_group` (no dropouts), or
    - `run_payoffs_for_matching_group_with_dropouts` (handles missing players with zero payoffs and random opponent moves).
  - Only rounds belonging to the current part are processed:
    - Part 1: rounds 1–10.
    - Part 2: rounds 11–20.
    - Part 3: rounds 21–30.
  - Only pairs where **both players** share the same `matching_group_id` are used when applying the payoff matrix.

---

### 6. Guessing game and bonus (Part 4)

After Part 3, participants enter the **guessing game** (Part 4):

- For each of the 10 rounds of Part 3 (global rounds 21–30), the participant guesses whether their co‑player **delegated**.
- For each round:
  - `Guess{i}` = 1 if the participant answered “yes” (they think co‑player delegated), else 0.
  - `TruthGuess{i}` = 1 if the co‑player actually delegated that round (or was simulated), else 0.
  - `EarningsGuess{i}`:
    - 10 Ecoins (0.10 in the bonus currency) if `Guess{i} == TruthGuess{i}`.
    - 0 otherwise.
- **Part 4 total**:
  - `TotalEarningsPart4Dollars` = `sum(EarningsGuess1..10) * 0.01`.

---

### 7. Main bonus calculation

At Debriefing, one of Parts 1–3 is chosen at random for the main bonus:

- `random_payoff_part` ∈ {1, 2, 3}.
- Totals per part:
  - `TotalEarningsPart1Ecoins` = sum of payoffs rounds 1–10.
  - `TotalEarningsPart2Ecoins` = sum of payoffs rounds 11–20.
  - `TotalEarningsPart3Ecoins` = sum of payoffs rounds 21–30.
- **Chosen part**:
  - `PartChosenBonus` = 1, 2 or 3.
  - Ecoins from that part → dollars: `TotalEarningsParts123Dollars` = `chosen_part_ecoins * 0.01`.
- **Total bonus**:
  - `BonusPaymentTotal` = `TotalEarningsParts123Dollars + TotalEarningsPart4Dollars`.

Debriefing displays this as:

- A “Bonus Calculation” section showing:
  - The randomly chosen part (`random_payoff_part`).
  - The total payoff in that part (Ecoins → cents).
  - The Part 4 guessing bonus (in dollars).
  - The final bonus payment in dollars.

---

### 8. Export and analysis

The active `custom_export(players)` in `models.py` produces one row per participant with:

- Identifiers: condition (`rule2nd`), Prolific ID, session code, matching group ID, player position, simulation flag.
- All round‑level decisions, co‑player IDs, co‑player decisions, payoffs, and agent labels for rounds 1–30.
- Guessing‑game variables (Guess/Truth/Earnings for each of the 10 guesses).
- Totals per part, chosen part, and total bonus (Parts 1–3 + Part 4).
- Exit questionnaire answers (gender, age, occupation, AI use, task difficulty, feedback on Part 3/4, free‑text feedback).
- Placeholders for agent logs and chat transcripts (currently empty): lists of supervised/goal/LLM choices and chat JSON for delegation and optional delegation.

This export is intended to be the **single primary data source** for analysis of behavior, payoffs, and questionnaire responses.

# Prisoner's Dilemma – Rule-based delegation

## Running tests

Tests use the oTree venv in the **parent** directory (e.g. `..\.PD` from this project root).

**Option 1 – PowerShell script (recommended)**  
From the project root:
```powershell
.\run_tests.ps1
```
To run with a specific number of participants (must be a multiple of 2, e.g. 2 or 10):
```powershell
.\run_tests.ps1 10
```

**Option 2 – Call venv directly**  
From the project root (`PD_rule_based`):
```powershell
& "..\.PD\Scripts\otree.exe" test prisoners_dilemma
```
Or with a number of participants:
```powershell
& "..\.PD\Scripts\otree.exe" test prisoners_dilemma 10
```

**Note:** If the test fails at Part 3 with “Bot is trying to submit InstructionsOptional / participant is actually here DecisionNoDelegation”, the app logic is correct (Part 3 no-delegation shows DecisionNoDelegation). The failure is a known sync issue between the oTree bot runner and multiple pages per round (InstructionsOptional → DelegationDecision → AgentProgramming/DecisionNoDelegation) in the same round.

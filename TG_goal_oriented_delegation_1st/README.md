# TG_goal_oriented_delegation_1st

Trust Game (sequential) with **goal-oriented (slider)**, and **`DELEGATION_FIRST=True`**.

## Treatment

| Item | Value |
|------|--------|
| Game | Sequential Trust Game (contingent 1st/2nd mover A/B) |
| Delegation UI | Slider sets approximate P(A); system samples 10 A/B decisions per role. |
| Order (`DELEGATION_FIRST`) | `True` — Part 1 = mandatory agent, Part 2 = human |
| Part layout | Part 1 = **mandatory agent**; Part 2 = **human** (no agent); Part 3 = **optional** delegate (same agent UI) or play yourself |
| Rounds | 30 (`num_rounds`), 10 per part |
| URL slug (`name_in_url`) | `exp_game414` |

Sibling app with reversed part order: [`TG_goal_oriented_delegation_2nd`](../TG_goal_oriented_delegation_2nd/).

## Payoffs (Ecoins)

| 1st mover | 2nd mover | Payoffs |
|-----------|-----------|---------|
| B | (ignored) | 30, 30 |
| A | A | 70, 70 |
| A | B | 0, 100 |

Roles are assigned at payoff time inside the matched trio. Implemented in `shared/tg_payoffs.py`.

## Session configs

| Config | Bots |
|--------|------|
| `TG_goal_oriented_delegation_1st` | No — **use this for Prolific** |
| `TG_goal_oriented_delegation_1st_with_bots` | Yes |

```bash
otree create_session TG_goal_oriented_delegation_1st 60
```

Use a session size **divisible by 3**. Optional: `bot_stop_at` in Create Session → Advanced.

---

## Page flow

oTree visits the same `page_sequence` every round; most pages `is_displayed` only on the right round / part. High-level path for one participant:

```mermaid
flowchart TD
    IC[InformedConsent] --> BD1[BotDetection]
    BD1 --> MI[MainInstructions]
    MI --> CT[ComprehensionTest]
    CT -->|fail| FT[FailedTest → Prolific]
    CT -->|pass| IN[Instructions]

    IN --> P1A[Agent programming<br/>Part 1 mandatory]
    P1A --> BW1[BatchWait Part 1]
    BW1 -->|quit| Q1[TimeOutquit]
    BW1 --> R1[Results Part 1]
    R1 --> P2H[Human decisions<br/>Part 2]
    P2H --> BW2[BatchWait Part 2]
    BW2 -->|quit| Q2[TimeOutquit]
    BW2 --> R2[Results Part 2]

    R2 --> DD3[DelegationDecision Part 3]
    DD3 -->|Yes| P3A[Agent programming]
    DD3 -->|No| P3H[Human decisions Part 3]
    P3A --> BW3[BatchWait Part 3]
    P3H --> BW3
    BW3 -->|quit| Q3[TimeOutquit]
    BW3 --> R3[Results Part 3]
    R3 --> IG[Guessing game]
    IG --> GD[GuessDelegation]
    GD --> RG[ResultsGuess]
    RG --> DB[Debriefing]
    DB --> EQ[ExitQuestionnaire]
    EQ --> BD2[BotDetection]
    BD2 --> TY[Thankyou → Prolific]
```

### Page sequence (from `pages.py`)

1. `InformedConsent` → `BotDetection` → `MainInstructions` → `ComprehensionTest` (`FailedTest` if fail)
2. Instructions (`InstructionsNoDelegation` / `InstructionsDelegation` / `InstructionsOptional`)
3. `DelegationDecision` (Part 3 only)
4. Agent: `TgGoalOrientedFirst` / `TgGoalOrientedSecond`
5. Human contingent blocks: `TG_V2_HUMAN_DECISIONS_FIRST_PAGES` + `…_SECOND_PAGES` (10+10 screens on the no-delegation part)
6. End of each part: `BatchWaitForGroup` → optional `TimeOutquit` → `Results`
7. After Part 3: `InstructionsGuessingGame` → `GuessDelegation` → `ResultsGuess`
8. `Debriefing` → `ExitQuestionnaire` → `BotDetection` → `Thankyou`

Shared page classes live in `pages_classes/`; this folder mostly wraps templates + `page_sequence`.

---

## Data flow

```mermaid
flowchart LR
    subgraph Input
      A[Agent or human UI]
    end
    subgraph Store
      C1[choice_first_mover<br/>per round]
      C2[choice_second_mover<br/>per round]
      V[participant.vars<br/>done flags / caches]
    end
    subgraph Match["BatchWaitForGroup"]
      Pool[FIFO pool of 3]
      Claim[Claim trio + roles]
      Pay[tg_payoffs<br/>directed round-robin]
    end
    subgraph Out
      GP[group_part_N<br/>group_position_part_N]
      PO[player.payoff Ecoins]
      Cache[results_display_cache]
      CSV[Custom export CSV]
    end
    A --> C1
    A --> C2
    A --> V
    C1 --> Pool
    C2 --> Pool
    Pool --> Claim --> Pay
    Pay --> GP
    Pay --> PO
    Pay --> Cache
    GP --> CSV
    PO --> CSV
    C1 --> CSV
    C2 --> CSV
```

### What gets written where

| Stage | Main fields / vars |
|-------|--------------------|
| Agent / human UI | Contingent `choice_first_mover` / `choice_second_mover` for rounds in the part; treatment-specific history (see below) |
| BatchWait success | `matching_group_id`, `matching_group_position`, then durable `group_part_N`, `group_position_part_N`, `can_proceed_to_results_part_N` |
| Payoffs | `role_assigned`, `payoff` (Ecoins); `results_display_cache` for Results/Debrief |
| Quit | `quit_to_prolific_results` → `TimeOutquit` → Prolific show-up URL |
| Export | Custom CSV via `shared/delegation_custom_export.py` (blanks / `"quit"` when unknown — no invented zeros) |

### Agent programming (this treatment)

Pages: `TgGoalOrientedFirst` / `TgGoalOrientedSecond`.

Slider sets approximate P(A); system samples 10 A/B decisions per role.

Saved / notable fields:

- `agent_prog_allocation` — JSON attempt history (`slider_value`, allocations, sampled A/B)
- Contingent choices written to `choice_first_mover` / `choice_second_mover` for the 10 rounds

---

## Worked example: P1, P2, P3 in one trio

In this app Part 1 is agent-programmed and Part 2 is human. The matching / payoff logic is identical for every TG treatment; only **how** the A/B plans are produced differs (goal-oriented (slider)).

### 1. Three people finish the part and wait

| Label | `id_in_session` | Arrives at BatchWait |
|-------|-----------------|----------------------|
| **P1** | 1 | first |
| **P2** | 2 | second |
| **P3** | 3 | third |

`BatchWaitForGroup` FIFO-claims the first three in the pool as **one matching group** and assigns trio positions:

| Player | `matching_group_position` / `GroupPositionPart*` |
|--------|---------------------------------------------------|
| P1 | 1 |
| P2 | 2 |
| P3 | 3 |

Durable after success: `group_part_N` (batch id) + `group_position_part_N`. If someone cannot wait long enough they may **quit** → Prolific show-up code; export marks `PartChosenBonus=quit` (earnings cells are `"quit"`, not `0.0`).

### 2. Directed round-robin opponents (N = 3)

Within the trio, each round each player has **one directed opponent** (not a mutual simultaneous pair write). Example for rounds 1–2:

| Round | P1 faces | P2 faces | P3 faces |
|-------|----------|----------|----------|
| 1 | P3 | P1 | P2 |
| 2 | P2 | P3 | P1 |

(Implemented by `compute_round_robin_assignments` in this app’s `models.py`.)

### 3. Contingent choices (what each person already submitted)

Before matching, each player stored **both** contingent moves for every round:

- `choice_first_mover` — what I would do as 1st mover  
- `choice_second_mover` — what I would do as 2nd mover  

**Example plans for round 1 only:**

| Player | If 1st mover | If 2nd mover |
|--------|--------------|--------------|
| P1 | A | B |
| P2 | B | A |
| P3 | A | A |

### 4. Role assignment + payoff for one directed match

Focus on **P1 → P3 in round 1**. At payoff time the code randomly assigns who is 1st vs 2nd **for that directed edge**, then looks up the contingency that matches the assigned role.

Suppose the RNG assigns:

- P1 = **first** mover → uses P1’s `choice_first_mover` = **A**  
- P3 = **second** mover → uses P3’s `choice_second_mover` = **A**  

Trust-game Ecoins (`shared/tg_payoffs.py`):

| 1st | 2nd | Payoffs (1st, 2nd) |
|-----|-----|---------------------|
| B | (ignored) | 30, 30 |
| A | A | **70, 70** |
| A | B | 0, 100 |

So this match: **P1 earns 70**, **P3 earns 70** on P1’s directed row (opponent column on Results shows the other player’s effective move). Other directed edges (P2→P1, P3→P2) are computed the same way with their own random roles.

```mermaid
sequenceDiagram
    participant P1
    participant Pool as BatchWait pool
    participant P2
    participant P3
    participant Pay as tg_payoffs
    P1->>Pool: join wait (pos later 1)
    P2->>Pool: join wait (pos later 2)
    P3->>Pool: join wait (pos later 3)
    Pool->>Pay: claim trio P1,P2,P3
    Pay->>Pay: round-robin + random roles
    Pay->>P1: role, payoff, cache row
    Pay->>P2: role, payoff, cache row
    Pay->>P3: role, payoff, cache row
    P1->>P1: Results table
    P2->>P2: Results table
    P3->>P3: Results table
```

### 5. What each person sees on Results

For each of the 10 rounds of the part: own effective choice, opponent’s effective choice, Ecoins.  
If `role_assigned` is missing, Ecoins stay **blank** in the custom export (no invented `0` from framework defaults).

### 6. Later parts

Parts 2 and 3 each form a **new** trio from whoever is waiting (FIFO again). Positions are stored separately as `GroupPart2` / `GroupPart3`. After Part 3, the guessing game asks whether each Part‑3 opponent delegated; unknown truth → `guess_payoff` left null (not `0`).


---

## Layout in this folder

| Path | Role |
|------|------|
| `models.py` | Constants, Player fields, round-robin + export hooks |
| `pages.py` | Thin wrappers + `page_sequence` |
| `tests.py` | Browser-bot tests |
| `templates/TG_goal_oriented_delegation_1st/` | App-specific HTML |

Shared logic: `pages_classes/`, `shared/tg_payoffs.py`, `shared/matching_batch.py`, `pages_classes/BatchWaitForGroup.py`.

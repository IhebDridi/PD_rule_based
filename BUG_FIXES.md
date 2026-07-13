# Bug fixes log

## TG Results Display ≠ DB payoff (directed round-robin overwrite)

**Status:** Fixed on `dev-branch`.  
**Symptom:** Debug flag `payoff_mismatch` — e.g. screen **100**, DB **30** — while the Results narrative correctly described the player’s directed match.

### Example (P1’s Round 1)

Narrative / screen (recomputed from directed opponent):

- P1 matched with **P3**
- P3 = 1st mover chose **A**; P1 = 2nd mover chose **B**
- Payoffs: P3 → 0, P1 → **100** Ecoins

DB after batch payoffs often showed P1 → **30**.

### Root cause

With a trio (N = 3), round-robin matching is **directed**, not mutual. In a typical Round 1 schedule:

| Player | Directed opponent |
|--------|-------------------|
| P1 | P3 |
| P2 | P1 |
| P3 | P2 |

So the edges are a cycle: **P1 → P3**, **P2 → P1**, **P3 → P2** (P1’s opponent is not P1’s reciprocal partner).

`run_payoffs_for_matching_group_tg` called `apply_tg_payoffs_for_pair(p, opp)` for **every** directed edge and that helper **wrote roles and payoffs on both players**. Order of overwrites for P1:

1. **P1 vs P3** → P1 correctly gets **100** (2nd mover; 1st A, 2nd B).
2. **P2 vs P1** → overwrites P1 with the P2–P1 game → often **30**.
3. Results still recompute from P1’s directed opponent **P3** → screen **100**.

Hence Display ≠ DB: screen followed the directed match used for Results; DB held the **last** overwrite from someone else’s directed edge.

### Fix

`apply_tg_payoffs_for_pair` in `shared/tg_payoffs.py` now writes **only the focal player** (`player_a`) by default (`write_both=False`). Each participant’s `role_assigned` / `payoff` come only from **their** directed opponent for that round.

So for P1:

- Result is created and stored on P1’s DB row **only** when processing **P1’s** directed edge (P1 → P3).
- When processing **P2 → P1**, only P2’s row is written; P1’s stored result is left alone.

Optional `write_both=True` remains for mutual-pair / unit-test cases that apply once for both sides.

Results earnings (`tg_results_row`) now prefer the **DB payoff** as source of truth (recompute only if DB is empty), so what the participant sees matches what is stored.

### Official match vs other directed matches (Results diagram)

The all-rounds grouping graph shows **one group per directed edge** (three groups in a trio). For the viewing participant:

| Label | Meaning |
|-------|---------|
| **YOUR official match** | Your directed opponent for that round. This is the game whose role/payoff were written to **your** DB row and shown in Results. |
| **{Pn}’s directed match (not yours)** | Another player’s focal edge. Illustrated for structure; it does **not** overwrite your DB. You may appear in their calculated roles (e.g. as opponent contingency), but that is not your stored result. |

If you see yourself in two groups with different Ecoins, only the badge **YOUR official match** is authoritative for your Results / DB.

### Verification notes

- Existing sessions already paid with the old logic keep wrong DB rows until payoffs are recomputed (**new session** after deploy).
- After the fix, `tg_debug_R*_flag` for this pattern should stay `ok` when display and DB both reflect the directed match.
- Related UI: Results all-rounds grouping diagram + per-round narratives (`shared/tg_results_diagrams.py`, `ResultsTG.html`).

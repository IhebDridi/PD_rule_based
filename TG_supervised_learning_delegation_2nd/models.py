"""
Prisoners' dilemma app models: constants, round-robin matching, grouping, payoffs, and custom export.

- Constants: payoff matrix, lobby timeouts, part/round mapping.
- Round-robin: compute_round_robin_assignments, get_opponent_in_round (with cache).
- Grouping: set_group_matrix_for_released_batch (batch + one "others" group for speed).
- Subsession.creating_session: mark everyone as not yet grouped (matching_group_id = -1).
- Group.set_payoffs: round-robin payoffs for batch groups; payoff 0 for waiting/leftover groups.
- Player: all form fields and helpers (get_agent_decision_*, get_part_data).
- Export: _opponent_for_export, custom_export.
- Lobby helpers: release_lobby_batch, run_payoffs_for_matching_group.
"""
from otree.api import *
import json
import random
from collections import defaultdict


# =============================================================================
# Constants
# =============================================================================

class Constants(BaseConstants):
    name_in_url = 'exp_game423'
    # None = one group of everyone at creation; real groups form only when lobby releases a batch (set_group_matrix_for_released_batch).
    players_per_group = None
    num_rounds = 30
    rounds_per_part = 10

    # Lobby: min players to start. Release as soon as ≥ MIN_PLAYERS_TO_START and min_wait passed (no grouping at lobby).
    # Groups are formed only right before Results (pool of 3); fixed size for simplicity.
    MIN_PLAYERS_TO_START = 3
    FIXED_GROUP_SIZE = 3
    LOBBY_MIN_WAIT_SECONDS = 1   # Minimum wait before forming a group (so first arrivers don’t leave before others join)
    LOBBY_WAIT_SECONDS_PART1 = 120   # Part 1: show wait-or-quit after this many seconds if still < 3 (e.g. 2 min)
    LOBBY_WAIT_SECONDS_PART2_3 = 60  # Parts 2–3: show wait-or-quit after this many seconds if still < 3 (e.g. 1 min)
    # Prolific return link when participant quits before matching (e.g. $1 compensation from lobby / early stages)
    PROLIFIC_RETURN_URL = 'https://app.prolific.com/submissions/complete?cc=CL4BO4RB'
    # Prolific show-up fee link when a part cannot be completed because others dropped out mid-experiment (results wait timeout).
    PROLIFIC_SHOWUP_FEE_URL = 'https://app.prolific.com/submissions/complete?cc=CL4BO4RB'

    # Part order: False = Part 1 No delegation, Part 2 Delegation (rule2nd). True = Part 1 Delegation, Part 2 No delegation.
    DELEGATION_FIRST = False

    PD_PAYOFFS = {
        ('A', 'A'): (70, 70),
        ('A', 'B'): (0, 100),
        ('B', 'A'): (100, 0),
        ('B', 'B'): (30, 30),
    }

    @staticmethod
    def get_part(round_number):
        """Map round_number (1–30) to part 1, 2, or 3. Rounds 1–10 → 1, 11–20 → 2, 21–30 → 3."""
        return (round_number - 1) // Constants.rounds_per_part + 1

    @staticmethod
    def part_no_delegation():
        """Part number shown in UI for the no-delegation block (e.g. Part 1 or Part 2 depending on DELEGATION_FIRST)."""
        return 2 if Constants.DELEGATION_FIRST else 1

    @staticmethod
    def part_delegation():
        """Part number shown in UI for the mandatory-delegation block."""
        return 1 if Constants.DELEGATION_FIRST else 2

    @staticmethod
    def is_mandatory_delegation_round(round_number):
        """True if this round is in the block where delegation is mandatory (Part 1 if DELEGATION_FIRST else Part 2)."""
        part = Constants.get_part(round_number)
        if Constants.DELEGATION_FIRST:
            return part == 1  # rounds 1-10 = delegation
        return part == 2  # rounds 11-20 = delegation


# =============================================================================
# Round-robin opponent assignment (used for N >= 3 batch groups)
# =============================================================================
def compute_round_robin_assignments(N_players, N_rounds=10):
    """
    Build round-robin opponent assignments for N_players over N_rounds.

    Returns: list of length N_players. result[i] = list of (opponent_0based_index, round_1based)
    for each round. Each player gets exactly one opponent per round; indices are 0-based for
    use with sorted_players[opp_idx]. Used by get_opponent_in_round and _opponent_for_export.
    """
    # 1-indexed as in user spec; then convert to 0-based at the end
    player_assignments = {p: [] for p in range(1, N_players + 1)}
    for r in range(1, N_rounds + 1):
        opponents = list(range(1, N_players + 1))
        for player in range(1, N_players + 1):
            for i in range(1, N_players):
                opponent = opponents[(player + i + r - 1) % N_players]
                if opponent != player:
                    player_assignments[player].append((opponent, r))
                    break
    # Convert to 0-based: result[i] = [(opp_0based, round_1based), ...]
    result = []
    for p in range(1, N_players + 1):
        result.append([(opp - 1, r) for (opp, r) in player_assignments[p]])
    return result


# Unused: was for batch lookup by id_in_subsession; grouping now uses set_group_matrix_for_released_batch only.
# def _batch_group_sorted_players(round_ss, batch_id_in_subsession):
#     """Return players in this round that belong to the batch, sorted by matching_group_position (1-based)."""
#     players = [p for p in round_ss.get_players() if p.id_in_subsession in batch_id_in_subsession]
#     return sorted(players, key=lambda p: p.participant.vars.get('matching_group_position', 0))


# Cache round-robin assignments by group size to avoid recomputing for every player in the same group.
_ROUND_ROBIN_CACHE = {}


def get_opponent_in_round(player, round_number):
    """
    Return the Player who is this player's opponent in the given round (for payoffs and results).

    Uses round-robin assignments when group size N >= 3; orders players by id_in_group so
    indices match compute_round_robin_assignments. Returns None for group size 0, 1, or 2.
    """
    me = player.in_round(round_number)
    # Fast path: when we form groups without set_group_matrix, use session-stored member list.
    gid = me.participant.vars.get("matching_group_id", -1)
    if gid is not None and gid >= 0:
        part = Constants.get_part(round_number)
        key = f"matching_group_members_part_{part}_{gid}"
        member_ids = player.session.vars.get(key)
        if member_ids and isinstance(member_ids, (list, tuple)) and len(member_ids) >= 3:
            if me.participant.id_in_session not in member_ids:
                return None
            round_ss = player.subsession.in_round(round_number)
            # Avoid ORM "IN" queries (oTree doesn't use Django's .objects). Filter in memory from this round's players.
            players = [p for p in round_ss.get_players() if p.participant.id_in_session in member_ids]
            if len(players) >= 3:
                players = sorted(players, key=lambda p: p.participant.vars.get("matching_group_position", 0))
                N = len(players)
                my_pos = me.participant.vars.get("matching_group_position", None)
                if not my_pos or my_pos < 1 or my_pos > N:
                    return None
                my_idx = my_pos - 1
                part_start = (part - 1) * Constants.rounds_per_part + 1
                round_in_part = round_number - part_start
                if N not in _ROUND_ROBIN_CACHE:
                    _ROUND_ROBIN_CACHE[N] = compute_round_robin_assignments(N, Constants.rounds_per_part)
                opp_idx, _ = _ROUND_ROBIN_CACHE[N][my_idx][round_in_part]
                if opp_idx is None or opp_idx < 0 or opp_idx >= N:
                    return None
                return players[opp_idx]
    group_players = list(me.group.get_players())
    N = len(group_players)
    if N == 0 or N == 1:
        return None
    if N == 2:
        return None  # No groups of 2; should not occur
    # N >= 3: round-robin with id_in_group order
    sorted_players = sorted(group_players, key=lambda p: p.id_in_group)
    if len(sorted_players) != N:
        return None
    my_idx = me.id_in_group - 1  # 1-based id_in_group -> 0-based index
    if my_idx < 0 or my_idx >= N:
        return None
    part = Constants.get_part(round_number)
    part_start = (part - 1) * Constants.rounds_per_part + 1
    round_in_part = round_number - part_start
    if round_in_part < 0 or round_in_part >= Constants.rounds_per_part:
        return None
    if N not in _ROUND_ROBIN_CACHE:
        _ROUND_ROBIN_CACHE[N] = compute_round_robin_assignments(N, Constants.rounds_per_part)
    assignments = _ROUND_ROBIN_CACHE[N]
    if round_in_part >= len(assignments[my_idx]):
        return None
    opp_idx, _ = assignments[my_idx][round_in_part]
    if opp_idx is None or opp_idx < 0 or opp_idx >= N:
        return None
    return sorted_players[opp_idx]


# =============================================================================
# UNUSED (commented out): group matrix rewriting
# =============================================================================
#
# We no longer rewrite oTree's group matrix (too slow in large sessions). Matching is handled by
# `matching_group_members_part_{part}_{gid}` in session.vars and per-participant vars.
#
# def set_group_matrix_for_released_batch(subsession, batch_players, part):
#     ...


# =============================================================================
# Subsession: session creation (no group matrix change; oTree uses one group of all)
# =============================================================================

class Subsession(BaseSubsession):
    def creating_session(self):
        """Run once per subsession. Round 1 only: set matching_group_id = -1 so everyone is 'not yet released'."""
        if self.round_number == 1:
            for p in self.get_players():
                p.participant.vars['matching_group_id'] = -1



# =============================================================================
# Group: payoff computation (round-robin for batch groups, 0 for waiting/fallback)
# =============================================================================

class Group(BaseGroup):
    def set_payoffs(self):
        from models_classes import set_payoffs_tg_batch_group

        set_payoffs_tg_batch_group(self)




# =============================================================================
# Player: form fields and helper methods
# =============================================================================

class Player(BasePlayer):
    """One row per participant per round. choice = A/B for PD; agent/human fields for delegation parts."""
    app_name = models.StringField(initial='rulebased_del1st')
    delegate_decision_optional_final = models.BooleanField()

    #NEW
    guess_opponent_delegated = models.StringField(
        choices=[
            ('yes', 'Yes, my opponent delegated their decisions'),
            ('no', 'No, my opponent did not delegate their decisions'),
        ],
        label="Based on your interaction, do you think your opponent delegated their decisions to an AI agent?",
        blank=True,
    )
    choice = models.StringField(
        choices=[('A', 'A'), ('B', 'B')],
        label="Please choose A or B",
        blank=True,
    )

    choice_first_mover = models.StringField(
        choices=[('A', 'A'), ('B', 'B')],
        label="If you are 1st mover this round, choose A or B",
        blank=True,
    )
    choice_second_mover = models.StringField(
        choices=[('A', 'A'), ('B', 'B')],
        label="If you are 2nd mover this round, choose A or B",
        blank=True,
    )
    role_assigned = models.StringField(
        choices=[('first', '1st mover'), ('second', '2nd mover')],
        blank=True,
    )
    guess_payoff = models.CurrencyField(blank=True)
    allocation = models.IntegerField(
        min=0,
        max=100,
        label="How much would you like to allocate to the other participant?",
        blank=True
    )
    
    final_allocations = models.LongStringField(blank=True)
    prolific_id = models.StringField()
    # Bot detection flag (written to DB). Set when attention checks indicate automated participation.
    bot_detected = models.BooleanField(initial=False)
    random_decisions = models.BooleanField(blank=True)
    random_payoff_part=models.IntegerField( blank=True, min=1, max=3 )

    # Tracks the number of failed comprehension attempts
    comprehension_attempts = models.IntegerField(initial=0) #new
    incorrect_answers = models.StringField(blank=True) #new
    agent_prog_allocation=models.StringField(blank=True) #new
    supervised_history = models.LongStringField(blank=True)
    supervised_dataset = models.LongStringField(blank=True)
    sample_cnt = models.IntegerField(blank=True)
    supervised_mean = models.FloatField(blank=True)
    supervised_last_generated_csv = models.LongStringField(blank=True)
    # Tracks whether the participant is excluded from the study
    is_excluded = models.BooleanField(initial=False)

    gender = models.StringField(
        choices=[
            ('male',        'Male'),
            ('female',      'Female'),
            ('nonbinary',   'Non-binary'),
            ('nosay',       'Prefer not to say'),
        ],
        label="How do you describe yourself?",
        widget=widgets.RadioSelect 
    )

    age = models.IntegerField(
        min=18, max=100,
        label="How old are you?",
    )

    occupation = models.StringField(
        max_length=100,
        label="What is your current main occupation?",
    )

    ai_use = models.StringField(
        choices=[
            ('never',       'Never'),
            ('monthly',     'A few times a month'),
            ('weekly',      'A few times a week'),
            ('daily',       'A few times a day'),
            ('constant',    'All the time'),
        ],
        label="How often do you interact with AI agents (e.g., ChatGPT)?",
        widget=widgets.RadioSelect 
    )

    task_difficulty = models.StringField(
        choices=[
            ('very_diff',   'Very difficult to understand'),
            ('diff',        'Difficult to understand'),
            ('neutral',     'Neutral'),
            ('easy',        'Easy to understand'),
            ('very_easy',   'Very easy to understand'),
        ],
        label="How would you rate the clarity of the experimental task?",
        widget=widgets.RadioSelect 
    )

    part_3_feedback = models.StringField(
        choices=[
            ('more_fun',   'You just had more fun that way.'),
            ('faster',        'You felt it would be faster that way.'),
            ('greedy',     'You thought you would make more money that way.'),
            ('utilitarian',        'You thought you would make better decisions that way.'),
            ('random',   'It was just random'),
            ('part_3_other',   'Other reason, specify:'),
        ],
        label="In Part 3, why did you (not) delegate? (Select the one that is closer to your reasons.)",
        widget=widgets.RadioSelect 
    )
    part_3_feedback_other = models.LongStringField(
    blank=True,
    label="Other reason, specify:",
    )

    part_4_feedback = models.StringField(
        choices=[
            ('expected_del_A',   'You expected the ones who delegate to play A.'),
            ('expected_no_del_A',   'You expected the ones who did not delegate to play A.'),
            ('same_action',        'You generally expected people to do the same as you did.'),
            ('opposite_action',     'You generally expected people to do the opposite that you did.'),
            ('random',   'It was just random'),
            ('part_4_other',   'Other reason, specify:'),
        ],
        label="In Part 4, what made you think that the other players were delegating (or not)?  (Select the one that is closer to your reasons.)",
        widget=widgets.RadioSelect 
    )
    part_4_feedback_other = models.LongStringField(
        blank=True,
        label="Other reason, specify:",
    )

    used_ai_or_bot = models.StringField(
        choices=[
            ('ai_did_everything', "Yes, I didn't even read the text; the AI did everything."),
            ('ai_advisor', 'Yes, as an advisor on what to do.'),
            ('ai_translate', 'Yes, to help me translate the task.'),
            ('no_distracted', 'No, but I was a bit distracted throughout the study.'),
            ('no_other_tabs', 'No, but I had some other tabs opened while waiting.'),
            ('no_focused', 'No, and I was fully focused on the study during the entire time.'),
        ],
        label="Did you use some type of AI agent or bot to answer our survey (apart from the ones provided to you in the experiment)? (Answer truthfully, your answer here will not impact your earnings.)",
        widget=widgets.RadioSelect,
    )


    feedback = models.LongStringField(
        blank=True,                # optional
        max_length=1000,
        label="Do you have any suggestions or comments about the experiment that you would like to share with the researchers? If yes, use the box below. (Optional)",
    )

    # Fields for comprehension test questions
    q1 = models.StringField(
        label="How many parts are there in this experiment?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q2 = models.StringField(
        label="How many rounds are there in each interactive task (Parts 1–3)?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q3 = models.StringField(
        label="In reference to the interactive tasks, in which part(s) will you make all decisions yourself?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q4 = models.StringField(
        label="In reference to the interactive tasks, in which part(s) will you delegate all decisions to an artificial delegate?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q5 = models.StringField(
        label="In Part 3, when do you decide whether to delegate or make decisions yourself?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q6 = models.StringField(
        label="If Player 1 chooses Option A and Player 2 chooses Option A, what are the earnings for both players?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q7 = models.StringField(
        label="If Player 1 chooses Option A and Player 2 chooses Option B, what are the earnings for both players?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q8 = models.StringField(
        label="If Player 1 chooses Option B and Player 2 chooses Option A, what are the earnings for both players?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q9 = models.StringField(
        label="If Player 1 chooses Option B and Player 2 chooses Option B, what are the earnings for both players?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q10 = models.StringField(
        label="What happens between each round of the interactive tasks (Parts 1–3)?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )

    # Mandatory delegation (Part 1)
    agent_decision_mandatory_delegation_round_1 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_delegation_round_2 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_delegation_round_3 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_delegation_round_4 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_delegation_round_5 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_delegation_round_6 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_delegation_round_7 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_delegation_round_8 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_delegation_round_9 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_delegation_round_10 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    agent_decision_mandatory_second_round_1 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    agent_decision_mandatory_second_round_2 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    agent_decision_mandatory_second_round_3 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    agent_decision_mandatory_second_round_4 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    agent_decision_mandatory_second_round_5 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    agent_decision_mandatory_second_round_6 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    agent_decision_mandatory_second_round_7 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    agent_decision_mandatory_second_round_8 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    agent_decision_mandatory_second_round_9 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    agent_decision_mandatory_second_round_10 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)

    #Track whether the participant chooses to delegate in Part 3
    delegate_decision_optional = models.BooleanField(
        label="Would you like to delegate your decisions to an AI agent for Part 3?",
        blank=False
    ) 

    #Human decisions (Part 2)
    human_decision_no_delegation_round_1 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_decision_no_delegation_round_2 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_decision_no_delegation_round_3 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_decision_no_delegation_round_4 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_decision_no_delegation_round_5 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_decision_no_delegation_round_6 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_decision_no_delegation_round_7 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_decision_no_delegation_round_8 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_decision_no_delegation_round_9 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_decision_no_delegation_round_10 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    human_second_no_delegation_round_1 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    human_second_no_delegation_round_2 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    human_second_no_delegation_round_3 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    human_second_no_delegation_round_4 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    human_second_no_delegation_round_5 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    human_second_no_delegation_round_6 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    human_second_no_delegation_round_7 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    human_second_no_delegation_round_8 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    human_second_no_delegation_round_9 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    human_second_no_delegation_round_10 = models.StringField(choices=[('A', 'A'), ('B', 'B')], blank=True)
    # Optional delegation (Part 3)
    decision_optional_delegation_round_1 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    decision_optional_delegation_round_2 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    decision_optional_delegation_round_3 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    decision_optional_delegation_round_4 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    decision_optional_delegation_round_5 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    decision_optional_delegation_round_6 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    decision_optional_delegation_round_7 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    decision_optional_delegation_round_8 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    decision_optional_delegation_round_9 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    decision_optional_delegation_round_10 = models.StringField(choices=[('A', 'A'), ('B', 'B')],blank=True)
    # Guessing (Part 3-4): one field per round
    guess_round_1  = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)
    guess_round_2  = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)
    guess_round_3  = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)
    guess_round_4  = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)
    guess_round_5  = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)
    guess_round_6  = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)
    guess_round_7  = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)
    guess_round_8  = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)
    guess_round_9  = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)
    guess_round_10 = models.StringField(choices=[('yes', 'Delegated'), ('no', 'Did not delegate')], blank=True)

    # per‑round payoff

    def get_agent_decision_mandatory(self, round_number):
        """Return the stored agent decision (A or B) for the given round in the mandatory-delegation part, or None."""
        field_name = f"agent_decision_mandatory_delegation_round_{round_number}"
        value = self.field_maybe_none(field_name)
        return value if value is not None else None

    def get_agent_decision_optional(self, round_number):
        """Return the stored agent decision for the given round in Part 3 (optional delegation). Raises if missing."""
        field_name = f"decision_optional_delegation_round_{round_number}"
        if hasattr(self, field_name):
            value = getattr(self, field_name)
            if value is None:
                raise ValueError(f"Agent allocation for {field_name} is None.")
            return value
        raise AttributeError(f"Agent allocation for {field_name} not found.")

    def get_part_data(self):
        """Return list of Player instances for all rounds in the current part (used for iteration)."""
        current_part = Constants.get_part(self.round_number)
        rounds = self.in_rounds(
            (current_part - 1) * Constants.rounds_per_part + 1,
            current_part * Constants.rounds_per_part
        )
        return rounds
    



# =============================================================================
# Custom export: opponent resolution and CSV generation
# =============================================================================

def _opponent_for_export(pr, r, round_data, rr_cache):
    """
    Return the opponent Player for participant pr in round r for the custom export.
    Uses pre-built round_data[r][group_id] = sorted_players and rr_cache for round-robin;
    no extra DB queries. Returns None if no opponent (group size <= 1 or invalid).
    """
    if r not in round_data:
        return None
    gid = getattr(pr, "group_id", None)
    if gid is None and getattr(pr, "group", None) is not None:
        gid = getattr(pr.group, "id", None)
    if gid is None:
        return None
    sorted_players = round_data[r].get(gid)
    if not sorted_players:
        return None
    N = len(sorted_players)
    if N <= 1:
        return None
    my_idx = next((i for i, p in enumerate(sorted_players) if p.id == pr.id), None)
    if my_idx is None or my_idx < 0 or my_idx >= N:
        return None
    if N == 2:
        return sorted_players[1 - my_idx]
    part = Constants.get_part(r)
    part_start = (part - 1) * Constants.rounds_per_part + 1
    round_in_part = r - part_start
    if round_in_part < 0 or round_in_part >= Constants.rounds_per_part:
        return None
    if N not in rr_cache:
        rr_cache[N] = compute_round_robin_assignments(N, Constants.rounds_per_part)
    assignments = rr_cache[N]
    if round_in_part >= len(assignments[my_idx]):
        return None
    opp_idx, _ = assignments[my_idx][round_in_part]
    if opp_idx is None or opp_idx < 0 or opp_idx >= N:
        return None
    return sorted_players[opp_idx]


def custom_export(players):
    """CSV custom export (shared implementation; matching-batch opponents, null-safe cells)."""
    from shared.delegation_custom_export import delegation_custom_export
    from shared.export_spec_factory import make_delegation_export_spec

    yield from delegation_custom_export(
        players,
        make_delegation_export_spec(__name__, Constants, compute_round_robin_assignments),
    )



# =============================================================================
# Lobby release and payoff runner (called from pages.Lobby and BatchWaitForGroup)
# =============================================================================

# def release_lobby_batch(subsession, batch_players, batch_id=0, part=1):
#     ...


def run_payoffs_for_matching_group(subsession, matching_group_id):
    """TG sequential payoffs for a released matching batch (grouping unchanged from PD)."""
    from shared.tg_payoffs import run_payoffs_for_matching_group_tg

    return run_payoffs_for_matching_group_tg(
        subsession,
        matching_group_id,
        Constants,
        compute_round_robin_assignments,
    )

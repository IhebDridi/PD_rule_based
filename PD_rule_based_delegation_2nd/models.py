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
import random
import sys
from collections import defaultdict

from models_classes import creating_session_mark_unmatched, set_payoffs_pd_batch_group

# Prefix for cache-miss / fallback logs (visible in terminal; use DEBUG or run with otree runserver).
RESULTS_DISPLAY_CACHE_LOG_PREFIX = "[results_display_cache]"


# =============================================================================
# Constants
# =============================================================================

class Constants(BaseConstants):
    name_in_url = 'exp_game121'
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
_BATCH_PLAYERS_CACHE = {}


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


def get_opponent_in_round_cached(player, round_number, round_players_cache):
    """
    Same as get_opponent_in_round but uses round_players_cache[round_number] instead of
    calling subsession.get_players() for that round. Use this when looking up opponents
    for many rounds in one request (e.g. Debriefing) to avoid N DB hits.
    round_players_cache: dict int -> list of Player (full list for that round from get_players()).
    """
    me = player.in_round(round_number)
    gid = me.participant.vars.get("matching_group_id", -1)
    if gid is not None and gid >= 0:
        part = Constants.get_part(round_number)
        key = f"matching_group_members_part_{part}_{gid}"
        member_ids = player.session.vars.get(key)
        if member_ids and isinstance(member_ids, (list, tuple)) and len(member_ids) >= 3:
            all_players_r = round_players_cache.get(round_number)
            if all_players_r is not None:
                players = [p for p in all_players_r if p.participant.id_in_session in member_ids]
                if len(players) >= 3:
                    players = sorted(
                        players,
                        key=lambda p: p.participant.vars.get("matching_group_position", 0),
                    )
                    N = len(players)
                    my_pos = me.participant.vars.get("matching_group_position", None)
                    if my_pos and 1 <= my_pos <= N:
                        my_idx = my_pos - 1
                        part_start = (part - 1) * Constants.rounds_per_part + 1
                        round_in_part = round_number - part_start
                        if N not in _ROUND_ROBIN_CACHE:
                            _ROUND_ROBIN_CACHE[N] = compute_round_robin_assignments(
                                N, Constants.rounds_per_part
                            )
                        opp_idx, _ = _ROUND_ROBIN_CACHE[N][my_idx][round_in_part]
                        if opp_idx is not None and 0 <= opp_idx < N:
                            return players[opp_idx]
    return get_opponent_in_round(player, round_number)


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
        creating_session_mark_unmatched(self)


# =============================================================================
# Group: payoff computation (round-robin for batch groups, 0 for waiting/fallback)
# =============================================================================

class Group(BaseGroup):
    def set_payoffs(self):
        set_payoffs_pd_batch_group(self)




# =============================================================================
# Player: form fields and helper methods
# =============================================================================

class Player(BasePlayer):
    """One row per participant per round. choice = A/B for PD; agent/human fields for delegation parts."""
    app_name = models.StringField(initial='rulebased_del2nd')
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
    )
    guess_payoff = models.CurrencyField(initial=0)
    allocation = models.IntegerField(
        min=0,
        max=100,
        label="How much would you like to allocate to the other participant?",
        blank=True
    )
    
    final_allocations = models.LongStringField()
    prolific_id = models.StringField()
    # Bot detection flag (written to DB). Set when attention checks indicate automated participation.
    bot_detected = models.BooleanField(initial=False)
    random_decisions = models.BooleanField(blank=True)
    random_payoff_part=models.IntegerField( blank=True, min=1, max=3 )

    # Tracks the number of failed comprehension attempts
    comprehension_attempts = models.IntegerField(initial=0) #new
    incorrect_answers = models.StringField(blank=True) #new
    agent_prog_allocation=models.StringField(initial='[]') #new
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
            ('faster',        'You felt it would be faster that way'),
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
        label="Do you have any suggestions or comments about the experiment that you would like to share with the researchers? If yes, use the box below.",
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
    q6 = models.StringField(
        label="If you choose Option A and the other player chooses Option A, what are your earnings in that round?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q7 = models.StringField(
        label="If you choose Option A and the other player chooses Option B, what are your earnings in that round?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q8 = models.StringField(
        label="If you choose Option B and the other player chooses Option A, what are your earnings in that round?",
        choices=['a', 'b', 'c', 'd'],
        blank=True
    )
    q9 = models.StringField(
        label="If you choose Option B and the other player chooses Option B, what are your earnings in that round?",
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
    part = Constants.get_part(r)
    part_start = (part - 1) * Constants.rounds_per_part + 1
    round_in_part = r - part_start
    if round_in_part < 0 or round_in_part >= Constants.rounds_per_part:
        return None

    # Fast path: use logical 3-person batch information if available.
    batch_gid = pr.participant.vars.get("matching_group_id", -1)
    if batch_gid is not None and batch_gid >= 0:
        session = pr.session
        key_members = f"matching_group_members_part_{part}_{batch_gid}"
        member_ids = session.vars.get(key_members)
        if member_ids and isinstance(member_ids, (list, tuple)) and len(member_ids) >= 3:
            cache_key = (session.code, part, batch_gid)
            players_start = _BATCH_PLAYERS_CACHE.get(cache_key)
            if not players_start:
                # Get the 3 Player objects for the first round of this part.
                first_round_ss = pr.subsession.in_round(part_start)
                players_start = [
                    p for p in first_round_ss.get_players()
                    if p.participant.id_in_session in member_ids
                ]
                players_start = sorted(
                    players_start,
                    key=lambda p: p.participant.vars.get("matching_group_position", 0),
                )
                if len(players_start) != 3:
                    return None
                _BATCH_PLAYERS_CACHE[cache_key] = players_start

            N = len(member_ids)
            if N not in rr_cache:
                rr_cache[N] = compute_round_robin_assignments(N, Constants.rounds_per_part)
            assignments = rr_cache[N]

            my_pos = pr.participant.vars.get("matching_group_position", None)
            if not my_pos or my_pos < 1 or my_pos > N:
                return None
            my_idx = my_pos - 1
            if round_in_part >= len(assignments[my_idx]):
                return None
            opp_idx, _ = assignments[my_idx][round_in_part]
            if opp_idx is None or opp_idx < 0 or opp_idx >= N:
                return None
            opp_player_start = players_start[opp_idx]
            return opp_player_start.in_round(r)

    # Fallback: use oTree's group_id-based grouping if batch info is missing.
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
    if N not in rr_cache:
        rr_cache[N] = compute_round_robin_assignments(N, Constants.rounds_per_part)
    assignments = rr_cache[N]
    if round_in_part >= len(assignments[my_idx]):
        return None
    opp_idx, _ = assignments[my_idx][round_in_part]
    if opp_idx is None or opp_idx < 0 or opp_idx >= N:
        return None
    return sorted_players[opp_idx]


# def custom_export2(players):
#     """
#     oTree custom export: yield CSV rows (header first, then one row per participant).
#     Builds round_data and rr_cache once, then uses _opponent_for_export for each round.
#     Handles quit_to_prolific (BonusPaymentTotal=1.0), random_payoff_part, and Part 4 guessing.
#     """
#     from collections import defaultdict

#     by_participant = defaultdict(list)
#     by_round = defaultdict(list)
#     for p in players:
#         by_participant[p.participant.code].append(p)
#         by_round[p.round_number].append(p)

#     # Prebuild round_data[r] = { group_id: sorted_players } to avoid per-row DB calls
#     round_data = {}
#     for r in range(1, Constants.num_rounds + 1):
#         if r not in by_round:
#             continue
#         by_group = defaultdict(list)
#         for p in by_round[r]:
#             gid = getattr(p, "group_id", None) or (getattr(p.group, "id", None) if getattr(p, "group", None) else None)
#             if gid is not None:
#                 by_group[gid].append(p)
#         round_data[r] = {
#             gid: sorted(plist, key=lambda p: p.participant.vars.get("matching_group_position", 0))
#             for gid, plist in by_group.items()
#         }
#     rr_cache = {}

#     header = [
#         "Condition", "ProlificID", "Session", "Group", "PlayerID", "IsSimulated",
#         "Gender", "Age", "Occupation", "AIuse", "TaskDifficulty",
#         "Part3Feedback", "Part3FeedbackOther", "Part4Feedback", "Part4FeedbackOther", "FeedbackFreeText",
#     ]
#     for r in range(1, 31):
#         header += [f"Round{r}Decision", f"Round{r}CoplayerID", f"Round{r}CoplayerDecision",
#                    f"Round{r}Ecoins", f"Round{r}PlayerAgent", f"Round{r}CoPlayerAgent"]
#     for i in range(1, 11):
#         header += [f"Guess{i}", f"TruthGuess{i}", f"EarningsGuess{i}Dollars"]
#     header += [
#         "TotalEarningsPart1Ecoins", "TotalEarningsPart2Ecoins", "TotalEarningsPart3Ecoins",
#         "PartChosenBonus", "TotalEarningsParts123Dollars", "TotalEarningsPart4Dollars", "BonusPaymentTotal",
#         "SupervisedListChoicesDelegation", "SupervisedListChoicesOptional",
#         "GoalListChoicesDelegation", "GoalListChoicesOptional", "LLMchatDelegation", "LLMchatOptional", "GameUsed",
#     ]

#     yield header

#     pvars = lambda p, k, default=None: p.participant.vars.get(k, default)
#     fld = lambda p, k: p.field_maybe_none(k)

#     for code, rounds in by_participant.items():
#         try:
#             rounds = sorted(rounds, key=lambda p: p.round_number)
#             p0 = rounds[0]
#             row = dict.fromkeys(header, "")

#             row["Condition"] = "rule2nd"
#             row["ProlificID"] = "SIMULATED" if pvars(p0, "is_simulated") else fld(p0, "prolific_id")
#             row["Session"] = p0.session.code
#             row["Group"] = pvars(p0, "matching_group_id")
#             row["PlayerID"] = pvars(p0, "matching_group_position")
#             row["IsSimulated"] = 1 if pvars(p0, "is_simulated") else 0
#             p_last = rounds[-1] if rounds else p0
#             row["Gender"] = fld(p_last, "gender")
#             row["Age"] = fld(p_last, "age")
#             row["Occupation"] = fld(p_last, "occupation")
#             row["AIuse"] = fld(p_last, "ai_use")
#             row["TaskDifficulty"] = fld(p_last, "task_difficulty")
#             row["Part3Feedback"] = fld(p_last, "part_3_feedback")
#             row["Part3FeedbackOther"] = fld(p_last, "part_3_feedback_other")
#             row["Part4Feedback"] = fld(p_last, "part_4_feedback")
#             row["Part4FeedbackOther"] = fld(p_last, "part_4_feedback_other")
#             row["FeedbackFreeText"] = fld(p_last, "feedback")

#             part_totals = [0.0, 0.0, 0.0]
#             for pr in rounds:
#                 r = pr.round_number
#                 other = _opponent_for_export(pr, r, round_data, rr_cache)
#                 row[f"Round{r}Decision"] = fld(pr, "choice") if fld(pr, "choice") is not None else ""
#                 pay_raw = pr.payoff or 0
#                 try:
#                     pay_float = float(pay_raw)
#                 except (TypeError, ValueError):
#                     pay_float = 0.0
#                 # Export per-round payoff in raw Ecoins (e.g. 30, 70, 100).
#                 try:
#                     row[f"Round{r}Ecoins"] = int(pay_float)
#                 except (TypeError, ValueError):
#                     row[f"Round{r}Ecoins"] = 0
#                 if other:
#                     row[f"Round{r}CoplayerDecision"] = fld(other, "choice") if fld(other, "choice") is not None else ""
#                     pos = pvars(other, "matching_group_position")
#                     if pos is not None and pos != "" and pos != -1:
#                         row[f"Round{r}CoplayerID"] = str(pos)
#                     else:
#                         row[f"Round{r}CoplayerID"] = str(getattr(other.participant, "id_in_session", "") or "")
#                 else:
#                     row[f"Round{r}CoplayerDecision"] = ""
#                     row[f"Round{r}CoplayerID"] = ""
#                 # Label which rounds are delegated vs. human, using the actual treatment and decisions:
#                 # - Parts 1–2: Constants.is_mandatory_delegation_round(r) → everyone uses the rule agent in that block.
#                 # - Part 3 (optional delegation): use each player's own delegate_decision_optional flag.
#                 part = Constants.get_part(r)
#                 if part in (1, 2):
#                     agent_self = "rule" if Constants.is_mandatory_delegation_round(r) else "no-agent"
#                 else:
#                     delegated_self = fld(pr, "delegate_decision_optional")
#                     agent_self = "rule" if delegated_self else "no-agent"

#                 if other:
#                     if part in (1, 2):
#                         agent_other = "rule" if Constants.is_mandatory_delegation_round(r) else "no-agent"
#                     else:
#                         delegated_other = fld(other, "delegate_decision_optional")
#                         agent_other = "rule" if delegated_other else "no-agent"
#                 else:
#                     agent_other = ""

#                 row[f"Round{r}PlayerAgent"] = agent_self
#                 row[f"Round{r}CoPlayerAgent"] = agent_other
#                 if r <= 10:
#                     part_totals[0] += pay_float
#                 elif r <= 20:
#                     part_totals[1] += pay_float
#                 else:
#                     part_totals[2] += pay_float

#             # Store per-part totals in raw Ecoins (0–1000), since the column name is *Ecoins.
#             for i, part_key in enumerate(
#                 ["TotalEarningsPart1Ecoins", "TotalEarningsPart2Ecoins", "TotalEarningsPart3Ecoins"],
#                 start=1,
#             ):
#                 try:
#                     row[part_key] = int(part_totals[i - 1])
#                 except (TypeError, ValueError):
#                     row[part_key] = 0

#             n_rounds = len(rounds)
#             for i in range(1, 11):
#                 idx = 19 + i
#                 pr = rounds[idx] if idx < n_rounds else None
#                 if pr is None:
#                     continue
#                 other = _opponent_for_export(pr, 20 + i, round_data, rr_cache)
#                 row[f"Guess{i}"] = 1 if fld(pr, "guess_opponent_delegated") == "yes" else 0
#                 row[f"TruthGuess{i}"] = 1 if (other and fld(other, "delegate_decision_optional")) else 0
#                 # Guess earnings: store in dollars (e.g. cu=10 → 0.1 dollars).
#                 gpay = fld(pr, "guess_payoff") or 0
#                 try:
#                     gpay_float = float(gpay)
#                 except (TypeError, ValueError):
#                     gpay_float = 0.0
#                 row[f"EarningsGuess{i}Dollars"] = round(gpay_float / 100.0, 4)

#             part_chosen = fld(p_last, "random_payoff_part")
#             _float = lambda x: float(x) if x is not None else 0.0
#             if pvars(p0, "quit_to_prolific"):
#                 row["PartChosenBonus"] = "quit"
#                 row["TotalEarningsParts123Dollars"] = 0.0
#                 row["TotalEarningsPart4Dollars"] = 0.0
#                 row["BonusPaymentTotal"] = 1.0
#             elif part_chosen in (1, 2, 3):
#                 ecoins = _float(part_totals[part_chosen - 1])
#                 row["PartChosenBonus"] = part_chosen
#                 row["TotalEarningsParts123Dollars"] = round(ecoins * 0.001, 4)
#                 # Guess earnings already stored in dollars per trial; sum directly.
#                 part4_dollars = sum(
#                     _float(row.get(f"EarningsGuess{i}Dollars")) for i in range(1, 11)
#                 )
#                 row["TotalEarningsPart4Dollars"] = round(part4_dollars, 4)
#                 row["BonusPaymentTotal"] = round(row["TotalEarningsParts123Dollars"] + row["TotalEarningsPart4Dollars"], 4)
#             else:
#                 row["PartChosenBonus"] = part_chosen if part_chosen is not None else ""
#                 row["TotalEarningsParts123Dollars"] = 0.0
#                 part4_dollars = sum(
#                     _float(row.get(f"EarningsGuess{i}Dollars")) for i in range(1, 11)
#                 )
#                 row["TotalEarningsPart4Dollars"] = round(part4_dollars, 4)
#                 row["BonusPaymentTotal"] = round(row["TotalEarningsPart4Dollars"], 4)

#             for k in ("SupervisedListChoicesDelegation", "SupervisedListChoicesOptional", "GoalListChoicesDelegation",
#                       "GoalListChoicesOptional", "LLMchatDelegation", "LLMchatOptional"):
#                 row[k] = ""
#             row["GameUsed"] = "PD"

#             yield [row[h] for h in header]
#         except Exception:
#             continue


def custom_export(players):
    """
    Variant of custom_export with:
    - All *Ecoins columns in raw Ecoins (0–100 per round, 0–1000 per part).
    - All *Dollars columns in dollars.
    - No per-round PlayerAgent / CoPlayerAgent columns.
    - Additional columns:
        * DelegatedPart1, DelegatedPart2, DelegatedPart3 (0 = no, 1 = yes)
        * Agent: high-level agent class ("no-agent", "rule", "super", "goal", "llm").
    """
    from collections import defaultdict

    by_participant = defaultdict(list)
    by_round = defaultdict(list)
    for p in players:
        by_participant[p.participant.code].append(p)
        by_round[p.round_number].append(p)

    # Prebuild round_data[r] = { group_id: sorted_players } to avoid per-row DB calls
    round_data = {}
    for r in range(1, Constants.num_rounds + 1):
        if r not in by_round:
            continue
        by_group = defaultdict(list)
        for p in by_round[r]:
            gid = getattr(p, "group_id", None)
            if gid is None:
                try:
                    g = getattr(p, "group", None)
                    gid = getattr(g, "id", None) if g is not None else None
                except Exception:
                    gid = None
            if gid is not None:
                by_group[gid].append(p)
        round_data[r] = {
            gid: sorted(plist, key=lambda p: p.participant.vars.get("matching_group_position", 0))
            for gid, plist in by_group.items()
        }
    rr_cache = {}

    header = [
        "Condition",
        "ProlificID",
        "Session",
        "Group",
        "PlayerID",
        "IsSimulated",
        "Gender",
        "Age",
        "Occupation",
        "AIuse",
        "TaskDifficulty",
        "Part3Feedback",
        "Part3FeedbackOther",
        "Part4Feedback",
        "Part4FeedbackOther",
        "UsedAiOrBot",
        "FeedbackFreeText",
    ]
    for r in range(1, 31):
        header += [
            f"Round{r}Decision",
            f"Round{r}CoplayerID",
            f"Round{r}CoplayerDecision",
            f"Round{r}Ecoins",
        ]
    for i in range(1, 11):
        header += [f"Guess{i}", f"TruthGuess{i}", f"EarningsGuess{i}Dollars"]
    # New high-level delegation / agent columns
    header += ["DelegatedPart1", "DelegatedPart2", "DelegatedPart3", "Agent"]
    header += [
        "TotalEarningsPart1Ecoins",
        "TotalEarningsPart2Ecoins",
        "TotalEarningsPart3Ecoins",
        "PartChosenBonus",
        "TotalEarningsParts123Dollars",
        "TotalEarningsPart4Dollars",
        "BonusPaymentTotal",
        "SupervisedListChoicesDelegation",
        "SupervisedListChoicesOptional",
        "GoalListChoicesDelegation",
        "GoalListChoicesOptional",
        "LLMchatDelegation",
        "LLMchatOptional",
        "GameUsed",
    ]

    yield header

    pvars = lambda p, k, default=None: p.participant.vars.get(k, default)
    fld = lambda p, k: p.field_maybe_none(k)

    def _pay_export_amount(pay_raw):
        """Convert oTree Currency / numeric payoff to float for export (avoids TypeError on some types)."""
        if pay_raw is None:
            return 0.0
        amt = getattr(pay_raw, "amount", pay_raw)
        try:
            return float(amt)
        except (TypeError, ValueError):
            return 0.0

    def _safe_opponent_for_export(pr, r):
        try:
            gid = pvars(pr, "matching_group_id", -1)
            has_real = gid is not None and gid >= 0
            if not has_real:
                return None
            return _opponent_for_export(pr, r, round_data, rr_cache)
        except Exception:
            return None

    def _safe_fld(p, name):
        try:
            return fld(p, name)
        except Exception:
            return None

    def _agent_label(condition: str, app_name: str) -> str:
        """Map condition/app_name to a coarse agent label."""
        text = f"{condition or ''} {app_name or ''}".lower()
        if "llm" in text:
            return "llm"
        if "super" in text:
            return "super"
        if "goal" in text:
            return "goal"
        if "rule" in text:
            return "rule"
        return "no-agent"

    for code, rounds in by_participant.items():
        try:
            rounds = sorted(rounds, key=lambda p: p.round_number)
            if not rounds:
                continue
            p0 = rounds[0]
            is_simulated = bool(pvars(p0, "is_simulated"))
            prolific_id = _safe_fld(p0, "prolific_id")
            # Drop ghost/unmatched export rows (typically placeholders with no prolific ID and no matching group).
            if (not is_simulated) and (not prolific_id):
                continue
            row = dict.fromkeys(header, "")

            row["Condition"] = "rule1st" if Constants.DELEGATION_FIRST else "rule2nd"
            row["ProlificID"] = (
                "SIMULATED" if is_simulated else (prolific_id or "")
            )
            row["Session"] = getattr(getattr(p0, "session", None), "code", "") or ""
            row["Group"] = pvars(p0, "matching_group_id")
            row["PlayerID"] = pvars(p0, "matching_group_position")
            row["IsSimulated"] = 1 if is_simulated else 0
            p_last = rounds[-1] if rounds else p0
            row["Gender"] = _safe_fld(p_last, "gender")
            row["Age"] = _safe_fld(p_last, "age")
            row["Occupation"] = _safe_fld(p_last, "occupation")
            row["AIuse"] = _safe_fld(p_last, "ai_use")
            row["TaskDifficulty"] = _safe_fld(p_last, "task_difficulty")
            row["Part3Feedback"] = _safe_fld(p_last, "part_3_feedback")
            row["Part3FeedbackOther"] = _safe_fld(p_last, "part_3_feedback_other")
            row["Part4Feedback"] = _safe_fld(p_last, "part_4_feedback")
            row["Part4FeedbackOther"] = _safe_fld(p_last, "part_4_feedback_other")
            row["UsedAiOrBot"] = _safe_fld(p_last, "used_ai_or_bot")
            row["FeedbackFreeText"] = _safe_fld(p_last, "feedback")

            part_totals = [0.0, 0.0, 0.0]
            for pr in rounds:
                r = pr.round_number
                other = _safe_opponent_for_export(pr, r)
                choice_val = _safe_fld(pr, "choice")
                row[f"Round{r}Decision"] = choice_val if choice_val is not None else ""
                pay_float = _pay_export_amount(getattr(pr, "payoff", None))
                # Per-round payoff exported as raw Ecoins integer.
                try:
                    row[f"Round{r}Ecoins"] = int(pay_float)
                except (TypeError, ValueError):
                    row[f"Round{r}Ecoins"] = 0

                if other:
                    oc = _safe_fld(other, "choice")
                    row[f"Round{r}CoplayerDecision"] = oc if oc is not None else ""
                    pos = pvars(other, "matching_group_position")
                    if pos is not None and pos != "" and pos != -1:
                        row[f"Round{r}CoplayerID"] = str(pos)
                    else:
                        row[f"Round{r}CoplayerID"] = str(
                            getattr(other.participant, "id_in_session", "") or ""
                        )
                else:
                    row[f"Round{r}CoplayerDecision"] = ""
                    row[f"Round{r}CoplayerID"] = ""

                if r <= 10:
                    part_totals[0] += pay_float
                elif r <= 20:
                    part_totals[1] += pay_float
                else:
                    part_totals[2] += pay_float

            # Store per-part totals in raw Ecoins (0–1000).
            for i, part_key in enumerate(
                [
                    "TotalEarningsPart1Ecoins",
                    "TotalEarningsPart2Ecoins",
                    "TotalEarningsPart3Ecoins",
                ],
                start=1,
            ):
                try:
                    row[part_key] = int(part_totals[i - 1])
                except (TypeError, ValueError):
                    row[part_key] = 0

            n_rounds = len(rounds)

            for i in range(1, 11):
                idx = 19 + i
                pr = rounds[idx] if idx < n_rounds else None
                if pr is None:
                    continue

                row[f"Guess{i}"] = 1 if _safe_fld(pr, "guess_opponent_delegated") == "yes" else 0

                other = _safe_opponent_for_export(pr, 20 + i)
                row[f"TruthGuess{i}"] = 1 if (
                    other and _safe_fld(other, "delegate_decision_optional")
                ) else 0
                gpay_float = _pay_export_amount(_safe_fld(pr, "guess_payoff"))
                # Export guess earnings in dollars (10 → 0.1).
                row[f"EarningsGuess{i}Dollars"] = round(gpay_float / 100.0, 4)

            # High-level delegation per part
            if Constants.DELEGATION_FIRST:
                delegated_part1 = 1
                delegated_part2 = 0
            else:
                delegated_part1 = 0
                delegated_part2 = 1
            delegated_part3 = 0
            for pr in rounds:
                if Constants.get_part(pr.round_number) == 3:
                    if _safe_fld(pr, "delegate_decision_optional"):
                        delegated_part3 = 1
                        break

            row["DelegatedPart1"] = delegated_part1
            row["DelegatedPart2"] = delegated_part2
            row["DelegatedPart3"] = delegated_part3
            row["Agent"] = _agent_label(row["Condition"], _safe_fld(p0, "app_name"))

            part_chosen = _safe_fld(p_last, "random_payoff_part")
            if isinstance(part_chosen, str) and part_chosen.strip().isdigit():
                part_chosen = int(part_chosen.strip())
            _float = lambda x: float(x) if x is not None else 0.0
            if pvars(p0, "quit_to_prolific"):
                row["PartChosenBonus"] = "quit"
                row["TotalEarningsParts123Dollars"] = 0.0
                row["TotalEarningsPart4Dollars"] = 0.0
                row["BonusPaymentTotal"] = 1.0
            elif part_chosen in (1, 2, 3):
                ecoins = _float(part_totals[part_chosen - 1])
                row["PartChosenBonus"] = part_chosen
                row["TotalEarningsParts123Dollars"] = round(ecoins * 0.001, 4)
                # Guess earnings already stored in dollars; sum directly.
                part4_dollars = sum(
                    _float(row.get(f"EarningsGuess{i}Dollars")) for i in range(1, 11)
                )
                row["TotalEarningsPart4Dollars"] = round(part4_dollars, 4)
                row["BonusPaymentTotal"] = round(
                    row["TotalEarningsParts123Dollars"] + row["TotalEarningsPart4Dollars"],
                    4,
                )
            else:
                row["PartChosenBonus"] = part_chosen if part_chosen is not None else ""
                row["TotalEarningsParts123Dollars"] = 0.0
                part4_dollars = sum(
                    _float(row.get(f"EarningsGuess{i}Dollars")) for i in range(1, 11)
                )
                row["TotalEarningsPart4Dollars"] = round(part4_dollars, 4)
                row["BonusPaymentTotal"] = round(row["TotalEarningsPart4Dollars"], 4)

            for k in (
                "SupervisedListChoicesDelegation",
                "SupervisedListChoicesOptional",
                "GoalListChoicesDelegation",
                "GoalListChoicesOptional",
                "LLMchatDelegation",
                "LLMchatOptional",
            ):
                row[k] = ""
            row["GameUsed"] = __name__.split("_", 1)[0].upper()

            yield [row[h] for h in header]
        except Exception as e:
            print(
                f"custom_export row failed participant_code={code!r}: {type(e).__name__}: {e}",
                file=sys.stderr,
                flush=True,
            )
            yield [f"ERROR: {type(e).__name__}: {e}"] + [""] * (len(header) - 1)

# =============================================================================
# Lobby release and payoff runner (called from pages.Lobby and BatchWaitForGroup)
# =============================================================================

# def release_lobby_batch(subsession, batch_players, batch_id=0, part=1):
#     ...


def _log_cache_miss(context, participant_id, reason, debug_extra=None):
    """Signal in terminal / debug that the results-display cache was not used (fallback to DB)."""
    msg = f"{RESULTS_DISPLAY_CACHE_LOG_PREFIX} FAILED context={context} participant_id={participant_id} reason={reason}"
    if debug_extra:
        msg += f" debug={debug_extra}"
    print(msg, file=sys.stderr, flush=True)


def get_results_display_from_cache(participant, part):
    """
    Return list of round dicts for the given part from participant.vars['results_display_cache'].
    Each dict has: round (1-based), my_choice, other_choice, payoff; part 3 also has other_delegated.
    Returns None if cache missing, wrong part, or invalid (length != 10).
    """
    try:
        cache = participant.vars.get("results_display_cache")
        if not cache or not isinstance(cache, dict):
            return None
        part_data = cache.get(f"part_{part}")
        if not part_data or not isinstance(part_data, list) or len(part_data) != Constants.rounds_per_part:
            return None
        return part_data
    except Exception:
        return None


def _build_results_display_cache_for_part(players_start, assignments, current_part, start, end):
    """
    Build per-player display cache for the current part (10 rounds).
    players_start: list of 3 Player objects (first round of part), sorted by matching_group_position.
    assignments: round-robin assignments for N=3.
    Returns list of 3 lists; each inner list has 10 dicts: round, my_choice, other_choice, payoff[, other_delegated].
    """
    part_start = (current_part - 1) * Constants.rounds_per_part + 1
    cache_by_player = [[] for _ in range(3)]
    for r in range(start, end + 1):
        round_in_part = r - part_start
        players_r = [p0.in_round(r) for p0 in players_start]
        for i, p in enumerate(players_r):
            opp_idx, _ = assignments[i][round_in_part]
            opp = players_r[opp_idx] if opp_idx is not None else None
            raw_payoff = getattr(p.payoff, "amount", p.payoff) if p.payoff is not None else 0
            try:
                payoff_int = int(raw_payoff)
            except (TypeError, ValueError):
                payoff_int = 0
            entry = {
                "round": round_in_part + 1,
                "my_choice": p.field_maybe_none("choice"),
                "other_choice": opp.field_maybe_none("choice") if opp else None,
                "payoff": payoff_int,
            }
            if current_part == 3:
                entry["other_delegated"] = bool(opp and opp.field_maybe_none("delegate_decision_optional"))
            cache_by_player[i].append(entry)
    return cache_by_player


def run_payoffs_for_matching_group(subsession, matching_group_id):
    """
    Run Group.set_payoffs for every round in the current part, but only for the group whose
    players all have the given matching_group_id. Waits until all 3 players have submitted
    choices for all rounds in the part before running payoffs (avoids None opponent choices
    when many bots/participants run concurrently).
    """
    rnd = subsession.round_number
    current_part = Constants.get_part(rnd)
    if current_part == 1:
        start, end = 1, 10
    elif current_part == 2:
        start, end = 11, 20
    elif current_part == 3:
        start, end = 21, 30
    else:
        return
    run_key = f"payoffs_run_matching_group_{matching_group_id}_part_{current_part}"
    if subsession.session.vars.get(run_key):
        return True
    # Final-boundary fail-open: at round 30, do not block forever on missing choices.
    # Missing choices are already handled below as zero payoff per round.
    allow_incomplete_choices = (current_part == 3 and rnd == 30)
    # Fast path: if we have the 3 member ids stored, compute payoffs directly without rewriting group matrix.
    key = f"matching_group_members_part_{current_part}_{matching_group_id}"
    member_ids = subsession.session.vars.get(key)
    if member_ids and isinstance(member_ids, (list, tuple)) and len(member_ids) >= 3:
        # Identify the 3 Player objects once (from the first round of the part).
        first_round_ss = subsession.in_round(start)
        players_start = [p for p in first_round_ss.get_players() if p.participant.id_in_session in member_ids]
        if len(players_start) != 3:
            return
        players_start = sorted(players_start, key=lambda p: p.participant.vars.get("matching_group_position", 0))

        def _all_choices_ready_for_three():
            """Check only the 3 relevant players (avoid scanning 500 players each round)."""
            for r in range(start, end + 1):
                for p0 in players_start:
                    pr = p0.in_round(r)
                    if pr.field_maybe_none("choice") is None:
                        return False
            return True

        # Fast exit: try again on next wait-page refresh instead of blocking this worker.
        if (not _all_choices_ready_for_three()) and (not allow_incomplete_choices):
            return False

        # Compute payoffs round-by-round using round-robin within these 3 players.
        N = len(member_ids)
        if N not in _ROUND_ROBIN_CACHE:
            _ROUND_ROBIN_CACHE[N] = compute_round_robin_assignments(N, Constants.rounds_per_part)
        assignments = _ROUND_ROBIN_CACHE[N]
        for r in range(start, end + 1):
            part_start_round = (current_part - 1) * Constants.rounds_per_part + 1
            round_in_part = r - part_start_round
            # Fetch just these 3 players for round r.
            players_r = [p0.in_round(r) for p0 in players_start]
            for i, p in enumerate(players_r):
                opp_idx, _ = assignments[i][round_in_part]
                opp = players_r[opp_idx] if opp_idx is not None else None
                c1 = p.field_maybe_none("choice")
                c2 = opp.field_maybe_none("choice") if opp else None
                if c1 is None or c2 is None:
                    p.payoff = cu(0)
                else:
                    pay = Constants.PD_PAYOFFS.get((c1, c2))
                    p.payoff = cu(pay[0]) if pay is not None else cu(0)

        # Write results-display cache for the group of 3 (so Results/Debriefing read from cache, not DB).
        try:
            cache_by_player = _build_results_display_cache_for_part(
                players_start, assignments, current_part, start, end
            )
            for i, p in enumerate(players_start):
                existing = p.participant.vars.get("results_display_cache") or {}
                if not isinstance(existing, dict):
                    existing = {}
                existing[f"part_{current_part}"] = cache_by_player[i]
                p.participant.vars["results_display_cache"] = existing
        except Exception as e:
            _log_cache_miss("run_payoffs_write", getattr(players_start[0].participant, "id", None), str(e), debug_extra=str(e))
        subsession.session.vars[run_key] = True
        return True
    # Find the group (same 3 players in every round)
    round_ss = subsession.in_round(start)
    all_players = list(round_ss.get_players())
    by_group = defaultdict(list)
    for p in all_players:
        by_group[p.group_id].append(p)
    players_in_group = None
    group = None
    for group_id, players in by_group.items():
        if len(players) < 3:
            continue
        if not all(p.participant.vars.get('matching_group_id') == matching_group_id for p in players):
            continue
        players_in_group = players
        group = players[0].group
        break
    if not players_in_group or not group:
        return
    participants = [p.participant for p in players_in_group]
    required = 3 * (end - start + 1)  # 3 players × 10 rounds

    def _all_choices_ready():
        """Readiness check for 3 players only (avoid scanning whole round player lists)."""
        players_start = sorted(players_in_group, key=lambda p: p.participant.vars.get("matching_group_position", 0))
        for r in range(start, end + 1):
            for p0 in players_start:
                pr = p0.in_round(r)
                if pr.field_maybe_none("choice") is None:
                    return False
        return True

    # Fast exit: try again on next wait-page refresh instead of blocking this worker.
    if (not _all_choices_ready()) and (not allow_incomplete_choices):
        return False
    for r in range(start, end + 1):
        round_ss = subsession.in_round(r)
        all_players_r = list(round_ss.get_players())
        by_group_r = defaultdict(list)
        for p in all_players_r:
            by_group_r[p.group_id].append(p)
        for group_id, players in by_group_r.items():
            if len(players) < 3:
                continue
            if not all(p.participant.vars.get('matching_group_id') == matching_group_id for p in players):
                continue
            players[0].group.set_payoffs()
            break
    subsession.session.vars[run_key] = True
    return True


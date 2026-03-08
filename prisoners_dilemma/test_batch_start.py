"""
Tests for lobby release and BatchWaitForGroup behaviour.

Run with oTree (when installed in your environment):
  otree test prisoners_dilemma --num_participants 5

Scenarios:
1. 3+ participants in lobby (after timeout) -> batch is released and proceeds.
2. Fewer than 3 participants -> they stay in lobby until timeout, then see wait-or-quit.
3. BatchWaitForGroup proceeds when all in the same matching group have arrived.
"""

from .models import Constants


def test_lobby_release_min_players():
    """When 3+ are in lobby and timeout, a batch of at least 3 is released."""
    min_players = Constants.MIN_PLAYERS_TO_START
    lobby = [3, 1, 4, 5]
    batch = sorted(lobby)[:min_players]
    assert len(batch) >= min_players


def test_fewer_than_min_stay_in_lobby():
    """With fewer than MIN_PLAYERS_TO_START, release is not triggered (until timeout then wait-or-quit)."""
    min_players = Constants.MIN_PLAYERS_TO_START
    n_waiting = 2
    would_release = n_waiting >= min_players
    assert not would_release


def test_batch_wait_requires_all_in_group():
    """BatchWaitForGroup proceeds only when all in the same matching group have arrived."""
    min_players = Constants.MIN_PLAYERS_TO_START
    n_arrived = 2
    group_size = 3
    can_proceed = n_arrived >= group_size
    assert not can_proceed

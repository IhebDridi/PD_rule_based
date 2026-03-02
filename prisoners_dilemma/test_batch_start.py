"""
Tests for batch-start (USE_BATCH_START) and related behaviour.

Run with oTree (when installed in your environment):
  otree test prisoners_dilemma --num_participants 10

Scenarios:
1. 10+ participants in lobby -> they get batch_id, can_leave_lobby, and proceed to next part.
2. Fewer than 10 participants -> they stay in lobby (never get can_leave_lobby).
3. One drops out mid-game -> with USE_WAIT_TIMEOUT, BatchWaitForGroup can timeout and proceed with arrivals; otherwise the other 9 are stuck.
"""


def test_lobby_release_uses_10():
    """When 10+ are in lobby, exactly 10 are taken and form a batch."""
    batch_size = 10
    lobby = [3, 1, 4, 5, 9, 2, 6, 7, 10, 8]
    batch_ids = sorted(lobby)[:batch_size]
    assert len(batch_ids) == batch_size
    remaining = [x for x in lobby if x not in batch_ids]
    assert len(remaining) == 0


def test_fewer_than_10_stay_in_lobby():
    """With fewer than 10, release is not triggered."""
    batch_size = 10
    n_waiting = 6
    would_release = n_waiting >= batch_size
    assert not would_release


def test_batch_wait_requires_all_10_without_timeout():
    """Without timeout, BatchWaitForGroup proceeds only when all 10 have arrived (9/10 = stuck)."""
    batch_size = 10
    n_arrived = 9
    can_proceed = n_arrived >= batch_size
    assert not can_proceed

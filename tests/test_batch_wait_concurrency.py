"""Tests for batch-wait pool draining and lock key stability."""

from shared.session_part_lock import advisory_lock_id, normalize_pool_ids, pop_next_trio_ids


def test_normalize_pool_dedupes_and_sorts():
    assert normalize_pool_ids([3, 1, 2, 2, 1]) == [1, 2, 3]


def test_pop_next_trio_deterministic_lowest_ids():
    trio, remaining = pop_next_trio_ids([5, 2, 9, 1, 7])
    assert trio == [1, 2, 5]
    assert remaining == [7, 9]


def test_drain_forty_participants_into_thirteen_trios():
    pool = list(range(1, 41))
    trios = []
    while True:
        trio, pool = pop_next_trio_ids(pool)
        if trio is None:
            break
        trios.append(trio)
    assert len(trios) == 13
    assert trios[0] == [1, 2, 3]
    assert trios[-1] == [37, 38, 39]
    assert pool == [40]


def test_advisory_lock_id_stable_per_session_and_part():
    class _Session:
        id = 42
        code = "abc"

    assert advisory_lock_id(_Session(), 1) == advisory_lock_id(_Session(), 1)
    assert advisory_lock_id(_Session(), 1) != advisory_lock_id(_Session(), 2)

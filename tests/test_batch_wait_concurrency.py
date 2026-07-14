"""Tests for batch-wait pool draining and lock key stability."""

import unittest

from shared.session_part_lock import (
    advisory_lock_id,
    normalize_pool_ids,
    pop_next_trio_ids,
    try_session_part_lock,
)


class BatchWaitConcurrencyTests(unittest.TestCase):
    def test_normalize_pool_dedupes_and_sorts(self):
        self.assertEqual(normalize_pool_ids([3, 1, 2, 2, 1]), [1, 2, 3])

    def test_pop_next_trio_deterministic_lowest_ids(self):
        trio, remaining = pop_next_trio_ids([5, 2, 9, 1, 7])
        self.assertEqual(trio, [1, 2, 5])
        self.assertEqual(remaining, [7, 9])

    def test_drain_forty_participants_into_thirteen_trios(self):
        pool = list(range(1, 41))
        trios = []
        while True:
            trio, pool = pop_next_trio_ids(pool)
            if trio is None:
                break
            trios.append(trio)
        self.assertEqual(len(trios), 13)
        self.assertEqual(trios[0], [1, 2, 3])
        self.assertEqual(trios[-1], [37, 38, 39])
        self.assertEqual(pool, [40])

    def test_advisory_lock_id_stable_per_session_and_part(self):
        class _Session:
            id = 42
            code = "abc"

        self.assertEqual(advisory_lock_id(_Session(), 1), advisory_lock_id(_Session(), 1))
        self.assertNotEqual(advisory_lock_id(_Session(), 1), advisory_lock_id(_Session(), 2))

    def test_try_session_part_lock_nonblocking_sqlite_fallback(self):
        """Second concurrent acquire must fail immediately (not wait)."""

        class _Session:
            id = 99
            code = "locktest"
            vars = {}

        with try_session_part_lock(_Session(), 1) as first:
            self.assertTrue(first)
            with try_session_part_lock(_Session(), 1) as second:
                self.assertFalse(second)
        with try_session_part_lock(_Session(), 1) as third:
            self.assertTrue(third)


if __name__ == "__main__":
    unittest.main()

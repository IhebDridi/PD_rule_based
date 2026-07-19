"""Unit tests for crash-recovery timed session flags (no oTree import)."""

import unittest

from shared.stale_session_flag import (
    clear_timed_flag,
    flag_is_fresh,
    try_acquire_timed_flag,
)


class StaleSessionFlagTests(unittest.TestCase):
    def test_acquire_when_missing(self):
        store = {}
        self.assertTrue(try_acquire_timed_flag(store, "k", 90, now=1000.0))
        self.assertEqual(store["k"], 1000.0)

    def test_fresh_blocks_second_acquire(self):
        store = {"k": 1000.0}
        self.assertFalse(try_acquire_timed_flag(store, "k", 90, now=1050.0))
        self.assertEqual(store["k"], 1000.0)

    def test_stale_timestamp_can_be_stolen(self):
        store = {"k": 1000.0}
        self.assertTrue(try_acquire_timed_flag(store, "k", 90, now=1100.0))
        self.assertEqual(store["k"], 1100.0)

    def test_legacy_bool_true_is_not_fresh(self):
        self.assertFalse(flag_is_fresh(True, 90, now=1000.0))
        store = {"k": True}
        self.assertTrue(try_acquire_timed_flag(store, "k", 90, now=1000.0))

    def test_clear(self):
        store = {"k": 1000.0}
        clear_timed_flag(store, "k")
        self.assertNotIn("k", store)


if __name__ == "__main__":
    unittest.main()

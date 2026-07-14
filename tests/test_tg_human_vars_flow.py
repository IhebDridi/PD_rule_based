"""Unit tests for TG v2 human block participant.vars storage."""

import unittest
from types import SimpleNamespace

from shared.tg_human_block_vars import (
    human_block_maps_complete,
    human_block_maps_from_vars,
    human_first_vars_key,
    human_second_vars_key,
    normalize_human_block_map,
    record_human_first_choice,
    record_human_second_choice,
)


class TgHumanVarsFlowTests(unittest.TestCase):
    def test_normalize_human_block_map(self):
        raw = {"1": "A", 2: "B", 3: "X", "4": None}
        self.assertEqual(normalize_human_block_map(raw), {1: "A", 2: "B"})

    def test_second_block_vars_survive_incremental_submits_without_preserve(self):
        """Simulate 10 single-field submits without player-row accumulation."""
        participant = SimpleNamespace(vars={})
        part = 1
        for round_i in range(1, 11):
            choice = "A" if round_i % 2 else "B"
            record_human_second_choice(participant, part, round_i, choice)

        first = {i: "A" for i in range(1, 11)}
        participant.vars[human_first_vars_key(part)] = first
        got_first, got_second = human_block_maps_from_vars(participant, part)
        self.assertEqual(got_first, first)
        self.assertEqual(got_second, {i: ("A" if i % 2 else "B") for i in range(1, 11)})
        self.assertTrue(human_block_maps_complete(got_first, got_second))

    def test_partial_maps_not_complete(self):
        participant = SimpleNamespace(vars={human_first_vars_key(1): {1: "A"}})
        first, second = human_block_maps_from_vars(participant, 1)
        self.assertFalse(human_block_maps_complete(first, second))


if __name__ == "__main__":
    unittest.main()

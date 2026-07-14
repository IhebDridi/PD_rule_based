"""Unit tests for targeted player lookup (no full subsession scan)."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from shared.tg_player_lookup import players_at_round_for_member_ids, sorted_trio_at_round


class TgPlayerLookupTests(unittest.TestCase):
    def test_players_at_round_preserves_order(self):
        class FakePlayer:
            def __init__(self, round_number, pid):
                self.round_number = round_number
                self.participant = SimpleNamespace(id_in_session=pid, vars={})

        class FakeParticipant:
            def __init__(self, pid, players):
                self.id_in_session = pid
                self._players = players

            def get_players(self):
                return self._players

        p1 = FakeParticipant(1, [FakePlayer(1, 1), FakePlayer(2, 1)])
        p2 = FakeParticipant(2, [FakePlayer(1, 2)])
        p3 = FakeParticipant(3, [FakePlayer(1, 3)])

        with patch(
            "shared.tg_player_lookup.participants_by_id_in_session",
            return_value={1: p1, 2: p2, 3: p3},
        ):
            players = players_at_round_for_member_ids(99, [3, 1, 2], 1)

        self.assertEqual([pl.participant.id_in_session for pl in players], [3, 1, 2])

    def test_sorted_trio_by_matching_position(self):
        class FakePlayer:
            def __init__(self, round_number, pid, pos):
                self.round_number = round_number
                self.participant = SimpleNamespace(
                    id_in_session=pid, vars={"matching_group_position": pos}
                )

        class FakeParticipant:
            def __init__(self, pid, players):
                self.id_in_session = pid
                self._players = players

            def get_players(self):
                return self._players

        # member_ids order 3,1,2 but positions 2,1,3 → sorted should be 1,3,2
        p1 = FakeParticipant(1, [FakePlayer(1, 1, 1)])
        p2 = FakeParticipant(2, [FakePlayer(1, 2, 3)])
        p3 = FakeParticipant(3, [FakePlayer(1, 3, 2)])
        with patch(
            "shared.tg_player_lookup.participants_by_id_in_session",
            return_value={1: p1, 2: p2, 3: p3},
        ):
            trio = sorted_trio_at_round(99, [3, 1, 2], 1)
        self.assertEqual([p.participant.id_in_session for p in trio], [1, 3, 2])


if __name__ == "__main__":
    unittest.main()

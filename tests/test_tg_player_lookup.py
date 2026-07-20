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

    def test_sorted_trio_uses_durable_part_position_not_live(self):
        """After rematch, live matching_group_position differs from Part 1 seats."""

        class FakePlayer:
            def __init__(self, round_number, pid, live_pos, part1_pos):
                self.round_number = round_number
                self.participant = SimpleNamespace(
                    id_in_session=pid,
                    vars={
                        "matching_group_position": live_pos,
                        "group_position_part_1": part1_pos,
                    },
                )

        class FakeParticipant:
            def __init__(self, pid, players):
                self.id_in_session = pid
                self._players = players

            def get_players(self):
                return self._players

        # Part 1 seats: id1→1, id3→2, id2→3. Live rematch positions are scrambled.
        p1 = FakeParticipant(1, [FakePlayer(1, 1, live_pos=3, part1_pos=1)])
        p2 = FakeParticipant(2, [FakePlayer(1, 2, live_pos=1, part1_pos=3)])
        p3 = FakeParticipant(3, [FakePlayer(1, 3, live_pos=2, part1_pos=2)])
        with patch(
            "shared.tg_player_lookup.participants_by_id_in_session",
            return_value={1: p1, 2: p2, 3: p3},
        ):
            trio = sorted_trio_at_round(99, [3, 1, 2], 1, part=1)
        self.assertEqual([p.participant.id_in_session for p in trio], [1, 3, 2])

    def test_sorted_trio_falls_back_to_member_ids_claim_order(self):
        class FakePlayer:
            def __init__(self, round_number, pid, live_pos):
                self.round_number = round_number
                self.participant = SimpleNamespace(
                    id_in_session=pid,
                    vars={"matching_group_position": live_pos},
                )

        class FakeParticipant:
            def __init__(self, pid, players):
                self.id_in_session = pid
                self._players = players

            def get_players(self):
                return self._players

        # No durable part seats — claim order wins (not live position).
        p1 = FakeParticipant(1, [FakePlayer(1, 1, 9)])
        p2 = FakeParticipant(2, [FakePlayer(1, 2, 1)])
        p3 = FakeParticipant(3, [FakePlayer(1, 3, 2)])
        with patch(
            "shared.tg_player_lookup.participants_by_id_in_session",
            return_value={1: p1, 2: p2, 3: p3},
        ):
            trio = sorted_trio_at_round(99, [3, 1, 2], 1, part=1)
        self.assertEqual([p.participant.id_in_session for p in trio], [3, 1, 2])


    def test_opponent_after_rematch_uses_durable_part1_seats(self):
        """Live matching_group_position from Part 2 must not scramble Part 1 opponents."""
        from shared.matching_batch import clear_matching_batch_cache, opponent_in_matching_batch

        clear_matching_batch_cache()

        class C:
            rounds_per_part = 10

            @staticmethod
            def get_part(r):
                return 1 if r <= 10 else 2

        def compute_rr(n, rounds):
            return [[(1, None)] + [(0, None)] * 9, [(0, None)] * 10, [(0, None)] * 10]

        class FakeSession:
            id = 7
            code = "rematch"
            vars = {
                "matching_group_members_part_1_10": [1, 2, 3],
                "matching_group_members_part_2_20": [1, 3, 2],
            }

        class FakePart:
            def __init__(self, pid, part1_pos, live_pos):
                self.id_in_session = pid
                self.vars = {
                    "matching_group_id": -1,
                    "matching_group_position": live_pos,
                    "group_part_1": 10,
                    "group_position_part_1": part1_pos,
                    "group_part_2": 20,
                    "group_position_part_2": live_pos,
                }

        players_by_id = {}

        class FakePlayer:
            def __init__(self, pid, part1_pos, live_pos, round_number=1):
                self.participant = FakePart(pid, part1_pos, live_pos)
                self.session = FakeSession()
                self.round_number = round_number

            def in_round(self, r):
                src = players_by_id[self.participant.id_in_session]
                return FakePlayer(
                    src.participant.id_in_session,
                    src.participant.vars["group_position_part_1"],
                    src.participant.vars["matching_group_position"],
                    r,
                )

        players_by_id[1] = FakePlayer(1, 1, 3)
        players_by_id[2] = FakePlayer(2, 2, 1)
        players_by_id[3] = FakePlayer(3, 3, 2)

        def fake_participants_by_id(session_id, ids):
            class Wrap:
                def __init__(self, pl):
                    self.id_in_session = pl.participant.id_in_session
                    self._pl = pl

                def get_players(self):
                    return [
                        FakePlayer(
                            self._pl.participant.id_in_session,
                            self._pl.participant.vars["group_position_part_1"],
                            self._pl.participant.vars["matching_group_position"],
                            r,
                        )
                        for r in range(1, 31)
                    ]

            return {int(i): Wrap(players_by_id[int(i)]) for i in ids}

        with patch(
            "shared.tg_player_lookup.participants_by_id_in_session",
            side_effect=fake_participants_by_id,
        ):
            opp = opponent_in_matching_batch(players_by_id[1], 1, C, compute_rr, {})
            trio = sorted_trio_at_round(7, [1, 2, 3], 1, part=1)

        self.assertEqual([p.participant.id_in_session for p in trio], [1, 2, 3])
        self.assertIsNotNone(opp)
        self.assertEqual(opp.participant.id_in_session, 2)


if __name__ == "__main__":
    unittest.main()

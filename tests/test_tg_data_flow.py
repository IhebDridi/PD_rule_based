"""Unit tests for TG data flow helpers and payoff/cache logic."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from shared.tg_data_helpers import (
    build_tg_results_cache_for_part,
    merge_block_map,
    read_human_first_map_from_player,
    tg_effective_choice,
    tg_export_choice_getter,
    tg_part_has_choices,
    write_tg_results_display_cache,
)
from shared.tg_payoffs import apply_tg_payoffs_for_pair, compute_tg_payoffs, tg_choices_ready


class _FakeFieldPlayer:
    def __init__(self, **fields):
        self._fields = fields

    def field_maybe_none(self, name):
        return self._fields.get(name)


class _RoundPlayer(_FakeFieldPlayer):
    def __init__(self, round_number, **fields):
        super().__init__(**fields)
        self.round_number = round_number
        self.payoff = fields.get("payoff")
        self.participant = SimpleNamespace(id_in_session=1, vars={})


class TgDataFlowTests(unittest.TestCase):
    def test_merge_block_map_falls_back_to_db_fields(self):
        participant = SimpleNamespace(vars={})
        player = _FakeFieldPlayer(human_decision_no_delegation_round_1="A", human_decision_no_delegation_round_2="B")
        merged = merge_block_map(participant, "missing_key", player, read_human_first_map_from_player)
        self.assertEqual(merged[1], "A")
        self.assertEqual(merged[2], "B")

    def test_tg_effective_choice_by_role(self):
        first = _FakeFieldPlayer(role_assigned="first", choice_first_mover="A", choice_second_mover="B")
        second = _FakeFieldPlayer(role_assigned="second", choice_first_mover="A", choice_second_mover="B")
        self.assertEqual(tg_effective_choice(first), "A")
        self.assertEqual(tg_effective_choice(second), "B")

    def test_tg_part_has_choices_and_export_getter(self):
        pr = _FakeFieldPlayer(
            round_number=1,
            choice_first_mover="A",
            choice_second_mover="B",
        )
        pr.round_number = 1
        self.assertTrue(tg_part_has_choices([pr], 1, 10))
        self.assertEqual(tg_export_choice_getter(pr), "tg")

    def test_compute_and_apply_tg_payoffs(self):
        import random

        a = _FakeFieldPlayer(choice_first_mover="A", choice_second_mover="B", id=1)
        b = _FakeFieldPlayer(choice_first_mover="B", choice_second_mover="A", id=2)
        a.role_assigned = None
        b.role_assigned = None
        a.payoff = None
        b.payoff = None

        ok = apply_tg_payoffs_for_pair(a, b, rng=random.Random(0))
        self.assertTrue(ok)
        self.assertIn(a.role_assigned, ("first", "second"))
        self.assertIn(b.role_assigned, ("first", "second"))
        self.assertNotEqual(a.role_assigned, b.role_assigned)
        self.assertEqual(compute_tg_payoffs("B", "A"), (30, 30))

    def test_tg_choices_ready(self):
        ready = _FakeFieldPlayer(choice_first_mover="A", choice_second_mover="B")
        not_ready = _FakeFieldPlayer(choice_first_mover="A", choice_second_mover=None)
        self.assertTrue(tg_choices_ready(ready))
        self.assertFalse(tg_choices_ready(not_ready))

    def test_results_cache_round_trip(self):
        assignments = [
            [(1, None), (2, None)] * 5,
            [(0, None), (2, None)] * 5,
            [(0, None), (1, None)] * 5,
        ]

        def _mk(rn, c1, c2, role, payoff):
            p = _RoundPlayer(rn, choice_first_mover=c1, choice_second_mover=c2, role_assigned=role, payoff=payoff)
            return p

        players_start = []
        for pos in range(3):
            p0 = MagicMock()
            rows = []
            for i in range(10):
                rn = i + 1
                opp_idx, _ = assignments[pos][i]
                me_c1, me_c2 = "A", "B"
                opp_c1, opp_c2 = "B", "A"
                role = "first" if pos < opp_idx else "second"
                payoff = 70 if role == "first" else 30
                me = _mk(rn, me_c1, me_c2, role, payoff)
                opp = _mk(rn, opp_c1, opp_c2, "second" if role == "first" else "first", 30)
                rows.append((me, opp))

            def _in_round(n, _rows=rows):
                return _rows[n - 1][0]

            p0.in_round = _in_round
            p0.participant = SimpleNamespace(vars={})
            players_start.append(p0)

        # Simpler cache smoke test with mocked in_round opponents via build function structure
        p0 = MagicMock()
        p1 = MagicMock()

        def make_player(pid, pos):
            pl = MagicMock()
            pl.participant = SimpleNamespace(id_in_session=pid, vars={})

            def in_round(n):
                me = _RoundPlayer(
                    n,
                    choice_first_mover="A",
                    choice_second_mover="B",
                    role_assigned="first" if pos == 0 else "second",
                    payoff=70,
                )
                return me

            pl.in_round = in_round
            return pl

        players_start = [make_player(1, 0), make_player(2, 1), make_player(3, 2)]
        write_tg_results_display_cache(players_start, assignments, 1, 1, 10, 10)
        cache = players_start[0].participant.vars.get("results_display_cache")
        self.assertIn("part_1", cache)
        self.assertEqual(len(cache["part_1"]), 10)


if __name__ == "__main__":
    unittest.main()

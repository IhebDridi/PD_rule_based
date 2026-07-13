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
from shared.tg_payoffs import (
    apply_tg_payoffs_for_pair,
    compute_tg_payoffs,
    tg_choices_ready,
    tg_results_row,
)


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

        ok = apply_tg_payoffs_for_pair(a, b, rng=random.Random(0), write_both=True)
        self.assertTrue(ok)
        self.assertIn(a.role_assigned, ("first", "second"))
        self.assertIn(b.role_assigned, ("first", "second"))
        self.assertNotEqual(a.role_assigned, b.role_assigned)
        self.assertEqual(compute_tg_payoffs("B", "A"), (30, 30))

    def test_apply_tg_payoffs_focal_only_does_not_overwrite_opponent(self):
        """Directed round-robin: only focal player is written so later matches cannot clobber them."""
        import random

        a = _FakeFieldPlayer(choice_first_mover="A", choice_second_mover="B", id=1)
        b = _FakeFieldPlayer(choice_first_mover="B", choice_second_mover="A", id=2)
        a.role_assigned = None
        b.role_assigned = "first"
        a.payoff = None
        b.payoff = 999

        ok = apply_tg_payoffs_for_pair(a, b, rng=random.Random(1), write_both=False)
        self.assertTrue(ok)
        self.assertIn(a.role_assigned, ("first", "second"))
        self.assertIsNotNone(a.payoff)
        self.assertEqual(b.role_assigned, "first")
        self.assertEqual(b.payoff, 999)

    def test_tg_choices_ready(self):
        ready = _FakeFieldPlayer(choice_first_mover="A", choice_second_mover="B")
        not_ready = _FakeFieldPlayer(choice_first_mover="A", choice_second_mover=None)
        self.assertTrue(tg_choices_ready(ready))
        self.assertFalse(tg_choices_ready(not_ready))

    def test_tg_results_row_second_mover_consistent_with_payoffs(self):
        """2nd mover display: opponent column is 1st-mover contingent; payoff matches game."""
        me = _FakeFieldPlayer(
            role_assigned="second",
            choice_first_mover="A",
            choice_second_mover="B",
            payoff=100,
        )
        opp = _FakeFieldPlayer(
            role_assigned="first",
            choice_first_mover="A",
            choice_second_mover="B",
        )
        row = tg_results_row(me, opp)
        self.assertEqual(row["role_assigned"], "2nd mover")
        self.assertEqual(row["my_choice"], "B")
        self.assertEqual(row["other_choice"], "A")
        self.assertEqual(row["payoff"], 100)

    def test_tg_results_row_first_mover_b_ignores_second(self):
        me = _FakeFieldPlayer(
            role_assigned="first",
            choice_first_mover="B",
            choice_second_mover="A",
            payoff=30,
        )
        opp = _FakeFieldPlayer(
            role_assigned="second",
            choice_first_mover="A",
            choice_second_mover="B",
        )
        row = tg_results_row(me, opp)
        self.assertEqual(row["my_choice"], "B")
        self.assertEqual(row["other_choice"], "B")
        self.assertEqual(row["payoff"], 30)

    def test_tg_results_row_opponent_role_mismatch_still_displays_correctly(self):
        """Player-relative opponent column even if opponent.role_assigned is wrong."""
        me = _FakeFieldPlayer(
            role_assigned="second",
            choice_first_mover="A",
            choice_second_mover="B",
            payoff=100,
        )
        opp = _FakeFieldPlayer(
            role_assigned="second",
            choice_first_mover="A",
            choice_second_mover="B",
        )
        row = tg_results_row(me, opp)
        self.assertEqual(row["other_choice"], "A")
        self.assertEqual(row["payoff"], 100)

    def test_part3_style_rows_all_consistent(self):
        """Regression: user-reported Part 3 table rows after display fix."""
        cases = [
            ("second", "B", "B", "A", 100),
            ("second", "B", "B", "B", 30),
            ("first", "B", "A", "A", 30),
        ]
        for my_role, my_first, my_second, opp_first, expected_pay in cases:
            opp_second = "A"
            me = _FakeFieldPlayer(
                role_assigned=my_role,
                choice_first_mover=my_first,
                choice_second_mover=my_second,
            )
            opp = _FakeFieldPlayer(
                role_assigned="first" if my_role == "second" else "second",
                choice_first_mover=opp_first,
                choice_second_mover=opp_second,
            )
            row = tg_results_row(me, opp)
            self.assertEqual(row["payoff"], expected_pay, msg=(my_role, opp_first))

    def test_tg_results_debug_builds_compare_rows(self):
        from unittest.mock import patch

        from shared.tg_results_debug import build_tg_results_debug

        class P:
            def __init__(self, **f):
                self._f = f
                self.payoff = f.get("payoff")
                self.participant = SimpleNamespace(
                    id_in_session=2, vars={"matching_group_position": 2}
                )

            def field_maybe_none(self, k):
                return self._f.get(k)

        player = SimpleNamespace()

        def in_round(r):
            return P(
                role_assigned="second",
                choice_first_mover="A",
                choice_second_mover="B",
                payoff=100,
            )

        player.in_round = in_round
        opp = P(
            role_assigned="first",
            choice_first_mover="A",
            choice_second_mover="B",
            payoff=0,
        )
        opp.participant.vars["matching_group_position"] = 1

        with patch("shared.tg_results_debug._otree_debug_mode", return_value=True):
            d = build_tg_results_debug(
                player, 21, 21, 3, lambda p, r: opp, rounds_per_part=10
            )
        self.assertTrue(d["summary_vars"]["tg_debug_all_ok"])
        self.assertEqual(d["summary_vars"]["tg_debug_mismatch_count"], 0)
        self.assertEqual(d["summary_vars"]["tg_debug_R1_flag"], "ok")
        self.assertEqual(d["rounds"][0]["display"]["payoff"], 100)
        self.assertEqual(d["rounds"][0]["db"]["payoff"], 100)

    def test_tg_results_debug_mismatch_shows_screen_vs_db_choice(self):
        from unittest.mock import patch

        from shared.tg_results_debug import build_tg_results_debug

        class P:
            def __init__(self, **f):
                self._f = f
                self.payoff = f.get("payoff")
                self.participant = SimpleNamespace(
                    id_in_session=1, vars={"matching_group_position": 1}
                )

            def field_maybe_none(self, k):
                return self._f.get(k)

        player = SimpleNamespace()

        def in_round(r):
            return P(
                role_assigned="first",
                choice_first_mover="A",
                choice_second_mover="B",
                payoff=30,
            )

        player.in_round = in_round
        opp = P(
            role_assigned="second",
            choice_first_mover="B",
            choice_second_mover="A",
            payoff=30,
        )
        opp.participant.vars["matching_group_position"] = 2

        with patch("shared.tg_results_debug._otree_debug_mode", return_value=True):
            with patch(
                "shared.tg_results_debug.tg_results_row",
                return_value={
                    "role_assigned": "1st mover",
                    "my_choice": "B",
                    "other_choice": "A",
                    "payoff": 70,
                },
            ):
                d = build_tg_results_debug(
                    player, 1, 1, 1, lambda p, r: opp, rounds_per_part=10
                )

        self.assertFalse(d["summary_vars"]["tg_debug_all_ok"])
        self.assertIn("my_choice_mismatch", d["rounds"][0]["flags"])
        self.assertIn("payoff_mismatch", d["rounds"][0]["flags"])
        self.assertEqual(d["rounds"][0]["mismatch"]["choice_screen"], "B")
        self.assertEqual(d["rounds"][0]["mismatch"]["choice_db"], "A")
        self.assertEqual(d["summary_vars"]["tg_debug_R1_choice_screen"], "B")
        self.assertEqual(d["summary_vars"]["tg_debug_R1_choice_db"], "A")
        self.assertIn("choice — screen: 'B'", d["summary_vars"]["tg_debug_R1_mismatch_detail"])

    def test_round_narrative_second_mover_both_b(self):
        from shared.tg_results_diagrams import _build_round_narrative

        text = _build_round_narrative(
            round_num=1,
            you_label="P2 (you)",
            opp_label="P1",
            assigned="second",
            first_move="B",
            second_move="B",
            your_payoff=30,
            opp_payoff=30,
            third_nodes=[
                {
                    "label": "P3",
                    "opponent_label": "P1",
                    "role": "2nd mover",
                    "payoff": 70,
                }
            ],
        )
        self.assertIn("matched with P1", text)
        self.assertIn("P1 was the 1st mover and chose B", text)
        self.assertIn("P2 was the 2nd mover and chose B", text)
        self.assertIn("30 Ecoins", text)
        self.assertIn("P3", text)

    def test_annotate_diagrams_with_debug(self):
        from shared.tg_results_diagrams import annotate_diagrams_with_debug

        diagrams = [{"round": 1, "round_narrative": "x"}]
        debug = [
            {
                "round": 1,
                "warn": True,
                "flags": ["payoff_mismatch"],
                "mismatch": {"summary": "payoff — screen: 70, DB: 30"},
            }
        ]
        annotate_diagrams_with_debug(diagrams, debug)
        self.assertTrue(diagrams[0]["has_mismatch"])
        self.assertEqual(diagrams[0]["mismatch_flags"], ["payoff_mismatch"])

    def test_build_all_rounds_tree(self):
        from shared.tg_results_diagrams import build_all_rounds_tree

        overview = {
            "member_labels_text": "P1 · P2 (you) · P3",
            "my_position": 2,
            "matching_group_id": 1,
        }
        rounds = [
            {
                "round": 1,
                "you": {"label": "P2 (you)", "role": "2nd mover", "choice": "B"},
                "opponent": {"label": "P1", "choice": "B"},
                "members": [
                    {
                        "label": "P1",
                        "choice_first": "A",
                        "choice_second": "B",
                    }
                ],
                "third": [{"label": "P3", "opponent_label": "P2", "role": "1st mover", "payoff": 70}],
                "first_move": "B",
                "second_move": "B",
                "your_payoff": 30,
                "has_mismatch": False,
            }
        ]
        tree = build_all_rounds_tree(overview, rounds)
        self.assertEqual(tree["round_count"], 1)
        self.assertTrue(tree["show_batch_id"])
        b = tree["branches"][0]
        self.assertEqual(b["opponent_label"], "P1")
        self.assertEqual(b["opp_contingent_first"], "A")
        self.assertIn("1st-mover contingency", b["opp_move_used_label"])

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

"""Tests for TG session inspector helpers."""

import unittest
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from shared.tg_data_helpers import (
    tg_part_has_round_data,
    tg_round_has_partial_contingents,
)
from shared.tg_results_debug import _build_mismatch_detail
from shared.tg_session_inspector import (
    _batch_overview,
    _day_bounds,
    _participant_prolific_id,
    filter_session_participants,
    inspect_tg_session_by_code,
    is_tg_session_config,
    list_tg_sessions,
    session_choice_label,
)


class TgSessionInspectorTests(unittest.TestCase):
    def test_is_tg_session_config(self):
        self.assertTrue(is_tg_session_config("TG_goal_oriented_delegation_1st"))
        self.assertFalse(is_tg_session_config("TG_session_inspector"))
        self.assertFalse(is_tg_session_config("PD_rule_based_delegation_1st"))

    def test_session_choice_label(self):
        label = session_choice_label(
            {
                "code": "abc123",
                "config_name": "TG_rule_based_delegation_1st",
                "num_participants": 9,
                "is_demo": True,
                "label": "test run",
                "created_label": "2026-07-14 09:00",
            }
        )
        self.assertIn("abc123", label)
        self.assertIn("demo", label)
        self.assertIn("2026-07-14", label)

    def test_day_bounds_inclusive(self):
        start, end = _day_bounds("2026-07-14", "2026-07-14")
        self.assertIsNotNone(start)
        self.assertIsNotNone(end)
        self.assertEqual(end - start, 24 * 60 * 60)

    def test_batch_overview_parses_session_vars(self):
        session = SimpleNamespace(
            vars={
                "matching_group_members_part_1_0": [1, 2, 3],
                "matching_group_members_part_2_1": [4, 5, 6],
                "other_key": "ignore",
            }
        )
        batches = _batch_overview(session)
        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0]["part"], 1)
        self.assertEqual(batches[0]["size"], 3)
        self.assertEqual(batches[0]["member_ids_text"], "1, 2, 3")
        self.assertEqual(batches[0]["member_labels"], "P1, P2, P3")
        self.assertEqual(batches[0]["trio_index"], 1)
        self.assertEqual(batches[1]["part"], 2)
        self.assertEqual(batches[1]["trio_index"], 1)

    def test_batch_overview_assigns_sequential_trio_index_within_part(self):
        session = SimpleNamespace(
            vars={
                "matching_group_members_part_1_1": [1, 2, 3],
                "matching_group_members_part_1_4": [4, 5, 6],
                "matching_group_members_part_1_7": [7, 8, 9],
            }
        )
        batches = _batch_overview(session)
        self.assertEqual([b["trio_index"] for b in batches], [1, 2, 3])
        self.assertEqual([b["batch_id"] for b in batches], [1, 4, 7])

    def test_group_parts_from_participant(self):
        from shared.tg_session_inspector import _group_parts_from_participant

        p = SimpleNamespace(
            vars={"group_part_1": 1, "group_position_part_1": 2, "group_part_3": 21}
        )
        out = _group_parts_from_participant(p)
        self.assertTrue(out["parts"][0]["has_group"])
        self.assertEqual(out["parts"][0]["group_id"], 1)
        self.assertFalse(out["parts"][1]["has_group"])
        self.assertEqual(out["parts"][2]["group_id"], 21)

    def test_inspect_missing_session(self):
        with patch("otree.models.Session.objects_get", side_effect=Exception("missing")):
            out = inspect_tg_session_by_code("nope")
        self.assertFalse(out["ok"])
        self.assertIn("not found", out["error"].lower())

    def test_inspect_rejects_non_tg_config(self):
        fake = SimpleNamespace(
            code="x",
            config={"name": "PD_rule_based_delegation_1st", "app_sequence": ["PD_rule_based_delegation_1st"]},
            num_participants=3,
            label="",
            id=1,
            vars={},
        )
        with patch("otree.models.Session.objects_get", return_value=fake):
            out = inspect_tg_session_by_code("x")
        self.assertFalse(out["ok"])

    def test_list_tg_sessions_date_filter(self):
        today = date.today()
        yesterday = today - timedelta(days=1)
        ts_today = datetime.combine(today, datetime.min.time()).timestamp() + 3600
        ts_old = datetime.combine(yesterday - timedelta(days=5), datetime.min.time()).timestamp()

        class FakeSession:
            def __init__(self, sid, code, name, created):
                self.id = sid
                self.code = code
                self.config = {"name": name, "app_sequence": [name]}
                self.num_participants = 3
                self.label = ""
                self.is_demo = False
                self._created = created

            def _created_readable(self):
                return "now"

        sessions = [
            FakeSession(2, "new", "TG_goal_oriented_delegation_1st", ts_today),
            FakeSession(1, "old", "TG_goal_oriented_delegation_1st", ts_old),
        ]

        class FakeQuery:
            def order_by(self, *a, **k):
                return self

            def limit(self, n):
                return sessions[:n]

        with patch("otree.models.Session.objects_filter", return_value=FakeQuery()):
            rows = list_tg_sessions(limit=10, date_from=today.isoformat(), date_to=today.isoformat())
        self.assertEqual([r["code"] for r in rows], ["new"])

    def test_tg_part_has_round_data_detects_partial_only(self):
        store = {}

        def _round(rn):
            if rn not in store:
                store[rn] = SimpleNamespace(
                    choice_first_mover=None,
                    choice_second_mover=None,
                    role_assigned=None,
                    payoff=None,
                )
            pr = store[rn]
            pr.field_maybe_none = lambda name, p=pr: getattr(p, name, None)
            return pr

        player = SimpleNamespace(in_round=_round)
        _round(3).choice_first_mover = "A"
        self.assertTrue(tg_part_has_round_data([player], 1, 10))
        self.assertTrue(tg_round_has_partial_contingents(_round(3)))

    def test_partial_contingent_mismatch_detail(self):
        detail = _build_mismatch_detail(
            {"my_choice": None, "other_choice": None, "role_assigned": "", "payoff": None},
            {"choice_first_mover": "A", "choice_second_mover": None, "role_assigned": None, "payoff": None},
            ["partial_contingent_choices"],
        )
        self.assertIn("partial contingents", detail["summary"])
        self.assertIn("c1='A'", detail["summary"])

    def test_filter_session_participants_by_range_and_prolific(self):
        def _players(pid):
            return [SimpleNamespace(field_maybe_none=lambda n, p=pid: p if n == "prolific_id" else None)]

        participants = [
            SimpleNamespace(id_in_session=1, get_players=lambda: _players("AAA")),
            SimpleNamespace(id_in_session=2, get_players=lambda: _players("BBB")),
            SimpleNamespace(id_in_session=3, get_players=lambda: _players("CCC")),
            SimpleNamespace(id_in_session=20, get_players=lambda: _players("ZZZ")),
        ]

        ranged = filter_session_participants(participants, participant_from=1, participant_to=2)
        self.assertEqual([p.id_in_session for p in ranged], [1, 2])

        wide = filter_session_participants(participants, participant_from=1, participant_to=20)
        self.assertEqual([p.id_in_session for p in wide], [1, 2, 3, 20])

        by_prolific = filter_session_participants(participants, prolific_id="bbb")
        self.assertEqual([p.id_in_session for p in by_prolific], [2])

        self.assertEqual(_participant_prolific_id(participants[0]), "AAA")


if __name__ == "__main__":
    unittest.main()

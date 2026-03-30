"""Supervised-learning: five example datasets + generated preview, all as Option A/B with fixed P(A) per dataset."""

import json
import random

from otree.api import Page

from pages_classes.model_bridge import get_constants
from pages_classes.page_helpers import _has_left_lobby_for_part, part_vars

# P(Option A) for dataset indices 0..4 (Option B with the remaining probability).
DATASET_P_A = [0.05, 0.25, 0.5, 0.75, 0.95]


def _sample_10_decisions(p_a: float) -> list:
    """Independent draws: A with probability p_a, else B."""
    return ["A" if random.random() < p_a else "B" for _ in range(10)]


def _decisions_to_csv(decisions: list) -> str:
    return ",".join(decisions)


class SupervisedLearning(Page):
    template_name = "PD_supervised_learning_delegation_1st/supervisedLearning.html"
    form_model = "player"
    form_fields = ["supervised_last_generated_csv"]

    @staticmethod
    def live_method(player, data):
        if not data or "dataset_num" not in data:
            return
        try:
            dnum = int(data["dataset_num"])
        except (TypeError, ValueError):
            return
        if dnum < 0 or dnum >= len(DATASET_P_A):
            return
        p_a = DATASET_P_A[dnum]
        decisions = _sample_10_decisions(p_a)
        response_str = _decisions_to_csv(decisions)

        raw = player.field_maybe_none("supervised_dataset")
        if not raw or str(raw).strip() in ("", "{}"):
            history = {}
        else:
            try:
                history = json.loads(raw)
            except json.JSONDecodeError:
                history = {}

        cnt = player.sample_cnt
        history[str(cnt)] = response_str
        player.supervised_dataset = json.dumps(history)
        player.sample_cnt = cnt + 1
        player.supervised_last_generated_csv = response_str
        player.supervised_mean = p_a

        return {player.id_in_group: {"response": response_str}}

    def is_displayed(self):
        C = get_constants(self.player)
        r = self.round_number
        current_part = C.get_part(r)
        if r in (1, 11, 21) and not _has_left_lobby_for_part(self.participant, current_part):
            return False

        if r == 1 and C.DELEGATION_FIRST:
            return not self.participant.vars.get("agent_programming_done_part1", False)
        if r == 11 and not C.DELEGATION_FIRST:
            return not self.participant.vars.get("agent_programming_done_part2", False)

        if current_part == 3:
            return (
                self.player.field_maybe_none("delegate_decision_optional") is True
                and not self.participant.vars.get("agent_programming_done_part3", False)
            )

        return False

    def _get_or_build_raw_datasets(self):
        key = "_supervised_ab_datasets_cache"
        cached = self.participant.vars.get(key)
        if cached is not None:
            return cached
        out = {}
        for i in range(5):
            out[i] = _sample_10_decisions(DATASET_P_A[i])
        self.participant.vars[key] = out
        return out

    def vars_for_template(self):
        C = get_constants(self.player)
        current_part = C.get_part(self.round_number)
        supervised_dataset = self._get_or_build_raw_datasets()
        json_serializable = {str(k): v for k, v in supervised_dataset.items()}
        self.player.supervised_history = json.dumps(json_serializable)

        formatted_datasets = []
        for i in range(5):
            arr = supervised_dataset[i]
            formatted_datasets.append(
                {
                    "dataset_num": i,
                    "allocations": [
                        {"round_num": round_num, "decision": d}
                        for round_num, d in enumerate(arr, start=1)
                    ],
                }
            )

        preview_rows = [{"round_num": i, "value": "-"} for i in range(1, 11)]
        show_confirm = False
        csv_prev = self.player.field_maybe_none("supervised_last_generated_csv")
        supervised_csv_hidden = csv_prev or ""
        if csv_prev:
            parts = [x.strip().upper() for x in csv_prev.split(",") if x.strip()]
            if len(parts) == 10 and all(p in ("A", "B") for p in parts):
                preview_rows = [{"round_num": i + 1, "value": parts[i]} for i in range(10)]
                show_confirm = True

        return {
            "datasets": formatted_datasets,
            "current_part": current_part,
            "delegate_decision": self.player.field_maybe_none("delegate_decision_optional"),
            "countdown_seconds": 90,
            "preview_rows": preview_rows,
            "show_confirm": show_confirm,
            "supervised_csv_hidden": supervised_csv_hidden,
            **part_vars(self.player),
        }

    def error_message(self, values):
        csv_val = (values.get("supervised_last_generated_csv") or "").strip()
        if not csv_val:
            return "Please select a dataset, click Generate, then Confirm."
        parts = [p.strip().upper() for p in csv_val.split(",") if p.strip()]
        if len(parts) != 10 or not all(p in ("A", "B") for p in parts):
            return "Please select a dataset, click Generate, then Confirm."
        return None

    def _last_generated_csv(self):
        raw = self.player.field_maybe_none("supervised_dataset") or "{}"
        try:
            hist = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not hist:
            return None
        last_key = list(hist.keys())[-1]
        return hist[last_key]

    def before_next_page(self):
        C = get_constants(self.player)
        r = self.round_number
        current_part = C.get_part(r)

        final_csv = (
            self.player.field_maybe_none("supervised_last_generated_csv") or self._last_generated_csv() or ""
        ).strip()
        if not final_csv:
            return
        tokens = [x.strip().upper() for x in final_csv.split(",") if x.strip()]
        if len(tokens) < 10 or not all(t in ("A", "B") for t in tokens[:10]):
            return

        decisions = {i + 1: tokens[i] for i in range(10)}
        self.player.final_allocations = final_csv

        if r == 1 and C.DELEGATION_FIRST:
            for i in range(1, 11):
                self.player.in_round(i).choice = decisions[i]
            self.participant.vars["agent_programming_part1"] = decisions
            self.participant.vars["agent_programming_done_part1"] = True

        elif r == 11 and not C.DELEGATION_FIRST:
            for i in range(1, 11):
                self.player.in_round(10 + i).choice = decisions[i]
            self.participant.vars["agent_programming_part2"] = decisions
            self.participant.vars["agent_programming_done_part2"] = True

        elif current_part == 3:
            start = 2 * C.rounds_per_part + 1
            for i in range(1, 11):
                self.player.in_round(start + i - 1).choice = decisions[i]
            self.participant.vars["agent_programming_part3"] = decisions
            self.participant.vars["agent_programming_done_part3"] = True

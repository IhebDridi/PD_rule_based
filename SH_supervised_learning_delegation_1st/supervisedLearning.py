import json
import random

from pages_classes import AgentProgramming
from pages_classes.model_bridge import get_constants


class SupervisedLearning(AgentProgramming):
    template_name = "SH_supervised_learning_delegation_1st/supervisedLearning.html"

    # Fixed datasets shown to every participant (shuffled positions, static content).
    # Means map to supervised "goal" strengths used to generate behavior.
    DATASET_MEANS = [0.0, 0.25, 0.5, 0.75, 1.0]
    FIXED_DATASET_DECISIONS = {
        # 1A/9B
        0: ["B", "B", "A", "B", "B", "B", "B", "B", "B", "B"],
        # 3A/7B
        1: ["A", "B", "B", "A", "B", "B", "B", "A", "B", "B"],
        # 5A/5B
        2: ["A", "B", "A", "B", "A", "B", "B", "A", "B", "A"],
        # 7A/3B
        3: ["A", "A", "B", "A", "A", "B", "A", "A", "B", "A"],
        # 9A/1B
        4: ["A", "A", "A", "A", "B", "A", "A", "A", "A", "A"],
    }

    def get_form_fields(self):
        return ["supervised_last_generated_csv"]

    def vars_for_template(self):
        current_part = get_constants(self.player).get_part(self.round_number)
        datasets = []
        for idx, mean_value in enumerate(self.DATASET_MEANS):
            decisions = self.FIXED_DATASET_DECISIONS[idx]
            datasets.append(
                {
                    "dataset_num": idx,
                    "mean_value": mean_value,
                    "allocations": [
                        {"round_num": i + 1, "decision": decisions[i]}
                        for i in range(10)
                    ],
                }
            )
        ctx = super().vars_for_template()
        csv_prev = self.player.field_maybe_none("supervised_last_generated_csv")
        preview_rows = [{"round_num": i, "value": "-"} for i in range(1, 11)]
        show_confirm = False
        supervised_csv_hidden = csv_prev or ""
        if csv_prev:
            parts = [x.strip().upper() for x in csv_prev.split(",") if x.strip()]
            if len(parts) == 10 and all(p in ("A", "B") for p in parts):
                preview_rows = [{"round_num": i + 1, "value": parts[i]} for i in range(10)]
                show_confirm = True
        ctx.update(
            {
                "datasets": datasets,
                "current_part": current_part,
                "preview_rows": preview_rows,
                "show_confirm": show_confirm,
                "supervised_csv_hidden": supervised_csv_hidden,
            }
        )
        return ctx

    def error_message(self, values):
        csv_val = (values.get("supervised_last_generated_csv") or "").strip()
        if not csv_val:
            return "Please select a dataset, click Generate, then Confirm."
        parts = [p.strip().upper() for p in csv_val.split(",") if p.strip()]
        if len(parts) != 10 or not all(p in ("A", "B") for p in parts):
            return "Please select a dataset, click Generate, then Confirm."
        return None

    @staticmethod
    def live_method(player, data):
        if not data:
            return
        dataset_num = data.get("dataset_num")
        try:
            dataset_num = int(dataset_num)
        except (TypeError, ValueError):
            dataset_num = None
        if dataset_num not in range(5):
            dataset_num = None

        if dataset_num is not None:
            mean_value = SupervisedLearning.DATASET_MEANS[dataset_num]
        else:
            try:
                mean_value = float(data.get("mean_value"))
            except (TypeError, ValueError):
                mean_value = 0.5
        mean_value = max(0.0, min(1.0, mean_value))

        # Calibrated mapping to avoid deterministic extremes:
        # 0 -> 5%, 0.25 -> 27.5%, 0.5 -> 50%, 0.75 -> 72.5%, 1 -> 95%.
        p_a = 0.05 + 0.90 * mean_value
        decisions = {
            i + 1: ("A" if random.random() < p_a else "B")
            for i in range(10)
        }
        allocations = [100 if decisions[i + 1] == "A" else 0 for i in range(10)]

        C = get_constants(player)
        r = player.round_number
        current_part = C.get_part(r)
        if r == 1 and C.DELEGATION_FIRST:
            player.participant.vars["agent_programming_part1"] = decisions
        elif r == 11 and not C.DELEGATION_FIRST:
            player.participant.vars["agent_programming_part2"] = decisions
        elif current_part == 3:
            player.participant.vars["agent_programming_part3"] = decisions

        history_raw = player.field_maybe_none("agent_prog_allocation") or "[]"
        try:
            history = json.loads(history_raw)
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
        history.append(
            {
                "round": r,
                "mean_value": mean_value,
                "allocations": allocations,
                "decisions": [decisions[i] for i in range(1, 11)],
            }
        )
        player.agent_prog_allocation = json.dumps(history)
        player.supervised_mean = float(mean_value)
        decisions_str = ",".join(decisions[i] for i in range(1, 11))
        player.supervised_last_generated_csv = decisions_str

        allocations_str = ",".join(str(x) for x in allocations)
        return {player.id_in_group: {"response": allocations_str, "decisions": decisions_str}}

    def before_next_page(self):
        super().before_next_page()

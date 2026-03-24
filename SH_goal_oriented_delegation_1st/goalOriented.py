import json
import random

from pages_classes import AgentProgramming

from .models import Constants


class GoalOriented(AgentProgramming):
    template_name = "SH_goal_oriented_delegation_1st/goalOriented.html"

    @staticmethod
    def live_method(player, data):
        if not data or "slider_value" not in data:
            return
        try:
            slider_value = float(data.get("slider_value"))
        except (TypeError, ValueError):
            slider_value = 0.5

        slider_value = max(0.0, min(1.0, slider_value))
        # Calibrated mapping:
        # 0 -> 5%, 0.25 -> 25%, 0.5 -> 50%, 0.75 -> 75%, 1 -> 95%.
        p_a = 0.05 + 0.90 * slider_value
        decisions = {
            i + 1: ("A" if random.random() < p_a else "B")
            for i in range(10)
        }
        allocations = [100 if decisions[i + 1] == "A" else 0 for i in range(10)]

        r = player.round_number
        if r == 1:
            player.participant.vars["agent_programming_part1"] = decisions
        elif r == 11:
            player.participant.vars["agent_programming_part2"] = decisions
        elif r == 21:
            player.participant.vars["agent_programming_part3"] = decisions

        # Keep a trace for export/debug; does not affect payoff logic.
        history_raw = player.agent_prog_allocation or "[]"
        try:
            history = json.loads(history_raw)
            if not isinstance(history, list):
                history = []
        except Exception:
            history = []
        history.append(
            {
                "round": r,
                "slider_value": slider_value,
                "allocations": allocations,
                "decisions": [decisions[i] for i in range(1, 11)],
            }
        )
        player.agent_prog_allocation = json.dumps(history)

        allocations_str = ",".join(str(x) for x in allocations)
        decisions_str = ",".join(decisions[i] for i in range(1, 11))
        return {player.id_in_group: {"response": allocations_str, "decisions": decisions_str}}

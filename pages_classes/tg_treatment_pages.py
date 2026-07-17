"""TG delegation treatment pages (goal-oriented, supervised, LLM) — two role blocks per part."""

from __future__ import annotations

import importlib
import json
import random

from otree.api import *

from shared.export_integrity import record_data_error
from shared.tg_block_validation import validate_tg_block_maps
from shared.tg_data_helpers import merge_block_map, read_agent_first_map_from_player

from .MistralPage import ChatGPTPage, _parse_strict_ten_ab
from .model_bridge import app_package_name, get_constants, is_tg_app
from .page_helpers import _has_left_lobby_for_part, is_excluded_from_study, part_vars
from .tg_v2_pages import (
    _agent_block_round,
    _copy_v2_agent_to_rounds,
    _part_agent_keys,
)


def _tg_supervised_csv_keys(part: int) -> tuple:
    """Part-scoped keys so mandatory vs optional supervised CSVs never overwrite each other."""
    return (
        f"_tg_supervised_csv_first_part_{part}",
        f"_tg_supervised_csv_second_part_{part}",
    )


def _tg_supervised_datasets_key(part: int, *, second: bool = False) -> str:
    suffix = "_second" if second else ""
    return f"_supervised_ab_datasets_cache{suffix}_part_{part}"


def _goal_slider_decisions(slider_value: float) -> dict:
    slider_value = max(0.0, min(1.0, float(slider_value)))
    p_a = 0.05 + 0.90 * slider_value
    return {i + 1: ("A" if random.random() < p_a else "B") for i in range(10)}


def _append_agent_prog_history(player, round_number: int, payload: dict) -> None:
    history_raw = player.field_maybe_none("agent_prog_allocation") or "[]"
    try:
        history = json.loads(history_raw)
        if not isinstance(history, list):
            history = []
    except (TypeError, ValueError):
        history = []
    history.append({"round": round_number, **payload})
    player.agent_prog_allocation = json.dumps(history)


def _safe_set_player_field(player, name: str, value) -> None:
    """Set a Player DB field only if it exists; never raise into the live request."""
    if not hasattr(player, name):
        return
    try:
        setattr(player, name, value)
    except Exception:
        return


def _write_agent_first_fields(player, decisions: dict, *, part: int | None = None) -> None:
    """Write 1st-mover agent block fields.

    Part 3 optional audit columns are filled only when the participant actually
    chose to delegate (never invent optional agent data on the human path).
    """
    try:
        mirror_optional = (
            part == 3 and player.field_maybe_none("delegate_decision_optional") is True
        )
    except Exception:
        mirror_optional = False
    for i in range(1, 11):
        d = decisions.get(i) or decisions.get(str(i))
        if d in ("A", "B"):
            _safe_set_player_field(player, f"agent_decision_mandatory_delegation_round_{i}", d)
            if mirror_optional:
                _safe_set_player_field(player, f"decision_optional_delegation_round_{i}", d)


def _write_agent_second_fields(player, decisions: dict, *, part: int | None = None) -> None:
    """Write 2nd-mover agent block fields (mandatory_* only; no optional_*_second schema)."""
    for i in range(1, 11):
        d = decisions.get(i) or decisions.get(str(i))
        if d in ("A", "B"):
            _safe_set_player_field(player, f"agent_decision_mandatory_second_round_{i}", d)


def _agent_block_finalize_error(participant, player, second_map: dict):
    Constants = get_constants(player)
    block_r = _agent_block_round(player) or player.round_number
    part = Constants.get_part(block_r)
    _, _, vars_key = _part_agent_keys(part)
    first_map = merge_block_map(
        participant, vars_key, player, read_agent_first_map_from_player
    )
    start_round = (part - 1) * Constants.rounds_per_part + 1
    block_err = validate_tg_block_maps(first_map, second_map, start_round)
    if block_err:
        record_data_error(participant, "PART_AGENT_CHOICES_INCOMPLETE", block_err)
    return block_err


class _TgAgentBlockFirst(Page):
    """Shared first-block display logic for TG treatment agent pages."""

    role_label = "1st mover"

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player)
        if block_r is None or self.round_number != block_r:
            return False
        part = Constants.get_part(block_r)
        if not _has_left_lobby_for_part(self.participant, part):
            return False
        first_done_key, done_key, _ = _part_agent_keys(part)
        return not self.participant.vars.get(first_done_key, False) and not self.participant.vars.get(
            done_key, False
        )

    def vars_for_template(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        return {
            "current_part": Constants.get_part(block_r),
            "countdown_seconds": 90,
            **part_vars(self.player),
        }

    def _store_first_block(self, decisions: dict) -> None:
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        first_done_key, _, vars_key = _part_agent_keys(part)
        _write_agent_first_fields(self.player, decisions, part=part)
        self.participant.vars[vars_key] = decisions
        self.participant.vars[first_done_key] = True


class _TgAgentBlockSecond(Page):
    """Shared second-block completion for TG treatment agent pages."""

    role_label = "2nd mover"

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player)
        if block_r is None or self.round_number != block_r:
            return False
        part = Constants.get_part(block_r)
        if not _has_left_lobby_for_part(self.participant, part):
            return False
        first_done_key, done_key, _ = _part_agent_keys(part)
        return self.participant.vars.get(first_done_key, False) and not self.participant.vars.get(
            done_key, False
        )

    def vars_for_template(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        return {
            "current_part": Constants.get_part(block_r),
            "countdown_seconds": 90,
            **part_vars(self.player),
        }

    def _block_finalize_error_message(self, second_map: dict):
        return _agent_block_finalize_error(self.participant, self.player, second_map)

    def _finalize_agent_block(self, second_map: dict) -> None:
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        _, done_key, vars_key = _part_agent_keys(part)
        first_map = merge_block_map(
            self.participant, vars_key, self.player, read_agent_first_map_from_player
        )
        _write_agent_second_fields(self.player, second_map, part=part)
        start_round = (part - 1) * Constants.rounds_per_part + 1
        block_err = validate_tg_block_maps(first_map, second_map, start_round)
        if block_err:
            record_data_error(
                self.participant,
                "PART_AGENT_CHOICES_INCOMPLETE",
                block_err,
            )
            return
        _copy_v2_agent_to_rounds(self.player, start_round, first_map, second_map)
        self.participant.vars[done_key] = True


class TgGoalOrientedFirst(_TgAgentBlockFirst):
    @property
    def template_name(self):
        return f"{app_package_name(self.player)}/goalOrientedFirst.html"

    @staticmethod
    def live_method(player, data):
        if not data or "slider_value" not in data:
            return
        try:
            slider_value = float(data.get("slider_value"))
        except (TypeError, ValueError):
            # Invalid payload: do not invent a 0.5 slider / A-B map.
            return
        decisions = _goal_slider_decisions(slider_value)
        allocations = [100 if decisions[i + 1] == "A" else 0 for i in range(10)]
        Constants = get_constants(player)
        block_r = _agent_block_round(player)
        if block_r is None:
            return
        part = Constants.get_part(block_r)
        _, _, vars_key = _part_agent_keys(part)
        player.participant.vars[vars_key] = decisions
        _append_agent_prog_history(
            player,
            player.round_number,
            {
                "role": "first",
                "slider_value": slider_value,
                "allocations": allocations,
                "decisions": [decisions[i] for i in range(1, 11)],
            },
        )
        allocations_str = ",".join(str(x) for x in allocations)
        decisions_str = ",".join(decisions[i] for i in range(1, 11))
        return {player.id_in_group: {"response": allocations_str, "decisions": decisions_str}}

    def error_message(self, values):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        _, _, vars_key = _part_agent_keys(part)
        decisions = dict(self.participant.vars.get(vars_key, {}))
        if len([d for d in decisions.values() if d in ("A", "B")]) < 10:
            record_data_error(
                self.participant, "GOAL_AGENT_FIRST_INCOMPLETE", f"part={part}"
            )
            return "Please complete all 10 agent decisions (1st mover) before continuing."
        return None

    def before_next_page(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        _, _, vars_key = _part_agent_keys(part)
        decisions = dict(self.participant.vars.get(vars_key, {}))
        if len([d for d in decisions.values() if d in ("A", "B")]) < 10:
            record_data_error(self.participant, "GOAL_AGENT_FIRST_INCOMPLETE", f"part={part}")
            return
        self._store_first_block(decisions)


class TgGoalOrientedSecond(_TgAgentBlockSecond):
    @property
    def template_name(self):
        return f"{app_package_name(self.player)}/goalOrientedSecond.html"

    @staticmethod
    def live_method(player, data):
        if not data or "slider_value" not in data:
            return
        try:
            slider_value = float(data.get("slider_value"))
        except (TypeError, ValueError):
            # Invalid payload: do not invent a 0.5 slider / A-B map.
            return
        decisions = _goal_slider_decisions(slider_value)
        allocations = [100 if decisions[i + 1] == "A" else 0 for i in range(10)]
        Constants = get_constants(player)
        block_r = _agent_block_round(player)
        part = (
            Constants.get_part(block_r)
            if block_r is not None
            else Constants.get_part(player.round_number)
        )
        _append_agent_prog_history(
            player,
            player.round_number,
            {
                "role": "second",
                "slider_value": slider_value,
                "allocations": allocations,
                "decisions": [decisions[i] for i in range(1, 11)],
            },
        )
        player.participant.vars[f"_tg_agent_second_pending_part_{part}"] = decisions
        allocations_str = ",".join(str(x) for x in allocations)
        decisions_str = ",".join(decisions[i] for i in range(1, 11))
        return {player.id_in_group: {"response": allocations_str, "decisions": decisions_str}}

    def error_message(self, values):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        second_map = dict(
            self.participant.vars.get(f"_tg_agent_second_pending_part_{part}", {}) or {}
        )
        if len([d for d in second_map.values() if d in ("A", "B")]) < 10:
            record_data_error(
                self.participant,
                "GOAL_AGENT_SECOND_INCOMPLETE",
                f"r={self.round_number}",
            )
            return "Please complete all 10 agent decisions (2nd mover) before continuing."
        return self._block_finalize_error_message(second_map)

    def before_next_page(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        second_map = dict(
            self.participant.vars.pop(f"_tg_agent_second_pending_part_{part}", {}) or {}
        )
        if len([d for d in second_map.values() if d in ("A", "B")]) < 10:
            record_data_error(
                self.participant,
                "GOAL_AGENT_SECOND_INCOMPLETE",
                f"r={self.round_number}",
            )
            return
        self._finalize_agent_block(second_map)


DATASET_P_A = [0.05, 0.25, 0.5, 0.75, 0.95]


def _sample_10_decisions(p_a: float) -> list:
    return ["A" if random.random() < p_a else "B" for _ in range(10)]


class TgSupervisedAgentFirst(_TgAgentBlockFirst):
    form_model = "player"
    form_fields = ["supervised_last_generated_csv"]

    @property
    def template_name(self):
        return f"{app_package_name(self.player)}/supervisedLearningFirst.html"

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
        decisions_list = _sample_10_decisions(p_a)
        response_str = ",".join(decisions_list)
        player.supervised_last_generated_csv = response_str
        player.supervised_mean = float(p_a)
        Constants = get_constants(player)
        block_r = _agent_block_round(player)
        if block_r is None:
            return
        part = Constants.get_part(block_r)
        _, _, vars_key = _part_agent_keys(part)
        player.participant.vars[vars_key] = {i + 1: decisions_list[i] for i in range(10)}
        return {player.id_in_group: {"response": response_str}}

    def _get_or_build_raw_datasets(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        key = _tg_supervised_datasets_key(part, second=False)
        cached = self.participant.vars.get(key)
        if cached is not None:
            return cached
        out = {i: _sample_10_decisions(DATASET_P_A[i]) for i in range(5)}
        self.participant.vars[key] = out
        return out

    def vars_for_template(self):
        ctx = super().vars_for_template()
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
        ctx.update(
            {
                "datasets": formatted_datasets,
                "delegate_decision": self.player.field_maybe_none("delegate_decision_optional"),
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

    def before_next_page(self):
        csv_val = (self.player.field_maybe_none("supervised_last_generated_csv") or "").strip()
        tokens = [x.strip().upper() for x in csv_val.split(",") if x.strip()]
        if len(tokens) != 10 or not all(t in ("A", "B") for t in tokens):
            record_data_error(self.participant, "SUPERVISED_AGENT_FIRST_INCOMPLETE", "")
            return
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        first_key, _ = _tg_supervised_csv_keys(part)
        self.participant.vars[first_key] = csv_val
        decisions = {i + 1: tokens[i] for i in range(10)}
        self._store_first_block(decisions)


class TgSupervisedAgentSecond(_TgAgentBlockSecond):
    form_model = "player"
    form_fields = ["supervised_last_generated_csv"]

    @property
    def template_name(self):
        return f"{app_package_name(self.player)}/supervisedLearningSecond.html"

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
        decisions_list = _sample_10_decisions(p_a)
        response_str = ",".join(decisions_list)
        player.supervised_last_generated_csv = response_str
        Constants = get_constants(player)
        block_r = _agent_block_round(player)
        part = Constants.get_part(block_r) if block_r is not None else Constants.get_part(player.round_number)
        player.participant.vars[f"_tg_agent_second_pending_part_{part}"] = {
            i + 1: decisions_list[i] for i in range(10)
        }
        return {player.id_in_group: {"response": response_str}}

    def _get_or_build_raw_datasets(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        key = _tg_supervised_datasets_key(part, second=True)
        cached = self.participant.vars.get(key)
        if cached is not None:
            return cached
        out = {i: _sample_10_decisions(DATASET_P_A[i]) for i in range(5)}
        self.participant.vars[key] = out
        return out

    def vars_for_template(self):
        ctx = super().vars_for_template()
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        supervised_dataset = self._get_or_build_raw_datasets()
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
        # Do not inherit first-block CSV as second-block preview.
        pending = self.participant.vars.get(f"_tg_agent_second_pending_part_{part}") or {}
        if len(pending) == 10 and all(pending.get(i) in ("A", "B") for i in range(1, 11)):
            preview_rows = [{"round_num": i, "value": pending[i]} for i in range(1, 11)]
            show_confirm = True
            supervised_csv_hidden = ",".join(pending[i] for i in range(1, 11))
        else:
            supervised_csv_hidden = ""
        ctx.update(
            {
                "datasets": formatted_datasets,
                "delegate_decision": self.player.field_maybe_none("delegate_decision_optional"),
                "preview_rows": preview_rows,
                "show_confirm": show_confirm,
                "supervised_csv_hidden": supervised_csv_hidden,
            }
        )
        return ctx

    def error_message(self, values):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        csv_val = (values.get("supervised_last_generated_csv") or "").strip()
        if not csv_val:
            return "Please select a dataset, click Generate, then Confirm."
        parts = [p.strip().upper() for p in csv_val.split(",") if p.strip()]
        if len(parts) != 10 or not all(p in ("A", "B") for p in parts):
            return "Please select a dataset, click Generate, then Confirm."
        second_map = dict(
            self.participant.vars.get(f"_tg_agent_second_pending_part_{part}", {}) or {}
        )
        if len(second_map) < 10:
            second_map = {i + 1: parts[i] for i in range(10)}
        return self._block_finalize_error_message(second_map)

    def before_next_page(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        pending_key = f"_tg_agent_second_pending_part_{part}"
        second_map = dict(self.participant.vars.pop(pending_key, {}) or {})
        csv_val = (self.player.field_maybe_none("supervised_last_generated_csv") or "").strip()
        if len(second_map) < 10 and csv_val:
            tokens = [x.strip().upper() for x in csv_val.split(",") if x.strip()]
            if len(tokens) == 10 and all(t in ("A", "B") for t in tokens):
                second_map = {i + 1: tokens[i] for i in range(10)}
                csv_val = ",".join(tokens)
        if len([d for d in second_map.values() if d in ("A", "B")]) < 10:
            record_data_error(self.participant, "SUPERVISED_AGENT_SECOND_INCOMPLETE", "")
            return
        if csv_val:
            _, second_key = _tg_supervised_csv_keys(part)
            self.participant.vars[second_key] = csv_val
        self._finalize_agent_block(second_map)


class TgLlmAgentFirst(ChatGPTPage):
    """LLM agent programming — contingent 1st-mover block."""

    @property
    def template_name(self):
        if is_tg_app(self.player):
            return f"{app_package_name(self.player)}/MistralPageFirst.html"
        return super().template_name

    def is_displayed(self):
        if not is_tg_app(self.player):
            return super().is_displayed()
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player)
        if block_r is None or self.round_number != block_r:
            return False
        part = Constants.get_part(block_r)
        if not _has_left_lobby_for_part(self.participant, part):
            return False
        first_done_key, done_key, _ = _part_agent_keys(part)
        return not self.participant.vars.get(first_done_key, False) and not self.participant.vars.get(
            done_key, False
        )

    def _conversation_field_name(self) -> str:
        return "conversation_history"

    def get_final_assistant_response(self):
        raw = self.player.field_maybe_none(self._conversation_field_name()) or "[]"
        try:
            conversation = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        for msg in reversed(conversation):
            if msg.get("role") != "assistant":
                continue
            choices = _parse_strict_ten_ab((msg.get("content") or "").strip())
            if choices:
                return {i: ch for i, ch in enumerate(choices, start=1)}
        return {}

    def error_message(self, values):
        if not is_tg_app(self.player):
            return None
        decisions = self.get_final_assistant_response()
        if not decisions or any(decisions.get(i) not in ("A", "B") for i in range(1, 11)):
            record_data_error(
                self.participant, "LLM_AGENT_FIRST_INCOMPLETE", f"r={self.round_number}"
            )
            return "Please obtain a complete 10-round A/B plan from the assistant before continuing."
        return None

    def before_next_page(self):
        if not is_tg_app(self.player):
            return super().before_next_page()
        decisions = self.get_final_assistant_response()
        if not decisions or any(decisions.get(i) not in ("A", "B") for i in range(1, 11)):
            record_data_error(self.participant, "LLM_AGENT_FIRST_INCOMPLETE", f"r={self.round_number}")
            return
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        first_done_key, _, vars_key = _part_agent_keys(part)
        _write_agent_first_fields(self.player, decisions, part=part)
        self.participant.vars[vars_key] = decisions
        self.participant.vars[first_done_key] = True

    @staticmethod
    def live_method(player, data):
        if not is_tg_app(player):
            return ChatGPTPage.live_method(player, data)
        return _tg_llm_live_method(player, data, "conversation_history")


class TgLlmAgentSecond(ChatGPTPage):
    """LLM agent programming — contingent 2nd-mover block."""

    @property
    def template_name(self):
        if is_tg_app(self.player):
            return f"{app_package_name(self.player)}/MistralPageSecond.html"
        return super().template_name

    def is_displayed(self):
        if not is_tg_app(self.player):
            return False
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player)
        if block_r is None or self.round_number != block_r:
            return False
        part = Constants.get_part(block_r)
        if not _has_left_lobby_for_part(self.participant, part):
            return False
        first_done_key, done_key, _ = _part_agent_keys(part)
        return self.participant.vars.get(first_done_key, False) and not self.participant.vars.get(
            done_key, False
        )

    def _conversation_field_name(self) -> str:
        return "conversation_history_second"

    def get_final_assistant_response(self):
        raw = self.player.field_maybe_none(self._conversation_field_name()) or "[]"
        try:
            conversation = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        for msg in reversed(conversation):
            if msg.get("role") != "assistant":
                continue
            choices = _parse_strict_ten_ab((msg.get("content") or "").strip())
            if choices:
                return {i: ch for i, ch in enumerate(choices, start=1)}
        return {}

    def error_message(self, values):
        second_map = self.get_final_assistant_response()
        if not second_map or any(second_map.get(i) not in ("A", "B") for i in range(1, 11)):
            record_data_error(
                self.participant, "LLM_AGENT_SECOND_INCOMPLETE", f"r={self.round_number}"
            )
            return "Please obtain a complete 10-round A/B plan from the assistant before continuing."
        return _agent_block_finalize_error(self.participant, self.player, second_map)

    def before_next_page(self):
        second_map = self.get_final_assistant_response()
        if not second_map or any(second_map.get(i) not in ("A", "B") for i in range(1, 11)):
            record_data_error(self.participant, "LLM_AGENT_SECOND_INCOMPLETE", f"r={self.round_number}")
            return
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        _, done_key, vars_key = _part_agent_keys(part)
        first_map = merge_block_map(
            self.participant, vars_key, self.player, read_agent_first_map_from_player
        )
        _write_agent_second_fields(self.player, second_map, part=part)
        start_round = (part - 1) * Constants.rounds_per_part + 1
        if _agent_block_finalize_error(self.participant, self.player, second_map):
            return
        _copy_v2_agent_to_rounds(self.player, start_round, first_map, second_map)
        self.participant.vars[done_key] = True

    @staticmethod
    def live_method(player, data):
        return _tg_llm_live_method(player, data, "conversation_history_second")


def _tg_llm_live_method(player, data, conversation_field: str):
    if not data or "message" not in data:
        return
    Constants = get_constants(player)
    current_part = Constants.get_part(player.round_number)
    conv_key = f"mistral_conversation_id_part_{current_part}_{conversation_field}"
    conversation_id = player.participant.vars.get(conv_key)
    try:
        assistant_module = importlib.import_module(f"{app_package_name(player)}.mistralassistant")
        assistant = assistant_module.MistralAssistant()
    except Exception as e:
        return {player.id_in_group: {"response": "Error initializing assistant: " + str(e)}}
    user_message = data["message"]
    response_text = ""
    new_cid = conversation_id
    from .MistralPage import (
        _MISTRAL_SEND_FAILURE_USER_MESSAGE,
        _MISTRAL_SEND_MAX_ATTEMPTS,
        _MISTRAL_SEND_RETRY_BASE_SLEEP_SEC,
    )
    import time

    cid_for_attempt = conversation_id
    for attempt in range(_MISTRAL_SEND_MAX_ATTEMPTS):
        try:
            response_text, new_cid = assistant.send_message(user_message, conversation_id=cid_for_attempt)
            break
        except Exception:
            if attempt + 1 >= _MISTRAL_SEND_MAX_ATTEMPTS:
                response_text = _MISTRAL_SEND_FAILURE_USER_MESSAGE
                new_cid = conversation_id
                break
            time.sleep(_MISTRAL_SEND_RETRY_BASE_SLEEP_SEC * (attempt + 1))
            cid_for_attempt = conversation_id
    if new_cid:
        player.participant.vars[conv_key] = new_cid
    raw = player.field_maybe_none(conversation_field) or "[]"
    try:
        conversation = json.loads(raw)
    except (TypeError, ValueError):
        conversation = []
    conversation.append({"role": "user", "content": user_message})
    conversation.append({"role": "assistant", "content": response_text})
    setattr(player, conversation_field, json.dumps(conversation))
    return {player.id_in_group: {"response": response_text}}

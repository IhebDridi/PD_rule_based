"""TG v2 pages: one screen per role (human decisions) or per role block (agent programming)."""

from otree.api import *

from shared.export_integrity import record_data_error
from shared.session_part_lock import persist_session_state
from shared.tg_block_validation import validate_tg_block_maps
from shared.tg_data_helpers import (
    copy_tg_contingent_maps_to_rounds,
    merge_block_map,
    read_agent_first_map_from_player,
    read_human_first_map_from_player,
)
from shared.tg_human_block_vars import (
    backfill_human_block_fields_on_player,
    human_block_maps_from_vars,
    record_human_first_choice,
    record_human_second_choice,
)

from .model_bridge import get_constants
from .page_helpers import _has_left_lobby_for_part, is_excluded_from_study, part_vars


def _human_decision_displayed(player, participant) -> bool:
    if is_excluded_from_study(player):
        return False
    Constants = get_constants(player)
    part = Constants.get_part(player.round_number)
    if player.round_number in (1, 11, 21) and not _has_left_lobby_for_part(participant, part):
        return False
    if part == 3:
        if player.field_maybe_none("delegate_decision_optional") is True:
            return False
        return True
    return not Constants.is_mandatory_delegation_round(player.round_number)


def _decision_template_vars(player, role_label: str) -> dict:
    Constants = get_constants(player)
    round_in_part = (player.round_number - 1) % Constants.rounds_per_part + 1
    current_part = Constants.get_part(player.round_number)
    return {
        "round_number": round_in_part,
        "current_part": current_part,
        "role_label": role_label,
        "countdown_seconds": 15,
        **part_vars(player),
    }


def _human_block_round(player) -> int | None:
    """First oTree round of a no-delegation part (where the 10+10 human blocks run)."""
    Constants = get_constants(player)
    r = player.round_number
    if Constants.is_mandatory_delegation_round(r):
        return None
    if Constants.get_part(r) == 3 and player.field_maybe_none("delegate_decision_optional") is True:
        return None
    part_start = (Constants.get_part(r) - 1) * Constants.rounds_per_part + 1
    if r == part_start:
        return r
    return None


def _part_human_keys(part: int) -> tuple:
    return (
        f"human_v2_first_done_part{part}",
        f"human_v2_done_part{part}",
        f"human_v2_first_part{part}",
    )


def _human_first_step_key(part: int) -> str:
    return f"human_v2_first_step_part{part}"


def _human_second_step_key(part: int) -> str:
    return f"human_v2_second_step_part{part}"


def _first_human_fields():
    return [f"human_decision_no_delegation_round_{i}" for i in range(1, 11)]


def _second_human_fields():
    return [f"human_second_no_delegation_round_{i}" for i in range(1, 11)]


def _first_human_complete(values) -> bool:
    return all(values.get(f"human_decision_no_delegation_round_{i}") in ("A", "B") for i in range(1, 11))


def _second_human_complete(values) -> bool:
    return all(values.get(f"human_second_no_delegation_round_{i}") in ("A", "B") for i in range(1, 11))


def _copy_v2_human_to_rounds(player, start_round: int, first_map: dict, second_map: dict) -> None:
    copy_tg_contingent_maps_to_rounds(player, start_round, first_map, second_map)


class TgV2HumanDecisionsFirst(Page):
    """One contingent 1st-mover human decision per page visit (10 visits per no-delegation part)."""

    template_name = "global/TgV2HumanDecisionsFirst.html"
    form_model = "player"
    preserve_unsubmitted_inputs = False

    def _part_and_step(self):
        Constants = get_constants(self.player)
        block_r = _human_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        step = self.participant.vars.get(_human_first_step_key(part), 0)
        return part, step

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        block_r = _human_block_round(self.player)
        if block_r is None or self.round_number != block_r:
            return False
        Constants = get_constants(self.player)
        part = Constants.get_part(block_r)
        if not _has_left_lobby_for_part(self.participant, part):
            return False
        first_done_key, done_key, _ = _part_human_keys(part)
        if self.participant.vars.get(first_done_key, False) or self.participant.vars.get(done_key, False):
            return False
        step = self.participant.vars.get(_human_first_step_key(part), 0)
        return step < 10

    def get_form_fields(self):
        if not self.is_displayed():
            return []
        _, step = self._part_and_step()
        return [f"human_decision_no_delegation_round_{step + 1}"]

    def vars_for_template(self):
        Constants = get_constants(self.player)
        block_r = _human_block_round(self.player) or self.round_number
        part, step = self._part_and_step()
        return {
            "current_part": part,
            "decision_round": step + 1,
            **part_vars(self.player),
        }

    def error_message(self, values):
        _, step = self._part_and_step()
        field = f"human_decision_no_delegation_round_{step + 1}"
        if values.get(field) not in ("A", "B"):
            return "Please choose A or B (as 1st mover) before continuing."
        return None

    def before_next_page(self):
        Constants = get_constants(self.player)
        block_r = _human_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        first_done_key, _, _ = _part_human_keys(part)
        step_key = _human_first_step_key(part)
        step = self.participant.vars.get(step_key, 0)
        round_i = step + 1
        choice = self.player.field_maybe_none(f"human_decision_no_delegation_round_{round_i}")
        record_human_first_choice(self.participant, part, round_i, choice)
        self.participant.vars[step_key] = round_i
        if round_i >= 10:
            self.participant.vars[first_done_key] = True


class TgV2HumanDecisionsSecond(Page):
    """One contingent 2nd-mover human decision per page visit (10 visits after the 1st-mover block)."""

    template_name = "global/TgV2HumanDecisionsSecond.html"
    form_model = "player"
    preserve_unsubmitted_inputs = False

    def _part_and_step(self):
        Constants = get_constants(self.player)
        block_r = _human_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        step = self.participant.vars.get(_human_second_step_key(part), 0)
        return part, step

    def is_displayed(self):
        if is_excluded_from_study(self.player):
            return False
        block_r = _human_block_round(self.player)
        if block_r is None or self.round_number != block_r:
            return False
        Constants = get_constants(self.player)
        part = Constants.get_part(block_r)
        if not _has_left_lobby_for_part(self.participant, part):
            return False
        first_done_key, done_key, _ = _part_human_keys(part)
        if not self.participant.vars.get(first_done_key, False) or self.participant.vars.get(done_key, False):
            return False
        step = self.participant.vars.get(_human_second_step_key(part), 0)
        return step < 10

    def get_form_fields(self):
        if not self.is_displayed():
            return []
        _, step = self._part_and_step()
        return [f"human_second_no_delegation_round_{step + 1}"]

    def vars_for_template(self):
        part, step = self._part_and_step()
        return {
            "current_part": part,
            "decision_round": step + 1,
            **part_vars(self.player),
        }

    def error_message(self, values):
        _, step = self._part_and_step()
        field = f"human_second_no_delegation_round_{step + 1}"
        if values.get(field) not in ("A", "B"):
            return "Please choose A or B (as 2nd mover) before continuing."
        if step + 1 < 10:
            return None
        Constants = get_constants(self.player)
        block_r = _human_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        first_map, second_map = human_block_maps_from_vars(self.participant, part)
        round_i = step + 1
        choice = values.get(f"human_second_no_delegation_round_{round_i}")
        if choice in ("A", "B"):
            second_map[round_i] = choice
        start_round = (part - 1) * Constants.rounds_per_part + 1
        block_err = validate_tg_block_maps(first_map, second_map, start_round)
        if block_err:
            record_data_error(
                self.participant,
                "HUMAN_CHOICES_INCOMPLETE",
                block_err,
            )
            return block_err
        return None

    def before_next_page(self):
        Constants = get_constants(self.player)
        block_r = _human_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        _, done_key, _ = _part_human_keys(part)
        step_key = _human_second_step_key(part)
        step = self.participant.vars.get(step_key, 0)
        round_i = step + 1
        choice = self.player.field_maybe_none(f"human_second_no_delegation_round_{round_i}")
        record_human_second_choice(self.participant, part, round_i, choice)
        self.participant.vars[step_key] = round_i
        if round_i < 10:
            return
        first_map, second_map = human_block_maps_from_vars(self.participant, part)
        start_round = (part - 1) * Constants.rounds_per_part + 1
        missing = []
        for i in range(1, 11):
            if first_map.get(i) not in ("A", "B") or second_map.get(i) not in ("A", "B"):
                missing.append(str(start_round + i - 1))
        if missing:
            record_data_error(
                self.participant,
                "HUMAN_CHOICES_INCOMPLETE",
                ",".join(missing),
            )
            return
        backfill_human_block_fields_on_player(self.player, first_map, second_map)
        _copy_v2_human_to_rounds(self.player, start_round, first_map, second_map)
        self.participant.vars[done_key] = True
        # Flush before oTree auto-skips into BatchWait in the same request.
        persist_session_state(self.session)


HUMAN_DECISIONS_PER_ROLE = 10
TG_V2_HUMAN_DECISIONS_FIRST_PAGES = [TgV2HumanDecisionsFirst] * HUMAN_DECISIONS_PER_ROLE
TG_V2_HUMAN_DECISIONS_SECOND_PAGES = [TgV2HumanDecisionsSecond] * HUMAN_DECISIONS_PER_ROLE


# Legacy per-round pages (superseded by block pages above).
class TgV2DecisionFirstMover(Page):
    """One A/B choice per oTree round: contingent 1st-mover decision for this round."""

    template_name = "global/TgV2DecisionFirstMover.html"
    form_model = "player"
    form_fields = ["choice_first_mover"]

    def is_displayed(self):
        return _human_decision_displayed(self.player, self.participant)

    def vars_for_template(self):
        return _decision_template_vars(self.player, "1st mover")

    def error_message(self, values):
        if values.get("choice_first_mover") not in ("A", "B"):
            return "Please choose A or B for your 1st-mover decision."
        return None

    def before_next_page(self):
        if self.player.field_maybe_none("choice_first_mover") not in ("A", "B"):
            record_data_error(
                self.participant,
                "CHOICE_MISSING",
                f"first_mover r={self.round_number}",
            )


class TgV2DecisionSecondMover(Page):
    """One A/B choice per oTree round: contingent 2nd-mover decision for this round."""

    template_name = "global/TgV2DecisionSecondMover.html"
    form_model = "player"
    form_fields = ["choice_second_mover"]

    def is_displayed(self):
        return _human_decision_displayed(self.player, self.participant)

    def vars_for_template(self):
        return _decision_template_vars(self.player, "2nd mover")

    def error_message(self, values):
        if values.get("choice_second_mover") not in ("A", "B"):
            return "Please choose A or B for your 2nd-mover decision."
        return None

    def before_next_page(self):
        if self.player.field_maybe_none("choice_second_mover") not in ("A", "B"):
            record_data_error(
                self.participant,
                "CHOICE_MISSING",
                f"second_mover r={self.round_number}",
            )


def _first_agent_fields():
    return [f"agent_decision_mandatory_delegation_round_{i}" for i in range(1, 11)]


def _second_agent_fields():
    return [f"agent_decision_mandatory_second_round_{i}" for i in range(1, 11)]


def _first_agent_complete(values) -> bool:
    return all(values.get(f"agent_decision_mandatory_delegation_round_{i}") in ("A", "B") for i in range(1, 11))


def _second_agent_complete(values) -> bool:
    return all(values.get(f"agent_decision_mandatory_second_round_{i}") in ("A", "B") for i in range(1, 11))


def _part_agent_keys(part: int) -> tuple:
    """Return (first_done_key, programming_done_key, first_vars_key)."""
    if part == 1:
        return (
            "agent_v2_first_done_part1",
            "agent_programming_done_part1",
            "agent_v2_first_part1",
        )
    if part == 2:
        return (
            "agent_v2_first_done_part2",
            "agent_programming_done_part2",
            "agent_v2_first_part2",
        )
    return (
        "agent_v2_first_done_part3",
        "agent_programming_done_part3",
        "agent_v2_first_part3",
    )


def _agent_block_round(player) -> int | None:
    """Round number where the v2 agent block starts for the current mandatory/optional part."""
    Constants = get_constants(player)
    r = player.round_number
    if r == 1 and Constants.DELEGATION_FIRST:
        return 1
    if r == 11 and not Constants.DELEGATION_FIRST:
        return 11
    if Constants.get_part(r) == 3 and r == 21:
        if player.field_maybe_none("delegate_decision_optional") is True:
            return 21
    return None


def _copy_v2_agent_to_rounds(player, start_round: int, first_map: dict, second_map: dict) -> None:
    copy_tg_contingent_maps_to_rounds(player, start_round, first_map, second_map)


class TgV2AgentProgrammingFirst(Page):
    """All 10 contingent 1st-mover agent decisions on one page."""

    template_name = "global/TgV2AgentProgrammingFirst.html"
    form_model = "player"
    preserve_unsubmitted_inputs = True

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

    def get_form_fields(self):
        if self.is_displayed():
            return _first_agent_fields()
        return []

    def vars_for_template(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        return {
            "current_part": Constants.get_part(block_r),
            "countdown_seconds": 90,
            **part_vars(self.player),
        }

    def error_message(self, values):
        if not _first_agent_complete(values):
            return "Please choose A or B for every round (as 1st mover) before continuing."
        return None

    def before_next_page(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        first_done_key, _, vars_key = _part_agent_keys(part)
        decisions = {
            i: self.player.field_maybe_none(f"agent_decision_mandatory_delegation_round_{i}")
            for i in range(1, 11)
        }
        self.participant.vars[vars_key] = decisions
        self.participant.vars[first_done_key] = True
        # Part 3 optional audit columns only when they chose to delegate.
        # Do not use hasattr(player, field): oTree raises TypeError on null fields.
        if part == 3 and self.player.field_maybe_none("delegate_decision_optional") is True:
            for i in range(1, 11):
                d = decisions.get(i)
                if d in ("A", "B"):
                    field = f"decision_optional_delegation_round_{i}"
                    try:
                        setattr(self.player, field, d)
                    except Exception:
                        pass


class TgV2AgentProgrammingSecond(Page):
    """All 10 contingent 2nd-mover agent decisions on one page."""

    template_name = "global/TgV2AgentProgrammingSecond.html"
    form_model = "player"
    preserve_unsubmitted_inputs = True

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

    def get_form_fields(self):
        if self.is_displayed():
            return _second_agent_fields()
        return []

    def vars_for_template(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        return {
            "current_part": Constants.get_part(block_r),
            "countdown_seconds": 90,
            **part_vars(self.player),
        }

    def error_message(self, values):
        if not _second_agent_complete(values):
            return "Please choose A or B for every round (as 2nd mover) before continuing."
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        _, _, vars_key = _part_agent_keys(part)
        first_map = merge_block_map(
            self.participant, vars_key, self.player, read_agent_first_map_from_player
        )
        second_map = {
            i: values.get(f"agent_decision_mandatory_second_round_{i}")
            or self.player.field_maybe_none(f"agent_decision_mandatory_second_round_{i}")
            for i in range(1, 11)
        }
        start_round = (part - 1) * Constants.rounds_per_part + 1
        block_err = validate_tg_block_maps(first_map, second_map, start_round)
        if block_err:
            record_data_error(
                self.participant,
                "PART_AGENT_CHOICES_INCOMPLETE",
                block_err,
            )
            return block_err
        return None

    def before_next_page(self):
        Constants = get_constants(self.player)
        block_r = _agent_block_round(self.player) or self.round_number
        part = Constants.get_part(block_r)
        _, done_key, vars_key = _part_agent_keys(part)
        first_map = merge_block_map(
            self.participant, vars_key, self.player, read_agent_first_map_from_player
        )
        second_map = {
            i: self.player.field_maybe_none(f"agent_decision_mandatory_second_round_{i}")
            for i in range(1, 11)
        }
        start_round = (part - 1) * Constants.rounds_per_part + 1
        missing = []
        for i in range(1, 11):
            f = first_map.get(i) or first_map.get(str(i))
            s = second_map.get(i)
            if f not in ("A", "B") or s not in ("A", "B"):
                missing.append(str(start_round + i - 1))
        if missing:
            record_data_error(
                self.participant,
                "PART_AGENT_CHOICES_INCOMPLETE",
                ",".join(missing),
            )
            return
        _copy_v2_agent_to_rounds(self.player, start_round, first_map, second_map)
        self.participant.vars[done_key] = True
        # Flush before oTree auto-skips into BatchWait in the same request.
        persist_session_state(self.session)

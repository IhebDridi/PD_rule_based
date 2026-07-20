"""
Single implementation of delegation study CSV custom_export logic.

Each app supplies a DelegationExportSpec (constants, labels, layout flags) and a thin
``def custom_export(players): yield from delegation_custom_export(players, SPEC)`` in models.py.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterator, List, Optional, Union

from shared.export_integrity import collect_export_integrity_errors
from shared.matching_batch import opponent_in_matching_batch


def coarse_agent_from_condition_app(condition: str, app_name: str) -> str:
    """Map exported Condition + Player.app_name to a coarse summary Agent label."""
    text = f"{condition or ''} {app_name or ''}".lower()
    if "llm" in text:
        return "llm"
    if "super" in text:
        return "super"
    if "goal" in text:
        return "goal"
    if "rule" in text:
        return "rule"
    return "no-agent"


def supervised_list_choices_export(
    pr: Any,
    get_fld: Callable[[Any, str], Any],
    *,
    part: Optional[int] = None,
) -> str:
    """Supervised agent blocks: datasets shown + every Generate attempt + confirmed CSVs.

    ``supervised_history`` may be legacy flat datasets or
    ``{datasets_first, datasets_second, attempts: [...]}``.
    For TG, pass ``part`` so confirmed CSVs use part-scoped participant.vars.
    """
    if not pr:
        return ""
    payload: dict = {}
    history = get_fld(pr, "supervised_history")
    if history:
        try:
            payload["history"] = json.loads(history) if isinstance(history, str) else history
        except Exception:
            payload["history_raw"] = history
    csv_confirmed = get_fld(pr, "supervised_last_generated_csv")
    if csv_confirmed:
        payload["confirmed_csv"] = csv_confirmed
    try:
        pvars = getattr(getattr(pr, "participant", None), "vars", None) or {}
        first_csv = second_csv = None
        if part is not None:
            first_key = f"_tg_supervised_csv_first_part_{part}"
            second_key = f"_tg_supervised_csv_second_part_{part}"
            first_csv = pvars.get(first_key)
            second_csv = pvars.get(second_key)
        # Legacy unscoped keys (pre part-scope) — only if part-scoped missing.
        if not first_csv:
            first_csv = pvars.get("_tg_supervised_csv_first")
        if not second_csv:
            second_csv = pvars.get("_tg_supervised_csv_second")
        if first_csv:
            payload["confirmed_csv_first"] = first_csv
        if second_csv:
            payload["confirmed_csv_second"] = second_csv
    except Exception:
        pass
    mean = get_fld(pr, "supervised_mean")
    if mean is not None and mean != "":
        payload["supervised_mean"] = mean
    if not payload:
        return ""
    return json.dumps(payload)


def _tg_effective_choice(role: Any, first_val: Any, second_val: Any) -> str:
    """Role-selected contingent choice actually played in a TG round."""
    if role == "first" and first_val in ("A", "B"):
        return first_val
    if role == "second" and second_val in ("A", "B"):
        return second_val
    return ""


def strip_allocations_json(raw_value: Any) -> str:
    if not raw_value or raw_value == "[]":
        return ""
    try:
        payload = json.loads(raw_value)
        if isinstance(payload, list):
            for item in payload:
                if isinstance(item, dict):
                    item.pop("allocations", None)
        return json.dumps(payload)
    except Exception:
        return raw_value if isinstance(raw_value, str) else ""


def opponent_for_export(
    pr: Any,
    r: int,
    round_data: dict,
    rr_cache: dict,
    C: Any,
    compute_rr: Callable[[int, int], Any],
) -> Any:
    if r not in round_data:
        return None
    gid = getattr(pr, "group_id", None)
    if gid is None and getattr(pr, "group", None) is not None:
        gid = getattr(pr.group, "id", None)
    if gid is None:
        return None
    sorted_players = round_data[r].get(gid)
    if not sorted_players:
        return None
    n_players = len(sorted_players)
    if n_players <= 1:
        return None
    my_idx = next((i for i, p in enumerate(sorted_players) if p.id == pr.id), None)
    if my_idx is None or my_idx < 0 or my_idx >= n_players:
        return None
    if n_players == 2:
        return sorted_players[1 - my_idx]
    part = C.get_part(r)
    part_start = (part - 1) * C.rounds_per_part + 1
    round_in_part = r - part_start
    if round_in_part < 0 or round_in_part >= C.rounds_per_part:
        return None
    if n_players not in rr_cache:
        rr_cache[n_players] = compute_rr(n_players, C.rounds_per_part)
    assignments = rr_cache[n_players]
    if round_in_part >= len(assignments[my_idx]):
        return None
    opp_idx, _ = assignments[my_idx][round_in_part]
    if opp_idx is None or opp_idx < 0 or opp_idx >= n_players:
        return None
    return sorted_players[opp_idx]


@dataclass(frozen=True)
class DelegationExportSpec:
    """Configure delegation_custom_export for a specific app (PD/SD/SH × treatment)."""

    constants: Any
    compute_rr: Callable[[int, int], Any]
    game_used: str
    condition_first: str
    condition_second: str

    # All bundled PD/SD/SH apps use "first_person_agents". "compact_rounds" is still supported here
    # (empty per-round agent cells; guess dollars primary) for any external/custom specs.
    layout: str

    # rule_based fills UsedAiOrBot from the player field; standard leaves that column empty
    demographics: str

    # standard = simple group_id resolution; rule_based_gid = guarded gid fetch like rule-based apps
    round_data_style: str

    # Token written in per-round agent columns when that side is using the agent (first layout only)
    per_round_agent_token: str

    # If set, row["Agent"] uses this string; if None, coarse_agent_from_condition_app(condition, app_name)
    summary_agent_fixed: Optional[str]

    # llm | goal | supervised | empty — controls list / chat extension columns
    extension: str

    # normal field_maybe_none | safe try/except wrapper (rule-based exports)
    access_mode: str

    # normal | safe_wrap | matching_group_guard (rule 2nd style)
    opponent_mode: str

    # simple = float(pr.payoff or 0); currency = .amount on Currency fields
    payoff_mode: str

    # direct = p0.session.code; safe = getattr chain
    session_mode: str

    # strict = SIMULATED else prolific_id as-is; or_empty = (prolific_id or "") when not simulated
    prolific_mode: str

    log_errors_to_stderr: bool = False

    # Rule-based apps write results_display_cache at payoff time; export flags if missing.
    results_cache_required: bool = False

    # Deprecated: export uses matching_batch only (no session-wide group_id fallback).
    custom_opponent_resolver: Optional[Callable[[Any, int, dict, dict], Any]] = None


def canonical_delegation_export_header() -> List[str]:
    """
    Column list used for every PD/SD/SH delegation app export.

    Superset of all per-spec columns so merged CSVs and cross-app pipelines share
    one header; cells that do not apply to a given treatment stay empty (or derived
    where noted in ``delegation_custom_export``).
    """
    header: List[str] = [
        "Condition",
        "AppName",
        "ProlificID",
        "Session",
        "Group",
        "GroupPart1",
        "GroupPart2",
        "GroupPart3",
        # Trio seat 1–3 within GroupPart (not id_in_session / Prolific).
        "GroupPosition",
        "GroupPositionPart1",
        "GroupPositionPart2",
        "GroupPositionPart3",
        # Legacy aliases — same values as GroupPosition*; kept for old analysis scripts.
        "PlayerID",
        "PlayerIDPart1",
        "PlayerIDPart2",
        "PlayerIDPart3",
        "TrioPosition",
        "TrioPositionPart1",
        "TrioPositionPart2",
        "TrioPositionPart3",
        "ExportErrors",
        "IsSimulated",
        "Gender",
        "Age",
        "Occupation",
        "AIuse",
        "TaskDifficulty",
        "Part3Feedback",
        "Part3FeedbackOther",
        "Part4Feedback",
        "Part4FeedbackOther",
        "UsedAiOrBot",
        "FeedbackFreeText",
    ]
    for r in range(1, 31):
        header += [
            f"Round{r}Decision",
            f"Round{r}DecisionFirstMover",
            f"Round{r}DecisionSecondMover",
            f"Round{r}RoleAssigned",
            f"Round{r}EffectiveDecision",
            f"Round{r}CoplayerID",
            f"Round{r}CoplayerDecision",
            f"Round{r}CoplayerDecisionFirstMover",
            f"Round{r}CoplayerDecisionSecondMover",
            f"Round{r}CoplayerRoleAssigned",
            f"Round{r}CoplayerEffectiveDecision",
            f"Round{r}Ecoins",
            f"Round{r}PlayerAgent",
            f"Round{r}CoPlayerAgent",
        ]
    for i in range(1, 11):
        header += [
            f"Guess{i}",
            f"TruthGuess{i}",
            f"EarningsGuess{i}",
            f"EarningsGuess{i}Dollars",
        ]
    header += ["DelegatedPart1", "DelegatedPart2", "DelegatedPart3", "Agent"]
    header += [
        "TotalEarningsPart1Ecoins",
        "TotalEarningsPart2Ecoins",
        "TotalEarningsPart3Ecoins",
        "PartChosenBonus",
        "TotalEarningsParts123Dollars",
        "TotalEarningsPart4Dollars",
        "BonusPaymentTotal",
        "SupervisedListChoicesDelegation",
        "SupervisedListChoicesOptional",
        "GoalListChoicesDelegation",
        "GoalListChoicesOptional",
        "LLMchatDelegation",
        "LLMchatOptional",
        "GameUsed",
    ]
    return header


def _build_round_data_standard(by_round: dict, num_rounds: int) -> dict:
    round_data = {}
    for r in range(1, num_rounds + 1):
        if r not in by_round:
            continue
        by_group = defaultdict(list)
        for p in by_round[r]:
            gid = getattr(p, "group_id", None) or (
                getattr(p.group, "id", None) if getattr(p, "group", None) else None
            )
            if gid is not None:
                by_group[gid].append(p)
        round_data[r] = {
            gid: sorted(plist, key=lambda p: p.participant.vars.get("matching_group_position", 0))
            for gid, plist in by_group.items()
        }
    return round_data


def _build_round_data_rule_based(by_round: dict, num_rounds: int) -> dict:
    round_data = {}
    for r in range(1, num_rounds + 1):
        if r not in by_round:
            continue
        by_group = defaultdict(list)
        for p in by_round[r]:
            gid = getattr(p, "group_id", None)
            if gid is None:
                try:
                    g = getattr(p, "group", None)
                    gid = getattr(g, "id", None) if g is not None else None
                except Exception:
                    gid = None
            if gid is not None:
                by_group[gid].append(p)
        round_data[r] = {
            gid: sorted(plist, key=lambda p: p.participant.vars.get("matching_group_position", 0))
            for gid, plist in by_group.items()
        }
    return round_data


def _pay_export_amount(pay_raw: Any) -> Optional[float]:
    if pay_raw is None:
        return None
    amt = getattr(pay_raw, "amount", pay_raw)
    try:
        return float(amt)
    except (TypeError, ValueError):
        return None


def _export_guess_cell(guess_val: Any) -> Union[int, str]:
    if guess_val == "yes":
        return 1
    if guess_val == "no":
        return 0
    return ""


def _export_truth_cell(other: Any, get_fld: Callable[[Any, str], Any]) -> Union[int, str]:
    if other is None:
        return ""
    delegated = get_fld(other, "delegate_decision_optional")
    if delegated is True:
        return 1
    if delegated is False:
        return 0
    return ""


def _export_ecoins_cell(pay_float: Optional[float]) -> Union[int, str]:
    if pay_float is None:
        return ""
    try:
        return int(pay_float)
    except (TypeError, ValueError):
        return ""


def _sum_export_numeric_cells(row: dict, keys: List[str], multiplier: float = 1.0) -> Optional[float]:
    """Sum all cells; return None if any is missing/invalid (never a partial sum)."""
    if not keys:
        return None
    total = 0.0
    for key in keys:
        raw = row.get(key)
        if raw is None or raw == "":
            return None
        try:
            total += float(raw) * multiplier
        except (TypeError, ValueError):
            return None
    return total


def delegation_custom_export(players: list, spec: DelegationExportSpec) -> Iterator[list]:
    C = spec.constants
    by_participant = defaultdict(list)
    by_round = defaultdict(list)
    for p in players:
        by_participant[p.participant.code].append(p)
        by_round[p.round_number].append(p)

    if spec.round_data_style == "rule_based_gid":
        round_data = _build_round_data_rule_based(by_round, C.num_rounds)
    else:
        round_data = _build_round_data_standard(by_round, C.num_rounds)
    rr_cache: dict = {}

    header = canonical_delegation_export_header()

    yield header

    pvars = lambda p, k, default=None: p.participant.vars.get(k, default)
    fld = lambda p, k: p.field_maybe_none(k)

    def get_fld(p, name):
        if spec.access_mode == "safe":
            try:
                return fld(p, name)
            except Exception:
                return None
        return fld(p, name)

    def resolve_opponent(pr, r):
        """Only opponents within the same released matching batch (never the whole session group)."""
        try:
            # Resolves via member lists even after Results sets matching_group_id = -1.
            return opponent_in_matching_batch(pr, r, C, spec.compute_rr, rr_cache)
        except Exception:
            if spec.opponent_mode != "safe_wrap":
                return None
            return None

    def player_pay_float(pr):
        if spec.payoff_mode == "currency_amount":
            return _pay_export_amount(getattr(pr, "payoff", None))
        return _pay_export_amount(getattr(pr, "payoff", None))

    for code, rounds in by_participant.items():
        try:
            rounds = sorted(rounds, key=lambda p: p.round_number)
            if not rounds:
                continue
            p0 = rounds[0]
            is_simulated = bool(pvars(p0, "is_simulated"))
            prolific_id = get_fld(p0, "prolific_id")
            if (not is_simulated) and (not prolific_id):
                continue
            row = dict.fromkeys(header, "")

            row["Condition"] = spec.condition_first if C.DELEGATION_FIRST else spec.condition_second
            app_name_val = get_fld(p0, "app_name")
            row["AppName"] = app_name_val if app_name_val is not None else ""
            if spec.prolific_mode == "or_empty":
                row["ProlificID"] = "SIMULATED" if is_simulated else (prolific_id or "")
            else:
                row["ProlificID"] = "SIMULATED" if is_simulated else prolific_id

            if spec.session_mode == "safe":
                row["Session"] = getattr(getattr(p0, "session", None), "code", "") or ""
            else:
                row["Session"] = p0.session.code

            # Per-part batch ids survive Results resetting matching_group_id to -1.
            # Only set after successful payoffs — empty means that part never completed matching.
            def _part_cell(prefix: str, part: int):
                v = pvars(p0, f"{prefix}_{part}")
                if v is None or v == -1 or v == "":
                    return ""
                return v

            def _first_present(*vals):
                for v in vals:
                    if v is not None and v != "" and v != -1:
                        return v
                return ""

            gp1, gp2, gp3 = _part_cell("group_part", 1), _part_cell("group_part", 2), _part_cell("group_part", 3)
            pp1 = _part_cell("group_position_part", 1)
            pp2 = _part_cell("group_position_part", 2)
            pp3 = _part_cell("group_position_part", 3)
            row["GroupPart1"] = gp1
            row["GroupPart2"] = gp2
            row["GroupPart3"] = gp3
            row["GroupPositionPart1"] = pp1
            row["GroupPositionPart2"] = pp2
            row["GroupPositionPart3"] = pp3
            # Legacy columns: prefer Part 3, else 2, else 1 (never export live -1 after reset).
            row["Group"] = _first_present(gp3, gp2, gp1)
            row["GroupPosition"] = _first_present(
                pp3, pp2, pp1, pvars(p0, "matching_group_position")
            )
            # Backward-compatible aliases (same values).
            row["PlayerIDPart1"] = pp1
            row["PlayerIDPart2"] = pp2
            row["PlayerIDPart3"] = pp3
            row["PlayerID"] = row["GroupPosition"]
            row["TrioPositionPart1"] = pp1
            row["TrioPositionPart2"] = pp2
            row["TrioPositionPart3"] = pp3
            row["TrioPosition"] = row["GroupPosition"]
            row["IsSimulated"] = 1 if is_simulated else 0
            p_last = rounds[-1] if rounds else p0
            row["Gender"] = get_fld(p_last, "gender")
            row["Age"] = get_fld(p_last, "age")
            row["Occupation"] = get_fld(p_last, "occupation")
            row["AIuse"] = get_fld(p_last, "ai_use")
            row["TaskDifficulty"] = get_fld(p_last, "task_difficulty")
            row["Part3Feedback"] = get_fld(p_last, "part_3_feedback")
            row["Part3FeedbackOther"] = get_fld(p_last, "part_3_feedback_other")
            row["Part4Feedback"] = get_fld(p_last, "part_4_feedback")
            row["Part4FeedbackOther"] = get_fld(p_last, "part_4_feedback_other")
            if spec.demographics == "rule_based":
                row["UsedAiOrBot"] = get_fld(p_last, "used_ai_or_bot") or ""
            else:
                # Goal / supervised / LLM also collect this on ExitQuestionnaire.
                row["UsedAiOrBot"] = get_fld(p_last, "used_ai_or_bot") or ""
            row["FeedbackFreeText"] = get_fld(p_last, "feedback")

            part_totals = [0.0, 0.0, 0.0]
            part_has_payoff = [False, False, False]
            label = spec.per_round_agent_token
            for pr in rounds:
                r = pr.round_number
                other = resolve_opponent(pr, r)
                if spec.game_used == "TG":
                    first_val = get_fld(pr, "choice_first_mover")
                    second_val = get_fld(pr, "choice_second_mover")
                    role_val = get_fld(pr, "role_assigned")
                    row[f"Round{r}DecisionFirstMover"] = first_val if first_val is not None else ""
                    row[f"Round{r}DecisionSecondMover"] = second_val if second_val is not None else ""
                    row[f"Round{r}RoleAssigned"] = role_val if role_val is not None else ""
                    row[f"Round{r}EffectiveDecision"] = _tg_effective_choice(
                        role_val, first_val, second_val
                    )
                    row[f"Round{r}Decision"] = ""
                    # Only export Ecoins when roles/payoffs were actually applied.
                    # Framework default Currency(0) must not look like a real TG outcome.
                    if role_val in ("first", "second"):
                        pay_float = player_pay_float(pr)
                    else:
                        pay_float = None
                else:
                    choice_val = get_fld(pr, "choice")
                    row[f"Round{r}Decision"] = choice_val if choice_val is not None else ""
                    pay_float = player_pay_float(pr)

                row[f"Round{r}Ecoins"] = _export_ecoins_cell(pay_float)

                if other:
                    if spec.game_used == "TG":
                        oc_first = get_fld(other, "choice_first_mover")
                        oc_second = get_fld(other, "choice_second_mover")
                        # Role the opponent played in THIS focal match (complement of focal role).
                        # Do not use other.role_assigned (that is their own directed edge).
                        if role_val == "first":
                            match_opp_role = "second"
                            row[f"Round{r}CoplayerEffectiveDecision"] = (
                                oc_second if oc_second in ("A", "B") else ""
                            )
                        elif role_val == "second":
                            match_opp_role = "first"
                            row[f"Round{r}CoplayerEffectiveDecision"] = (
                                oc_first if oc_first in ("A", "B") else ""
                            )
                        else:
                            match_opp_role = ""
                            row[f"Round{r}CoplayerEffectiveDecision"] = ""
                        row[f"Round{r}CoplayerDecisionFirstMover"] = (
                            oc_first if oc_first is not None else ""
                        )
                        row[f"Round{r}CoplayerDecisionSecondMover"] = (
                            oc_second if oc_second is not None else ""
                        )
                        row[f"Round{r}CoplayerRoleAssigned"] = match_opp_role
                        row[f"Round{r}CoplayerDecision"] = ""
                    else:
                        oc = get_fld(other, "choice")
                        row[f"Round{r}CoplayerDecision"] = oc if oc is not None else ""
                    pos = pvars(other, f"group_position_part_{C.get_part(r)}")
                    if pos is None or pos == "" or pos == -1:
                        pos = pvars(other, "matching_group_position")
                    # Export only the trio position. Never invent session seat IDs
                    # (matching / payoffs resolve opponents via member lists, not this column).
                    if pos is not None and pos != "" and pos != -1:
                        row[f"Round{r}CoplayerID"] = str(pos)
                    else:
                        row[f"Round{r}CoplayerID"] = ""
                else:
                    row[f"Round{r}CoplayerDecision"] = ""
                    row[f"Round{r}CoplayerID"] = ""
                    if spec.game_used == "TG":
                        row[f"Round{r}CoplayerDecisionFirstMover"] = ""
                        row[f"Round{r}CoplayerDecisionSecondMover"] = ""
                        row[f"Round{r}CoplayerRoleAssigned"] = ""
                        row[f"Round{r}CoplayerEffectiveDecision"] = ""

                if spec.layout == "first_person_agents":
                    if C.is_mandatory_delegation_round(r):
                        agent_self = label
                    elif r > 2 * C.rounds_per_part:
                        deleg_self = get_fld(pr, "delegate_decision_optional")
                        if deleg_self is True:
                            agent_self = label
                        elif deleg_self is False:
                            agent_self = "no-agent"
                        else:
                            agent_self = ""
                    else:
                        agent_self = "no-agent"
                    if other is not None:
                        if C.is_mandatory_delegation_round(r):
                            agent_other = label
                        elif r > 2 * C.rounds_per_part:
                            deleg_other = get_fld(other, "delegate_decision_optional")
                            if deleg_other is True:
                                agent_other = label
                            elif deleg_other is False:
                                agent_other = "no-agent"
                            else:
                                agent_other = ""
                        else:
                            agent_other = "no-agent"
                    else:
                        agent_other = ""
                    row[f"Round{r}PlayerAgent"] = agent_self
                    row[f"Round{r}CoPlayerAgent"] = agent_other

                if pay_float is not None:
                    if r <= 10:
                        part_totals[0] += pay_float
                        part_has_payoff[0] = True
                    elif r <= 20:
                        part_totals[1] += pay_float
                        part_has_payoff[1] = True
                    else:
                        part_totals[2] += pay_float
                        part_has_payoff[2] = True

            for i, part_key in enumerate(
                [
                    "TotalEarningsPart1Ecoins",
                    "TotalEarningsPart2Ecoins",
                    "TotalEarningsPart3Ecoins",
                ],
                start=1,
            ):
                row[part_key] = (
                    int(part_totals[i - 1]) if part_has_payoff[i - 1] else ""
                )

            n_rounds = len(rounds)
            for i in range(1, 11):
                idx = 19 + i
                pr = rounds[idx] if idx < n_rounds else None
                if pr is None:
                    continue
                row[f"Guess{i}"] = _export_guess_cell(get_fld(pr, "guess_opponent_delegated"))
                other = resolve_opponent(pr, 20 + i)
                row[f"TruthGuess{i}"] = _export_truth_cell(other, get_fld)
                gpay = get_fld(pr, "guess_payoff")
                if gpay is None:
                    row[f"EarningsGuess{i}"] = ""
                    row[f"EarningsGuess{i}Dollars"] = ""
                else:
                    try:
                        gpay_float = float(gpay)
                    except (TypeError, ValueError):
                        gpay_float = None
                    if gpay_float is None:
                        row[f"EarningsGuess{i}"] = ""
                        row[f"EarningsGuess{i}Dollars"] = ""
                    elif spec.layout == "compact_rounds":
                        row[f"EarningsGuess{i}Dollars"] = round(gpay_float / 100.0, 4)
                        row[f"EarningsGuess{i}"] = ""
                    else:
                        row[f"EarningsGuess{i}"] = gpay
                        row[f"EarningsGuess{i}Dollars"] = round(gpay_float * 0.01, 4)

            if C.DELEGATION_FIRST:
                delegated_part1 = 1
                delegated_part2 = 0
            else:
                delegated_part1 = 0
                delegated_part2 = 1
            if spec.game_used == "TG":
                # Three-way: 1 / 0 / "" — never invent "did not delegate" from None.
                delegated_part3 = ""
                for pr in rounds:
                    if C.get_part(pr.round_number) == 3:
                        v = get_fld(pr, "delegate_decision_optional")
                        if v is True:
                            delegated_part3 = 1
                            break
                        if v is False:
                            delegated_part3 = 0
                            break
            else:
                delegated_part3 = 0
                for pr in rounds:
                    if C.get_part(pr.round_number) == 3:
                        if get_fld(pr, "delegate_decision_optional"):
                            delegated_part3 = 1
                            break
            row["DelegatedPart1"] = delegated_part1
            row["DelegatedPart2"] = delegated_part2
            row["DelegatedPart3"] = delegated_part3

            if spec.summary_agent_fixed is not None:
                row["Agent"] = spec.summary_agent_fixed
            else:
                row["Agent"] = coarse_agent_from_condition_app(
                    row["Condition"], get_fld(p0, "app_name") or ""
                )

            part_chosen = get_fld(p_last, "random_payoff_part")
            if isinstance(part_chosen, str) and part_chosen.strip().isdigit():
                part_chosen = int(part_chosen.strip())
            # Live BatchWait/TimeOut quit sets quit_to_prolific_results; older
            # paths may still use quit_to_prolific. Treat either as show-up quit.
            if pvars(p0, "quit_to_prolific") or pvars(p0, "quit_to_prolific_results"):
                # Label quit explicitly — never invent played earnings as 0.0.
                # BonusPaymentTotal stays 1.0 (known $1 show-up); PartChosenBonus=quit.
                row["PartChosenBonus"] = "quit"
                row["TotalEarningsParts123Dollars"] = "quit"
                row["TotalEarningsPart4Dollars"] = "quit"
                row["BonusPaymentTotal"] = 1.0
            elif part_chosen in (1, 2, 3):
                if part_has_payoff[part_chosen - 1]:
                    ecoins = float(part_totals[part_chosen - 1])
                    row["TotalEarningsParts123Dollars"] = round(ecoins * 0.001, 4)
                else:
                    row["TotalEarningsParts123Dollars"] = ""
                row["PartChosenBonus"] = part_chosen
                if spec.layout == "compact_rounds":
                    part4_dollars = _sum_export_numeric_cells(
                        row, [f"EarningsGuess{j}Dollars" for j in range(1, 11)]
                    )
                else:
                    part4_dollars = _sum_export_numeric_cells(
                        row, [f"EarningsGuess{j}" for j in range(1, 11)], multiplier=0.01
                    )
                row["TotalEarningsPart4Dollars"] = (
                    round(part4_dollars, 4) if part4_dollars is not None else ""
                )
                parts123 = row["TotalEarningsParts123Dollars"]
                # Only sum when both sides are known; never fill missing with 0.0.
                if parts123 != "" and part4_dollars is not None:
                    row["BonusPaymentTotal"] = round(
                        float(parts123) + float(part4_dollars), 4
                    )
                else:
                    row["BonusPaymentTotal"] = ""
            else:
                row["PartChosenBonus"] = part_chosen if part_chosen is not None else ""
                row["TotalEarningsParts123Dollars"] = ""
                if spec.layout == "compact_rounds":
                    part4_dollars = _sum_export_numeric_cells(
                        row, [f"EarningsGuess{j}Dollars" for j in range(1, 11)]
                    )
                else:
                    part4_dollars = _sum_export_numeric_cells(
                        row, [f"EarningsGuess{j}" for j in range(1, 11)], multiplier=0.01
                    )
                row["TotalEarningsPart4Dollars"] = (
                    round(part4_dollars, 4) if part4_dollars is not None else ""
                )
                row["BonusPaymentTotal"] = (
                    round(part4_dollars, 4) if part4_dollars is not None else ""
                )

            delegation_round = 1 if C.DELEGATION_FIRST else 11
            deleg_pr = rounds[delegation_round - 1] if len(rounds) >= delegation_round else None
            optional_round = 21
            opt_pr = rounds[optional_round - 1] if len(rounds) >= optional_round else None

            for k in (
                "SupervisedListChoicesDelegation",
                "SupervisedListChoicesOptional",
                "GoalListChoicesDelegation",
                "GoalListChoicesOptional",
                "LLMchatDelegation",
                "LLMchatOptional",
            ):
                row[k] = ""

            if spec.extension == "llm":
                def _llm_chat(pr):
                    if not pr:
                        return ""
                    first = get_fld(pr, "conversation_history") or ""
                    if spec.game_used == "TG":
                        second = get_fld(pr, "conversation_history_second") or ""
                        if first and second:
                            return first + "\n---\n" + second
                        return first or second
                    return first

                row["LLMchatDelegation"] = _llm_chat(deleg_pr)
                row["LLMchatOptional"] = (
                    _llm_chat(opt_pr)
                    if opt_pr and get_fld(opt_pr, "delegate_decision_optional")
                    else ""
                )
            elif spec.extension == "goal":
                row["GoalListChoicesDelegation"] = strip_allocations_json(
                    (get_fld(deleg_pr, "agent_prog_allocation") if deleg_pr else "") or ""
                )
                row["GoalListChoicesOptional"] = strip_allocations_json(
                    (
                        (
                            get_fld(opt_pr, "agent_prog_allocation")
                            if get_fld(opt_pr, "delegate_decision_optional")
                            else ""
                        )
                        if opt_pr
                        else ""
                    )
                    or ""
                )
            elif spec.extension == "supervised":
                delegation_part = 1 if C.DELEGATION_FIRST else 2
                row["SupervisedListChoicesDelegation"] = supervised_list_choices_export(
                    deleg_pr, get_fld, part=delegation_part
                )
                row["SupervisedListChoicesOptional"] = (
                    supervised_list_choices_export(opt_pr, get_fld, part=3)
                    if opt_pr and get_fld(opt_pr, "delegate_decision_optional") is True
                    else ""
                )

            row["GameUsed"] = spec.game_used

            get_choice = (
                (lambda pr: (
                    "tg"
                    if get_fld(pr, "choice_first_mover") in ("A", "B")
                    and get_fld(pr, "choice_second_mover") in ("A", "B")
                    else None
                ))
                if spec.game_used == "TG"
                else (lambda pr: get_fld(pr, "choice"))
            )
            row["ExportErrors"] = "; ".join(
                collect_export_integrity_errors(
                    p0.participant,
                    rounds,
                    C,
                    p0.session,
                    resolve_opponent,
                    get_choice,
                    results_cache_required=spec.results_cache_required,
                )
            )

            yield [row[h] for h in header]
        except Exception as e:
            if spec.log_errors_to_stderr:
                print(
                    f"custom_export row failed participant_code={code!r}: {type(e).__name__}: {e}",
                    file=sys.stderr,
                    flush=True,
                )
            yield [f"ERROR: {type(e).__name__}: {e}"] + [""] * (len(header) - 1)

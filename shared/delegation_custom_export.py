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
from typing import Any, Callable, Iterator, List, Optional


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


def strip_allocations_json(raw_value: Any) -> str:
    if not raw_value:
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

    # "first_person_agents" = per-round PlayerAgent/CoPlayerAgent + guess ecoins columns
    # "compact_rounds" = no per-round agents; guess *Dollars columns
    layout: str

    # standard = Part3…FeedbackFreeText only; rule_based = adds UsedAiOrBot before FeedbackFreeText
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

    # When set, export uses this (e.g. models._opponent_for_export) so batch / group logic stays per-app.
    custom_opponent_resolver: Optional[Callable[[Any, int, dict, dict], Any]] = None


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


def _pay_export_amount(pay_raw: Any) -> float:
    if pay_raw is None:
        return 0.0
    amt = getattr(pay_raw, "amount", pay_raw)
    try:
        return float(amt)
    except (TypeError, ValueError):
        return 0.0


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

    header: List[str] = [
        "Condition",
        "ProlificID",
        "Session",
        "Group",
        "PlayerID",
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
    ]
    if spec.demographics == "rule_based":
        header += ["UsedAiOrBot"]
    header += ["FeedbackFreeText"]

    for r in range(1, 31):
        header += [
            f"Round{r}Decision",
            f"Round{r}CoplayerID",
            f"Round{r}CoplayerDecision",
            f"Round{r}Ecoins",
        ]
        if spec.layout == "first_person_agents":
            header += [f"Round{r}PlayerAgent", f"Round{r}CoPlayerAgent"]

    guess_suffix = "Dollars" if spec.layout == "compact_rounds" else ""
    for i in range(1, 11):
        if guess_suffix:
            header += [f"Guess{i}", f"TruthGuess{i}", f"EarningsGuess{i}Dollars"]
        else:
            header += [f"Guess{i}", f"TruthGuess{i}", f"EarningsGuess{i}"]

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
        if spec.custom_opponent_resolver is not None:
            if spec.opponent_mode == "matching_group_guard":
                try:
                    gid = pvars(pr, "matching_group_id", -1)
                    has_real = gid is not None and gid >= 0
                    if not has_real:
                        return None
                    return spec.custom_opponent_resolver(pr, r, round_data, rr_cache)
                except Exception:
                    return None
            if spec.opponent_mode == "safe_wrap":
                try:
                    return spec.custom_opponent_resolver(pr, r, round_data, rr_cache)
                except Exception:
                    return None
            return spec.custom_opponent_resolver(pr, r, round_data, rr_cache)
        if spec.opponent_mode == "matching_group_guard":
            try:
                gid = pvars(pr, "matching_group_id", -1)
                has_real = gid is not None and gid >= 0
                if not has_real:
                    return None
                return opponent_for_export(pr, r, round_data, rr_cache, C, spec.compute_rr)
            except Exception:
                return None
        if spec.opponent_mode == "safe_wrap":
            try:
                return opponent_for_export(pr, r, round_data, rr_cache, C, spec.compute_rr)
            except Exception:
                return None
        return opponent_for_export(pr, r, round_data, rr_cache, C, spec.compute_rr)

    def player_pay_float(pr):
        if spec.payoff_mode == "currency_amount":
            return _pay_export_amount(getattr(pr, "payoff", None))
        raw = pr.payoff or 0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

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
            if spec.prolific_mode == "or_empty":
                row["ProlificID"] = "SIMULATED" if is_simulated else (prolific_id or "")
            else:
                row["ProlificID"] = "SIMULATED" if is_simulated else prolific_id

            if spec.session_mode == "safe":
                row["Session"] = getattr(getattr(p0, "session", None), "code", "") or ""
            else:
                row["Session"] = p0.session.code

            row["Group"] = pvars(p0, "matching_group_id")
            row["PlayerID"] = pvars(p0, "matching_group_position")
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
                row["UsedAiOrBot"] = get_fld(p_last, "used_ai_or_bot")
            row["FeedbackFreeText"] = get_fld(p_last, "feedback")

            part_totals = [0.0, 0.0, 0.0]
            label = spec.per_round_agent_token
            for pr in rounds:
                r = pr.round_number
                other = resolve_opponent(pr, r)
                choice_val = get_fld(pr, "choice")
                row[f"Round{r}Decision"] = choice_val if choice_val is not None else ""

                pay_float = player_pay_float(pr)
                try:
                    row[f"Round{r}Ecoins"] = int(pay_float)
                except (TypeError, ValueError):
                    row[f"Round{r}Ecoins"] = 0

                if other:
                    oc = get_fld(other, "choice")
                    row[f"Round{r}CoplayerDecision"] = oc if oc is not None else ""
                    pos = pvars(other, "matching_group_position")
                    if pos is not None and pos != "" and pos != -1:
                        row[f"Round{r}CoplayerID"] = str(pos)
                    else:
                        row[f"Round{r}CoplayerID"] = str(
                            getattr(other.participant, "id_in_session", "") or ""
                        )
                else:
                    row[f"Round{r}CoplayerDecision"] = ""
                    row[f"Round{r}CoplayerID"] = ""

                if spec.layout == "first_person_agents":
                    if C.is_mandatory_delegation_round(r):
                        agent_self = label
                    elif r > 2 * C.rounds_per_part:
                        agent_self = label if get_fld(pr, "delegate_decision_optional") else "no-agent"
                    else:
                        agent_self = "no-agent"
                    if other is not None:
                        if C.is_mandatory_delegation_round(r):
                            agent_other = label
                        elif r > 2 * C.rounds_per_part:
                            agent_other = (
                                label if get_fld(other, "delegate_decision_optional") else "no-agent"
                            )
                        else:
                            agent_other = "no-agent"
                    else:
                        agent_other = ""
                    row[f"Round{r}PlayerAgent"] = agent_self
                    row[f"Round{r}CoPlayerAgent"] = agent_other

                if r <= 10:
                    part_totals[0] += pay_float
                elif r <= 20:
                    part_totals[1] += pay_float
                else:
                    part_totals[2] += pay_float

            for i, part_key in enumerate(
                [
                    "TotalEarningsPart1Ecoins",
                    "TotalEarningsPart2Ecoins",
                    "TotalEarningsPart3Ecoins",
                ],
                start=1,
            ):
                try:
                    row[part_key] = int(part_totals[i - 1])
                except (TypeError, ValueError):
                    row[part_key] = 0

            n_rounds = len(rounds)
            for i in range(1, 11):
                idx = 19 + i
                pr = rounds[idx] if idx < n_rounds else None
                if pr is None:
                    continue
                row[f"Guess{i}"] = 1 if get_fld(pr, "guess_opponent_delegated") == "yes" else 0
                other = resolve_opponent(pr, 20 + i)
                row[f"TruthGuess{i}"] = 1 if (other and get_fld(other, "delegate_decision_optional")) else 0
                gpay = get_fld(pr, "guess_payoff") or 0
                try:
                    gpay_float = float(gpay)
                except (TypeError, ValueError):
                    gpay_float = 0.0
                if spec.layout == "compact_rounds":
                    row[f"EarningsGuess{i}Dollars"] = round(gpay_float / 100.0, 4)
                else:
                    row[f"EarningsGuess{i}"] = gpay

            if C.DELEGATION_FIRST:
                delegated_part1 = 1
                delegated_part2 = 0
            else:
                delegated_part1 = 0
                delegated_part2 = 1
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
            _float = lambda x: float(x) if x is not None else 0.0
            if pvars(p0, "quit_to_prolific"):
                row["PartChosenBonus"] = "quit"
                row["TotalEarningsParts123Dollars"] = 0.0
                row["TotalEarningsPart4Dollars"] = 0.0
                row["BonusPaymentTotal"] = 1.0
            elif part_chosen in (1, 2, 3):
                ecoins = _float(part_totals[part_chosen - 1])
                row["PartChosenBonus"] = part_chosen
                row["TotalEarningsParts123Dollars"] = round(ecoins * 0.001, 4)
                if spec.layout == "compact_rounds":
                    part4_dollars = sum(
                        _float(row.get(f"EarningsGuess{j}Dollars")) for j in range(1, 11)
                    )
                    row["TotalEarningsPart4Dollars"] = round(part4_dollars, 4)
                else:
                    part4_ecoins = sum(_float(row.get(f"EarningsGuess{j}")) for j in range(1, 11)) * 0.01
                    row["TotalEarningsPart4Dollars"] = round(part4_ecoins, 4)
                row["BonusPaymentTotal"] = round(
                    row["TotalEarningsParts123Dollars"] + row["TotalEarningsPart4Dollars"], 4
                )
            else:
                row["PartChosenBonus"] = part_chosen if part_chosen is not None else ""
                row["TotalEarningsParts123Dollars"] = 0.0
                if spec.layout == "compact_rounds":
                    part4_dollars = sum(
                        _float(row.get(f"EarningsGuess{j}Dollars")) for j in range(1, 11)
                    )
                    row["TotalEarningsPart4Dollars"] = round(part4_dollars, 4)
                else:
                    part4_ecoins = sum(_float(row.get(f"EarningsGuess{j}")) for j in range(1, 11)) * 0.01
                    row["TotalEarningsPart4Dollars"] = round(part4_ecoins, 4)
                row["BonusPaymentTotal"] = round(row["TotalEarningsPart4Dollars"], 4)

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
                row["LLMchatDelegation"] = (get_fld(deleg_pr, "conversation_history") if deleg_pr else "") or ""
                row["LLMchatOptional"] = (
                    (
                        get_fld(opt_pr, "conversation_history")
                        if get_fld(opt_pr, "delegate_decision_optional")
                        else ""
                    )
                    if opt_pr
                    else ""
                ) or ""
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
                row["SupervisedListChoicesDelegation"] = strip_allocations_json(
                    (get_fld(deleg_pr, "agent_prog_allocation") if deleg_pr else "") or ""
                )
                row["SupervisedListChoicesOptional"] = strip_allocations_json(
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

            row["GameUsed"] = spec.game_used

            yield [row[h] for h in header]
        except Exception as e:
            if spec.log_errors_to_stderr:
                print(
                    f"custom_export row failed participant_code={code!r}: {type(e).__name__}: {e}",
                    file=sys.stderr,
                    flush=True,
                )
            yield [f"ERROR: {type(e).__name__}: {e}"] + [""] * (len(header) - 1)

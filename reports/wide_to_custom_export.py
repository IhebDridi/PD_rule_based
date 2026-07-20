"""
Convert oTree wide CSV into the delegation custom-export schema (no oTree runtime needed).

Usage:
  python reports/wide_to_custom_export.py
  python reports/wide_to_custom_export.py --session xh3fj087 --input path.csv --output out.csv
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PAYOFFS = {
    ("A", "A"): (70.0, 70.0),
    ("A", "B"): (0.0, 100.0),
    ("B", "A"): (100.0, 0.0),
    ("B", "B"): (30.0, 30.0),
}

DEFAULT_APP = "TG_goal_oriented_delegation_1st"
DEFAULT_SESSION = "xh3fj087"
DEFAULT_INPUT = Path(r"c:\Users\waben\Downloads\check_Data.csv")
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "xh3fj087_custom_export_from_wide.csv"


def canonical_header() -> List[str]:
    header: List[str] = [
        "Condition", "AppName", "ProlificID", "Session",
        "Group", "GroupPart1", "GroupPart2", "GroupPart3",
        "GroupPosition", "GroupPositionPart1", "GroupPositionPart2", "GroupPositionPart3",
        "PlayerID", "PlayerIDPart1", "PlayerIDPart2", "PlayerIDPart3",
        "TrioPosition", "TrioPositionPart1", "TrioPositionPart2", "TrioPositionPart3",
        "IsSimulated",
        "Gender", "Age", "Occupation", "AIuse", "TaskDifficulty",
        "Part3Feedback", "Part3FeedbackOther", "Part4Feedback", "Part4FeedbackOther",
        "UsedAiOrBot", "FeedbackFreeText",
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
        header += [f"Guess{i}", f"TruthGuess{i}", f"EarningsGuess{i}", f"EarningsGuess{i}Dollars"]
    header += [
        "DelegatedPart1", "DelegatedPart2", "DelegatedPart3", "Agent",
        "TotalEarningsPart1Ecoins", "TotalEarningsPart2Ecoins", "TotalEarningsPart3Ecoins",
        "PartChosenBonus", "TotalEarningsParts123Dollars", "TotalEarningsPart4Dollars",
        "BonusPaymentTotal",
        "SupervisedListChoicesDelegation", "SupervisedListChoicesOptional",
        "GoalListChoicesDelegation", "GoalListChoicesOptional",
        "LLMchatDelegation", "LLMchatOptional", "GameUsed",
        "ExportErrors",
    ]
    return header


def tg_effective(role, first_val, second_val) -> str:
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


def export_guess_cell(guess_val: Any):
    if guess_val == "yes":
        return 1
    if guess_val == "no":
        return 0
    return ""


def export_ecoins_cell(pay_float: Optional[float]):
    if pay_float is None:
        return ""
    try:
        return int(pay_float)
    except (TypeError, ValueError):
        return ""


def sum_export_numeric_cells(row: dict, keys: List[str], multiplier: float = 1.0) -> Optional[float]:
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


def part_total_if_complete(total: float, payoff_count: int, expected_rounds: int) -> Optional[float]:
    if payoff_count != expected_rounds:
        return None
    return total


def g(row: dict, app: str, rnd: int, field: str) -> str:
    return (row.get(f"{app}.{rnd}.player.{field}") or "").strip()


def parse_bool01(raw: str) -> Optional[bool]:
    if raw in ("1", "True", "true", "yes"):
        return True
    if raw in ("0", "False", "false", "no"):
        return False
    return None


def as_float(raw: str) -> Optional[float]:
    if raw in ("", None):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def role_of(row: dict, app: str, rnd: int) -> str:
    return g(row, app, rnd, "role_assigned") or g(row, app, rnd, "role")


def round_bundle(row: dict, app: str, rnd: int) -> Optional[dict]:
    role = role_of(row, app, rnd)
    c1 = g(row, app, rnd, "choice_first_mover")
    c2 = g(row, app, rnd, "choice_second_mover")
    pay = as_float(g(row, app, rnd, "payoff"))
    if role not in ("first", "second"):
        return None
    if c1 not in ("A", "B") or c2 not in ("A", "B"):
        return None
    return {
        "pid": row["participant.id_in_session"],
        "code": row["participant.code"],
        "role": role,
        "c1": c1,
        "c2": c2,
        "pay": pay,
        "deleg": parse_bool01(g(row, app, rnd, "delegate_decision_optional")),
    }


def payoff_consistent(a: dict, b: dict) -> bool:
    if a["role"] == b["role"]:
        return False
    first, second = (a, b) if a["role"] == "first" else (b, a)
    key = (first["c1"], second["c2"])
    if key not in PAYOFFS:
        return False
    exp_f, exp_s = PAYOFFS[key]
    if first["pay"] is None or second["pay"] is None:
        return False
    return abs(first["pay"] - exp_f) < 0.01 and abs(second["pay"] - exp_s) < 0.01


def build_coplayer_maps(rows: List[dict], app: str) -> Dict[str, Dict[int, dict]]:
    by_round: Dict[int, List[dict]] = defaultdict(list)
    for row in rows:
        for rnd in range(1, 31):
            b = round_bundle(row, app, rnd)
            if b:
                by_round[rnd].append(b)

    matched: Dict[str, Dict[int, dict]] = defaultdict(dict)
    for rnd, bundles in by_round.items():
        used = set()
        firsts = [b for b in bundles if b["role"] == "first"]
        seconds = [b for b in bundles if b["role"] == "second"]
        for f in firsts:
            if f["code"] in used:
                continue
            cands = [s for s in seconds if s["code"] not in used and payoff_consistent(f, s)]
            if len(cands) != 1:
                continue
            s = cands[0]
            rev = [x for x in firsts if x["code"] not in used and payoff_consistent(x, s)]
            if len(rev) != 1:
                continue
            used.add(f["code"])
            used.add(s["code"])
            matched[f["code"]][rnd] = s
            matched[s["code"]][rnd] = f
    return matched


def is_quit_row(row: dict) -> bool:
    return (row.get("participant._current_page_name") or "") == "TimeOutquit"


def has_any_play(row: dict, app: str) -> bool:
    for rnd in range(1, 31):
        if role_of(row, app, rnd) in ("first", "second"):
            return True
        if g(row, app, rnd, "choice_first_mover") in ("A", "B"):
            return True
    return False


def build_row(row: dict, app: str, coplayers: Dict[int, dict]) -> dict:
    header = canonical_header()
    out = dict.fromkeys(header, "")
    errors = ["reconstructed_from_wide_csv"]
    page = row.get("participant._current_page_name") or ""
    code = row.get("participant.code") or ""
    pid = row.get("participant.id_in_session") or ""

    prolific = ""
    for rnd in range(1, 31):
        v = g(row, app, rnd, "prolific_id")
        if v:
            prolific = v
            break
    if prolific:
        out["ProlificID"] = prolific
    else:
        out["ProlificID"] = code
        errors.append("ProlificID_is_participant_code_fallback")

    out["Condition"] = "goal1st"
    out["AppName"] = g(row, app, 1, "app_name") or app
    out["Session"] = row.get("session.code") or ""
    out["IsSimulated"] = 0
    out["GameUsed"] = "TG"
    out["Agent"] = "goal"
    errors.append("GroupPart_and_trio_seats_unavailable_in_wide")

    out["Gender"] = g(row, app, 30, "gender")
    out["Age"] = g(row, app, 30, "age")
    out["Occupation"] = g(row, app, 30, "occupation")
    out["AIuse"] = g(row, app, 30, "ai_use")
    out["TaskDifficulty"] = g(row, app, 30, "task_difficulty")
    out["Part3Feedback"] = g(row, app, 30, "part_3_feedback")
    out["Part3FeedbackOther"] = g(row, app, 30, "part_3_feedback_other")
    out["Part4Feedback"] = g(row, app, 30, "part_4_feedback")
    out["Part4FeedbackOther"] = g(row, app, 30, "part_4_feedback_other")
    out["UsedAiOrBot"] = g(row, app, 30, "used_ai_or_bot")
    out["FeedbackFreeText"] = g(row, app, 30, "feedback")

    part_totals = [0.0, 0.0, 0.0]
    part_counts = [0, 0, 0]
    coplayer_matched = 0
    coplayer_missing = 0
    agent_token = "goal"

    for rnd in range(1, 31):
        role = role_of(row, app, rnd)
        c1 = g(row, app, rnd, "choice_first_mover")
        c2 = g(row, app, rnd, "choice_second_mover")
        pay = as_float(g(row, app, rnd, "payoff"))

        out[f"Round{rnd}Decision"] = ""
        out[f"Round{rnd}DecisionFirstMover"] = c1 if c1 in ("A", "B") else ""
        out[f"Round{rnd}DecisionSecondMover"] = c2 if c2 in ("A", "B") else ""
        out[f"Round{rnd}RoleAssigned"] = role if role in ("first", "second") else ""
        out[f"Round{rnd}EffectiveDecision"] = tg_effective(role, c1, c2)

        pay_float = pay if role in ("first", "second") else None
        out[f"Round{rnd}Ecoins"] = export_ecoins_cell(pay_float)

        other = coplayers.get(rnd)
        if other:
            coplayer_matched += 1
            oc1, oc2 = other["c1"], other["c2"]
            if role == "first":
                match_opp_role = "second"
                out[f"Round{rnd}CoplayerEffectiveDecision"] = oc2 if oc2 in ("A", "B") else ""
            elif role == "second":
                match_opp_role = "first"
                out[f"Round{rnd}CoplayerEffectiveDecision"] = oc1 if oc1 in ("A", "B") else ""
            else:
                match_opp_role = ""
                out[f"Round{rnd}CoplayerEffectiveDecision"] = ""
            out[f"Round{rnd}CoplayerDecisionFirstMover"] = oc1
            out[f"Round{rnd}CoplayerDecisionSecondMover"] = oc2
            out[f"Round{rnd}CoplayerRoleAssigned"] = match_opp_role
            out[f"Round{rnd}CoplayerDecision"] = ""
            out[f"Round{rnd}CoplayerID"] = str(other["pid"])
        else:
            if role in ("first", "second"):
                coplayer_missing += 1
            for k in (
                "CoplayerDecision", "CoplayerID", "CoplayerDecisionFirstMover",
                "CoplayerDecisionSecondMover", "CoplayerRoleAssigned", "CoplayerEffectiveDecision",
            ):
                out[f"Round{rnd}{k}"] = ""

        if 1 <= rnd <= 10:
            agent_self = agent_token
            agent_other = agent_token if other else ""
        elif 11 <= rnd <= 20:
            agent_self = "no-agent"
            agent_other = "no-agent" if other else ""
        else:
            deleg_self = parse_bool01(g(row, app, rnd, "delegate_decision_optional"))
            agent_self = agent_token if deleg_self is True else ("no-agent" if deleg_self is False else "")
            if other is not None:
                od = other.get("deleg")
                agent_other = agent_token if od is True else ("no-agent" if od is False else "")
            else:
                agent_other = ""
        out[f"Round{rnd}PlayerAgent"] = agent_self
        out[f"Round{rnd}CoPlayerAgent"] = agent_other

        if pay_float is not None:
            if 1 <= rnd <= 10:
                part_totals[0] += pay_float
                part_counts[0] += 1
            elif 11 <= rnd <= 20:
                part_totals[1] += pay_float
                part_counts[1] += 1
            elif 21 <= rnd <= 30:
                part_totals[2] += pay_float
                part_counts[2] += 1

    errors.append(f"coplayer_unique_matches={coplayer_matched};coplayer_unmatched_rounds={coplayer_missing}")
    errors.append(f"participant_id_in_session={pid};page={page}")

    for i, key in enumerate(
        ["TotalEarningsPart1Ecoins", "TotalEarningsPart2Ecoins", "TotalEarningsPart3Ecoins"]
    ):
        complete = part_total_if_complete(part_totals[i], part_counts[i], 10)
        out[key] = int(complete) if complete is not None else ""

    for i in range(1, 11):
        rnd = 20 + i
        out[f"Guess{i}"] = export_guess_cell(g(row, app, rnd, "guess_opponent_delegated"))
        other = coplayers.get(rnd)
        if other is None:
            out[f"TruthGuess{i}"] = ""
        else:
            od = other.get("deleg")
            out[f"TruthGuess{i}"] = 1 if od is True else (0 if od is False else "")
        gpay = as_float(g(row, app, rnd, "guess_payoff"))
        if gpay is None:
            out[f"EarningsGuess{i}"] = ""
            out[f"EarningsGuess{i}Dollars"] = ""
        else:
            out[f"EarningsGuess{i}"] = gpay
            out[f"EarningsGuess{i}Dollars"] = round(gpay * 0.01, 4)

    out["DelegatedPart1"] = 1
    out["DelegatedPart2"] = 0
    d3 = parse_bool01(g(row, app, 21, "delegate_decision_optional"))
    out["DelegatedPart3"] = 1 if d3 is True else (0 if d3 is False else "")

    out["GoalListChoicesDelegation"] = strip_allocations_json(g(row, app, 1, "agent_prog_allocation"))
    out["GoalListChoicesOptional"] = (
        strip_allocations_json(g(row, app, 21, "agent_prog_allocation")) if d3 is True else ""
    )

    part_chosen_raw = g(row, app, 30, "random_payoff_part")
    part_chosen: Any = int(part_chosen_raw) if part_chosen_raw.isdigit() else part_chosen_raw

    if is_quit_row(row):
        out["PartChosenBonus"] = "quit"
        out["TotalEarningsParts123Dollars"] = "quit"
        out["TotalEarningsPart4Dollars"] = "quit"
        out["BonusPaymentTotal"] = 1.0
    elif part_chosen in (1, 2, 3):
        complete = part_total_if_complete(
            part_totals[part_chosen - 1], part_counts[part_chosen - 1], 10
        )
        out["TotalEarningsParts123Dollars"] = (
            round(complete * 0.001, 4) if complete is not None else ""
        )
        out["PartChosenBonus"] = part_chosen
        part4 = sum_export_numeric_cells(
            out, [f"EarningsGuess{j}" for j in range(1, 11)], multiplier=0.01
        )
        out["TotalEarningsPart4Dollars"] = round(part4, 4) if part4 is not None else ""
        if out["TotalEarningsParts123Dollars"] != "" and part4 is not None:
            out["BonusPaymentTotal"] = round(
                float(out["TotalEarningsParts123Dollars"]) + float(part4), 4
            )
        else:
            out["BonusPaymentTotal"] = ""
    else:
        out["PartChosenBonus"] = part_chosen if part_chosen not in ("", None) else ""
        out["TotalEarningsParts123Dollars"] = ""
        part4 = sum_export_numeric_cells(
            out, [f"EarningsGuess{j}" for j in range(1, 11)], multiplier=0.01
        )
        out["TotalEarningsPart4Dollars"] = round(part4, 4) if part4 is not None else ""
        out["BonusPaymentTotal"] = ""

    out["ExportErrors"] = "; ".join(errors)
    return out


def convert(input_path: Path, output_path: Path, session: str, app: str) -> Tuple[int, int]:
    with input_path.open(newline="", encoding="utf-8-sig") as f:
        all_rows = [r for r in csv.DictReader(f) if r.get("session.code") == session]

    keep = []
    for r in all_rows:
        page = r.get("participant._current_page_name") or ""
        if page in ("Thankyou", "TimeOutquit", "BatchWaitForGroup") or has_any_play(r, app):
            keep.append(r)

    coplayer_by_code = build_coplayer_maps(keep, app)
    header = canonical_header()
    written = 0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in sorted(keep, key=lambda x: int(x.get("participant.id_in_session") or 0)):
            out = build_row(r, app, coplayer_by_code.get(r.get("participant.code") or "", {}))
            w.writerow([out[h] for h in header])
            written += 1
    return len(all_rows), written


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--session", default=DEFAULT_SESSION)
    p.add_argument("--app", default=DEFAULT_APP)
    args = p.parse_args()
    n_sess, n_out = convert(args.input, args.output, args.session, args.app)
    print(f"Session {args.session}: {n_sess} wide rows -> {n_out} custom-export rows")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()

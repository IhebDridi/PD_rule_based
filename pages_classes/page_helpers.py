"""Shared helpers for PD delegation page classes (no dependency on a specific app's ``models``)."""

from .model_bridge import get_constants

# Minimum seconds all batch members must have been on BatchWaitForGroup before payoffs run (avoids races).
BATCH_WAIT_MIN_SECONDS = 2


def _has_left_lobby_for_part(participant, part):
    """
    Return True for all participants.

    Original version checked lobby flags (has_left_lobby / has_left_lobby_part_X), but with the
    current design there is no Lobby in the flow, so everyone should be allowed to proceed to
    instructions and decision pages without a prior lobby gate.
    """
    return True


BOT_PROLIFIC_CODE = "1234567890GenerativeAI4U"


def _is_bot_suspected(participant):
    return bool(participant.vars.get("bot_suspected", False))


def comprehension_payoff_correct_letters(player):
    """
    Correct radio values for payoff questions q6–q9 when options are fixed as:
    A=0, B=30 or 50 (50 if any matrix cell uses 50), C=70, D=100.
    """
    C = get_constants(player)
    pd = getattr(C, "PD_PAYOFFS", None)
    if not isinstance(pd, dict):
        return {"q6": "c", "q7": "a", "q8": "d", "q9": "b"}
    aa = pd[("A", "A")][0]
    ab = pd[("A", "B")][0]
    ba = pd[("B", "A")][0]
    bb = pd[("B", "B")][0]
    b_mid = 50 if 50 in (aa, ab, ba, bb) else 30
    value_to_letter = {0: "a", b_mid: "b", 70: "c", 100: "d"}

    def letter(your_payoff):
        return value_to_letter.get(your_payoff, "a")

    return {
        "q6": letter(aa),
        "q7": letter(ab),
        "q8": letter(ba),
        "q9": letter(bb),
    }


def part_vars(player):
    """Template vars for part labels (part_no_delegation, part_delegation) used across instruction pages."""
    C = get_constants(player)
    out = {
        "part_no_delegation": C.part_no_delegation(),
        "part_delegation": C.part_delegation(),
    }
    pd = getattr(C, "PD_PAYOFFS", None)
    if isinstance(pd, dict):
        # Your earnings when row choice is yours and column is opponent's (matches table + comprehension text).
        aa = pd[("A", "A")][0]
        ab = pd[("A", "B")][0]
        ba = pd[("B", "A")][0]
        bb = pd[("B", "B")][0]
        out["payoff_AA"] = aa
        out["payoff_AB"] = ab
        out["payoff_BA"] = ba
        out["payoff_BB"] = bb
        mx = max(aa, ab, ba, bb)
        out["payoff_max_per_round"] = mx
        # 10 Ecoins = 1 cent; 10 rounds at max per round → mx cents total bonus from interactive tasks.
        out["payoff_max_cents_per_round"] = mx // 10
        out["payoff_max_bonus_usd"] = f"{mx // 100}.{mx % 100:02d}"
        out["comp_payoff_50_in_matrix"] = 50 in (aa, ab, ba, bb)
    else:
        # Always define keys so ComprehensionTest.html never raises UndefinedVariable.
        out["payoff_AA"] = out["payoff_AB"] = out["payoff_BA"] = out["payoff_BB"] = ""
        out["payoff_max_per_round"] = 100
        out["payoff_max_cents_per_round"] = 10
        out["payoff_max_bonus_usd"] = "1.00"
        out["comp_payoff_50_in_matrix"] = False
    return out

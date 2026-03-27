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
        out["payoff_AA"] = pd[("A", "A")][0]
        out["payoff_AB"] = pd[("A", "B")][0]
        out["payoff_BA"] = pd[("B", "A")][0]
        out["payoff_BB"] = pd[("B", "B")][0]
    else:
        # Always define keys so ComprehensionTest.html never raises UndefinedVariable.
        out["payoff_AA"] = out["payoff_AB"] = out["payoff_BA"] = out["payoff_BB"] = ""
    return out

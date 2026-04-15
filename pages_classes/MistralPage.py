import importlib
import json
import re
import time

from otree.api import *

from .model_bridge import app_package_name, get_constants
from .page_helpers import _has_left_lobby_for_part, part_vars

_STRICT_TEN_AB_RE = re.compile(r"^\s*[AB]\s*(,\s*[AB]\s*){9}\s*$", re.IGNORECASE)

# Mistral API: retry transient failures; one user+assistant pair is written after the final outcome.
_MISTRAL_SEND_MAX_ATTEMPTS = 6
_MISTRAL_SEND_RETRY_BASE_SLEEP_SEC = 1.25
_MISTRAL_SEND_FAILURE_USER_MESSAGE = (
    "Retrying is taking longer than expected. Please try sending your message again in a few seconds."
)


def _parse_strict_ten_ab(text):
    """Return 10 A/B choices from a strict single line, else None."""
    if not text or not isinstance(text, str):
        return None
    for line in text.strip().splitlines():
        line = line.strip()
        if _STRICT_TEN_AB_RE.match(line):
            parts = [p.strip().upper() for p in line.split(",")]
            if len(parts) == 10 and all(p in ("A", "B") for p in parts):
                return parts
    return None


def _mistral_payload_user_message(player, user_message, conversation_id):
    """
    On the first API turn for this Mistral thread only, prepend session payoffs + part order.
    The participant UI and conversation_history still store only the raw user_message.
    """
    if conversation_id is not None:
        return user_message

    C = get_constants(player)
    current_part = C.get_part(player.round_number)
    lines = [
        "[RESEARCH_SESSION_CONTEXT — for the agent only; participants do not see this block.]",
    ]

    pv = part_vars(player)
    try:
        aa = int(pv["payoff_AA"])
        ab = int(pv["payoff_AB"])
        ba = int(pv["payoff_BA"])
        bb = int(pv["payoff_BB"])
    except (KeyError, TypeError, ValueError):
        pass
    else:
        lines.append(
            "Your_earnings_Ecoins (your_choice, opponent_choice): "
            f"(A,A)={aa}; (A,B)={ab}; (B,A)={ba}; (B,B)={bb}."
        )

    df = getattr(C, "DELEGATION_FIRST", None)
    if df is not None:
        p_del = C.part_delegation()
        p_nd = C.part_no_delegation()
        lines.append(
            "Part_structure (UI part numbers): "
            f"DELEGATION_FIRST={df}; mandatory_delegation_block=Part {p_del}; "
            f"self_decisions_each_round_block=Part {p_nd}; "
            "Part_3=optional_delegate_or_self. "
            f"This_chat_is_for_part_index={current_part}."
        )
    else:
        lines.append(f"This_chat_is_for_part_index={current_part}.")

    lines.append("[END_RESEARCH_SESSION_CONTEXT]")
    lines.append("")
    lines.append("Participant message (follow your output rules; reply only to this):")
    lines.append(user_message)
    return "\n".join(lines)


class ChatGPTPage(Page):
    """
    Shared LLM delegation page:
    - visible in mandatory-delegation start round (1 or 11) and Part 3 optional delegation (21)
    - accepts only strict 10-item A/B output
    - writes decisions into per-round Player.choice and marks agent_programming_done_partX
    """

    form_model = "player"
    form_fields = []

    @property
    def template_name(self):
        return f"{app_package_name(self.player)}/MistralPage.html"

    def is_displayed(self):
        Constants = get_constants(self.player)
        r = self.round_number
        current_part = Constants.get_part(r)
        if r in (1, 11, 21) and not _has_left_lobby_for_part(self.participant, current_part):
            return False
        if r == 1 and Constants.DELEGATION_FIRST:
            return not self.participant.vars.get("agent_programming_done_part1", False)
        if r == 11 and not Constants.DELEGATION_FIRST:
            return not self.participant.vars.get("agent_programming_done_part2", False)
        if current_part == 3:
            return (
                self.player.field_maybe_none("delegate_decision_optional") is True
                and not self.participant.vars.get("agent_programming_done_part3", False)
            )
        return False

    def vars_for_template(self):
        return {
            "current_part": get_constants(self.player).get_part(self.round_number),
            "delegate_decision": self.player.field_maybe_none("delegate_decision_optional"),
            "countdown_seconds": 90,
            **part_vars(self.player),
        }

    def get_final_assistant_response(self):
        raw = self.player.field_maybe_none("conversation_history") or "[]"
        try:
            conversation = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        for msg in reversed(conversation):
            if msg.get("role") != "assistant":
                continue
            content = (msg.get("content") or "").strip()
            choices = _parse_strict_ten_ab(content)
            if choices:
                return {i: ch for i, ch in enumerate(choices, start=1)}
        return {}

    def save_choices_to_rounds(self, mapping):
        if not mapping:
            return
        for r in range(1, 11):
            if mapping.get(r) not in ("A", "B"):
                return

        Constants = get_constants(self.player)
        r = self.round_number
        current_part = Constants.get_part(r)

        if r == 1 and Constants.DELEGATION_FIRST:
            base = 1
            done_key = "agent_programming_done_part1"
        elif r == 11 and not Constants.DELEGATION_FIRST:
            base = 11
            done_key = "agent_programming_done_part2"
        elif current_part == 3 and r == 21:
            base = 21
            done_key = "agent_programming_done_part3"
        else:
            return

        for rel_round in range(1, 11):
            ch = mapping.get(rel_round)
            if ch in ("A", "B"):
                self.player.in_round(base + rel_round - 1).choice = ch
        self.participant.vars[done_key] = True

    def before_next_page(self):
        decisions = self.get_final_assistant_response()
        self.save_choices_to_rounds(decisions)

    @staticmethod
    def live_method(player, data):
        if not data or "message" not in data:
            return

        Constants = get_constants(player)
        current_part = Constants.get_part(player.round_number)
        conv_key = f"mistral_conversation_id_part_{current_part}"
        conversation_id = player.participant.vars.get(conv_key)

        try:
            assistant_module = importlib.import_module(f"{app_package_name(player)}.mistralassistant")
            assistant = assistant_module.MistralAssistant()
        except Exception as e:
            return {player.id_in_group: {"response": "Error initializing assistant: " + str(e)}}

        user_message = data["message"]
        api_user_message = _mistral_payload_user_message(player, user_message, conversation_id)
        response_text = ""
        new_cid = conversation_id
        cid_for_attempt = conversation_id
        for attempt in range(_MISTRAL_SEND_MAX_ATTEMPTS):
            try:
                response_text, new_cid = assistant.send_message(
                    api_user_message, conversation_id=cid_for_attempt
                )
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

        raw = player.field_maybe_none("conversation_history") or "[]"
        try:
            conversation = json.loads(raw)
        except (TypeError, ValueError):
            conversation = []

        conversation.append({"role": "user", "content": user_message})
        conversation.append({"role": "assistant", "content": response_text})
        player.conversation_history = json.dumps(conversation)

        return {player.id_in_group: {"response": response_text}}

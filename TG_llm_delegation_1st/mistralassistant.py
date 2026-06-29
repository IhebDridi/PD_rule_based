"""
Mistral beta conversations API: one agent_id, start or append conversation, return assistant text.
"""
import os

try:
    from mistralai.client import Mistral
except ImportError:
    Mistral = None


def _get_api_key():
    try:
        import settings
        return getattr(settings, 'MISTRAL_API_KEY', None) or os.environ.get('MISTRAL_API_KEY')
    except Exception:
        return os.environ.get('MISTRAL_API_KEY')


def _get_agent_id():
    try:
        import settings
        return getattr(settings, 'MISTRAL_AGENT_ID', None) or os.environ.get('MISTRAL_AGENT_ID')
    except Exception:
        return os.environ.get('MISTRAL_AGENT_ID')


class MistralAssistant:
    """Talk to a Mistral agent via beta conversations (start/append). Returns assistant text."""

    def __init__(self, api_key=None, agent_id=None):
        self.api_key = api_key or _get_api_key()
        self.agent_id = agent_id or _get_agent_id()
        self._client = None

    def _client_or_raise(self):
        if Mistral is None:
            raise RuntimeError("mistralai package not installed. pip install mistralai")
        if not self.api_key:
            raise ValueError("MISTRAL_API_KEY not set (env or settings)")
        if not self.agent_id:
            raise ValueError("MISTRAL_AGENT_ID not set (env or settings)")
        if self._client is None:
            self._client = Mistral(api_key=self.api_key)
        return self._client

    def send_message(self, user_message, conversation_id=None):
        """
        Send user message and return (response_text, conversation_id_for_next).
        If conversation_id is None, starts a new conversation; otherwise appends.
        """
        client = self._client_or_raise()
        inputs = [{"role": "user", "content": user_message}]

        if conversation_id is None:
            resp = client.beta.conversations.start(
                agent_id=self.agent_id,
                inputs=inputs,
            )
        else:
            resp = client.beta.conversations.append(
                conversation_id=conversation_id,
                inputs=inputs,
            )

        new_cid = getattr(resp, 'conversation_id', None) or (resp.get('conversation_id') if isinstance(resp, dict) else None)
        outputs = getattr(resp, 'outputs', None) or (resp.get('outputs') if isinstance(resp, dict) else None) or []
        text = ""
        if outputs:
            first = outputs[0]
            if isinstance(first, dict):
                text = first.get('content', '')
            else:
                text = getattr(first, 'content', str(first) if first is not None else '')
        return (text or "", new_cid)

from __future__ import annotations

from .client import LLMClient
from .models import InferenceConfig, InferenceResponse, Message


class Conversation:
    """Single-process, single-conversation reference implementation.

    Superseded by ChatService + a ConversationStore (session-addressed,
    survives across processes) but kept as the simplest correct version of
    the append-user / infer / append-assistant loop.
    """

    def __init__(self, client: LLMClient, config: InferenceConfig | None = None):
        self._client = client
        self._config = config or InferenceConfig()
        self.history: list[Message] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def send(self, user_text: str) -> InferenceResponse:
        """One turn: append user msg -> infer over full history -> append reply."""
        self.history.append(Message(role="user", content=user_text))

        try:
            response = self._client.infer(self.history, self._config)
        except Exception:
            # Undo the user turn on failure so history never holds a
            # dangling, reply-less message.
            self.history.pop()
            raise

        self.history.append(Message(role="assistant", content=response.text))
        self.total_input_tokens += response.input_tokens
        self.total_output_tokens += response.output_tokens

        return response

    @property
    def turn_count(self) -> int:
        return len(self.history) // 2

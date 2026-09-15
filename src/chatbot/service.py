from __future__ import annotations

from .client import LLMClient
from .models import InferenceConfig, Message, TurnResult
from .storage import ConversationStore
from .truncation import TruncationConfig, truncate_history


class ChatService:
    """Session-addressed multi-turn chat. Holds no conversation state
    itself — only a client and a store — so any process or replica can
    handle any session by loading its history from the store."""

    def __init__(
        self,
        client: LLMClient,
        store: ConversationStore,
        config: InferenceConfig | None = None,
        truncation_config: TruncationConfig | None = None,
    ):
        self._client = client
        self._store = store
        self._config = config or InferenceConfig()
        self._truncation_config = truncation_config or TruncationConfig()

    def create_session(self) -> str:
        """Start a new conversation; return its handle."""
        return self._store.create_session()

    def send(self, session_id: str, user_text: str) -> TurnResult:
        """One turn of one conversation: load -> infer -> append."""
        history = self._store.load(session_id)
        turn_number = len(history) // 2 + 1

        # Keeps recent turns verbatim and folds older ones into a rolling
        # summary; a no-op until the conversation exceeds the window.
        recent_history, summarized = truncate_history(
            session_id, history, self._client, self._store, self._truncation_config
        )

        user_msg = Message(role="user", content=user_text)
        # Counted with the same model and no system prompt, so the number
        # is this message's own tokens under the right tokenizer — not
        # inflated by the shared system prompt, and not silently using the
        # wrong model's tokenizer.
        count_config = InferenceConfig(model=self._config.model)
        user_msg.token_count = self._client.count_tokens([user_msg], count_config)

        # Nothing is persisted until this succeeds.
        response = self._client.infer(recent_history + [user_msg], self._config)

        assistant_msg = Message(
            role="assistant", content=response.text, token_count=response.output_tokens
        )
        self._store.append(session_id, user_msg, assistant_msg)

        return TurnResult(
            text=response.text,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            stop_reason=response.stop_reason,
            turn_number=turn_number,
            summarized=summarized,
        )

    def get_history(self, session_id: str) -> list[Message]:
        """Expose history read-only — for UIs that re-render the transcript."""
        return self._store.load(session_id)

    def session_exists(self, session_id: str) -> bool:
        return self._store.session_exists(session_id)

from __future__ import annotations

from .client import LLMClient
from .models import InferenceConfig, InferenceResponse, Message
from .storage import ConversationStore
from .truncation import TruncationConfig, truncate_history


# ---------------------------------------------------------------------------
# LEARNING NOTE — what changed from Conversation (conversation.py):
#
#   Conversation:  ONE conversation, state INSIDE the object (self.history),
#                  caller holds the object itself.
#   ChatService:   MANY conversations, state in a STORE, caller holds only
#                  a session_id string.
#
# That swap — "hold the object" -> "hold an ID" — is the core production
# move. An ID is serializable: it can live in a cookie, a URL, a JSON
# body, another service. An object can't. Everything below follows from
# this one decision.
# ---------------------------------------------------------------------------


class ChatService:
    """The service layer: session-addressed multi-turn chat.

    [LEARNING] Note what this class does NOT have: a `self.history`.
    The service holds no conversation state at all — it holds *capabilities*
    (a client to call, a store to read/write). Every request follows

        load -> compute -> append

    and between requests the service remembers nothing. This is called a
    STATELESS SERVICE (state lives in the store, not the service), and
    it's what makes the later HTTP jump trivial: any process, any worker,
    any replica can serve turn 5 of a conversation it has never seen —
    it just loads the history by ID. Horizontal scaling falls out for free.
    """

    def __init__(
        self,
        client: LLMClient,
        store: ConversationStore,
        config: InferenceConfig | None = None,
        truncation_config: TruncationConfig | None = None,
    ):
        # [LEARNING] All three collaborators are INJECTED, not constructed
        # here. The service doesn't know or care which store it got —
        # InMemoryStore in tests, SQLiteStore in the demo, Postgres later.
        # "Depend on the interface, receive the implementation" is what
        # makes each layer testable in isolation.
        self._client = client
        self._store = store
        self._config = config or InferenceConfig()
        self._truncation_config = truncation_config or TruncationConfig()

    def create_session(self) -> str:
        """Start a new conversation; return its handle."""
        return self._store.create_session()

    def send(self, session_id: str, user_text: str) -> InferenceResponse:
        """One turn of one conversation: load -> infer -> append."""

        # 1. LOAD — rebuild the conversation from storage. Fresh every
        #    call: no cache of "the last history I saw". (A cache would
        #    be a second copy of the truth that can go stale — the store
        #    is the single source of truth.)
        history = self._store.load(session_id)

        # 1.5 TRUNCATE — the seam noted in the module docstring below.
        #     Keeps the last N turns verbatim; folds anything older into a
        #     one-paragraph summary prepended into the first kept message
        #     (see truncation.py for why it's NOT put in the system prompt).
        #     When the conversation is still shorter than the window, this
        #     is just `history` unchanged.
        recent_history = truncate_history(history, self._client, self._truncation_config)

        user_msg = Message(role="user", content=user_text)

        # 2. COMPUTE — same infer() as always. Note: `recent_history +
        #    [user_msg]` builds the prompt WITHOUT mutating anything.
        #    Nothing has been persisted yet.
        response = self._client.infer(recent_history + [user_msg], self._config)

        # 3. APPEND — persist the completed pair, only now that infer()
        #    succeeded.
        #    [LEARNING] Compare with Conversation.send(), which appended
        #    the user turn FIRST and needed a try/except + pop() to undo
        #    it on failure. Here the ordering makes rollback unnecessary:
        #    if infer() raises, we simply never reach this line, and the
        #    store still holds a clean, consistent history. Reordering
        #    operations so failure needs no cleanup beats writing cleanup
        #    code — a pattern worth carrying everywhere.
        self._store.append(session_id, user_msg, Message(role="assistant", content=response.text))

        return response

    def get_history(self, session_id: str) -> list[Message]:
        """Expose history read-only — for UIs that re-render the transcript."""
        return self._store.load(session_id)

    def session_exists(self, session_id: str) -> bool:
        return self._store.session_exists(session_id)


# ---------------------------------------------------------------------------
# WHERE THE REMAINING PRODUCTION STEPS PLUG IN — all inside send():
#
#   truncation:   DONE — see step 1.5 above and truncation.py. Note it only
#                 affects what's SENT to the model; `self._store.append()`
#                 below still persists the full, untruncated pair. The store
#                 is the permanent record; truncation is a read-time view.
#   caching:      inside COMPUTE — cache_control on the prompt the client
#                 builds. The service doesn't change.
#   HTTP server:  a thin handler that parses {session_id, text} from a
#                 request body and calls service.send(). The service is
#                 already stateless, so it's server-ready as-is.
#   concurrency:  two simultaneous send() calls for the SAME session can
#                 interleave their load/append (both load N messages, both
#                 append — one pair may be computed against a stale view).
#                 Fix belongs at the store or a per-session lock. Deferred
#                 until the HTTP server makes it real.
# ---------------------------------------------------------------------------

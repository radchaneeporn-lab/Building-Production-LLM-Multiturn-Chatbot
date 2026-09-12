from __future__ import annotations

from .client import LLMClient
from .models import InferenceConfig, InferenceResponse, Message


# ---------------------------------------------------------------------------
# LEARNING NOTE — the single most important fact about multi-turn:
# This is the step of "Started sending the whole conversation back every turn"
# 
#   THE API IS STATELESS. There is no "session" on Anthropic's side.
#   Every call to /v1/messages is a brand-new request; the model only
#   "remembers" the conversation because WE resend the entire history
#   every single turn. "Multi-turn" is a client-side illusion built
#   from repeated single-turn inference.
#
# So the diff from single-turn is tiny, and it is ALL bookkeeping:
#
#   single-turn:   messages = [one user msg]  -> infer -> print, done
#   multi-turn:    history  = []                              [NEW state]
#                  loop:
#                    history.append(user turn)                [NEW step 1]
#                    infer(history)          <- SAME call as single-turn
#                    history.append(assistant turn)           [NEW step 2]
#
# Nothing changes in client.py or models.py. That is the payoff of the
# stateless-client design: transport (client) and state (here) are
# separate concerns, so adding state touches only this new file.
# ---------------------------------------------------------------------------


class Conversation:
    """Owns the message history for one conversation.

    [NEW vs single-turn] This whole class. In single-turn inference the
    messages list was a throwaway local variable; now it must survive
    across calls, so it becomes instance state with a defined owner.

    In production this "owner of state" role is exactly what gets swapped
    out later: today it's a Python list in memory; in a real service it
    becomes rows in a DB / Redis keyed by conversation_id, because the
    process handling turn 5 may not be the process that handled turn 1.
    The interface (send in, response out) stays the same — only the
    storage behind `history` changes. Designing that seam now is the
    research -> production bridge.
    """

    def __init__(self, client: LLMClient, config: InferenceConfig | None = None):
        self._client = client
        self._config = config or InferenceConfig()

        # [NEW] The conversation state. This list IS the conversation.
        self.history: list[Message] = []

        # [NEW, production habit] Track cumulative usage. Because the full
        # history is resent every turn, input tokens grow with every turn
        # (turn N pays for turns 1..N-1 again). Watching this number is
        # how you *feel* why production systems need prompt caching and
        # context-window management.
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def send(self, user_text: str) -> InferenceResponse:
        """One turn: append user msg -> infer over full history -> append reply."""

        # [NEW step 1] The user turn is appended to persistent history,
        # not built into a fresh throwaway list.
        self.history.append(Message(role="user", content=user_text))

        try:
            # [SAME] Identical call to single-turn inference. The only
            # difference is what we pass: the WHOLE history, not one message.
            response = self._client.infer(self.history, self._config)
        except Exception:
            # [NEW, production habit] If the call fails, remove the user
            # turn we just appended. Invariant: history only ever contains
            # completed user/assistant PAIRS (plus the in-flight user turn
            # during a call). Without this, a failed call leaves a dangling
            # user message, and a retry would append a second one.
            self.history.pop()
            raise

        # [NEW step 2] Append the assistant's reply. THIS is the line that
        # creates "memory": next turn, the model will re-read its own
        # previous answer as part of the prompt. Forget this line and the
        # model amnesia-loops — every turn looks like the first.
        self.history.append(Message(role="assistant", content=response.text))

        self.total_input_tokens += response.input_tokens
        self.total_output_tokens += response.output_tokens

        return response

    @property
    def turn_count(self) -> int:
        # history holds user+assistant pairs, so turns = pairs
        return len(self.history) // 2


# ---------------------------------------------------------------------------
# WHAT'S DELIBERATELY *NOT* HERE YET — the production checklist this file
# grows into. Each is absent on purpose so the core loop stays visible:
#
# 1. Context-window management. History grows forever; eventually it
#    exceeds the model's context window (or just gets expensive). Real
#    systems truncate old turns, summarize them (compaction), or use the
#    API's server-side compaction. Symptom you'd hit without it: a 400
#    error or runaway input-token cost.
#
# 2. Prompt caching. Since turns 1..N-1 are resent verbatim on turn N,
#    they are a perfect cache prefix — cache_control on the last message
#    makes repeated history ~10x cheaper. Research code ignores this;
#    production code lives or dies by it.
#
# 3. Persistence. `history` dies with the process. Production: serialize
#    Messages (they're dataclasses — trivial to JSON) into a store keyed
#    by conversation_id, load them back at the start of each request.
#
# 4. Streaming in the loop. send() uses the blocking infer(); a chat UI
#    would use infer_streaming() and append the accumulated text after
#    the stream ends — the history logic is unchanged, which proves the
#    state/transport separation is right.
#
# 5. Concurrency. Two requests for the same conversation at once would
#    interleave appends. Production adds a lock or per-conversation queue.
# ---------------------------------------------------------------------------

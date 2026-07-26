from __future__ import annotations

from dataclasses import dataclass

from .client import LLMClient
from .models import InferenceConfig, Message
from .storage import ConversationStore


# ---------------------------------------------------------------------------
# LEARNING NOTE — the strategy this file implements:
#
# Full history keeps growing forever; at some point it stops fitting the
# context window (and even before that, it gets expensive). Two common
# fixes, combined here:
#
#   WINDOW:     keep the last N turns verbatim — the model needs recent
#               exchanges word-for-word (a user might refer back to exact
#               phrasing from 2 turns ago).
#   SUMMARIZE:  compress everything OLDER than the window into a short
#               paragraph — old turns matter for continuity (names, facts,
#               decisions) but not verbatim.
#
# "Turn" here = one (user, assistant) pair. The store only ever appends
# complete pairs (see ChatService.send), so `history` loaded from it is
# always an even-length list — len(history) // 2 is a safe turn count.
#
# [LEARNING] Why ROLLING, not recompute-from-scratch:
# The window slides forward one turn at a time, so on every call past the
# threshold, exactly ONE turn newly falls out of the window. Naively,
# you'd re-summarize the entire old segment every call — turn 20
# re-reads turns 1-16, turn 21 re-reads turns 1-17, and so on: O(n) work
# repeated every turn. Instead, the store remembers (summary_text,
# summarized_through_turn) from last time, and each call folds in ONLY
# the one turn that just aged out: new_summary = fold(old_summary,
# newly_aged_out_turn). O(1) LLM work per turn instead of O(n).
# ---------------------------------------------------------------------------


@dataclass
class TruncationConfig:
    keep_last_n_turns: int = 4


_SUMMARY_SYSTEM_PROMPT = (
    "You maintain a running summary of an ongoing conversation. You may "
    "be given an existing summary plus new messages that happened since "
    "it was written — merge them into ONE updated summary. Preserve "
    "names, facts, and decisions the assistant will need to stay "
    "consistent in later turns. Be concise: a short paragraph, not a "
    "transcript."
)


def truncate_history(
    session_id: str,
    history: list[Message],
    client: LLMClient,
    store: ConversationStore,
    config: TruncationConfig | None = None,
) -> list[Message]:
    """Return the history that should actually be sent to the model.

    Below the window: `history` unchanged. Above it: the last N turns,
    with a rolling summary of everything older PREPENDED INTO THE FIRST
    message's content — not placed in the system prompt (see below), and
    not added as a new Message (see below).

    [LEARNING] Why not the system prompt:
    `system` is the one part of a request that's supposed to stay
    perfectly stable across an entire conversation — that's what makes it
    cheap to cover with a single prompt-cache breakpoint for the whole
    session. The summary changes every time the window advances, so
    putting it in `system` would make the ONE block that should never
    change churn instead — the opposite of what caching wants. Keeping
    it inside `messages` costs nothing extra on that front: this array
    was already guaranteed to change turn-to-turn (it's a sliding window,
    not an append-only log), so it was never a stable cache prefix to
    begin with.

    [LEARNING] Why prepended INTO an existing message instead of a new one:
    Anthropic's API requires messages to strictly alternate user/assistant,
    starting with user. `recent_turns` already starts with a user message,
    so splicing in a separate synthetic message would either duplicate the
    user role back-to-back or (if given the assistant role) violate the
    "must start with user" rule. Prefixing the summary text into the
    existing first message's content changes zero roles — alternation
    stays exactly as valid as it already was.
    """
    config = config or TruncationConfig()
    total_turns = len(history) // 2

    if total_turns <= config.keep_last_n_turns:
        return history

    # How many turns should be *represented in the summary* as of this call.
    turns_to_summarize = total_turns - config.keep_last_n_turns
    existing_summary, summarized_through = store.get_summary(session_id)

    if turns_to_summarize > summarized_through:
        # [LEARNING] Only the DELTA — the turn(s) that aged out since the
        # last call — gets read here, not the whole old segment. On the
        # common path (window advances by exactly one turn per call) this
        # slice is a single turn: 2 messages, not 2*n.
        newly_aged_out = history[summarized_through * 2 : turns_to_summarize * 2]
        transcript = "\n".join(f"{m.role}: {m.content}" for m in newly_aged_out)

        if existing_summary:
            prompt_content = (
                f"Existing summary:\n{existing_summary}\n\n"
                f"New messages to fold in:\n{transcript}"
            )
        else:
            prompt_content = f"Conversation to summarize:\n\n{transcript}"

        # [LEARNING] Sent as ONE user message, not replayed as multi-turn
        # messages. Replaying would end on an assistant message (turn-pairs
        # end that way), and the API would try to CONTINUE that assistant
        # turn instead of producing a fresh summary. A single user message
        # always ends on user, so the model replies with exactly the
        # updated summary we want.
        summary_response = client.infer_create(
            [Message(role="user", content=prompt_content)],
            InferenceConfig(system=_SUMMARY_SYSTEM_PROMPT, max_tokens=512),
        )
        summary_text = summary_response.text
        store.set_summary(session_id, summary_text, turns_to_summarize)
    else:
        # Window hasn't advanced since last call (shouldn't normally
        # happen within one send(), but keeps the function correct if
        # called more than once against the same state).
        summary_text = existing_summary

    recent_turns = history[turns_to_summarize * 2 :]
    first_recent = recent_turns[0]
    prefixed_first = Message(
        role=first_recent.role,
        content=(
            f"Summary of earlier conversation:\n{summary_text}"
            f"\n\n---\n\n{first_recent.content}"
        ),
    )
    return [prefixed_first, *recent_turns[1:]]


# ---------------------------------------------------------------------------
# WHAT'S DELIBERATELY *NOT* HERE YET:
#
# 1. A token-budget trigger instead of a fixed turn count — real systems
#    truncate based on estimated tokens remaining, not "4 turns" flatly.
# 2. Concurrency safety for get_summary/set_summary — two simultaneous
#    send() calls on the same session could race (both read the same
#    summarized_through, both write). Same caveat as append() in
#    storage.py: fine for one process, needs a lock or DB transaction
#    once the HTTP server makes concurrent calls real.
# 3. Request-level audit logging. The exact prefixed prompt sent to the
#    model (summary + recent turns) is still never persisted anywhere —
#    only the clean original messages and the rolling summary are. If
#    you need to reconstruct "what exact bytes did we send on turn 12,"
#    that's a separate, append-only log this deliberately doesn't add.
# ---------------------------------------------------------------------------

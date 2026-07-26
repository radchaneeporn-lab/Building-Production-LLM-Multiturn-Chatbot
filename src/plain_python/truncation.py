from __future__ import annotations

from dataclasses import dataclass

from .client import LLMClient
from .models import InferenceConfig, Message


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
# ---------------------------------------------------------------------------


@dataclass
class TruncationConfig:
    keep_last_n_turns: int = 4


_SUMMARY_SYSTEM_PROMPT = (
    "Summarize the conversation transcript given below. Preserve names, "
    "facts, and decisions the assistant will need to stay consistent in "
    "later turns. Be concise: a short paragraph, not a transcript."
)


def truncate_history(
    history: list[Message],
    client: LLMClient,
    config: TruncationConfig | None = None,
) -> list[Message]:
    """Return the history that should actually be sent to the model.

    Below the window: `history` unchanged. Above it: the last N turns,
    with the summary of everything older PREPENDED INTO THE FIRST message's
    content — not placed in the system prompt, and not added as a new
    Message.

    [LEARNING] Why not the system prompt:
    `system` is the one part of a request that's supposed to stay
    perfectly stable across an entire conversation — that's what makes it
    cheap to cover with a single prompt-cache breakpoint for the whole
    session. The summary changes on every call past the window (the split
    boundary advances by one turn each time), so putting it in `system`
    would make the ONE block that should never change churn every turn —
    the opposite of what caching wants. Keeping the summary inside
    `messages` costs nothing extra on that front: this array was already
    guaranteed to change turn-to-turn (it's a sliding window, not an
    append-only log), so it was never a stable cache prefix to begin with.

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

    split_at = (total_turns - config.keep_last_n_turns) * 2
    old_turns, recent_turns = history[:split_at], history[split_at:]

    # [LEARNING] old_turns is flattened into ONE user message rather than
    # replayed as multi-turn messages. Replaying them would end on an
    # assistant message (old_turns is turn-pairs), and the API would then
    # try to CONTINUE that assistant turn instead of producing a fresh
    # summary. A single user message asking "summarize this text" always
    # ends on user, so the model responds with exactly the summary we want.
    transcript = "\n".join(f"{m.role}: {m.content}" for m in old_turns)
    summary_request = Message(
        role="user",
        content=f"Conversation to summarize:\n\n{transcript}",
    )
    summary_response = client.infer_create(
        [summary_request],
        InferenceConfig(system=_SUMMARY_SYSTEM_PROMPT, max_tokens=512),
    )

    first_recent = recent_turns[0]
    prefixed_first = Message(
        role=first_recent.role,
        content=(
            f"Summary of earlier conversation:\n{summary_response.text}"
            f"\n\n---\n\n{first_recent.content}"
        ),
    )
    return [prefixed_first, *recent_turns[1:]]


# ---------------------------------------------------------------------------
# WHAT'S DELIBERATELY *NOT* HERE YET:
#
# 1. Caching the summary. Every call beyond the window re-summarizes the
#    ENTIRE old segment from scratch — turn 20 re-summarizes turns 1-16,
#    turn 21 re-summarizes turns 1-17, and so on. That's an extra LLM call
#    per turn, of growing size. The production fix: persist "summary text"
#    + "summarized through turn X" in the store, and only ask the model to
#    fold in the ONE newly-aged-out turn each time, instead of redoing the
#    whole prefix.
# 2. A token-budget trigger instead of a fixed turn count — real systems
#    truncate based on estimated tokens remaining, not "4 turns" flatly.
# ---------------------------------------------------------------------------

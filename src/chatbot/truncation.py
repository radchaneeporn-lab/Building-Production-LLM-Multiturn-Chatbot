from __future__ import annotations

from dataclasses import dataclass

from .client import LLMClient
from .models import InferenceConfig, Message
from .storage import ConversationStore


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
) -> tuple[list[Message], bool]:
    """Keep the last N turns verbatim; fold anything older into a rolling
    summary prepended into the first kept message's content.

    Below the window: history is returned unchanged, summarized=False.

    The summary is rolling, not recomputed — each call only folds in the
    turn that just aged out of the window, so cost per call stays constant
    instead of growing with conversation length.

    It goes in `messages`, not `system`: system is meant to stay
    byte-identical for prompt caching, and the summary changes every time
    the window advances.

    It's prepended into the first kept message rather than added as a new
    one because the API requires strict user/assistant alternation
    starting with user — a synthetic message would break that; editing an
    existing message's content doesn't.
    """
    config = config or TruncationConfig()
    total_turns = len(history) // 2

    if total_turns <= config.keep_last_n_turns:
        return history, False

    turns_to_summarize = total_turns - config.keep_last_n_turns
    existing_summary, summarized_through = store.get_summary(session_id)

    if turns_to_summarize > summarized_through:
        newly_aged_out = history[summarized_through * 2 : turns_to_summarize * 2]
        transcript = "\n".join(f"{m.role}: {m.content}" for m in newly_aged_out)

        if existing_summary:
            prompt_content = (
                f"Existing summary:\n{existing_summary}\n\n"
                f"New messages to fold in:\n{transcript}"
            )
        else:
            prompt_content = f"Conversation to summarize:\n\n{transcript}"

        # Sent as a single user message (not replayed turn by turn) so it
        # ends on "user" and the model replies with a fresh summary
        # instead of continuing an assistant turn.
        summary_response = client.infer_create(
            [Message(role="user", content=prompt_content)],
            InferenceConfig(system=_SUMMARY_SYSTEM_PROMPT, max_tokens=512),
        )
        summary_text = summary_response.text
        store.set_summary(session_id, summary_text, turns_to_summarize)
    else:
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
    return [prefixed_first, *recent_turns[1:]], True

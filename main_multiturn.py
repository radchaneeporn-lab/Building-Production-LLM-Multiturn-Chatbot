"""Entry point: multi-turn chat REPL. Run from the project root:

    python main_multiturn.py

Type a message, get a reply, repeat. `exit` / `quit` (or Ctrl+C) to leave.

LEARNING NOTE — diff this file against main_plain.py (single-turn):
  main_plain.py:    build one Message -> client.infer([msg]) -> print, done
  this file:        the SAME call inside a while-loop, with the messages
                    list moved into Conversation so it survives iterations

Three changes, nothing else:
  1. the hardcoded user_message becomes input() inside a loop     [the loop]
  2. `messages = [Message(...)]` moves into Conversation.history  [the state]
  3. append-user / append-assistant happen inside convo.send()    [the bookkeeping]

Note what this loop CANNOT see: the Anthropic SDK. It talks only to
Conversation (state layer), which talks only to LLMClient (transport
layer). That layering is the production shape in miniature:

    UI loop  ->  conversation/session layer  ->  provider adapter

In a real service the "UI loop" becomes an HTTP handler, and Conversation's
in-memory list becomes a DB lookup by conversation_id — but this file's
logic barely changes. That seam is the point.
"""

from dotenv import load_dotenv

from src.chatbot.client import LLMClient
from src.chatbot.conversation import Conversation
from src.chatbot.models import InferenceConfig

load_dotenv()  # reads ANTHROPIC_API_KEY from .env if present


def main() -> None:
    client = LLMClient()

    config = InferenceConfig(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system="You are a helpful assistant. Be concise.",
    )

    convo = Conversation(client, config)

    print("Multi-turn chat. Type 'exit' to quit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            # Ctrl+C / Ctrl+D exit cleanly instead of dumping a stack
            # trace — small thing, but it's the difference between a
            # script and a tool.
            print()
            break

        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        response = convo.send(user_input)

        print(f"\nAssistant: {response.text}\n")
        # Watch `in=` climb every turn even when your messages stay short —
        # that's the whole history being resent each call. This number is
        # why prompt caching and compaction exist in production systems.
        print(
            f"  [turn {convo.turn_count} | "
            f"this turn: in={response.input_tokens} out={response.output_tokens} | "
            f"conversation total: in={convo.total_input_tokens} "
            f"out={convo.total_output_tokens}]\n"
        )

    print(
        f"Bye. {convo.turn_count} turns, "
        f"{convo.total_input_tokens + convo.total_output_tokens} tokens total."
    )


if __name__ == "__main__":
    main()

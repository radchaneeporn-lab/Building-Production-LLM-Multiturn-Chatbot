"""Entry point: session-addressed chat over SQLite. Run from project root:

    python main_service.py                 # start a NEW session
    python main_service.py <session-id>    # RESUME an existing session

THE EXPERIMENT THAT PROVES PERSISTENCE (do this):
  1. python main_service.py          -> note the printed session ID
  2. tell the model your name, chat a bit, type 'exit'
  3. python main_service.py <that-id>
  4. ask "what's my name?"  -> it remembers. The process died;
     the conversation didn't. That's the entire point of this step.

LEARNING NOTE — diff against main_multiturn.py:
  main_multiturn.py:  convo = Conversation(client, config)   # holds state
  this file:          session_id = "..."                     # holds an ID
The loop body is nearly identical — but what the caller keeps changed
from an object to a string. A string can go in a cookie, a URL, a JSON
body. That's what makes the next step (HTTP server) a thin wrapper
instead of a rewrite.
"""

import sys

from dotenv import load_dotenv

from src.plain_python.client import LLMClient
from src.plain_python.models import InferenceConfig
from src.plain_python.service import ChatService
from src.plain_python.storage import SQLiteStore

load_dotenv()


def main() -> None:
    # --- composition root -------------------------------------------------
    # [LEARNING] This is the ONE place where concrete implementations are
    # chosen and wired together: SQLiteStore (not InMemoryStore), real
    # LLMClient (not a fake), this particular config. Everything deeper
    # down works against interfaces. Swap SQLiteStore() for
    # InMemoryStore() here and the whole app still runs — one-line change.
    client = LLMClient()
    store = SQLiteStore("conversations.db")
    config = InferenceConfig(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system="You are a helpful assistant. Be concise.",
    )
    service = ChatService(client, store, config)
    # ----------------------------------------------------------------------

    # Resume if an ID was given, else create — the caller's only "state"
    # is this string.
    if len(sys.argv) > 1:
        session_id = sys.argv[1]
        if not service.session_exists(session_id):
            print(f"Unknown session: {session_id}")
            sys.exit(1)
        # Re-render the transcript so the user sees what they're resuming.
        # [LEARNING] The UI rebuilds its view from the store — the store is
        # the single source of truth, the screen is just a projection of it.
        print(f"Resuming session {session_id}\n")
        for m in service.get_history(session_id):
            label = "You" if m.role == "user" else "Assistant"
            print(f"{label}: {m.content}\n")
    else:
        session_id = service.create_session()
        print(f"New session: {session_id}")
        print(f"(resume later with:  python main_service.py {session_id})\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if user_input.lower() in {"exit", "quit"}:
            break
        if not user_input:
            continue

        # [LEARNING] The call site: ID + text in, response out. This line
        # is already exactly the shape of the future HTTP endpoint
        # POST /chat {"session_id": ..., "text": ...} — the server step
        # will just be this line behind a route handler.
        response = service.send(session_id, user_input)

        print(f"\nAssistant: {response.text}\n")
        print(
            f"  [in={response.input_tokens} out={response.output_tokens} "
            f"stop={response.stop_reason}]\n"
        )

    print(f"Bye. Resume anytime:  python main_service.py {session_id}")


if __name__ == "__main__":
    main()

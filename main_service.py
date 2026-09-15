"""Command-line chat, no server needed. Run from the project root:

    python main_service.py                 # start a new session
    python main_service.py <session-id>    # resume an existing one
"""

import sys

from dotenv import load_dotenv

from src.chatbot.client import LLMClient
from src.chatbot.config import load_inference_config, load_store
from src.chatbot.service import ChatService

load_dotenv()


def main() -> None:
    # Composition root: the one place concrete implementations are chosen.
    # load_store() picks Postgres if DATABASE_URL is set, SQLite otherwise.
    client = LLMClient()
    store = load_store()
    config = load_inference_config()
    service = ChatService(client, store, config)

    if len(sys.argv) > 1:
        session_id = sys.argv[1]
        if not service.session_exists(session_id):
            print(f"Unknown session: {session_id}")
            sys.exit(1)
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

        response = service.send(session_id, user_input)

        print(f"\nAssistant: {response.text}\n")
        print(
            f"  [in={response.input_tokens} out={response.output_tokens} "
            f"stop={response.stop_reason}]\n"
        )

    store.close()
    print(f"Bye. Resume anytime:  python main_service.py {session_id}")


if __name__ == "__main__":
    main()

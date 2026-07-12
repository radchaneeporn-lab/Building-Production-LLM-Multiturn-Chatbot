"""Entry point: single-turn inference with the plain Python version."""

import os

from dotenv import load_dotenv

from src.plain_python.client import LLMClient
from src.plain_python.models import InferenceConfig

load_dotenv()  # reads ANTHROPIC_API_KEY from .env if present


def main() -> None:
    client = LLMClient()

    config = InferenceConfig(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system="You are a helpful assistant. Be concise."
    )

    user_message = "how to bring back the confidence and self esteem after several times of falling in the job interviewing processes"

    print(f"User: {user_message}\n")

    response = client.infer(user_message=user_message, config=config)

    print(f"Assistant: {response.text}")
    print(f"\n--- usage ---")
    print(f"input tokens : {response.input_tokens}")
    print(f"output tokens: {response.output_tokens}")
    print(f"total tokens : {response.total_tokens}")
    print(f"stop reason  : {response.stop_reason}")


if __name__ == "__main__":
    main()

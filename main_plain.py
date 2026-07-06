"""Entry point: single-turn inference with the plain Python version."""

import os

from dotenv import load_dotenv

from src.plain_python.client import LLMClient
from src.plain_python.models import InferenceConfig

load_dotenv()  # reads ANTHROPIC_API_KEY from .env if present


def main() -> None:
    client = LLMClient()

    config = InferenceConfig(
        model="claude-opus-4-8",
        max_tokens=1024,
        system="You are a helpful assistant. Be concise.",
        thinking={"type": "adaptive"},
    )

    user_message = "Explain why sometimes making mistakes or fail in thing benefit us"

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

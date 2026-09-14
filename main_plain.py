"""Entry point: single-turn inference with the plain Python version."""

import os

from dotenv import load_dotenv

from src.chatbot.client import LLMClient
from src.chatbot.config import load_inference_config
from src.chatbot.models import Message

load_dotenv()  # reads ANTHROPIC_API_KEY from .env if present


def main() -> None:
    client = LLMClient()

    # See src/chatbot/config.py — env-configurable via
    # MODEL_NAME/MAX_TOKENS/SYSTEM_PROMPT instead of hardcoded here.
    config = load_inference_config()

    user_message = "how to bring back the confidence and self esteem after several times of falling in the job interviewing processes"

    messages = [Message(role="user", content=user_message)]

    response = client.infer(messages=messages, config=config)
    # anthropic client has many inference type, can chosse client.infer(), client.infer_create,
    # client.infer_streaming
    print(f"Assistant: {response.text}")
    print(f"\n--- usage ---")
    print(f"input tokens : {response.input_tokens}")
    print(f"output tokens: {response.output_tokens}")
    print(f"total tokens : {response.total_tokens}")
    print(f"stop reason  : {response.stop_reason}")


if __name__ == "__main__":
    main()

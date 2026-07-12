from __future__ import annotations

import os

import anthropic

from .models import InferenceConfig, InferenceResponse, Message




class LLMClient:
    """Thin wrapper around the Anthropic SDK for single-turn inference."""

    def __init__(self):

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        self._client = anthropic.Anthropic(api_key=api_key)

    def infer(
        self,
        user_message: str,
        config: InferenceConfig | None = None,
    ) -> InferenceResponse:
        """Send a single user message and return the assistant response.

        Uses streaming internally so long outputs don't hit request timeouts.
        """
        if config is None:
            config = InferenceConfig()

        messages = [Message(role="user", content=user_message)]
        api_messages = [m.to_api_dict() for m in messages]

        # Build kwargs; only include 'system' and 'thinking' when set
        kwargs: dict = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": api_messages,
        }
        if config.system:
            kwargs["system"] = config.system
        # if config.thinking:
        #     kwargs["thinking"] = config.thinking

        # .stream() + .get_final_message() gives us streaming safety with a
        # clean blocking interface — no partial-response handling needed here.
        with self._client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()

        # Extract the first text block from the response content list.
        # Adaptive thinking may prepend a thinking block; we skip those.
        text = next(
            (block.text for block in response.content if block.type == "text"),
            "",
        )

        return InferenceResponse(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or "unknown",
        )

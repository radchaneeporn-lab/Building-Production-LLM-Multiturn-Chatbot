from __future__ import annotations

import os
from typing import Iterator

import anthropic

from .models import InferenceConfig, InferenceResponse, Message


class LLMClient:
    """The only file that imports `anthropic`. Everything else in this
    codebase talks to InferenceConfig/InferenceResponse instead.

    Three ways to call the model, in one place so the tradeoff is visible:
      infer_create()    — plain .create(), simplest, risks a timeout on long outputs
      infer()            — .stream() but returns the final message, the default
      infer_streaming()  — .stream() yielded incrementally, for token-by-token UIs
    """

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        self._client = anthropic.Anthropic(api_key=api_key)

    @staticmethod
    def _to_inference_response(response) -> InferenceResponse:
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

    def count_tokens(
        self,
        messages: list[Message],
        config: InferenceConfig | None = None,
    ) -> int:
        """Token count for exactly `messages` — no completion generated.

        Not the same as reading input_tokens off a past response: that
        number is cumulative for the whole request, not per-message.
        """
        if config is None:
            config = InferenceConfig()

        kwargs: dict = {
            "model": config.model,
            "messages": [m.to_api_dict() for m in messages],
        }
        if config.system:
            kwargs["system"] = config.system

        result = self._client.messages.count_tokens(**kwargs)
        return result.input_tokens

    def infer_create(
        self,
        messages: list[Message],
        config: InferenceConfig | None = None,
    ) -> InferenceResponse:
        """Blocking call, no streaming. Fine for short outputs; for large
        max_tokens the connection can sit silent long enough that a proxy
        kills it as stalled — that risk is why infer() exists."""
        if config is None:
            config = InferenceConfig()

        kwargs: dict = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [m.to_api_dict() for m in messages],
        }
        if config.system:
            kwargs["system"] = config.system

        response = self._client.messages.create(**kwargs)
        return self._to_inference_response(response)

    def infer(
        self,
        messages: list[Message],
        config: InferenceConfig | None = None,
    ) -> InferenceResponse:
        """The default choice for almost everything. Streams under the
        hood so the connection stays alive during a long generation, but
        blocks and returns the same InferenceResponse as infer_create() —
        callers can't tell the two apart."""
        if config is None:
            config = InferenceConfig()

        kwargs: dict = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [m.to_api_dict() for m in messages],
        }
        if config.system:
            kwargs["system"] = config.system

        with self._client.messages.stream(**kwargs) as stream:
            response = stream.get_final_message()

        return self._to_inference_response(response)

    def infer_streaming(
        self,
        messages: list[Message],
        config: InferenceConfig | None = None,
    ) -> Iterator[str]:
        """Yields text as it's generated, for UIs that render incrementally.
        Note the return type is Iterator[str], not InferenceResponse —
        usage/stop_reason arrive at the end of the stream and aren't
        surfaced here."""
        if config is None:
            config = InferenceConfig()

        kwargs: dict = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [m.to_api_dict() for m in messages],
        }
        if config.system:
            kwargs["system"] = config.system

        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

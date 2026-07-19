from __future__ import annotations

import os
from typing import Iterator

import anthropic

from .models import InferenceConfig, InferenceResponse, Message


class LLMClient:
    """Same class as your client.py, but with all three inference styles
    side by side so the differences are visible in one place.

    VARIANT MAP
    -----------
    infer_create()            .create()                blocking, no live resource, no `with`
    infer()                   .stream() + final msg    your current code: streaming safety, blocking feel
    infer_streaming()         .stream() + deltas       true incremental output; changes the return contract
    (footnote at bottom)      .create(stream=True)     raw events, no accumulation; rarely what you want

    Next: if I back at this, I will continue learning the decoding stategies that can use with each inference technique
    """

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is not set")
        self._client = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Shared helper: both blocking variants end at the same translation
    # point — provider Message in, inert InferenceResponse out.
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # VARIANT 1: plain .create() — the simplest possible inference
    # ------------------------------------------------------------------
    def infer_create(
        self,
        messages: list[Message],
        config: InferenceConfig | None = None,
    ) -> InferenceResponse:
        """Blocking call. Request goes out, method blocks, finished Message
        comes back.

        NOTE — no `with` here, and that is correct:
          .create() returns only after the HTTP cycle is COMPLETE.
          There is no live connection left in your hands, so there is
          nothing to close. Inert value -> no context manager.

        LIMITATION:
          For large max_tokens, the connection can sit silent long enough
          that intermediaries kill it as stalled ("HTTP timeout"). Fine for
          short outputs; risky at 16k+ tokens. That risk is the entire
          reason variant 2 exists.

        SUITABLE FOR:
          - short outputs: classification, extraction, routing, short Q&A
          - backend jobs where nobody watches the response arrive
          - tests/scripts where simplicity beats robustness
        NOT SUITABLE FOR:
          - long generations (essays, code files, reports) — timeout risk
          - chat UIs — user stares at a spinner until the whole reply lands
        TRADEOFF:
          simplest possible code, but worst time-to-first-token and one
          timeout loses the entire response (no partial output to salvage).
        """
        if config is None:
            config = InferenceConfig()

        kwargs: dict = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [m.to_api_dict() for m in messages],
        }
        if config.system:
            kwargs["system"] = config.system

        response = self._client.messages.create(**kwargs)   # <-- no `with`
        return self._to_inference_response(response)

    # ------------------------------------------------------------------
    # VARIANT 2: .stream() + get_final_message() — YOUR CURRENT infer()
    # ------------------------------------------------------------------
    def infer(
        self,
        messages: list[Message],
        config: InferenceConfig | None = None,
    ) -> InferenceResponse:
        """Streams under the hood, blocks on the surface.

        STREAM-CASE NOTES:
        (1) `with` is REQUIRED here. .stream() hands back a live SSE
            connection (an open socket) while events are still arriving.
            __exit__ closes it even if get_final_message() raises mid-
            stream. Live resource -> context manager.
        (2) get_final_message() drains every event while the SDK's
            bookkeeper accumulates them into a complete Message —
            byte-for-byte what .create() would have returned.
        (3) WHY this variant over variant 1: the arriving SSE events act
            as a heartbeat, so nothing times the connection out during a
            long generation. Same return value, timeout-proof transport.
        (4) The caller cannot tell variants 1 and 2 apart. Identical
            signature, identical InferenceResponse. Transport choice is
            sealed inside the boundary — that's the adapter doing its job.

        SUITABLE FOR:
          - the default choice for almost everything server-side:
            long outputs, agentic loops, big max_tokens — anywhere you
            want the finished message but can't risk a timeout
        NOT SUITABLE FOR:
          - UIs that need to render text as it's generated (the caller
            still waits for the full message — use variant 3 for that)
        TRADEOFF:
          timeout-proof transport for the price of one `with` block;
          no time-to-first-token benefit reaches the caller, since the
          method still returns only when generation is complete.
        """
        if config is None:
            config = InferenceConfig()

        kwargs: dict = {
            "model": config.model,
            "max_tokens": config.max_tokens,
            "messages": [m.to_api_dict() for m in messages],
        }
        if config.system:
            kwargs["system"] = config.system

        with self._client.messages.stream(**kwargs) as stream:   # <-- `with` mandatory
            response = stream.get_final_message()

        return self._to_inference_response(response)

    # ------------------------------------------------------------------
    # VARIANT 3: .stream() consumed incrementally — true streaming
    # ------------------------------------------------------------------
    def infer_streaming(
        self,
        messages: list[Message],
        config: InferenceConfig | None = None,
    ) -> Iterator[str]:
        """Yields text deltas as the model produces them.

        STREAM-CASE NOTES:
        (1) Look at the return type: Iterator[str], NOT InferenceResponse.
            Incremental delivery cannot hide behind a single inert value —
            the streaming nature LEAKS INTO THE CONTRACT. This is the
            architectural cost of a typing effect: the caller must now
            loop, so main_plain.py changes from
                response = client.infer(...)
            to
                for chunk in client.infer_streaming(...): print(chunk, ...)
            models.py is untouched; provider types still never escape.
        (2) The `with` wraps the ENTIRE consumption, because the connection
            stays open for as long as the caller keeps pulling chunks.
            A generator keeps the socket open across yields — if the
            caller abandons the loop early, generator cleanup triggers
            __exit__ and the connection is closed rather than leaked.
        (3) Usage/stop_reason arrive at the END of the stream (in the
            final message_delta), so a pure chunk iterator can't easily
            report tokens. Production designs either yield a final
            summary object after the text chunks, or expose a callback.
            Kept simple here on purpose.

        SUITABLE FOR:
          - chat UIs and CLIs: perceived latency drops from
            "whole response time" to "time to first token"
          - very long outputs where the user should see progress
        NOT SUITABLE FOR:
          - pipelines that need the complete text before acting on it
            (parsing JSON, chaining into the next call) — you'd just
            re-accumulate the chunks; use variant 2 instead
          - anywhere token accounting matters, unless you add the
            final-summary mechanism described in note (3)
        TRADEOFF:
          best perceived latency, but the streaming nature leaks into
          the caller's contract (loop instead of a single value) and
          usage/stop_reason handling requires extra design.
        """
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
            for text in stream.text_stream:   # only the text deltas
                yield text
            # stream fully consumed; __exit__ closes the connection here


# ----------------------------------------------------------------------
# FOOTNOTE — the fourth style, shown for completeness, not recommended:
#
#     events = self._client.messages.create(**kwargs, stream=True)
#     for event in events:
#         ...  # raw SSE events; YOU assemble the message yourself
#
# This is the low-level path: less memory, no accumulated final Message,
# no snapshot bookkeeping. You'd hand-build the text from
# content_block_delta events and read stop_reason/usage from
# message_delta. Only worth it when you need maximum control or minimum
# memory. For everything else, .stream() (variants 2/3) is the right
# abstraction level.
#
# FOOTNOTE 2 — Batch API (client.messages.batches.create), a genuinely
# different inference type rather than a transport variant:
#
#     batch = self._client.messages.batches.create(requests=[...])
#     # ...poll batch.processing_status until "ended", then fetch results
#
# Submit up to 100K requests at once; results arrive asynchronously
# (usually < 1 hour, max 24h) at 50% of standard token prices.
#   SUITABLE FOR:   offline bulk work — dataset labeling, nightly evals,
#                   bulk summarization — anything not latency-sensitive.
#   NOT SUITABLE:   chat or anything needing an answer now; results come
#                   back in arbitrary order, keyed by custom_id.
#   TRADEOFF:       half the cost, but minutes-to-hours latency plus the
#                   create → poll → fetch plumbing. Doesn't fit this
#                   class's request/response shape, so it's not a method
#                   here — it would be its own BatchClient.
# ----------------------------------------------------------------------
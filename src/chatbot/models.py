from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# The Anthropic API expects messages in this exact shape.
# Using a dataclass keeps it typed while staying close to the raw dict.
@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str
    # [LEARNING] Not sent to the API — see to_api_dict(). Populated at
    # write time (service.py) from the real API response instead of
    # re-tokenizing later, so a future token-budget truncation trigger
    # can sum these instead of re-counting the whole history each call.
    token_count: int | None = None

    def to_api_dict(self) -> dict:
        return {"role": self.role, "content": self.content}

 
@dataclass
class InferenceConfig:
    # [LEARNING] These field defaults only apply when InferenceConfig() is
    # constructed with NO arguments — e.g. a quick script, a test, or a
    # fallback deep in client.py/service.py. Every real entry point
    # (main_api.py, main_service.py, main_multiturn.py, main_plain.py)
    # builds its config explicitly via config.py's load_inference_config()
    # and does NOT go through these defaults. Editing a value here changes
    # nothing about the running app — change MODEL_NAME/MAX_TOKENS/
    # SYSTEM_PROMPT in the environment instead (see config.py).
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 50
    system: str | None = None
    # Above configuration depend on the model also
    # Adaptive thinking: model decides whether to think based on complexity.
    # Set to None to disable thinking entirely.
    # thinking: dict | None = field(default_factory=lambda: {"type": "adaptive"})
    

@dataclass
class InferenceResponse:
    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# [LEARNING] ChatService.send() used to just return the InferenceResponse
# it got from client.infer() — but "was this turn summarized?" and "which
# turn number is this?" are things ONLY the service layer knows (they
# come from truncate_history() and from len(history), not from the model
# call itself). Rather than bolt those onto InferenceResponse (which would
# make client.infer() a liar about fields it never computes), this is a
# separate dataclass that carries the model's own fields through
# unchanged (so existing callers like main_service.py, which only read
# .text/.input_tokens/.output_tokens/.stop_reason, keep working) plus the
# two service-level facts a UI wants to show per turn.
@dataclass
class TurnResult:
    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str
    turn_number: int
    summarized: bool

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

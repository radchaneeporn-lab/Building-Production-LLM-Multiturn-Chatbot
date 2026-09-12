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
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 16_000
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

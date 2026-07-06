from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# The Anthropic API expects messages in this exact shape.
# Using a dataclass keeps it typed while staying close to the raw dict.
@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str

    def to_api_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class InferenceConfig:
    model: str = "claude-opus-4-8"
    max_tokens: int = 16_000
    system: str | None = None
    # Adaptive thinking: model decides whether to think based on complexity.
    # Set to None to disable thinking entirely.
    thinking: dict | None = field(default_factory=lambda: {"type": "adaptive"})


@dataclass
class InferenceResponse:
    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

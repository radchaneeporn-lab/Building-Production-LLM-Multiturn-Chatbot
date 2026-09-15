from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str
    # Not sent to the API (see to_api_dict) — stored so token budgets can
    # be summed later without re-tokenizing the whole history.
    token_count: int | None = None

    def to_api_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class InferenceConfig:
    # These defaults only apply when no value is given. Every real entry
    # point builds its config via config.py's load_inference_config()
    # instead — change MODEL_NAME/MAX_TOKENS/SYSTEM_PROMPT in the
    # environment, not here.
    model: str = "claude-haiku-4-5-20251001"
    max_tokens: int = 50
    system: str | None = None


@dataclass
class InferenceResponse:
    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class TurnResult:
    """Same fields as InferenceResponse, plus what only the service layer
    knows: which turn this is, and whether it was summarized."""

    text: str
    input_tokens: int
    output_tokens: int
    stop_reason: str
    turn_number: int
    summarized: bool

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

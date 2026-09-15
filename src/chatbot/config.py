from __future__ import annotations

import os

from .models import InferenceConfig
from .storage import ConversationStore, PostgresStore, SQLiteStore

# Single source of truth for the values every entry point needs. Change
# MODEL_NAME / MAX_TOKENS / SYSTEM_PROMPT / DATABASE_URL in the
# environment — editing the constants below only changes the fallback
# used when that variable is unset.

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_MAX_TOKENS = 712
DEFAULT_SYSTEM_PROMPT = "You are a helpful assistant. Be concise."


def load_inference_config() -> InferenceConfig:
    """Build the InferenceConfig every entry point should use."""
    return InferenceConfig(
        model=os.environ.get("MODEL_NAME", DEFAULT_MODEL),
        max_tokens=int(os.environ.get("MAX_TOKENS", DEFAULT_MAX_TOKENS)),
        system=os.environ.get("SYSTEM_PROMPT", DEFAULT_SYSTEM_PROMPT),
    )


def load_store() -> ConversationStore:
    """Pick the store implementation from the environment.

    DATABASE_URL set   -> PostgresStore (deployed path)
    DATABASE_URL unset -> SQLiteStore at DB_PATH (local, no server needed)
    """
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return PostgresStore(database_url)
    return SQLiteStore(os.environ.get("DB_PATH", "conversations.db"))
